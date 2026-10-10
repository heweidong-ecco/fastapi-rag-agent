'use strict';
/* 工具与记忆页的**纯逻辑**：七个面板的路径/方法/口径 + 结果归一 + 格式化。
 * ⛔ 本文件不碰 DOM、不发请求 —— 与 `panel.js` / `lab.js` / `cost.js` 同一形状。
 *
 * 🔴 为什么单独一个文件：**"这一格的数从哪来、还活不活得下去"必须只有一份**。
 *    本仓前科（`DEC-047`）：`/agent/cost/overview` 曾把**进程内存**当"一共花了多少钱"答，
 *    实测库里有 4216 tokens 它答 `0` —— **不报错、界面照常出数**。
 *    ⇒ 这一份的核心不是"画表格"，是**每格自带口径徽标**（进程内存 / 代码常量 / 真调 MCP / 落容器磁盘）。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ Node 把 .js 当 CommonJS ⇒ 不能用 import/export。
 *    所以下面是**经典脚本**（浏览器 <script src> 直接用），末尾条件导出给 Node 的 require。
 */

/* ══════════════ 1 · 七个面板（规格 §2.7 的 5 条 + §2.8 的 2 条）══════════════
 *
 * 🔴 `source` 五态（⛔ 别合并 —— 它们对「重启后还在不在」的答案**各不相同**）：
 *      `mem`   进程内存里的字典 ⇒ **重启归零**（`app/tools/tool_health.py` 的 `_tool_health`）
 *      `const` 代码里的常量表   ⇒ 与运行无关（`TOOLS_DEFINITION`）
 *      `live`  **当场真起 MCP client 去拿** ⇒ 不是缓存，慢、且可能因环境失败
 *      `disk`  Mem0 落**容器内磁盘**（`./.mem0/qdrant`）⇒ ⚠️ **平台重启容器同样会丢**
 *      `mixed` 表来自常量 + 健康那一半来自进程内存 ⇒ 重启后**表还在、健康没了**
 * 🔴 `method`：两条记忆接口是 **POST 但参数在 query**（见 §2 那段注释，⛔ 别改成发 body）。
 */
const PANELS = {
  available: { path: '/api/v1/agent/available_tools',     name: '可用工具（已剔除不健康的）', method: 'GET',  source: 'mixed', group: 'tools' },
  health:    { path: '/api/v1/agent/tool_health',         name: '工具健康状态',               method: 'GET',  source: 'mem',   group: 'tools' },
  refresh:   { path: '/api/v1/agent/tool_health/refresh', name: '手动刷新体检',               method: 'POST', source: 'mem',   group: 'tools' },
  versions:  { path: '/api/v1/agent/tool_versions',       name: '工具版本',                   method: 'GET',  source: 'const', group: 'tools' },
  mcp:       { path: '/api/v1/agent/mcp_tools_dynamic',   name: 'MCP 动态工具表',             method: 'GET',  source: 'live',  group: 'tools' },
  memadd:    { path: '/api/v1/agent/memory/add',          name: '写入长期记忆',               method: 'POST', source: 'disk',  group: 'memory' },
  memsearch: { path: '/api/v1/agent/memory/search',       name: '检索长期记忆',               method: 'GET',  source: 'disk',  group: 'memory' },
};

/** 口径徽标的**文案**（页面标题上那个角标的 title）—— ⛔ 别在 HTML 里再抄一遍。 */
const SOURCE_LABELS = {
  mem:   '进程内存 · 重启归零',
  const: '代码里的常量表 · 与运行无关',
  live:  '当场真起 MCP 去拿 · 不是缓存',
  disk:  '落容器内磁盘 · 平台重启同样会丢',
  mixed: '常量表 + 进程内存（健康那一半重启归零）',
};

/** 口径徽标的**短名**（印在角标上，一句话以内）。 */
const SOURCE_BADGES = {
  mem:   '进程内存',
  const: '代码常量',
  live:  '真调 MCP',
  disk:  '容器磁盘',
  mixed: '常量+内存',
};

/** 口径徽标的 class（`tools.html` 的 `<style>` 里定义 —— 五种色，⛔ 不许长成一个样）。 */
const SOURCE_CLASSES = {
  mem: 'src-mem', const: 'src-const', live: 'src-live', disk: 'src-disk', mixed: 'src-mixed',
};

/** 取一个面板的定义。⛔ 未知 key **抛错**（响亮 > 静默 —— `DEC-051` 那族）。 */
function panelOf(key) {
  const p = PANELS[key];
  if (!p) throw new Error(`unknown panel: ${key}`);
  return p;
}

function sourceOf(key) { return panelOf(key).source; }
function sourceBadge(key) { return SOURCE_BADGES[sourceOf(key)]; }
function sourceClassOf(key) { return SOURCE_CLASSES[sourceOf(key)]; }

/* ══════════════ 2 · 请求形状 ══════════════
 *
 * 🔴🔴 **两条记忆接口的坑（本页最容易写错的一处）**：
 *    `POST /agent/memory/add` 与 `GET /agent/memory/search` 的参数
 *    **在 query string 里，⛔ 不是 JSON body**。
 *    判据（从运行中的 app 现读，⛔ 不是读代码猜的）：
 *      `app.openapi()` ⇒ `content in=query required=True` · `memory_space in=query default='default'`
 *      `app.openapi()` ⇒ `query   in=query required=True` · `memory_space in=query default='default'`
 *    ⚠️ 照"POST 就该发 body"的直觉写 ⇒ 服务端回 **422**，而**页面看起来一切正常**（只是永远失败）。
 *    📌 守卫 ⇒ `tools.test.js` 里那条「记忆接口的参数在 query，⛔ 不在 body」。
 */

/** 记忆空间名的兜底值 —— 与服务端默认值**逐字一致**（`'default'`）。 */
const DEFAULT_MEMORY_SPACE = 'default';

/**
 * 一次面板运行 → `{ path, method, query }`。
 * ⚠️ **参数只给收它的那两条端点** —— 多塞不会报错（FastAPI 忽略多余 query），
 *    但那会让读的人以为别的端点也认这些参数。⛔ 别"统一一下"。
 */
function buildRequest(key, values) {
  const p = panelOf(key);
  const v = values || {};
  const query = {};

  if (key === 'memadd') {
    // 🔴 `content` 是**必填**（服务端 `required=True`）⇒ 空的**不拼**，由按钮那边先挡。
    if (v.content) query.content = v.content;
    query.memory_space = v.memory_space || DEFAULT_MEMORY_SPACE;
  } else if (key === 'memsearch') {
    if (v.query) query.query = v.query;
    query.memory_space = v.memory_space || DEFAULT_MEMORY_SPACE;
  }

  return { path: p.path, method: p.method, query };
}

/** 🔴 记忆那两格的必填项缺了没 —— 页面据此**不发请求**（发了必 422，而 422 会让人以为后端坏了）。
 *  ⚠️ **要 trim 再判** —— 光敲了几个空格也是"空"（`'   '` 在 JS 里是**真值**，
 *     不 trim 就会把一条全是空格的记忆写进去，而**没人会报错**）。 */
function missingRequired(key, values) {
  const v = values || {};
  const blank = (x) => !String(x === undefined || x === null ? '' : x).trim();
  if (key === 'memadd' && blank(v.content)) return '要写的内容不能空';
  if (key === 'memsearch' && blank(v.query)) return '要检索的关键词不能空';
  return null;
}

/* ══════════════ 3 · 口径与警示 ══════════════ */

/**
 * 该面板要不要挂一条"这数会消失 / 不是缓存"的警示条。
 * ⛔ `const` 返回 `null` —— 给它挂警示条就是**狼来了**（它与运行、与重启都无关）。
 */
function persistenceWarning(key) {
  const s = sourceOf(key);
  if (s === 'mem') {
    return '这一格读的是**进程内存** —— 平台重启容器就归零，⛔ 不是"工具都没了"。'
         + '它和「工具版本」那一格不一样是正常的（那格是代码里的常量表）。';
  }
  if (s === 'mixed') {
    return '这一格是**两种来源拼起来的**：工具表来自代码常量（重启还在），'
         + '而每条的**健康状态**来自进程内存（重启归零）⇒ 重启后表还在、状态全没了。';
  }
  if (s === 'live') {
    return '这一格是**当场真起一个 MCP client 去拿**的，⛔ 不是读缓存 —— '
         + '所以它比上面几格慢，也可能因环境起不来（那时是环境问题，⛔ 不是工具没了）。';
  }
  if (s === 'disk') {
    return '这一格写 / 读的是 Mem0 的**本地库**（落在容器内的磁盘上）—— '
         + '⚠️ **平台重启容器同样会丢**（单容器、没有挂卷），所以它和"进程内存"其实一样不耐重启。';
  }
  return null;
}

/** 该面板"这一格的数是【谁的】"。工具那五格是**系统能力**，⛔ 不是"某个人的数"。 */
function scopeNote(key) {
  if (panelOf(key).group === 'memory') {
    return '这二格是【你自己的】：服务端按 `user_name:memory_space` 把记忆分开，⛔ 看不到别人的。';
  }
  return '这五格是【系统能力】的现状，⛔ 不是"你的数" —— 工具表住在代码 / 进程里，与是谁无关。';
}

/* ══════════════ 4 · 取值与格式化 ══════════════ */

/** 🔴 缺值一律画 `—`，⛔ **绝不编 0**（本仓立场：不许印没有数据源的数）。 */
function show(v) {
  if (v === undefined || v === null || v === '') return '—';
  return String(v);
}

/** 🔴 **缺值必须先挡掉**：`Number(null) === 0`、`Number('') === 0`
 *  ⇒ 直接 `Number()` 会把"没这个数"印成 **`0`**（本仓明令禁止的那件事；`cost.js` 栽过 `fmtMoney`）。 */
function _finiteOrNull(v) {
  if (v === undefined || v === null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(v) {
  const n = _finiteOrNull(v);
  return n === null ? show(v) : n.toLocaleString('en-US');
}

/** 🔴 **`last_checked` 是 epoch【秒】**（Python `time.time()`）⇒ 要 **×1000** 才是 JS 的毫秒。
 *  ⚠️ 忘了 ×1000 ⇒ 页面显示 **1970-01-01**，而**不报任何错**。 */
function fmtEpoch(v) {
  const n = _finiteOrNull(v);
  if (n === null) return show(v);
  const d = new Date(n * 1000);
  if (Number.isNaN(d.getTime())) return show(v);
  const p = (x) => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
       + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

/** 健康状态 → 中文。⛔ 认不出的**原样印**（别把它吞成"未知" —— 那会丢掉后端真说的话）。 */
function healthText(s) {
  if (s === 'healthy') return '正常';
  if (s === 'unhealthy') return '不健康';
  if (s === undefined || s === null || s === '') return '—';
  return String(s);
}

/** `{k: {...}}` → `[[k, {...}], …]`（⛔ 不是对象的当空）。 */
function dictRows(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return [];
  return Object.keys(v).map((k) => [k, v[k]]);
}

function rowsOf(payload, field) {
  const v = payload && payload[field];
  return Array.isArray(v) ? v : [];
}

/** MCP 的 `inputSchema` → 参数名那串（⛔ 认不出就回 `''`，别抛）。 */
function schemaParams(schema) {
  if (!schema || typeof schema !== 'object') return '';
  const props = schema.properties;
  if (!props || typeof props !== 'object') return '';
  return Object.keys(props).join(', ');
}

/* ══════════════ 5 · 每个面板的展示模型 ══════════════
 *
 * 🔴 每一条都**只读它自己那个端点真给的键** —— 拼错键不会报错，只会画一排 `—`。
 *    所以下面的键**从端点源码 / `app.openapi()` 抄**（`app/routing/api_v1_agent.py`）。
 */

function kvRows(key, p) {
  const payload = p || {};
  switch (key) {
    case 'available':
      // ⚠️ `total` 是服务端算的 `healthy + unhealthy`。
      return [
        ['可用（含未体检过的）', fmtNum(rowsOf(payload, 'healthy_tools').length)],
        ['不健康（已被剔除）', fmtNum(rowsOf(payload, 'unhealthy_tools').length)],
        ['合计', fmtNum(payload.total)],
      ];
    case 'health':
    case 'refresh':
      return [['体检表里的工具条数', fmtNum(dictRows(payload.tools).length)]];
    case 'versions':
      return [['版本表里的工具条数', fmtNum(dictRows(payload.tool_versions).length)]];
    case 'mcp':
      return [['MCP 报上来的工具条数', fmtNum(payload.total)]];
    case 'memadd':
      return [
        ['结果', show(payload.status)],
        ['写进了哪个记忆空间', show(payload.memory_space)],
        ['写进去的内容', show(payload.content)],
      ];
    case 'memsearch': {
      const hits = rowsOf(payload, 'memories');
      return [
        ['检索词', show(payload.query)],
        ['记忆空间', show(payload.memory_space)],
        ['命中条数', fmtNum(hits.length)],
      ];
    }
    default:
      return [];
  }
}

/** 表格型面板：`{cols, rows}`；不是表格 ⇒ `null`。 */
function tableOf(key, p) {
  const payload = p || {};
  if (key === 'available') {
    const rows = rowsOf(payload, 'healthy_tools').map((t) => ([
      show(t.name), show(t.version), show(t.description),
    ]));
    return { cols: ['工具', '版本', '说明'], rows };
  }
  if (key === 'health' || key === 'refresh') {
    const rows = dictRows(payload.tools).map(([name, h]) => ([
      name, healthText(h && h.status), fmtEpoch(h && h.last_checked),
    ]));
    return { cols: ['工具', '状态', '上次体检'], rows };
  }
  if (key === 'versions') {
    const rows = dictRows(payload.tool_versions).map(([name, ver]) => ([name, show(ver)]));
    return { cols: ['工具', '版本'], rows };
  }
  if (key === 'mcp') {
    const rows = rowsOf(payload, 'tools').map((t) => ([
      show(t.name), schemaParams(t.inputSchema), show(t.description),
    ]));
    return { cols: ['工具（MCP 上的名字）', '参数', '说明'], rows };
  }
  return null;
}

/** 第二个表：只有 `available` 有（**不健康**那张 —— 它是**坏消息**，⛔ 别和好消息混一张表）。 */
function table2Of(key, p) {
  const payload = p || {};
  if (key !== 'available') return null;
  const names = rowsOf(payload, 'unhealthy_tools');
  return { cols: ['不健康的工具（已从可用清单里剔除）'], rows: names.map((n) => [show(n)]) };
}

/** 第三个表：只有 `memsearch` 有（命中的记忆原文，一条一行）。 */
function table3Of(key, p) {
  const payload = p || {};
  if (key !== 'memsearch') return null;
  const hits = rowsOf(payload, 'memories');
  return { cols: ['命中的记忆'], rows: hits.map((m) => [show(m)]) };
}

/** 截断提示（`app/tests/test_truncation_declared.py` 那道门管的两种形状）。 */
function truncationNotice(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.has_more === true) return '还有下一页。';
  if (payload.truncated === true) return `结果被截断了 —— 服务端一共有 ${payload.total} 条。`;
  return null;
}

/**
 * 空态必须解释**为什么空**（`frontend/README.md` §四 第 8 条）。
 * ⚠️ 七格的"为什么空"**⛔ 不是同一句话** —— 它们各有各的正常理由。
 */
function emptyReason(key) {
  switch (key) {
    case 'health':
      return '体检表是空的 —— 它读**进程内存**，而且**只有 `TEST_ARGS_MAP` 里登记过的工具才会进体检表**。'
           + '⛔ 不等于"工具都没了"（工具表看「工具版本」那一格，那格是代码常量，重启也在）。';
    case 'refresh':
      return '刚刷完还是空的 —— 那说明 `TEST_ARGS_MAP` 里**一个工具都没登记**（属于配置问题），'
           + '⛔ 不是"刷新按钮没生效"，也⛔ 不是"工具没了"。';
    case 'memsearch':
      return '这个记忆空间里还没有相关记忆 —— 先用上面那格写一条，再回来检索。⛔ 不是接口坏了。';
    case 'memadd':
      return '这一格正常情况下总会有一条回执 —— 空的话说明接口返回的形状变了，先核后端。';
    case 'available':
      return '可用清单是空的 —— 它来自代码里的工具表，**不该空** ⇒ 多半是接口返回的形状变了，先核后端。';
    case 'mcp':
      return 'MCP 一个工具都没报上来 —— 它是**当场起 MCP client 去拿**的，'
           + '起不来时这里就是空的（⛔ 那是环境问题，不是"工具没了"）。';
    default:
      return '这一格现在没有数据 —— 要么还没跑过，要么来源本身就是空的（⛔ 不等于坏了）。';
  }
}

const RagTools = {
  PANELS, SOURCE_LABELS, SOURCE_BADGES, SOURCE_CLASSES, DEFAULT_MEMORY_SPACE,
  panelOf, sourceOf, sourceBadge, sourceClassOf,
  buildRequest, missingRequired,
  persistenceWarning, scopeNote,
  show, fmtNum, fmtEpoch, healthText, dictRows, rowsOf, schemaParams,
  kvRows, tableOf, table2Of, table3Of,
  truncationNotice, emptyReason,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagTools;                     // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagTools = RagTools;                    // 浏览器（`<script src>` 之后就是全局）
}
