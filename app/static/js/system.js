'use strict';
/* 系统与执行器页的**纯逻辑**：四个面板的路径/方法/口径 + 结果归一 + 格式化。
 * ⛔ 本文件不碰 DOM、不发请求 —— 与 `panel.js` / `lab.js` / `cost.js` / `tools.js` 同一形状。
 *
 * 🔴 本页两件最容易写错的事（都写在下面各自那一段里）：
 *    ① **三条端点在【根路径】上**（`/health` `/ready` `/metrics`）—— ⛔ 不是 `/api/v1/...`
 *    ② **`/metrics` 回的是 `text/plain`**（Prometheus 格式）—— 当 JSON 解会**当场抛**
 */

/* ══════════════ 1 · 四个面板（规格 §2.9 的 1 条 + §2.13 的 3 条）══════════════
 *
 * 🔴🔴 **⚠️ 注意路径：只有第 1 条带 `/api/v1`。**
 *    后三条挂在**根路径**上（`app/main.py` 的 `@app.get("/health")` 等，
 *    ⛔ **不在** `include_router(prefix="/api/v1")` 里）。
 *    ⚠️ 本仓硬约束 #8 是「**每个 URL 字面量必须带 `/api/v1`**」（`test_web_pages.py` 扫全部 `.html`）——
 *    **它对这一页不适用**，因为本页**一个字面量都不写**（全从本函数出）。
 *    ⇒ 真尺子在 `system.test.js`，而它必须钉**"三条根路径 + 一条带前缀"**，
 *      ⛔ **不能照抄 `tools.test.js` 那条「全部以 `/api/v1` 开头」**（照抄会把对的写成错的）。
 *
 * 🔴 `source` 两态（⛔ 别合并 —— 它们对"重启后还在不在"的答案不同）：
 *      `live` 当场真跑 / 真探 ⇒ **不是读缓存**
 *      `mem`  进程内注册表的**累计** ⇒ **重启归零**（`prometheus_client` 的计数器就在进程里）
 */
const PANELS = {
  exec:    { path: '/api/v1/agent/execute_code', name: '执行一段 Python',  method: 'POST', source: 'live', group: 'exec' },
  health:  { path: '/health',                    name: '健康检查',        method: 'GET',  source: 'live', group: 'system' },
  ready:   { path: '/ready',                     name: '就绪探针',        method: 'GET',  source: 'live', group: 'system' },
  metrics: { path: '/metrics',                   name: 'Prometheus 指标',  method: 'GET',  source: 'mem',  group: 'system', raw: true },
};

const SOURCE_LABELS = {
  live: '当场真跑 / 真探 · 不是读缓存',
  mem:  '进程内累计 · 重启归零',
};

const SOURCE_BADGES = { live: '当场真跑', mem: '进程内存' };

const SOURCE_CLASSES = { live: 'src-live', mem: 'src-mem' };

/** 取一个面板的定义。⛔ 未知 key **抛错**（响亮 > 静默 —— `DEC-051` 那族）。 */
function panelOf(key) {
  const p = PANELS[key];
  if (!p) throw new Error(`unknown panel: ${key}`);
  return p;
}

function sourceOf(key) { return panelOf(key).source; }
function sourceBadge(key) { return SOURCE_BADGES[sourceOf(key)]; }
function sourceClassOf(key) { return SOURCE_CLASSES[sourceOf(key)]; }

/** 🔴 **这一格回的是不是 `text/plain`**（⇒ ⛔ 绝不许 `JSON.parse`）。
 *  ⚠️ 判据是**面板定义上的 `raw`**，⛔ 不是"运行时看 content-type"——
 *     后者在 401/503 那类错误响应上会**换个结果**，而那正是最该稳定的时候。 */
function isRaw(key) { return panelOf(key).raw === true; }

/* ══════════════ 2 · 请求形状 ══════════════
 *
 * 🔴🔴 **`POST /agent/execute_code` 的参数在 query，⛔ 不是 JSON body。**
 *    判据（从运行中的 app 现读，⛔ 不是读代码猜的）：
 *      `app.openapi()` ⇒ `code in=query required=True`
 *    ⚠️ 同 `memory/add` 那一处：照"POST 就该发 body"的直觉写 ⇒ 服务端回 **422**，
 *      而**页面看起来一切正常**（只是永远失败）。守卫 ⇒ `system.test.js`。
 */
function buildRequest(key, values) {
  const p = panelOf(key);
  const v = values || {};
  const query = {};

  if (key === 'exec') {
    // 🔴 `code` 是**必填**（服务端 `required=True`）⇒ 空的**不拼**，由按钮那边先挡。
    if (v.code) query.code = v.code;
  }

  return { path: p.path, method: p.method, query };
}

/** 🔴 必填项缺了没 —— 页面据此**不发请求**（发了必 422，会被读成"后端坏了"）。 */
function missingRequired(key, values) {
  const v = values || {};
  const blank = (x) => !String(x === undefined || x === null ? '' : x).trim();
  if (key === 'exec' && blank(v.code)) return '要执行的代码不能空';
  return null;
}

/* ══════════════ 3 · 口径与警示 ══════════════ */

/**
 * 该面板要不要挂一条"这数会消失 / 它不是缓存"的警示条。
 * ⚠️ 四格**各说各的**，⛔ 不是同一句 —— 它们踩的坑不一样。
 */
function persistenceWarning(key) {
  if (key === 'exec') {
    return '这一段代码是发出去真跑的，⛔ 不是模拟。⚠️ 它跑在无网硬化容器里'
         + '（无外网 · 独立容器 · 有墙钟上限），⛔ 别指望它能跑任何东西 —— 读写文件 / 联网 / 装库都会被拒。';
  }
  if (key === 'health') {
    return '这一格是当场探的（真去 ping 一次 DB 与 Redis）—— 结果不落库，刷新即重算。'
         + '⚠️ 它不检查 embedding API（那是有意的：避免开销与级联故障），'
         + '所以这一格全绿 ⛔ 不等于"所有依赖都好"。';
  }
  if (key === 'ready') {
    return '⚠️ 它和上面那一格【不是一回事】：健康 = "依赖在不在"，就绪 = "能不能接流量"。'
         + '🔴 刚启动的 10 秒内它必然回 503 —— 那是设计的等待，⛔ 不是坏了。';
  }
  return '这一格读的是进程内的指标注册表 ⇒ 平台重启容器就归零（⛔ 不是"你没用过"）。';
}

/** 该面板"这一格的数是【谁的】"。四格都是**系统能力**，⛔ 不是"某个人的数"。 */
function scopeNote(key) {
  if (key === 'exec') {
    return '执行结果只回给你这一次调用（`requested_by` 就是你自己）；⚠️ 它不落库 —— 刷新就没了。';
  }
  if (key === 'metrics') return '这一格是【全站口径】（所有请求累加在一起），⛔ 不分是谁发的。';
  if (key === 'ready') {
    return '这一格说的是【服务自己准备好了没】—— 它是给编排系统（K8s / 负载均衡）看的信号，'
         + '与是谁、跑过什么无关。';
  }
  return '这一格是【系统自身】的现状，⛔ 不是"你的数" —— 与是谁、跑过什么无关。';
}

/* ══════════════ 4 · 取值与格式化 ══════════════ */

/** 🔴 缺值一律画 `—`，⛔ **绝不编 0**（本仓立场：不许印没有数据源的数）。 */
function show(v) {
  if (v === undefined || v === null || v === '') return '—';
  return String(v);
}

function _finiteOrNull(v) {
  if (v === undefined || v === null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(v) {
  const n = _finiteOrNull(v);
  return n === null ? show(v) : n.toLocaleString('en-US');
}

/** 健康状态 → 中文。⛔ 认不出的**原样印**（别把它吞成"未知" —— 那会丢掉后端真说的话）。 */
function healthText(s) {
  if (s === 'healthy') return '正常';
  if (s === 'unhealthy') return '不健康';
  if (s === 'ready') return '就绪';
  if (s === undefined || s === null || s === '') return '—';
  return String(s);
}

/** 🔴 **`/metrics` 的原文预览** —— 它可能上千行，⛔ 不许整段塞进 DOM。
 *  ⚠️ 截断要**说出来**（本仓立场：`has_more` / `truncated` 两种形状分开说），
 *     并且要**报出总行数**，否则读的人不知道少了多少。 */
function rawPreview(text, maxLines) {
  const n = Number.isFinite(maxLines) && maxLines > 0 ? Math.trunc(maxLines) : 60;
  const s = text === undefined || text === null ? '' : String(text);
  if (s === '') return { lines: [], shown: 0, total: 0, truncated: false };
  const all = s.split('\n');
  const lines = all.slice(0, n);
  return { lines, shown: lines.length, total: all.length, truncated: all.length > lines.length };
}

/** `{k: v}` → `[[k, v], …]`（⛔ 不是对象的当空）。 */
function dictRows(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return [];
  return Object.keys(v).map((k) => [k, v[k]]);
}

/** 🔴 非 2xx 时后端回的**是另一个形状**（`{error, code, status_code}`）——
 *  它**没有** `checks` / `status` 那些键。⇒ 页面要先认这个形状，⛔ 别硬按 200 那支读。 */
function errorPayloadOf(p) {
  if (!p || typeof p !== 'object') return null;
  if (typeof p.error !== 'string') return null;
  return { message: p.error, code: show(p.code), statusCode: show(p.status_code) };
}

/* ══════════════ 5 · 每个面板的展示模型 ══════════════
 *
 * 🔴 每一条都**只读它自己那个端点真给的键** —— 拼错键不会报错，只会画一排 `—`。
 *    键**从端点源码抄**（`app/main.py` 的 `_compute_health` / `readiness_check` · `api_v1_agent.py`）。
 */

function kvRows(key, p) {
  const payload = p || {};

  // 🔴 先认**错误形状** —— 503 那支与 200 那支**键完全不同**（见 `errorPayloadOf`）
  const err = errorPayloadOf(payload);
  if (err) {
    return [['后端说', err.message], ['错误码', err.code], ['HTTP', err.statusCode]];
  }

  switch (key) {
    case 'exec':
      return [
        ['你发出去的代码', show(payload.code)],
        ['执行结果', show(payload.result)],
      ];
    case 'health':
      return [['总体', healthText(payload.status)]];
    case 'ready':
      return [['状态', healthText(payload.status)]];
    case 'metrics':
      return [];   // 那一格是原文，⛔ 不做 kv
    default:
      return [];
  }
}

/** 表格型面板：`{cols, rows}`；不是表格 ⇒ `null`。 */
function tableOf(key, p) {
  const payload = p || {};
  if (errorPayloadOf(payload)) return null;
  if (key === 'health') {
    // 🔴 `checks` 是**固定三项**（database / redis / embedding_api）—— 逐项列出来，
    //    ⛔ 别只画一个"总体"（那会把"哪一项挂了"藏起来）。
    const rows = dictRows(payload.checks).map(([name, v]) => [name, show(v)]);
    return { cols: ['依赖', '结果'], rows };
  }
  return null;
}

/** 截断提示（`test_truncation_declared.py` 那道门管的两种形状）。 */
function truncationNotice(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.has_more === true) return '还有下一页。';
  if (payload.truncated === true) return `结果被截断了 —— 服务端一共有 ${payload.total} 条。`;
  return null;
}

/**
 * 空态必须解释**为什么空**（`frontend/README.md` §四 第 8 条）。
 * ⚠️ 四格的"为什么空"**⛔ 不是同一句话**。
 */
function emptyReason(key) {
  switch (key) {
    case 'exec':
      return '这一格正常情况下总会有一条结果或一段报错 —— 空的话说明接口返回的形状变了，先核后端。';
    case 'health':
      return '没读到 checks —— 那一项来自后端的 `_compute_health()`，不该空 ⇒ 多半是返回形状变了。';
    case 'ready':
      return '没读到 status —— 它在 200 时固定回 `{"status":"ready"}`，不该空 ⇒ 先核后端。';
    case 'metrics':
      return '指标原文是空的 —— 那说明进程内注册表一条都没登记（⛔ 不是"服务没在跑"，'
           + '接口本身能回就说明它在跑）。';
    default:
      return '这一格现在没有数据 —— 要么还没跑过，要么来源本身就是空的（⛔ 不等于坏了）。';
  }
}

const RagSystem = {
  PANELS, SOURCE_LABELS, SOURCE_BADGES, SOURCE_CLASSES,
  panelOf, sourceOf, sourceBadge, sourceClassOf, isRaw,
  buildRequest, missingRequired,
  persistenceWarning, scopeNote,
  show, fmtNum, healthText, rawPreview, dictRows, errorPayloadOf,
  kvRows, tableOf, truncationNotice, emptyReason,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagSystem;                    // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagSystem = RagSystem;                  // 浏览器（`<script src>` 之后就是全局）
}
