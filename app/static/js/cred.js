'use strict';
/* 页头那一小块**凭据控件**的唯一实现（`DEC-143`）。
 *
 * ⛔ 本文件只做两件网外的事：**领一把**（走 `session.js`）与**读一次额度**。
 *    「该不该领」「本地有没有」这些**判定不在这里** —— 在 `session.js` 里。
 *    ⇒ 分工：`session.js` 管**凭据本身**，`cred.js` 管**页头怎么显示它**。
 *
 * ## 🔴 为什么单独一个文件（而不是让 8 个页面各写一段）
 *
 * 这一块要**一模一样地出现在 8 个页面上**（对话 / 检索实验室 / 人工接管 / 成本看板 /
 * 执行轨迹 / 工具与记忆 / 系统与执行器 / 运维探针）。
 * 本仓立场（`DEC-089` · `panel.js` 头部也引了同一条）：
 * **同一个东西两份实现必然漂移，而没有任何门会因为你只改了一头而变红。**
 * ⇒ 源码级复制 8 份 = 把刚收掉的债（8 份 `KEY_STORE`）原地重来一遍。
 *
 * ## 🔴 三条约定
 *
 * ① **⛔ 一个字节的凭据明文都不进 DOM。** 只显示「有没有」和「还剩多少」
 *    （`DEC-143 §四`）。显示明文只有风险：会被复制、会被转贴，
 *    还会让访客以为"这是我要保管的东西"。
 *
 * ② **领不到 ⇒ 老实退回「自己填」。** 本仓那条路（`uvicorn main:app`）上
 *    `/api/v1/demo/claim` **压根不存在** ⇒ 404 —— **那是正常的，⛔ 不是故障**。
 *    所以这里**不弹错、不报红**，只是把那两块切回今天的样子。
 *
 * ③ **取不到额度就不显示数字。** 本仓：「**不许印没有数据源的数**」——
 *    宁可只显示「已自动获得」，⛔ 也不把 `undefined` 拼上去。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ 经典脚本（浏览器 `<script src>` 直接用，
 *    必须在 `session.js` **之后**加载），末尾条件导出给 Node 的 `require`。
 *
 * 🔴🔴 **整体包在一个 IIFE 里** —— ⛔ 别把这层括号去掉。理由与 `session.js` 那份同一条：
 *    经典脚本的顶层绑定**全是全局的**，而页面自己有 `function el(tag, cls, text)`。
 *    本文件若顶层写 `function el(id)`，**两处会互相顶掉**，而**不报错** ——
 *    表现是"页头那两块怎么都不开/不关"（最坏的一种：静默）。
 *    ⇒ 现在本文件对外**只留 `window.RagCred` 一个键**（守卫：`cred.test.js` 末条）。
 */

(function () {

/** 页头那 6 个约定 id。⚠️ 8 个页面都得有前三个；后三个没有时**跳过**（`chat` 就是那种）。 */
const CRED_IDS = {
  auto: 'cred-auto',       // 「凭据 已自动获得」那一块（含里面那个数字 span）
  quota: 'cred-quota',     // 上面那块里的数字 span
  swap: 'swapkey',         // 「换一把」按钮
  manual: 'cred-manual',   // 今天那种「API Key 输入框」的 label（没有 ⇒ 跳过）
  save: 'save',            // 今天那颗「保存」按钮（没有 ⇒ 跳过）
};

/** 取元素；**没有就返回 null**（⛔ 别抛 —— `chat` 那页就没有 `cred-manual` / `save`）。 */
function el(id) {
  return (typeof document !== 'undefined' && document) ? document.getElementById(id) : null;
}

/** 切显隐；元素不存在 ⇒ **跳过**（见上）。 */
function setHidden(id, hidden) {
  const n = el(id);
  if (n) n.hidden = !!hidden;
}

/**
 * 🔴 自动 / 手动 两块页头控件的**唯一**一处切换。
 *
 * ⚠️ **别在别处再切一次** —— 两处切就会不一致（表现是"输入框和只读那块同时出现"）。
 * @param {boolean} auto `true` ⇒ 只读那块（自动领到了）；`false` ⇒ 今天那种「填 + 保存」
 */
function applyMode(auto) {
  setHidden(CRED_IDS.auto, !auto);
  setHidden(CRED_IDS.swap, !auto);
  setHidden(CRED_IDS.manual, auto);
  setHidden(CRED_IDS.save, auto);
}

/**
 * 页头那把额度的**当场读数**（`/api/v1/agent/token/budget`，10 个能力页里 5 个已经在读）。
 *
 * ⚠️ **取不到就保持原样**（只显示「已自动获得」）—— 见文件头约定 ③。
 * ⚠️ 单位是 **token**（`DEC-040`：额度全套统一到 token 口径，⛔ 不是"次"）。
 */
function refreshQuota() {
  const n = el(CRED_IDS.quota);
  if (!n) return;
  fetch('/api/v1/agent/token/budget', { headers: { 'X-API-Key': RagSession.key() } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (b) {
      // 🔴 判据是 **"它得是个有限的数"**，⛔ 不是 `!== undefined` ——
      //    后者挡不住 `null`（`null` 拼进字符串会印成 `NaN`，而页面上看不出哪里错了）
      //    和 `NaN`。本仓立场：「**不许印没有数据源的数**」。
      if (!b || typeof b.remaining !== 'number' || !isFinite(b.remaining)) return;
      n.textContent = ' · 今日还剩 ' + b.remaining + ' tokens';
    })
    .catch(function () { /* 取不到 ⇒ 就不显示数字，页头仍写着"已自动获得" */ });
}

/**
 * 把「换一把」接上。
 *
 * ⚠️ **换完一律重开一次页面**（领到 / 领不到都一样）—— 让页面拿手里那把**重新走一遍**：
 * · 领到了 ⇒ 新凭据，页面按它重来；
 * · 领不到 ⇒ 重开之后 `mount()` 会走「退回自己填」那条路，与今天一致。
 * 这样⛔ 不需要在 8 个页面里各写一套"换完怎么重新起页"的逻辑。
 *
 * ⚠️ 语义说明：清掉本地那把再领 ⇒ 后端 `_revoke()` 会先撤掉这个访客名下旧的
 * （⇒ **一个访客最多一把活着的**）。⚠️ 但**额度桶是按 `user_name` 算的**
 * ⇒ 换一把**换不来新额度** —— 它解决的是"手里这把不顶用了"（过期 / 失效）。
 */
function wireSwap() {
  const b = el(CRED_IDS.swap);
  if (!b) return;
  b.onclick = async function () {
    RagSession.clear();
    await RagSession.ensureKey();
    location.reload();
  };
}

/**
 * ⭐ 页面装配的唯一入口：**凭据就位之后再起页面**。
 *
 * 🔴 为什么必须"先就位再起"：demo 那条路上**首访**时手里还没有凭据，
 *    这时页面若照旧发请求，第一批全是 401 —— 而访客什么都没做错。
 *
 * @param {(auto: boolean) => void} onReady 凭据弄妥之后跑页面自己的起法
 *   （`auto` = 页头现在是不是"自动"形态）。⚠️ **同步回调**，就在这轮里跑。
 * @returns {Promise<boolean>} 页头是不是"自动"形态
 */
async function mount(onReady) {
  const auto = !!(await RagSession.ensureKey());
  applyMode(auto);
  wireSwap();
  if (auto) refreshQuota();
  if (typeof onReady === 'function') onReady(auto);
  return auto;
}

const RagCred = { CRED_IDS, applyMode, refreshQuota, wireSwap, mount };

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagCred;                  // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagCred = RagCred;                  // 浏览器（`<script src>` 之后就是全局）
}

})();   // ⛔ 别去掉 —— 见文件头：去掉它，`el` 会与页面自己那个 `el` 互相顶掉，且**不报错**

