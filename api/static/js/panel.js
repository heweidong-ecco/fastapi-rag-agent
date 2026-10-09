'use strict';
/* 能力面板的**纯逻辑**：边界提示文案 / 参数拼串 / 四态 / 截断 / 错误文案。
 * ⛔ 本文件不碰 DOM、不发请求 —— 与 `sse.js` 同一形状（经典脚本 + 条件导出）。
 *
 * 🔴 为什么单独一个文件：**25 个能力面板要复用同一套**东西。
 *    本仓前科（`DEC-089`）：`sse.js` 之所以是**唯一**解析引用的地方，就是因为
 *    两份实现同一个东西**必然漂移**，而**没有任何门会因为你只改了一头而变红**。
 *    ⇒ 这里同理：边界文案、四态判定、截断提示，**全站就这一份**。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ Node 把 .js 当 CommonJS ⇒ 不能用 import/export。
 *    所以下面是**经典脚本**（浏览器 <script src> 直接用），末尾条件导出给 Node 的 require。
 */

/* ══════════════ 1 · 边界标注（规格 §3.6.2 · 业务方 2026-10-09 过目定稿）══════════════
 *
 * 🔴 **前 4 条 = 平台/额度边界** —— 目的是【归因】：让访客把「重启丢数据 / 限流 / 额度」
 *    **归给平台**，⛔ 不是当成我们的 bug（业务方原话：「95% 的人不知道平台限制和要求」）。
 * ⚠️ **第 5 条 `verify` 单独一类** —— 它讲的是「**我们的系统能自证到什么程度**」，
 *    与平台限制**无关**。混进上面那 4 条里会让归因**反向**
 *    （访客会读成"验证不完整也是平台的锅"）⇒ 所以它虽然也在这一份里，⛔ 别和它们并排渲染。
 */
const BOUNDARY_KEYS = ['platform_restart', 'quota', 'rate_limit', 'real_api', 'verify'];

/**
 * 取一条边界文案。
 *
 * 🔴 **两种形态，由 `data` 决定**：
 * - **给了数**（`quota` / `rate_limit`）⇒ 出现**具体数字**（规格 §3.6.3：⛔ 不许写成"有限制"这种虚的）
 * - **没给数**（未登录 / 还没取到）⇒ 给**不带数字的说明版**，并**指向哪里能看到数**
 *
 * ⚠️ **⛔ 绝不在没数据时把 `undefined` 印出去** —— 本仓立场：
 *    「**不许印"没有数据源"的数**」（规格 §五 · `api/test_trace_page.py` 那个前科）。
 *    ⇒ 所以调用的地方**必须**判断自己有没有数，而不是拼上去碰运气。
 * ⚠️ 未知 key ⇒ **抛错**（`DEC-051` 那族：响亮 > 静默）。
 */
function boundaryText(key, data) {
  const d = data || {};
  const known = (v) => v !== undefined && v !== null && v !== '';
  const hasQuota = known(d.used) && known(d.limit) && known(d.remaining);
  const hasRpm = known(d.rpm);

  switch (key) {
    case 'platform_restart':
      return '本 demo 跑在魔搭创空间的免费档上。平台重启后会清空数据 —— 这是【平台限制】，⛔ 不是系统故障。';
    case 'quota':
      // ⚠️ 数字必须【当场读数】—— 写死就过期（本仓前科：手写的路由表已经对不上了）
      if (!hasQuota) {
        return '每个访客有独立的每日 token 额度；登录后这里会显示你「今日已用 / 上限 / 剩余」。';
      }
      return `你今日已用 ${d.used} / 上限 ${d.limit} tokens，剩余 ${d.remaining}。`;
    case 'rate_limit':
      if (!hasRpm) {
        return '每个访客有独立的额度桶，按分钟限流；超了会看到 429 与一张说明卡（⛔ 不是你点坏了）。';
      }
      return `每个访客有独立的额度桶；限流约 ${d.rpm} 次/分钟。超了会看到 429 与一张说明卡（⛔ 不是你点坏了）。`;
    case 'real_api':
      return '这里真的在调大模型：每次提问都会产生真实的 token 消耗。额度用尽当天不再服务，次日恢复。';
    case 'verify':
      return '怎么验它真的做完了 ⇒ 引用可点开看原文 · 停止真的停住 · 敏感操作会停下来等你批 · 每次调用花了多少。';
    default:
      // 🔴 **响亮 > 静默**（`DEC-051` 那族）：⛔ 别 `return ''` ——
      //    那样页面上会**静默少一条边界标注**，而没有任何东西会红。
      throw new Error(`unknown boundary key: ${key}`);
  }
}

/* ══════════════ 2 · 参数 → query string ══════════════ */

/** 把表单值拼成 query string。⛔ 空串 / `undefined` / `null` **跳过**（不是拼成 `k=`）。 */
function paramQuery(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

/* ══════════════ 3 · 四态（规格 §四 · ⛔ 不许只做默认态）══════════════ */

/**
 * 判定一次响应该显示哪一态。
 *
 * 🔴 **本仓的拒绝形状是 HTTP 200 + `{"status":"error"}`**（`DEC-088`）——
 *    ⇒ ⛔ **只看 `r.ok` 会把"无权查看"当成成功**，也⛔ 别只认 `'error' in payload`。
 *    两个形状都要认（这条是 2026-10-09 实测跑红过一次才收下的）。
 */
function stateOf(payload) {
  if (!payload || typeof payload !== 'object') return 'error';
  if (payload.status === 'error' || 'error' in payload) return 'error';
  const arr = Object.values(payload).find((v) => Array.isArray(v));
  return arr && arr.length === 0 ? 'empty' : 'ok';
}

/**
 * ⭐ **空态必须解释为什么空**（`frontend/README.md` §四 第 8 条）。
 * 光写「暂无数据」**不是解释** —— 访客会以为是坏了。
 */
function emptyReason() {
  return '这里现在没有数据 —— 要么这条线程还没跑过，要么来源本身就是空的（⛔ 不等于坏了）。';
}

/* ══════════════ 4 · 截断（`api/test_truncation_declared.py` 那道门）══════════════ */

/**
 * 🔴 **两种形状【分开】，⛔ 不合并**：
 * · `has_more` = 可以翻页（还有下一页）
 * · `truncated` + `total` = 服务端**砍掉了**后面的（翻不到）
 * ⚠️ 并成一句会让"翻页"和"丢了"读起来一样 —— 那是两种不同的坏。
 */
function truncationNotice(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.has_more === true) return '还有下一页。';
  if (payload.truncated === true) return `结果被截断了 —— 服务端一共有 ${payload.total} 条。`;
  return null;
}

/* ══════════════ 5 · 错误文案 ══════════════ */

/** 三种失败**分开说**（⛔ 不合并成一句 —— `DEC-085:231-237` 已裁过这条）。 */
function errorText(status) {
  if (status === 401 || status === 403) return '没有权限或未登录 —— 这条接口要 API Key。';
  if (status === 429) return '额度用尽或被限流了。这是额度，⛔ 不是故障；全站日级额度次日恢复。';
  if (status === 503) return '服务暂时不可用（平台可能在重启容器）。稍后再试。';
  return `请求失败（HTTP ${status}）。`;
}

const RagPanel = {
  BOUNDARY_KEYS, boundaryText, paramQuery, stateOf, emptyReason, truncationNotice, errorText,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagPanel;                     // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagPanel = RagPanel;                    // 浏览器（`<script src>` 之后就是全局）
}
