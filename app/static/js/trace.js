'use strict';
/* Trace 页（`DEC-093` · `F2`）的**纯逻辑** —— ⛔ 本文件里不许出现 `document` / `fetch`。
   ⚠️ 本仓**没有打包器**：`.js` 在 Node 眼里是 CommonJS ⇒ 文件尾【两样都要挂】
      （`module.exports` 给 `node --test`，`window.RagTrace` 给浏览器）。
      少挂一个 ⇒ 页面报 `RagTrace is not defined`，而且 **`node --test` 照样全绿**。
   跑法：node --test app/static/js/trace.test.js */

// ==================== 两条轴的名字，写死一处 ====================
// ⚠️ 它们**不是**同一种东西，⛔ 别在页面别处再拼一遍字面量
//    （见 docs/specs/tool_visualizer.md 顶部「两条轴别混」）。
const AXIS_TRACE = '追踪轴（进程内存 · 一次工具调用一条）';
const AXIS_COST = '成本轴（PG token_usage_logs · 一次模型调用一条）';

// ==================== ① 格式化 ====================

/* 金额一律 4 位小数 —— 与既有页面、与 `token_tracker` 的日志口径一致。
   ⚠️ 单位是**元**（`token_tracker.py` 的单价表写死「元/1000 tokens」），⛔ 不是美元。 */
function formatYuan(n) {
  if (n === null || n === undefined || n === '' || isNaN(Number(n))) return '--';
  return '¥' + Number(n).toFixed(4);
}

function formatMs(ms) {
  if (ms === null || ms === undefined || isNaN(Number(ms))) return '--';
  const v = Number(ms);
  return v < 1000 ? Math.round(v) + 'ms' : (v / 1000).toFixed(1) + 's';
}

function formatInt(n) {
  if (n === null || n === undefined || isNaN(Number(n))) return '--';
  return String(Number(n));
}

/* 🔴 本文件最要紧的一个函数。
   `token_usage_logs.created_at` 是 **`TIMESTAMP`（无时区）**，PG 容器是 `Etc/UTC`
   ⇒ 后端必须给它补上 `+00:00`（`token_tracker._iso_utc`）。
   若后端哪天**忘了标区**，`new Date("2026-09-20T09:16:22")` 会**当成浏览器本地时间**解析
   ⇒ 东八区用户看到的时刻**静默早 8 小时**，而且**不报任何错**。
   ⇒ 所以这里**主动拒绝**不带区的时间戳：宁可显示 `--`，也不显示一个错的时刻。
   ⚠️ 判据不是"后端会标区"（那是假设），而是"这里不肯猜"（这是代码）。 */
const _HAS_TZ = /(Z|[+-]\d{2}:?\d{2})$/;

function parseWhen(iso) {
  if (typeof iso !== 'string' || !_HAS_TZ.test(iso)) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

/* 回**浏览器本地时区**的 `YYYY-MM-DD HH:mm:ss`（人看的是墙上时钟，不是 UTC）。
   ⚠️ 用 `getFullYear()` 这一族（本地）而不是 `getUTCFullYear()` —— 后者才是"忘了转时区"的写法。 */
function formatWhen(iso) {
  const d = parseWhen(iso);
  if (!d) return '--';
  const p = (x) => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
    ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

// ==================== ② 成本轴（下半页） ====================

/* 🔴 **合计来自服务端，本函数【不】把 rows 加起来。**
   理由：明细有 `LIMIT`（`token_tracker._BREAKDOWN_LIMIT`）。
   若页面自己求和，笔数一多"总花费"就**静默变小**，而且不报任何错 ——
   这正是本仓判据表里最恨的那种量（看起来对、其实在测别的东西）。
   ⇒ 求和只在 SQL 里做一次；页面显示、并**在截断时说出来**。 */
function summarizeCost(json) {
  const items = (json && json.items) || [];
  const total = (json && json.total) || {};
  return {
    ok: !!(json && Array.isArray(json.items)),
    count: total.count || 0,
    totalTokens: total.total_tokens || 0,
    totalCost: total.total_cost || 0,
    /* 服务端会说它截断了；页面兜底也算一遍（两个条件满足其一就提示） */
    truncated: !!(json && json.truncated) || (total.count || 0) > items.length,
    rows: items.map((it) => ({
      purpose: it.purpose || '(未标用途)',
      model: it.model || '--',
      promptTokens: it.prompt_tokens || 0,
      completionTokens: it.completion_tokens || 0,
      totalTokens: it.total_tokens || 0,
      cost: it.cost || 0,
      when: formatWhen(it.created_at),
    })),
  };
}

// ==================== ③ 追踪轴（上半页） ====================

/* ⚠️ `agent_decisions` 在服务端是 `List[dict]`、**形状不保证**
   （`tool_visualizer.record_agent_decision` 直接把调用方的 dict 追加进去）。
   ⇒ 只做"能读就读"的摘要，⛔ 别假设有 `type` / `reasoning` 这些键。 */
function summarizeDecisions(decisions) {
  if (!Array.isArray(decisions)) return [];
  return decisions.map((d, i) => {
    if (d === null || typeof d !== 'object') return { index: i + 1, text: String(d) };
    const keys = Object.keys(d);
    const text = keys.length
      ? keys.slice(0, 4).map((k) => k + '=' + _short(d[k])).join(' · ')
      : '(空决策)';
    return { index: i + 1, text: text };
  });
}

function _short(v) {
  if (v === null || v === undefined) return String(v);
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
  return s.length > 60 ? s.slice(0, 60) + '…' : s;
}

function summarizeTrace(traceJson) {
  const notFound = !!(traceJson && traceJson.error);
  const t = (traceJson && traceJson.trace) || null;
  const calls = (t && t.tool_calls) || [];
  return {
    ok: !!t,
    hasTrace: !!t,
    notFound: notFound,
    error: notFound ? traceJson.error : null,
    threadId: (t && t.thread_id) || null,
    userQuery: (t && t.user_query) || '',
    durationMs: (t && t.duration_ms) ?? null,
    toolCount: calls.length,
    /* ⚠️ 服务端这两个字段【现在恒为 0】（`finish_trace` 的两个调用点都没传它们）
       ⇒ 本页**不显示**它们（概览只留耗时与工具次数），免得把假数印出来。 */
    totalTokensServer: (t && t.total_tokens) ?? null,
    totalCostServer: (t && t.total_cost) ?? null,
    steps: calls.map((c) => ({
      name: c.tool_name || '(未命名工具)',
      status: c.status || 'unknown',
      durationMs: c.duration_ms,
      errorMessage: c.error_message || '',
      resultPreview: c.result || '',
      argsPreview: _short(c.arguments),
    })),
    decisions: summarizeDecisions(t && t.agent_decisions),
    finalOutput: (t && t.final_output) || '',
  };
}

/* 上半页为空时**必须解释为什么**（⛔ 不是印一句"未找到"）。

   🔴 **2026-10-08（`N16`）改过一次文案** —— 原先这里写的是
      「**演示路径本来就不写轨迹** —— `/chat` → `/rag/stream_search` 走的是检索链」，
      而 `N16` 之后**那条链也建轨迹了** ⇒ 那句话**变成了假话**。
   ⚠️ **页面里印假话比印"未找到"更糟**：它会把排查引到**错的方向**上，
      而且看的人**没有理由怀疑它**。⇒ 文案必须跟着事实走。

   今天**仍然成立**的三条原因：
   ① **那条链不建轨迹** —— 会建的是 `/agent/mcp_chat` · `/agent/mcp_chat_stream`
      （`DEC-093`）与 `/rag/stream_search`（`N16`）；**其余花钱的链仍不建**；
   ② **重启即空** —— 追踪轴是**进程内存**，重启清空，而下半页的成本在 PG 里活着；
   ③ 这个 thread_id 真没被用过。 */
function emptyTraceReason(info) {
  const it = info || {};
  if (it.hasTrace) return null;
  if (it.error) return '没能读到轨迹：' + it.error;

  const head = '这个线程没有执行轨迹。';
  if ((it.costCount || 0) > 0) {
    return head +
      '⚠️ 但它【有 ' + it.costCount + ' 笔模型调用记录】⇒ 请求确实发生、只是没被记进追踪轴。' +
      '两种可能：① 它走的那条链不建轨迹（会建的只有 /agent/mcp_chat、' +
      '/agent/mcp_chat_stream 与 /rag/stream_search 三条）；' +
      '② API 进程重启过 —— 追踪轴在进程内存里，重启即清空（它不落库）。' +
      '⚠️ 两种情况下，下半页的成本账都是完整的 ⇒ 上半页空【不代表】这次请求没花钱。';
  }
  return head +
    '两种可能：① 这个 thread_id 从没被用过；' +
    '② API 进程重启过 —— 追踪轴存在**进程内存**里，重启即清空（它不落库）。' +
    '⚠️ 下半页的成本账在 PostgreSQL 里，不受重启影响。';
}

// ==================== ④ URL ====================

/* ⛔ `encodeURIComponent` 不能省 —— thread_id 是前端生成的，可能带 `#` / `&` / 空格。 */
function buildPath(threadId) {
  return '/api/v1/agent/trace/' + encodeURIComponent(threadId);
}

function buildCostPath(threadId) {
  return buildPath(threadId) + '/cost';
}

function readThreadId(search) {
  const q = new URLSearchParams(search || '');
  const v = (q.get('thread_id') || '').trim();
  return v || 'default';     // ⚠️ 与后端 4 个 Agent 端点的默认值一致
}

// ==================== 挂载（⛔ 两样都要） ====================

const RagTrace = {
  AXIS_TRACE, AXIS_COST,
  formatYuan, formatMs, formatInt, formatWhen, parseWhen,
  summarizeCost, summarizeTrace, summarizeDecisions, emptyTraceReason,
  buildPath, buildCostPath, readThreadId,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagTrace;                 // Node（node --test / require）
}
if (typeof window !== 'undefined') {
  window.RagTrace = RagTrace;                // 浏览器（<script src> 之后就是全局）
}
