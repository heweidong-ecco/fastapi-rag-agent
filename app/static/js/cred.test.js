'use strict';
/* `cred.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/cred.test.js（已进 ci.yml 的 run 块，glob）

🔴 **本文件全程用 `vm` 造一个假浏览器**（`document` / `localStorage` / `fetch` 都是假的），
   而且**把真的 `session.js` 一起装进去** —— 因为 `cred.js` 的动作全是"读了凭据之后干什么"，
   只测它自己而不测它和 `session.js` 的接缝，等于没测。
   ⚠️ 具体说：本文件里 **`cred.js` 从不 `require('./session.js')`** ——
      浏览器上它就是读全局 `RagSession`。所以这里也得让它们**在同一个上下文里**跑，
      ⛔ 不然测的是另一种接法。 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SESSION_SRC = fs.readFileSync(path.join(__dirname, 'session.js'), 'utf8');
const CRED_SRC = fs.readFileSync(path.join(__dirname, 'cred.js'), 'utf8');

/** 8 个页面页头都有的那 3 个 id。 */
const HEAD_IDS = ['cred-auto', 'cred-quota', 'swapkey'];
/** 7 个页面有、`chat` **没有**的那 3 个（它自己那张登录页顶替了）。 */
const FORM_IDS = ['cred-manual', 'save', 'apikey'];

/** 造一个假页面 + 假浏览器，跑一遍 `session.js` 和 `cred.js`。
 *
 * @param {{ids?: string[], stored?: object, claim?: Function, budget?: Function}} opts
 *   `ids` ⇒ 页面上**存在**哪些 id（默认全有）；`stored` ⇒ 假的 localStorage 初始内容；
 *   `claim` ⇒ 假的那条领凭据端点；`budget` ⇒ 假的额度端点
 */
function makePage(opts) {
  const o = opts || {};
  const ids = o.ids || HEAD_IDS.concat(FORM_IDS);
  const nodes = {};
  for (const id of ids) nodes[id] = { id, hidden: false, textContent: '' };

  const store = Object.assign({}, o.stored || {});
  const calls = [];
  const state = { reloads: 0 };

  const sandbox = {
    window: {},
    console,
    document: { getElementById: (id) => (id in nodes ? nodes[id] : null) },
    location: { reload: () => { state.reloads += 1; } },
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    },
    fetch: (url, init) => {
      calls.push({ url: String(url), init: init || {} });
      if (String(url).includes('/demo/claim')) {
        if (!o.claim) return Promise.reject(new Error('测试里没给 claim'));
        return o.claim(url, init);
      }
      if (String(url).includes('/agent/token/budget')) {
        if (!o.budget) return Promise.reject(new Error('测试里没给 budget'));
        return o.budget(url, init);
      }
      return Promise.reject(new Error('测试里没预期的请求：' + url));
    },
    crypto: { randomUUID: () => 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' },
  };

  // 🔴 **`window` 就是全局对象本身** —— 真浏览器里如此（`window === globalThis`）。
  //    ⚠️ 用两个对象假装的话，`cred.js` 里那句**裸的** `RagSession` 在沙箱里根本找不到
  //       （它挂的是 `window.RagSession`）⇒ 测出来的接法与浏览器上不是一种。
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  const before = new Set(Object.keys(sandbox));
  vm.runInContext(SESSION_SRC, sandbox);     // ⚠️ 顺序不能反 —— 浏览器上也是 session 先
  const afterSession = new Set(Object.keys(sandbox));
  const sessionAdded = Object.keys(sandbox).filter((k) => !before.has(k));
  vm.runInContext(CRED_SRC, sandbox);
  const added = Object.keys(sandbox).filter((k) => !afterSession.has(k));

  return { sandbox, nodes, store, calls, state, added, sessionAdded, R: sandbox.RagCred };
}

/** 让 `refreshQuota()` 里那串 `.then` 跑完（假 fetch 是已 resolve 的 promise）。 */
function settle() {
  return new Promise((r) => setImmediate(r)).then(() => new Promise((r) => setImmediate(r)));
}

function okClaim(apiKey) {
  return () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ api_key: apiKey, user_name: 'demo-x', expires_in_days: 7 }),
  });
}

function okBudget(b) {
  return () => Promise.resolve({ ok: true, json: () => Promise.resolve(b) });
}

/* ══════════════ 1 · 🔴 领到了 ⇒ 页头变成"自动·只读" ══════════════ */

test('🔴 demo 那条路（领到了）⇒ 只读那块**显示**，「填 + 保存」那块**收起来**', async () => {
  const p = makePage({ claim: okClaim('K-NEW'), budget: okBudget({ remaining: 4242 }) });
  const auto = await p.R.mount();
  assert.strictEqual(auto, true);
  assert.strictEqual(p.nodes['cred-auto'].hidden, false, '领到了却没显示"已自动获得"');
  assert.strictEqual(p.nodes['swapkey'].hidden, false, '领到了却没有"换一把"');
  assert.strictEqual(p.nodes['cred-manual'].hidden, true, '领到了还让访客看着一个输入框 ⇒ 他会以为要自己填');
  assert.strictEqual(p.nodes['save'].hidden, true, '那只"保存"按钮留着 ⇒ 同上');
});

test('🔴 页头显示的是**当场读到的额度**（token 口径）', async () => {
  const p = makePage({ claim: okClaim('K-NEW'), budget: okBudget({ remaining: 4242 }) });
  await p.R.mount();
  await settle();
  assert.match(p.nodes['cred-quota'].textContent, /4242/);
  assert.match(p.nodes['cred-quota'].textContent, /token/);
});

test('`mount()` **在凭据弄妥之后**才回调 `onReady`（页面自己的起法）', async () => {
  const p = makePage({ claim: okClaim('K-NEW'), budget: okBudget({ remaining: 1 }) });
  const seen = [];
  await p.R.mount((auto) => { seen.push([auto, p.sandbox.window.RagSession.key()]); });
  assert.deepStrictEqual(seen, [[true, 'K-NEW']], '回调时手里还没有凭据 ⇒ 页面第一批请求会是 401');
});

/* ══════════════ 2 · 🔴 领不到 ⇒ 退回今天的样子（本文件最要紧的一组） ══════════════ */

test('🔴 本仓那条路（404）⇒ 退回「填 + 保存」，⛔ 不抛、⛔ 不弹错', async () => {
  // ⚠️ 这是**最常见**的一种：本仓跑 `main:app` ⇒ 每个页面**每次都**撞上它。
  const p = makePage({ claim: () => Promise.resolve({ ok: false, status: 404 }) });
  const auto = await p.R.mount();
  assert.strictEqual(auto, false);
  assert.strictEqual(p.nodes['cred-auto'].hidden, true, '这条路压根领不到，却显示"已自动获得" ⇒ 撒谎');
  assert.strictEqual(p.nodes['swapkey'].hidden, true);
  assert.strictEqual(p.nodes['cred-manual'].hidden, false, '退回不了"自己填" ⇒ 这条路**彻底没法用**了');
  assert.strictEqual(p.nodes['save'].hidden, false);
});

test('🔴 网络错 / 端点没起 ⇒ 同样退回「填 + 保存」，⛔ 不抛', async () => {
  const p = makePage({ claim: () => Promise.reject(new Error('boom')) });
  assert.strictEqual(await p.R.mount(), false);
  assert.strictEqual(p.nodes['cred-manual'].hidden, false);
});

test('🔴 领不到时**一个额度请求都不发**（页头没有数字可填）', async () => {
  const p = makePage({ claim: () => Promise.resolve({ ok: false, status: 404 }) });
  await p.R.mount();
  await settle();
  assert.deepStrictEqual(p.calls.map((c) => c.url), ['/api/v1/demo/claim'],
    '领不到还去问额度 ⇒ 又是一条注定 401 的请求');
});

/* ══════════════ 3 · 🔴🔴 页头⛔ 不出现凭据明文（`DEC-143 §四`） ══════════════ */

test('🔴🔴 领到之后，**页面节点的文字里不带那把凭据**（只显示"有"和"剩多少"）', async () => {
  const SECRET = 'sk-PLAINTEXT-MUST-NOT-APPEAR-0123456789';
  const p = makePage({ claim: okClaim(SECRET), budget: okBudget({ remaining: 7 }) });
  await p.R.mount();
  await settle();
  for (const id of Object.keys(p.nodes)) {
    const t = String(p.nodes[id].textContent || '');
    assert.ok(!t.includes(SECRET),
      `节点 #${id} 里出现了凭据明文 ⇒ 会被复制、会被转贴（显示它只有风险、没有好处）`);
  }
});

test('🔴 那个数字 span 里⛔ 不许出现 `undefined` / `NaN`（本仓：「不许印没有数据源的数」）', async () => {
  for (const bad of [undefined, null, {}, { remaining: undefined }, { remaining: NaN }]) {
    const p = makePage({ claim: okClaim('K'), budget: okBudget(bad) });
    await p.R.mount();
    await settle();
    const t = p.nodes['cred-quota'].textContent;
    assert.strictEqual(t, '', `额度是 ${JSON.stringify(bad)} 时，页头印出了「${t}」`);
  }
});

test('额度端点挂了 ⇒ 数字那块**保持为空**，只读那块**照旧显示**（⛔ 别整块收起来）', async () => {
  const p = makePage({ claim: okClaim('K'), budget: () => Promise.reject(new Error('nope')) });
  await p.R.mount();
  await settle();
  assert.strictEqual(p.nodes['cred-quota'].textContent, '');
  assert.strictEqual(p.nodes['cred-auto'].hidden, false, '只是读不到额度，不该把"已自动获得"也收起来');
});

/* ══════════════ 4 · 换一把 ══════════════ */

test('🔴「换一把」⇒ 先清手里那把、再领一把新的一起重开放页；**不是**两个都留着', async () => {
  const p = makePage({
    stored: { rag_api_key: 'K-OLD', rag_visitor_id: 'v-12345678' },
    claim: okClaim('K-NEW'),
    budget: okBudget({ remaining: 1 }),
  });
  await p.R.mount();
  await p.nodes['swapkey'].onclick();
  assert.strictEqual(p.store.rag_api_key, 'K-NEW', '换完手里还是旧那把 ⇒ "换一把"没换');
  assert.strictEqual(p.state.reloads, 1, '换完没重开页面 ⇒ 页面还在拿旧凭据发请求');
});

test('🔴「换一把」时**访客标识不清** —— 清了就等于凭空多出一个访客（额度也另算一份）', async () => {
  const p = makePage({ claim: okClaim('K-NEW'), budget: okBudget({ remaining: 1 }) });
  await p.R.mount();                                   // 首访 ⇒ 领一次
  await p.nodes['swapkey'].onclick();                  // 换一把 ⇒ 再领一次
  const claims = p.calls.filter((c) => c.url.includes('/demo/claim'));
  assert.strictEqual(claims.length, 2, '要么没领、要么多领了 —— 本用例的前提是"领两次"');
  const first = JSON.parse(claims[0].init.body).visitor_id;
  const second = JSON.parse(claims[1].init.body).visitor_id;
  assert.strictEqual(first, second, '换了访客标识 ⇒ 后端会按**另一个**访客记账，而人还是同一个');
  assert.strictEqual(p.store.rag_visitor_id, first, '标识没存下来 ⇒ 每次刷新都换一个访客');
});

test('⚠️「换一把」也领不到（端点没了）⇒ 仍然重开一次 —— 重开后 `mount()` 自然会退回"自己填"', async () => {
  const p = makePage({
    stored: { rag_api_key: 'K-OLD' },
    claim: () => Promise.resolve({ ok: false, status: 500 }),
    budget: okBudget({ remaining: 1 }),
  });
  await p.R.mount();
  await p.nodes['swapkey'].onclick();
  assert.strictEqual(p.store.rag_api_key, undefined, '旧那把没清掉 ⇒ 页面会一直拿一把已经不管用的凭据');
  assert.strictEqual(p.state.reloads, 1, '不重开 ⇒ 页面停在"旧凭据 + 空页头"这个中间态');
});

/* ══════════════ 5 · `chat` 那种页（少了 3 个元素）⛔ 不许抛 ══════════════ */

test('🔴 页面上没有「填 + 保存」那块（`chat` 就是）⇒ `applyMode` **跳过**，⛔ 不抛', async () => {
  const p = makePage({ ids: HEAD_IDS, claim: okClaim('K'), budget: okBudget({ remaining: 1 }) });
  assert.doesNotThrow(() => { p.R.applyMode(false); p.R.applyMode(true); });
  assert.strictEqual(p.nodes['cred-manual'], undefined, '本用例的前提是那 3 个元素确实不存在');
});

test('🔴 连「已自动获得」那块都没有 ⇒ 三个内部函数**全部跳过**，⛔ 不抛', async () => {
  const p = makePage({ ids: [], claim: okClaim('K') });
  assert.doesNotThrow(() => p.R.refreshQuota());
  assert.doesNotThrow(() => p.R.wireSwap());
  assert.strictEqual(await p.R.mount(), true, '页头没有那块，但凭据本身照样得领到');
});

/* ══════════════ 6 · 合约：这份文件不许把"判定"搬进来 ══════════════ */

test('🔴 本文件⛔ 不自己判"本地有没有凭据" —— 那一条**只有** `session.js` 说了算', () => {
  // ⚠️ 判据：源码里⛔ 不许再出现那个存储键的字面量。
  //    出现了 ⇒ 这里就长出了**第二份**"凭据在哪、叫什么"的实现 ⇒ 正是本文件要防的那种漂移。
  //    ⚠️ 与 `tools.test.js` / `system.test.js` 同族：**先把注释剥掉**再找，
  //       否则本段注释自己就会被算成命中（本仓栽过这个坑）。
  const stripped = CRED_SRC
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
  assert.ok(!stripped.includes('rag_api_key'), '`cred.js` 里出现了存储键 ⇒ 那一条判定被抄了第二份');
  assert.ok(!stripped.includes('localStorage'), '`cred.js` 里直接碰了 `localStorage` ⇒ 绕过了 `session.js`');
});

test('导出对象存在且接口齐全 —— 守卫失效时这条会红（⛔ 别直接删了它）', () => {
  const p = makePage({});
  for (const k of ['applyMode', 'refreshQuota', 'wireSwap', 'mount']) {
    assert.strictEqual(typeof p.R[k], 'function', `window.RagCred.${k} 不是函数`);
  }
  assert.strictEqual(p.R.CRED_IDS.auto, 'cred-auto');
  assert.strictEqual(p.R.CRED_IDS.swap, 'swapkey');
});

/* ══════════════ 7 · 🔴🔴 全局污染守卫 ══════════════ */

test('🔴🔴 `cred.js` 除了 `RagCred` **不许再留别的全局键**（`el` 尤其要命）', () => {
  // ⚠️ 为什么单独钉 `el`：**8 个页面里 7 个自己有 `function el(tag, cls, text)`**
  //    （造元素那个小工具）。本文件的 `el(id)` 若也是顶层函数 ⇒ 两处**互相顶掉**，
  //    而且**不报错** —— 表现是"页头那两块怎么都不开/不关"（静默错，最难查的那种）。
  //    ⇒ 整份包在 IIFE 里，**只留一个键**。
  const p = makePage({});
  assert.deepStrictEqual(p.added, ['RagCred'],
    `\`cred.js\` 往 window 上多挂了：${p.added.join(', ')} ⇒ 与页面自己的顶层绑定撞车的面又回来了`);
  assert.deepStrictEqual(p.sessionAdded, ['RagSession'], '前提坏了：`session.js` 自己也在漏全局');
});
