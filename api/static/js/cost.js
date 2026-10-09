'use strict';
/* 成本看板的**纯逻辑**：九个面板的路径/参数/口径标注 + 结果归一 + 格式化。
 * ⛔ 本文件不碰 DOM、不发请求 —— 与 `panel.js` / `lab.js` / `trace.js` 同一形状。
 *
 * 🔴 为什么单独一个文件：**"这一格的数是【谁的】、来自【哪里】"必须只有一份**。
 *    本仓有前科（`DEC-047`）：`/agent/cost/overview` 曾把**进程内存**当"一共花了多少钱"答，
 *    实测库里有 4216 tokens 它答 `0` —— **不报错、界面照常出数**。
 *    ⇒ 这一份的核心不是"画表格"，是**每个面板都自带口径标签**（读库 / 进程内存 / 常量表）
 *    + **谁的数**（本人 / 全站）。
 */

/* ══════════════ 1 · 九个面板（规格 §2.5 的 9 条 + §2.6 的 3 条）══════════════
 *
 * 🔴 `source` 三态（⛔ 别合并 —— 它们对"重启后还在不在"的答案相反）：
 *      `db`    读 `token_usage_logs` / `cost_records` 表 ⇒ **重启不影响**
 *      `mem`   进程内存的字典 ⇒ **重启归零**（`DEC-047` §遗留）
 *      `const` 代码里的常量表 ⇒ 与运行无关
 * 🔴 `scope`（这一格的数是谁的）：
 *      `self` 本人 · `self+global` 两个都有（要**分开标**）· `config` 配置常量
 */
const PANELS = {
  overview:   { path: '/api/v1/agent/cost/overview',       name: '花费总览',    source: 'db',    scope: 'self' },
  records:    { path: '/api/v1/agent/cost/records',        name: '花费明细',    source: 'db',    scope: 'self' },
  history:    { path: '/api/v1/agent/token/history',       name: '每日趋势',    source: 'db',    scope: 'self' },
  monthly:    { path: '/api/v1/agent/cost/monthly_report', name: '月度报告',    source: 'db',    scope: 'self' },
  budget:     { path: '/api/v1/agent/token/budget',        name: '我的额度',    source: 'db',    scope: 'self+global' },
  memusage:   { path: '/api/v1/agent/token/usage',         name: '进程内累计',  source: 'mem',   scope: 'self' },
  check:      { path: '/api/v1/agent/budget/check',        name: '预算检查',    source: 'mem',   scope: 'self' },
  estimates:  { path: '/api/v1/agent/budget/estimates',    name: '单次预估成本', source: 'const', scope: 'config' },
  intercepts: { path: '/api/v1/agent/budget/intercepts',   name: '我的拦截次数', source: 'mem',   scope: 'self' },
};

const SOURCE_LABELS = {
  db:    '读库 · 重启不影响',
  mem:   '进程内存 · 重启归零',
  const: '代码里的常量表',
};

/** 🔴 **有意不露**的三条（`DEC-124`）—— 它们**不是"懒得做"**，是**露出来会撒谎 / 会越权**。
 *  ⚠️ 每一条都必须写明理由（规格 §2.14 的口径：不露也要写成一条记录）。 */
const NOT_EXPOSED = [
  {
    path: '/api/v1/agent/token/recent',
    why: '它读的是进程内那张【所有人共用】的记录表（_usage_records），'
       + '每条记录里都带【别人的 user_name】。⇒ 公开 demo 不露（同 §2.14 那类）。'
       + '⚠️ 端点的 user_name 形参【收了却没用】（get_recent_usage(limit+1) 没传它）—— 已登记。',
  },
  {
    path: '/api/v1/agent/token/purpose',
    why: '【全站口径、不分用户】（get_purpose_summary() 吃的是全体累加的字典）。'
       + '⇒ 本人的用途拆分另有更准的出口：「花费总览」的 by_purpose（读库）。',
  },
  {
    path: '/api/v1/agent/token/thread',
    why: '【全站口径、不分用户】（_thread_summary 按 thread_id 累加，那是所有人的会话）。'
       + '⇒ 本人的线程成本另有出口：/agent/trace/{thread_id}/cost（执行轨迹页下半栏）。',
  },
];

/** 取一个面板的定义。⛔ 未知 key **抛错**（响亮 > 静默 —— `DEC-051` 那族）。 */
function panelOf(key) {
  const p = PANELS[key];
  if (!p) throw new Error(`unknown panel: ${key}`);
  return p;
}

/* ══════════════ 2 · 请求形状 ══════════════ */

/** 夹进端点声明的范围；⛔ 非法值回落默认，⛔ 不回落 0。 */
function clampInt(v, def, min, max) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < min) return def;
  return Math.min(max, Math.trunc(n));
}

/**
 * 一次面板运行 → `{ path, query }`（成本看板全是 GET，没有 body）。
 *
 * 🔴 **参数只给收它的那几条端点** —— 多塞不会报错（FastAPI 忽略多余 query），
 *    但那会让读的人以为"这条也按天筛"。⛔ 别"统一一下"。
 */
function buildRequest(key, values) {
  const p = panelOf(key);
  const v = values || {};
  const query = {};

  if (key === 'records') {
    query.days = clampInt(v.days, 7, 1, 365);
    query.limit = clampInt(v.limit, 100, 1, 1000);
  } else if (key === 'history') {
    query.days = clampInt(v.days, 30, 1, 365);
  } else if (key === 'monthly') {
    if (v.year !== undefined && v.year !== '') query.year = clampInt(v.year, 2000, 2000, 9999);
    if (v.month !== undefined && v.month !== '') query.month = clampInt(v.month, 1, 1, 12);
  } else if (key === 'check') {
    // ⚠️ 这两个是【可选】的：空串要**跳过**，⛔ 不能拼成 `?tool_name=`（那会被当成"筛空工具"）
    if (v.tool_name) query.tool_name = v.tool_name;
    if (v.purpose) query.purpose = v.purpose;
  }

  return { path: p.path, query };
}

/* ══════════════ 3 · 口径标注（🔴 本页最要紧的一半）══════════════ */

/** 该面板要不要挂"内存口径"的警示条。⛔ `db` / `const` 不挂（挂了就是狼来了）。 */
function memoryWarning(key) {
  const p = panelOf(key);
  if (p.source !== 'mem') return null;
  return '这一格读的是进程内存，重启归零。它和上面「读库」那几格的数不一样是正常的，'
       + '⛔ 不是谁坏了。';
}

/** 该面板"这一格是谁的数"—— 一栏里有两套口径时，这句话必须能分开说。 */
function scopeNote(key) {
  const p = panelOf(key);
  if (p.scope === 'self+global') {
    return '本条同时给了两套口径：used_today / daily_budget / remaining 是【你本人】的日额度；'
         + 'global_* 是【全站合计】日额度。⛔ 两者不是同一个上限的两半。';
  }
  if (p.scope === 'config') return '这一格是【配置常量】，不是运行时统计 —— 与是谁、跑了多久都无关。';
  return null;
}

/* ══════════════ 4 · 取值与格式化 ══════════════ */

/** 🔴 缺值一律画 `—`，⛔ **绝不编 0**（本仓立场：不许印没有数据源的数）。 */
function show(v) {
  if (v === undefined || v === null || v === '') return '—';
  return String(v);
}

/** 🔴 **缺值必须先挡掉**：`Number(null) === 0`、`Number('') === 0`
 *  ⇒ 直接 `Number()` 会把"没这个数"印成 **`0.0000`**（本仓明令禁止的那件事）。
 *  ⚠️ 这条是**自测抓出来的**（`cost.test.js` 首跑红：`fmtMoney(null)` 回了 `'0.0000'`）。 */
function _finiteOrNull(v) {
  if (v === undefined || v === null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(v) {
  const n = _finiteOrNull(v);
  return n === null ? show(v) : n.toLocaleString('en-US');
}

/** 金额：四位小数（与后端 `round(x, 4)` 同口径）。 */
function fmtMoney(v) {
  const n = _finiteOrNull(v);
  return n === null ? show(v) : n.toFixed(4);
}

function rowsOfTable(payload, field) {
  const v = payload && payload[field];
  return Array.isArray(v) ? v : [];
}

/* ══════════════ 5 · 每个面板的展示模型 ══════════════

 * 🔴 每一条都**只读它自己那个端点真给的键** —— 拼错键不会报错，只会画一排 `—`。
 *    所以下面 `kvRows` 的键**从端点源码抄**（`api/api_v1_agent.py` 与 `api/token_tracker.py`）。
 */

function kvRows(key, p) {
  const payload = p || {};
  switch (key) {
    case 'overview':
      return [
        ['总花费（元，全时）', fmtMoney(payload.total_cost)],
        ['总 token（全时）', fmtNum(payload.total_tokens)],
        ['调用次数', fmtNum(payload.total_calls)],
      ];
    case 'budget':
      return [
        ['我 · 今日已用 token', show(payload.used_today)],
        ['我 · 每日上限', show(payload.daily_budget)],
        ['我 · 今日剩余', show(payload.remaining)],
        ['全站 · 每日上限', show(payload.global_daily_limit)],
        ['全站 · 今日已用', show(payload.global_used_today)],
        ['全站 · 今日剩余', show(payload.global_remaining)],
      ];
    case 'memusage': {
      const s = (payload.summary && typeof payload.summary === 'object') ? payload.summary : {};
      return [
        ['进程内 token', fmtNum(s.total_tokens)],
        ['进程内花费（元）', fmtMoney(s.total_cost)],
        ['进程内调用次数', fmtNum(s.calls)],
      ];
    }
    case 'monthly': {
      const s = (payload.summary && typeof payload.summary === 'object') ? payload.summary : {};
      return [
        ['报告期', show(payload.report_period)],
        ['已过天数 / 当月天数', show(payload.elapsed_days) + ' / ' + show(payload.days_in_month)],
        ['总花费（元）', fmtMoney(s.total_cost)],
        ['总 token', fmtNum(s.total_tokens)],
        ['调用次数', fmtNum(s.total_calls)],
        ['日均花费（元）', fmtMoney(s.daily_average_cost)],
        ['日均 token', fmtNum(s.daily_average_tokens)],
        ['单次均费（元）', fmtMoney(s.cost_per_call)],
      ];
    }
    case 'check':
      return [
        ['是否放行', payload.allowed === true ? '允许' : (payload.allowed === false ? '不允许' : '—')],
        ['原因', show(payload.reason)],
        ['本次预估花费（元）', payload.estimated_cost === null || payload.estimated_cost === undefined
          ? '—（没传 tool_name，估不了）' : fmtMoney(payload.estimated_cost)],
      ];
    case 'intercepts':
      return [['累计拦截次数', fmtNum(payload.total_intercepts)]];
    default:
      return [];
  }
}

/** 表格型面板：`{cols, rows}`；不是表格 ⇒ `null`。 */
function tableOf(key, p) {
  const payload = p || {};
  if (key === 'records') {
    const rows = rowsOfTable(payload, 'records').map((r) => ([
      show(r.created_at), show(r.model), show(r.purpose),
      fmtNum(r.total_tokens), fmtMoney(r.total_cost),
      show(r.thread_id), show(r.tool_name),
    ]));
    return { cols: ['时间', '模型', '用途', 'token', '花费（元）', 'thread_id', '工具'], rows };
  }
  if (key === 'history') {
    const rows = rowsOfTable(payload, 'history').map((r) => ([
      show(r.date), fmtNum(r.tokens), fmtMoney(r.cost), fmtNum(r.calls),
    ]));
    return { cols: ['日期', 'token', '花费（元）', '调用次数'], rows };
  }
  if (key === 'overview') {
    const rows = dictRows(payload.by_purpose).map(([k, v]) => ([
      k, fmtNum(v.total_tokens), fmtMoney(v.total_cost), fmtNum(v.calls),
    ]));
    return { cols: ['用途', 'token', '花费（元）', '调用次数'], rows };
  }
  if (key === 'monthly') {
    const rows = rowsOfTable(payload, 'by_purpose').map((r) => ([
      show(r.purpose), fmtNum(r.tokens), fmtMoney(r.cost), fmtNum(r.calls), show(r.percentage) + '%',
    ]));
    return { cols: ['用途', 'token', '花费（元）', '调用次数', '占比'], rows };
  }
  if (key === 'estimates') {
    const rows = dictRows(payload.tool_estimates).map(([k, v]) => ([k, fmtMoney(v)]));
    return { cols: ['工具', '单次预估（元）'], rows };
  }
  return null;
}

/** 第二个表（只有月度报告有：按模型）。 */
function table2Of(key, p) {
  const payload = p || {};
  if (key !== 'monthly') return null;
  const rows = rowsOfTable(payload, 'by_model').map((r) => ([
    show(r.model), fmtNum(r.tokens), fmtMoney(r.cost), fmtNum(r.calls), show(r.percentage) + '%',
  ]));
  return { cols: ['模型', 'token', '花费（元）', '调用次数', '占比'], rows };
}

/** `{k: {...}}` → `[[k, {...}], …]`（⛔ 不是数组的当空）。 */
function dictRows(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return [];
  return Object.keys(v).map((k) => [k, v[k]]);
}

/** 截断提示（`api/test_truncation_declared.py` 那道门管的两种形状）。 */
function truncationNotice(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.has_more === true) return '还有下一页。';
  if (payload.truncated === true) return '结果被截断了 —— 服务端还有更多记录（调大 Days/Limit 或缩小范围再看）。';
  return null;
}

/** 空态必须解释**为什么空**（`frontend/README.md` §四 第 8 条）。 */
function emptyReason(key) {
  const p = panelOf(key);
  if (p.source === 'mem') {
    return '这一格是空的 —— 它读**进程内存**，**进程重启过就会归零**，'
         + '⛔ 不等于"你没花过钱"（真账在上面那几格读库的）。';
  }
  return '这一格是空的 —— 这个用户名下还没有记账记录，⛔ 不是接口坏了。去对话页问一句就会有。';
}

/** 估算是常量表 ⇒ 空态是另一回事（那是配置问题，不是"你没花钱"）。 */
function estimatesEmptyReason() {
  return '常量表是空的 —— 那是**配置**问题（`TOOL_ESTIMATED_COST` 没填），⛔ 与运行无关。';
}

const RagCost = {
  PANELS, SOURCE_LABELS, NOT_EXPOSED,
  panelOf, clampInt, buildRequest,
  memoryWarning, scopeNote,
  show, fmtNum, fmtMoney,
  kvRows, tableOf, table2Of, dictRows,
  truncationNotice, emptyReason, estimatesEmptyReason,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagCost;                      // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagCost = RagCost;                      // 浏览器（`<script src>` 之后就是全局）
}
