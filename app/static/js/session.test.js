'use strict';
/* `session.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/session.test.js（已进 ci.yml 的 run 块，glob）

🔴 **本文件全程用 `vm` 造一个假浏览器**（`localStorage` / `fetch` / `crypto` 都是假的）——
   因为 `session.js` 的价值**全在"拿不到时怎么办"**，而那几条只有**把 fetch 弄坏**才测得到。 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SRC = fs.readFileSync(path.join(__dirname, 'session.js'), 'utf8');

/** 造一个假浏览器环境，跑一遍 `session.js`，把 `window.RagSession` 交出来。
 *
 * @param {{stored?: object, fetchImpl?: Function, uuid?: string}} opts
 *   `stored` ⇒ 假的 localStorage 初始内容；`fetchImpl` ⇒ 假的 fetch；`uuid` ⇒ 假的 randomUUID
 */
function makeSandbox(opts) {
  const o = opts || {};
  const store = Object.assign({}, o.stored || {});
  const calls = [];
  const sandbox = {
    window: {},
    console,
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    },
    fetch: (url, init) => {
      calls.push({ url, init });
      if (!o.fetchImpl) return Promise.reject(new Error('测试里没给 fetchImpl'));
      return o.fetchImpl(url, init);
    },
    crypto: { randomUUID: () => (o.uuid || 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee') },
  };
  // 🔴 **`window` 就是全局对象本身** —— 真浏览器里如此（`window === globalThis`）。
  //    ⚠️ 这两者**不能**用两个对象假装：`session.js` 是**经典脚本**，它只往 `window` 上挂，
  //       而别的文件是**裸着**写 `RagSession` 去读全局的。两者不是同一个对象时，
  //       测出来的接法和浏览器上不是一种（本仓前科：「**同源的两个输入不能互相作证**」）。
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  const before = new Set(Object.keys(sandbox));
  vm.runInContext(SRC, sandbox);
  const added = Object.keys(sandbox).filter((k) => !before.has(k));
  return { R: sandbox.RagSession, store, calls, sandbox, added };
}

/** 造一个"成功领到"的假响应。 */
function okResponse(apiKey) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ api_key: apiKey, user_name: 'demo-x', expires_in_days: 7 }),
  });
}

/* ══════════════ 1 · 约定 ①：本地有 ⇒ ⛔ 不再领 ══════════════ */

test('🔴 本地已经有凭据 ⇒ **一个请求都不发**（"只领一把"的**唯一**保证）', async () => {
  const { R, calls } = makeSandbox({ stored: { rag_api_key: 'K-EXISTING' } });
  const got = await R.ensureKey();
  assert.strictEqual(got, 'K-EXISTING');
  assert.deepStrictEqual(calls, [], '本地有还去领了 ⇒ 会把这个访客的凭据换掉，而他从不知道');
});

test('`key()` 是**同步**的，且与今天各页面那个 `key()` 同签名（没有 ⇒ 空串）', () => {
  const a = makeSandbox({ stored: { rag_api_key: 'K1' } });
  assert.strictEqual(a.R.key(), 'K1');
  const b = makeSandbox({});
  assert.strictEqual(b.R.key(), '');
});

/* ══════════════ 2 · 领一把：成功那条路 ══════════════ */

test('首访（本地没有）⇒ 去领一把，**存下来**再回', async () => {
  const { R, store, calls } = makeSandbox({ fetchImpl: () => okResponse('K-NEW') });
  const got = await R.ensureKey();
  assert.strictEqual(got, 'K-NEW');
  assert.strictEqual(store.rag_api_key, 'K-NEW', '领到了却没存 ⇒ 每次开页面都要重领');
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].url, '/api/v1/demo/claim');
  assert.strictEqual(calls[0].init.method, 'POST');
  const body = JSON.parse(calls[0].init.body);
  assert.ok(body.visitor_id, '没带 visitor_id —— 后端会 422');
});

/* ══════════════ 3 · 🔴 领不到时【静默退回】—— 本文件最要紧的一组 ══════════════ */

test('🔴 **404（= 本仓那条路，这条路由压根不存在）⇒ 回空串，⛔ 不抛**', async () => {
  // ⚠️ 这是**最常见**的一种：本仓跑 `main:app` ⇒ 页面**每次都**会撞上它。
  //    ⛔ 绝不能因此报错 —— 那会让本仓那条路上每次开页面都像出了事。
  const { R } = makeSandbox({ fetchImpl: () => Promise.resolve({ ok: false, status: 404 }) });
  assert.strictEqual(await R.ensureKey(), '');
});

test('🔴 网络错 / 请求发不出去 ⇒ 回空串，⛔ 不抛', async () => {
  const { R } = makeSandbox({ fetchImpl: () => Promise.reject(new Error('boom')) });
  assert.strictEqual(await R.ensureKey(), '');
});

test('🔴 回的不是 JSON ⇒ 回空串，⛔ 不抛', async () => {
  const { R } = makeSandbox({
    fetchImpl: () => Promise.resolve({ ok: true, json: () => Promise.reject(new Error('not json')) }),
  });
  assert.strictEqual(await R.ensureKey(), '');
});

test('🔴 200 但**没有 api_key 字段** ⇒ 回空串（⛔ 别把 undefined 存进去）', async () => {
  const { R, store } = makeSandbox({
    fetchImpl: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ user_name: 'x' }) }),
  });
  assert.strictEqual(await R.ensureKey(), '');
  assert.strictEqual(store.rag_api_key, undefined, '把空的东西存进去了 ⇒ `key()` 会说"有凭据"');
});

test('🔴 `localStorage` 不可用（隐私模式）⇒ `key()` 回空串，⛔ 不让整页挂掉', async () => {
  const sandbox = { window: {}, console, crypto: { randomUUID: () => 'x' } };
  sandbox.localStorage = {
    getItem: () => { throw new Error('denied'); },
    setItem: () => { throw new Error('denied'); },
    removeItem: () => { throw new Error('denied'); },
  };
  sandbox.fetch = () => Promise.reject(new Error('no'));
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox);
  assert.strictEqual(sandbox.window.RagSession.key(), '');
  assert.strictEqual(await sandbox.window.RagSession.ensureKey(), '');
});

/* ══════════════ 4 · 访客标识 ══════════════ */

test('🔴 访客标识的形状**必须能被后端接受**（`[A-Za-z0-9_-]{8,64}`）', () => {
  const { R } = makeSandbox({});
  const v = R.visitorId();
  assert.match(v, /^[A-Za-z0-9_-]{8,64}$/,
    '形状不对 ⇒ 后端回 422 ⇒ 访客永远领不到，而页面上只会看到"退回自己填"');
});

test('🔴 同一个浏览器两次 ⇒ **同一个标识**（存下来了）；换个存储 ⇒ 换一个', () => {
  const a = makeSandbox({ uuid: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' });
  assert.strictEqual(a.R.visitorId(), a.R.visitorId());
  assert.strictEqual(a.store.rag_visitor_id, a.R.visitorId(), '没存下来 ⇒ 每次刷新都换一个访客');
  const b = makeSandbox({ stored: a.store, uuid: 'ffffffff-0000-1111-2222-333333333333' });
  assert.strictEqual(b.R.visitorId(), a.store.rag_visitor_id, '存过标识时⛔ 不该重新生成');
});

test('没有 `crypto.randomUUID`（非安全上下文）⇒ 退回随机串，形状仍合规', () => {
  const { R } = makeSandbox({});
  // 把 crypto 去掉再跑一遍
  const sandbox = { window: {}, console, localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } };
  sandbox.fetch = () => Promise.reject(new Error('no'));
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox);
  const v = sandbox.window.RagSession.visitorId();
  assert.match(v, /^[A-Za-z0-9_-]{8,64}$/);
  void R;
});

/* ══════════════ 5 · 结构型守卫：渲染出去的文字⛔ 不许带 markdown 记号 ══════════════ */

test('🔴 本文件不产生任何给访客看的文案 ⇒ 但**它自己**也不许带 markdown 记号被渲染', () => {
  // ⚠️ 与 tools / system / ops / approvals 同族：本仓页面一律 `textContent`。
  //    本文件目前**没有**面向用户的字符串，这条是**防将来**——
  //    一旦有人在这里加文案并拼进页面，`**` 会原样印出来。
  const stripped = SRC
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
  const exported = stripped.match(/const RagSession = \{[\s\S]*?\};/);
  assert.ok(exported, '没找到那个导出对象 —— 本用例的判据跟着失效，⛔ 别直接删了它');
  assert.ok(!exported[0].includes('**'), '导出对象里出现了 `**`');
});

/* ══════════════ 6 · 浏览器侧：这个全局真的存在吗 ══════════════ */

test('把 session.js 当【经典脚本】跑一遍 ⇒ window.RagSession 存在且接口齐全', () => {
  const { R } = makeSandbox({});
  for (const k of ['key', 'save', 'clear', 'visitorId', 'ensureKey']) {
    assert.strictEqual(typeof R[k], 'function', `window.RagSession.${k} 不是函数`);
  }
  assert.strictEqual(R.KEY_STORE, 'rag_api_key', '键名换了 ⇒ 老访客手里那把凭空丢了');
  assert.strictEqual(R.CLAIM_PATH, '/api/v1/demo/claim');
});

/* ══════════════ 7 · 🔴🔴 全局污染守卫（2026-10-10 真栽过一次） ══════════════ */

test('🔴🔴 本文件对外**只许留 `RagSession` 一个全局键**（多一个都可能撞死页面）', () => {
  // ⚠️ 为什么这条值钱：本文件原先顶层直接写 `function key()` ⇒ 那是**全局的** ⇒
  //    与 8 个页面各自那句 `const key = …` 撞上 ⇒ 浏览器报
  //    `SyntaxError: Identifier 'key' has already been declared`
  //    ⇒ **整个内联脚本一行都不执行，页面全死**，而 pytest / node 用例**全绿**
  //    （它们只读文本，不解析 JS）—— 只有把页面真打开才看得见。
  //    ⇒ 现在整份包在 IIFE 里，**只留一个键**；这条守卫钉住它。
  const { added } = makeSandbox({});
  assert.deepStrictEqual(added, ['RagSession'],
    '本文件往 window 上多挂了东西 ⇒ 与页面自己的顶层绑定撞车的面又回来了');
});
