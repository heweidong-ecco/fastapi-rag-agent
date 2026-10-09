'use strict';
/* 接管页的**纯逻辑**：消息归一 / 工具摘要 / 计时文案 / 轮询节拍 / 两个载荷构造。
 * ⛔ 本文件不碰 DOM、不发请求。
 *
 * 🔴 为什么单独一个文件：硬门 D 标着「最容易假完成」，而本仓立场是
 *    「写不出命令的，就是还没核过」。这几条是**能写成命令**的那部分 ⇒ 抽出来用 node --test 钉住。
 *    渲染 / 点击 / 轮询循环留在 approvals.html 里，仍靠 DevTools 手工。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ Node 把 .js 当 CommonJS ⇒ 不能用 import/export。
 *    所以下面是**经典脚本**（浏览器 <script src> 直接用），末尾两侧都挂。
 */

const POLL_MS = 5000;
const DEFAULT_PAGE_SIZE = 50;      // 与后端 `limit: int = 50` 的默认值同口径

/** 一条消息的**可显示文本**。`content` 可能是 `str` / `list`（多模态 parts）/ 别的。 */
function messageText(msg) {
  const content = msg && msg.content;
  if (content === null || content === undefined) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (part && typeof part.text === 'string') return part.text;
      if (part && part.type) return '[' + part.type + ']';
      return '';
    }).join('');
  }
  return String(content);
}

/** 工具调用摘要 —— ⚠️ **与后端 `approval_audit.summarize_tool_calls` 同一句话**（改一处要改两处）。 */
function summarizeToolCalls(toolCalls) {
  if (!Array.isArray(toolCalls) || toolCalls.length === 0) return '(无工具调用)';
  const runs = [];
  for (const tc of toolCalls) {
    const name = (tc && tc.name) || '?';
    if (runs.length && runs[runs.length - 1][0] === name) runs[runs.length - 1][1] += 1;
    else runs.push([name, 1]);
  }
  return runs.map(([n, c]) => (c > 1 ? n + '×' + c : n)).join('、');
}

/** 卡了多久的人话。坏值 ⇒ `—`（⛔ 别显示 `NaN 分钟`）。 */
function formatElapsed(seconds) {
  if (typeof seconds !== 'number' || !isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + ' 分钟';
  return Math.floor(minutes / 60) + ' 小时 ' + (minutes % 60) + ' 分';
}

/** 轮询节拍（裁定 5）：**只在页面可见时**轮询；不可见 ⇒ `null`（调用方不排下一次）。 */
function nextPollDelay(visibilityState) {
  return visibilityState === 'visible' ? POLL_MS : null;
}

/** 上下文端点的查询串。`owner` 是**可选收窄**（裁定 6）。 */
function buildContextQuery(threadId, owner) {
  const q = new URLSearchParams();
  q.set('thread_id', threadId);
  if (owner) q.set('owner', owner);
  return q.toString();
}

/** `POST /agent/approve` 的查询串。
 *  🔴 **拒绝时 ⛔ 不许带 `edited_answer`** —— 后端本来就会忽略它
 *     （"拒绝的语义是别做了"）⇒ 带上就是在发一个**假信号**。 */
function buildApprovePayload(threadId, owner, decision, editedText) {
  const q = new URLSearchParams();
  q.set('thread_id', threadId);
  q.set('approved', String(decision === 'approve'));
  if (owner) q.set('owner', owner);
  if (decision === 'approve' && editedText) q.set('edited_answer', editedText);
  return q.toString();
}

/** 分页的**纯逻辑**（`frontend/README.md` §六）。
 *
 * 🔴 为什么要单独一条（那份规范里的两条红线）：
 *  ① **⛔ 不许前端假分页** —— 本函数**只算"下一页从哪开始"**，⛔ 不切数组、⛔ 不缓存全量。
 *     真正的分页由服务端 `limit` / `offset` 完成。
 *  ② **⛔ 不许猜「还有更多」** —— `hasMore` **只能由服务端告诉我们**。
 *     ⛔ 尤其**不许拿 `count === limit` 推**：那在"正好一整页、后面没有了"时会显示一个
 *     **点不动的下一页**（而且不报错）。⇒ 缺失一律当 `false`
 *     —— 「**没告诉你有更多**」⛔ 不等于「**有更多**」。
 *
 * ⚠️ 页码用 **`floor(offset / limit) + 1`**，⛔ 不是四舍五入（`limit=50, offset=120` ⇒ 第 3 页）。
 * ⚠️ `limit` 非法（0 / 负 / NaN）⇒ 回落 `DEFAULT_PAGE_SIZE` —— ⛔ 否则 `nextOffset` 会**原地打转**。
 */
function pagerState({ offset, limit, hasMore } = {}) {
  const lim = (typeof limit === 'number' && isFinite(limit) && limit > 0)
    ? Math.floor(limit) : DEFAULT_PAGE_SIZE;
  const off = (typeof offset === 'number' && isFinite(offset) && offset > 0)
    ? Math.floor(offset) : 0;
  const page = Math.floor(off / lim) + 1;
  return {
    page,
    limit: lim,
    offset: off,
    hasPrev: off > 0,
    hasNext: hasMore === true,              // 🔴 严格 `=== true`，见上面红线②
    prevOffset: Math.max(0, off - lim),
    nextOffset: off + lim,
    label: '第 ' + page + ' 页',
  };
}

const RagApprovals = {
  POLL_MS, messageText, summarizeToolCalls, formatElapsed, nextPollDelay,
  buildContextQuery, buildApprovePayload, pagerState, DEFAULT_PAGE_SIZE,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagApprovals;                   // Node（node --test / require）
}
if (typeof window !== 'undefined') {
  window.RagApprovals = RagApprovals;              // 浏览器（<script src> 之后就是全局）
}
