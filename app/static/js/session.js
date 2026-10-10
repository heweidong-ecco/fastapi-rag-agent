'use strict';
/* 访客凭据的**唯一一份**取法（`DEC-143`）。⛔ 本文件不碰 DOM、⛔ 不发除了"领一把"以外的请求。
 *
 * ## 为什么要有它
 *
 * 🔴 **在此之前有【8 份】一样的实现** —— 8 个页面各写一遍
 *    （`grep -l "const KEY_STORE" app/static/web/*.html` ⇒ 8）。
 *    等刀 9 / 刀 10 做完会变 **10 份** ⇒ **越早收越便宜**。
 *
 * ## 🔴 三条约定（⛔ 改这个文件之前先读）
 *
 * ① **本地已经有凭据 ⇒ 直接用它，⛔ 不再领。**
 *    ⚠️ 这条是"**一个访客只领一把**"的**唯一**保证 —— 后端**做不到**：
 *    `app/access/auth.py` 只往库里写 sha256，**明文只在发的那一刻给一次**。
 *    ⇒ 所以"领一把"这个动作**必须由前端把住**。
 *
 * ② **领不到时【静默退回今天的行为】** —— 页面那边会回落到"自己有一个输入框"。
 *    🔴 **⛔ 不许把失败弹成错误**：
 *    - 本仓那条路（`uvicorn main:app`）上**压根没有** `/api/v1/demo/claim` ⇒ **404**，
 *      而那是**正常的**，⛔ 不是故障；
 *    - demo 那条路上它才存在。
 *    ⇒ 两种路都跑得通，**页面形态由"拿没拿到"决定，⛔ 不由"有没有报错"决定**。
 *
 * ③ **⛔ 不把凭据显示给访客。** 访客**不需要看见它** —— 显示只有风险（会被复制、会被转贴，
 *    还会让人以为"这是我要保管的东西"）。只显示"**有没有**"和"**还剩多少**"。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ Node 把 .js 当 CommonJS ⇒ 不能用 import/export。
 *    所以下面是**经典脚本**（浏览器 `<script src>` 直接用），末尾条件导出给 Node 的 require。
 *
 * 🔴🔴 **整体包在一个 IIFE 里** —— ⛔ 别把这层括号去掉。
 *    经典脚本的顶层 `function` / `const` **全是全局的**，而 8 个页面各自也有一份自己的
 *    顶层绑定（比如每页都有 `const key = …`、`function el(…)`）。
 *    2026-10-10 实测：本文件原先顶层直接写 `function key()` ⇒ 与页面那句 `const key` 撞上
 *    ⇒ **`SyntaxError: Identifier 'key' has already been declared`**
 *    ⇒ **整个内联脚本一行都不执行，页面是死的**，而 956 条 pytest + 265 条 node 用例**全绿**
 *    （那些只读文本，不解析 JS）—— **只有把页面真打开才看得见**。
 *    ⇒ 现在本文件对外**只留 `window.RagSession` 一个键**（守卫：`session.test.js` 末条）。
 */

(function () {

/** ⚠️ **与今天同一个键**（⛔ 不换名 —— 换名 = 老访客手里那把凭空丢了）。 */
const KEY_STORE = 'rag_api_key';

/** 访客标识的存储键。⚠️ 它是**这个浏览器**的标识，⛔ 不是账号。 */
const VID_STORE = 'rag_visitor_id';

/** demo 那条端点的路径 —— ⚠️ **只在 demo 的入口下存在**（本仓那条路上打过去是 404）。 */
const CLAIM_PATH = '/api/v1/demo/claim';

/** 本地那把凭据（没有就 `''`）。**同步** —— 与今天各页面那个 `key()` 同签名。 */
function key() {
  try {
    return localStorage.getItem(KEY_STORE) || '';
  } catch (e) {
    // ⚠️ 隐私模式 / 存储被禁时 `localStorage` 会抛 ⇒ **当"没有"处理**，⛔ 别让页面整体挂掉。
    return '';
  }
}

/** 存起来。⚠️ 存不进去也**不抛**（同上）。 */
function save(k) {
  try { localStorage.setItem(KEY_STORE, String(k || '')); } catch (e) { /* 见上 */ }
}

/** 清掉（页面那个"换一把"按钮用）。 */
function clear() {
  try { localStorage.removeItem(KEY_STORE); } catch (e) { /* 见上 */ }
}

/**
 * 取这个浏览器的**访客标识**；没有就生成一个存下来。
 *
 * ⚠️ **⛔ 不许用浏览器指纹**（那是隐私面）。随机串就够 —— 它的作用只是
 * 「**同一个浏览器认得出是同一个访客**」。
 * ⚠️ 形状要满足后端的校验：`[A-Za-z0-9_-]{8,64}` ⇒ 这里去掉 `randomUUID` 里的连字符。
 */
function visitorId() {
  let v = '';
  try { v = localStorage.getItem(VID_STORE) || ''; } catch (e) { v = ''; }
  if (v) return v;

  let raw = '';
  if (typeof crypto !== 'undefined' && crypto && typeof crypto.randomUUID === 'function') {
    raw = crypto.randomUUID();
  } else {
    // ⚠️ 退回一个够随机的串（`crypto.randomUUID` 要安全上下文：https 或 localhost）。
    raw = String(Date.now()) + '-' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  }
  v = String(raw).replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64);
  try { localStorage.setItem(VID_STORE, v); } catch (e) { /* 见上 */ }
  return v;
}

/**
 * ⭐ **首访时静默领一把凭据**；已经有就直接回它。
 *
 * 🔴 **它永远【不抛】、也永远不弹错误**（见文件头约定 ②）——
 *    拿不到就回 `''`，页面据此**退回今天那种"自己填"的形态**。
 *
 * @returns {Promise<string>} 凭据；**拿不到就是 `''`**
 */
async function ensureKey() {
  const have = key();
  if (have) return have;                 // 约定 ①：本地有 ⇒ ⛔ 不再领

  try {
    const r = await fetch(CLAIM_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visitor_id: visitorId() }),
    });
    // ⚠️ **404 = 本仓那条路**（这条路由根本不存在）⇒ **正常**，静默退回。
    //    其他非 2xx 也一视同仁：⛔ 不弹错。
    if (!r.ok) return '';
    const payload = await r.json();
    const k = payload && typeof payload.api_key === 'string' ? payload.api_key : '';
    if (!k) return '';
    save(k);
    return k;
  } catch (e) {
    // ⚠️ 网络错 / 不是 JSON ⇒ 同样静默退回。⛔ 别在这里 `console.error` 出一堆红字，
    //    那会让本仓那条路上**每次开页面都像出了事**。
    return '';
  }
}

const RagSession = { KEY_STORE, VID_STORE, CLAIM_PATH, key, save, clear, visitorId, ensureKey };

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagSession;              // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagSession = RagSession;           // 浏览器（`<script src>` 之后就是全局）
}

})();   // ⛔ 别去掉 —— 见文件头：去掉它，上面那些绑定全变全局，会撞页面自己的顶层同名绑定
