'use strict';
/* `panel.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test api/static/js/panel.test.js（已接进 ci.yml 的 run 块，glob） */
const test = require('node:test');
const assert = require('node:assert');

const {
  BOUNDARY_KEYS, boundaryText, paramQuery, stateOf,
  emptyReason, truncationNotice, errorText,
} = require('./panel.js');

/* ══════════════ 1 · 边界标注（规格 §3.6.2）══════════════ */

test('boundaryText：五个 key 都有非空文案', () => {
  for (const k of BOUNDARY_KEYS) {
    const s = boundaryText(k, { used: 1, limit: 2, remaining: 1, rpm: 10 });
    assert.ok(typeof s === 'string' && s.length > 10, `${k} 的文案为空`);
  }
});

test('🔴 boundaryText：未登记的 key 必须【抛错】，⛔ 不许静默回落成空串', () => {
  // 静默回落 = 页面上少一条边界标注，而**没有任何东西会红**（本仓「响亮 > 静默」那族）。
  assert.throws(() => boundaryText('nope'), /unknown boundary key/);
});

test('🔴 boundaryText：平台重启那条必须把限制【指向平台】', () => {
  // 这一条的【目的就是归因】——业务方原话：「标注和提示是告诉他 demo 放的平台有这些限制，
  // ⛔ 不是我们的产品代码的 bug」。⇒ 措辞里必须同时有「平台」和「不是故障」。
  const s = boundaryText('platform_restart');
  assert.match(s, /平台/);
  assert.match(s, /不是系统故障|不是.*bug/);
});

test('boundaryText：额度那条是【当场读数】，⛔ 不写死', () => {
  const s = boundaryText('quota', { used: 120, limit: 500, remaining: 380 });
  assert.match(s, /120/); assert.match(s, /500/); assert.match(s, /380/);
});

test('🔴 boundaryText：没数据时⛔ 不许把 undefined 印出去（首页未登录就走这条路）', () => {
  // 本仓立场：「不许印"没有数据源"的数」（规格 §五 · trace 页那两格的前科）。
  for (const k of ['quota', 'rate_limit']) {
    const s = boundaryText(k);                    // ⛔ 不传 data
    assert.doesNotMatch(s, /undefined|NaN|null/, `${k} 把空值拼进文案了：${s}`);
    assert.ok(s.length > 10, `${k} 的无数据版太短 ⇒ 等于没说`);
  }
});

test('⚠️ boundaryText：verify 是【另一类】—— 它讲"我们自证到什么程度"，⛔ 与平台限制无关', () => {
  // 混进前 4 条里会让归因【反向】（访客读成"验证不完整也是平台的锅"）。
  const s = boundaryText('verify');
  assert.doesNotMatch(s, /平台限制/, 'verify 那条⛔ 不能说成平台限制 —— 它是我们自己的事');
  assert.ok(BOUNDARY_KEYS[4] === 'verify', 'verify 必须是第 5 个 —— 渲染时要与前面 4 条分开');
});

/* ══════════════ 2 · 参数拼串 ══════════════ */

test('paramQuery：空值跳过 · 会编码 · 空对象回空串', () => {
  assert.strictEqual(paramQuery({}), '');
  assert.strictEqual(paramQuery({ q: 'a b', n: 3, skip: '' }), '?q=a%20b&n=3');
  // `0` 是**合法值**，⛔ 别被 falsy 判掉
  assert.strictEqual(paramQuery({ skip: undefined, keep: 0 }), '?keep=0');
});

/* ══════════════ 3 · 四态 ══════════════ */

test('🔴 stateOf：本仓的拒绝形状是 200 + {"status":"error"}，⛔ 别只看 r.ok', () => {
  // `DEC-088`：接口的四类拒绝**全是 HTTP 200 + {"status":"error"}**
  // ⇒ 只看 `r.ok` 会把"无权查看"当成成功（`approvals.html` 栽过这条）。
  assert.strictEqual(stateOf({ status: 'error' }), 'error');
  assert.strictEqual(stateOf({ error: 'boom' }), 'error');
  assert.strictEqual(stateOf(null), 'error');
});

test('stateOf：ok / empty 分开（空的定义 = 键在、但那个数组是空的）', () => {
  assert.strictEqual(stateOf({ items: [] }), 'empty');
  assert.strictEqual(stateOf({ items: [1] }), 'ok');
});

test('emptyReason：必须【解释为什么空】，⛔ 不是"暂无数据"四个字', () => {
  const s = emptyReason();
  assert.ok(s.length > 20, '空态理由太短 ⇒ 等于没解释');
  assert.match(s, /为什么|要么|不等于坏了/);
});

/* ══════════════ 4 · 截断（`api/test_truncation_declared.py` 那道门）══════════════ */

test('🔴 truncationNotice：两种形状【分开】· ⛔ 不合并 · 没有就回 null', () => {
  assert.strictEqual(truncationNotice({ items: [1] }), null);
  assert.match(truncationNotice({ has_more: true, items: [1] }), /下一页|更多/);
  assert.match(truncationNotice({ truncated: true, total: 900, items: [1] }), /900/);
});

/* ══════════════ 5 · 错误文案 ══════════════ */

test('🔴 errorText：401/403 · 429 · 503 是【三句话】，⛔ 不合并成一句', () => {
  const a = errorText(401), b = errorText(429), c = errorText(503);
  assert.notStrictEqual(a, b); assert.notStrictEqual(b, c); assert.notStrictEqual(a, c);
  assert.match(b, /额度|限流|恢复/);          // 429 要说清"这是额度、何时恢复"
  assert.match(b, /不是故障/);
});

/* ══════════════ 6 · 结构型守卫：文案【只许有一份】 ══════════════
 *
 * 🔴 为什么要有这条：本仓前科（`DEC-089`）—— `sse.js` 之所以是**唯一**解析引用的地方，
 *    正是因为「两处实现同一个东西**必然漂移**」，而页面上**不报任何错**。
 *    边界文案同理：`panel.js` 一份 + 某个 `.html` 里抄一段 ⇒ 改了一头就漂。
 *    ⚠️ 光写注释挡不住 —— 本仓原话：「**有结构才执行，只有文字就漏**」。
 */
const fs = require('node:fs');
const path = require('node:path');
const JS_DIR = __dirname;
const WEB_DIR = path.join(__dirname, '..', 'web');
// ⚠️ 针脚**分两段拼**，让本文件自身不包含那个连续子串 —— 否则守卫会被**自己**绊倒。
const NEEDLE = '魔搭创空间' + '的免费档';

function frontendSources() {
  const out = [];
  for (const dir of [JS_DIR, WEB_DIR]) {
    let names;
    try { names = fs.readdirSync(dir); } catch (e) { continue; }   // 目录还不存在就跳过
    for (const n of names) {
      if (!/\.(js|html)$/.test(n) || n.endsWith('.test.js')) continue;
      out.push(path.join(dir, n));
    }
  }
  return out;
}

test('🔴 边界文案只许有一份（结构型：数的是【文件】，⛔ 不是"我记得没抄第二份"）', () => {
  const files = frontendSources();
  // 🔴 先证明尺子有读数 —— 空集合断言会一路绿着放行（`DEC-065` 那族）
  assert.ok(files.length >= 4, `只扫到 ${files.length} 份前端源文件 —— 扫描失效了`);
  const hit = files
    .filter((f) => fs.readFileSync(f, 'utf8').includes(NEEDLE))
    .map((f) => path.relative(path.join(JS_DIR, '..', '..'), f).replace(/\\/g, '/'));
  assert.deepStrictEqual(
    hit, ['static/js/panel.js'],
    '边界文案在别处又出现了一份 ⇒ 两处会漂移，而页面上不报错（表现是"改了一处另一处没变"）',
  );
});

/* ══════════════ 7 · 浏览器侧：`RagPanel` 这个全局真的存在吗 ══════════════
 *
 * 🔴 `node --test` 走 `module.exports`，**浏览器走的是另一条路**（经典脚本 ⇒ 全局）。
 *    `sse.js` 有过前科：当时只挂了 `module.exports` ⇒ 页面里每一处 `RagSse.xxx`
 *    都 `ReferenceError`，而 **node 用例全绿、页面加载时也不报**。
 */
const vm = require('node:vm');

function loadInBrowserLikeSandbox() {
  const src = fs.readFileSync(path.join(JS_DIR, 'panel.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return sandbox.window;
}

test('把 panel.js 当【经典脚本】跑一遍 ⇒ window.RagPanel 存在且接口齐全', () => {
  const w = loadInBrowserLikeSandbox();
  assert.strictEqual(typeof w.RagPanel, 'object', 'panel.js 没挂 window.RagPanel ⇒ 页面里全报 ReferenceError');
  for (const k of ['boundaryText', 'paramQuery', 'stateOf', 'emptyReason', 'truncationNotice', 'errorText']) {
    assert.strictEqual(typeof w.RagPanel[k], 'function', `window.RagPanel.${k} 不是函数`);
  }
  assert.ok(Array.isArray(w.RagPanel.BOUNDARY_KEYS), 'BOUNDARY_KEYS 不是数组');
});
