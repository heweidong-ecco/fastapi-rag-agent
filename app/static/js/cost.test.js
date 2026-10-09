'use strict';
/* `cost.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/cost.test.js（已接进 ci.yml 的 run 块，glob）

🔴 本文件**同时是九条路径 `/api/v1` 前缀的守卫** —— 页面走 `RagCost.buildRequest()` 拼路径，
   于是 `app/tests/test_web_pages.py`（只扫页面源码里的**字面量**）对本页**空过**
   （与 `trace.js` / `lab.js` 同一分工）。 */
const test = require('node:test');
const assert = require('node:assert');

const {
  PANELS, NOT_EXPOSED, panelOf, clampInt, buildRequest,
  memoryWarning, scopeNote, show, fmtNum, fmtMoney,
  kvRows, tableOf, table2Of, dictRows,
  truncationNotice, emptyReason, estimatesEmptyReason,
} = require('./cost.js');

/* ══════════════ 1 · 路径与面板数 ══════════════ */

test('🔴 十个面板的 path【全部带 `/api/v1`】—— 少前缀页面就 100% 404（`DEC-094`）', () => {
  const keys = Object.keys(PANELS);
  assert.strictEqual(keys.length, 10, `规格 §2.5(9) + §2.6(3) − 有意不露(2) = 10，实际 ${keys.length}`);
  for (const k of keys) {
    assert.match(PANELS[k].path, /^\/api\/v1\//, `${k} 的 path 没带 /api/v1：${PANELS[k].path}`);
  }
});

test('🔴 面板与「有意不露」两张表【不许重叠】—— 一条接口不能既露又声明不露', () => {
  const exposed = Object.keys(PANELS).map((k) => PANELS[k].path);
  for (const item of NOT_EXPOSED) {
    assert.ok(!exposed.includes(item.path), `${item.path} 同时在两张表里`);
  }
});

test('🔴 「有意不露」两条都必须写明理由（⛔ 不许只写个路径就完事）', () => {
  // 规格 §2.14 的口径：不露也要**写成一条可读的记录**，否则下一个人会以为"忘了做"。
  assert.strictEqual(NOT_EXPOSED.length, 2);
  for (const item of NOT_EXPOSED) {
    assert.ok(item.why && item.why.length > 20, `${item.path} 的理由太短 ⇒ 等于没说`);
  }
  const paths = NOT_EXPOSED.map((x) => x.path).sort();
  assert.deepStrictEqual(paths, [
    '/api/v1/agent/token/purpose', '/api/v1/agent/token/thread',
  ], '不露的是这两条（都是全站口径）；⚠️ `token/recent` 已修好并移进 PANELS —— 见它那一行');
});

test('🔴 panelOf：未登记的 key 必须【抛错】，⛔ 不许静默回落', () => {
  assert.throws(() => panelOf('nope'), /unknown panel/);
});

/* ══════════════ 2 · 口径标注（本页最要紧的一半）══════════════ */

test('🔴 memoryWarning：**只有** source=mem 的面板才挂警——db / const 挂了就是狼来了', () => {
  for (const k of ['memusage', 'recent', 'check', 'intercepts']) {
    assert.match(memoryWarning(k), /重启归零/, `${k} 是内存口径，必须警示`);
  }
  for (const k of ['overview', 'records', 'history', 'monthly', 'budget', 'estimates']) {
    assert.strictEqual(memoryWarning(k), null, `${k} 不是内存口径，⛔ 别给它挂"重启归零"`);
  }
});

test('🔴 三态 source 一个都不能少，且必须是这三种（口径地图）', () => {
  const bySource = {};
  for (const k of Object.keys(PANELS)) bySource[PANELS[k].source] = (bySource[PANELS[k].source] || 0) + 1;
  assert.deepStrictEqual(bySource, { db: 5, mem: 4, const: 1 }, `实际 ${JSON.stringify(bySource)}`);
});

test('🔴 scopeNote：budget 那条必须**同时**点名"本人"与"全站"', () => {
  const s = scopeNote('budget');
  assert.match(s, /本人/); assert.match(s, /全站/);
  assert.match(s, /daily_budget|remaining/);
});

test('scopeNote：estimates 是配置常量 —— ⛔ 别说成"统计"', () => {
  assert.match(scopeNote('estimates'), /配置常量/);
  assert.strictEqual(scopeNote('overview'), null, '本人读库的面板不需要额外口径说明');
});

/* ══════════════ 3 · 请求形状 ══════════════ */

test('buildRequest：参数只给收它的端点（⛔ 别给九条都塞 days/limit）', () => {
  assert.deepStrictEqual(buildRequest('overview', { days: 3, limit: 9 }).query, {});
  assert.deepStrictEqual(buildRequest('intercepts', { days: 3 }).query, {});
  assert.deepStrictEqual(buildRequest('memusage', {}).query, {});
  assert.deepStrictEqual(buildRequest('recent', { days: 3, limit: 9 }).query, {});
  assert.deepStrictEqual(buildRequest('estimates', {}).query, {});
  assert.deepStrictEqual(buildRequest('budget', {}).query, {});
});

test('buildRequest：records 的 days/limit · history 的 days · monthly 的 year/month', () => {
  assert.deepStrictEqual(buildRequest('records', { days: 7, limit: 100 }).query, { days: 7, limit: 100 });
  assert.deepStrictEqual(buildRequest('history', { days: 30 }).query, { days: 30 });
  assert.deepStrictEqual(buildRequest('monthly', { year: 2026, month: 10 }).query, { year: 2026, month: 10 });
  // ⚠️ year/month 不给就**不带**（后端 None ⇒ 默认当月）—— ⛔ 别送个 0 进去
  assert.deepStrictEqual(buildRequest('monthly', {}).query, {});
  assert.deepStrictEqual(buildRequest('monthly', { year: '', month: '' }).query, {});
});

test('🔴 clampInt：夹进范围，非法值回落默认（⛔ 不回落 0）；month 夹在 1–12', () => {
  assert.strictEqual(clampInt(5, 7, 1, 365), 5);
  assert.strictEqual(clampInt(0, 7, 1, 365), 7);
  assert.strictEqual(clampInt('', 30, 1, 365), 30);
  assert.strictEqual(clampInt(9999, 100, 1, 1000), 1000);
  assert.deepStrictEqual(buildRequest('monthly', { month: 13 }).query, { month: 12 });
  assert.deepStrictEqual(buildRequest('monthly', { month: 0 }).query, { month: 1 });
});

test('🔴 buildRequest：check 的可选参数【空串要跳过】—— ⛔ 不能拼成 `?tool_name=`', () => {
  assert.deepStrictEqual(buildRequest('check', {}).query, {});
  assert.deepStrictEqual(buildRequest('check', { tool_name: '', purpose: '' }).query, {});
  assert.deepStrictEqual(buildRequest('check', { tool_name: 'web_search' }).query, { tool_name: 'web_search' });
});

/* ══════════════ 4 · 取值与格式化 ══════════════ */

test('🔴 show：缺值一律 `—`，⛔ **绝不编 0**（不许印没有数据源的数）', () => {
  assert.strictEqual(show(undefined), '—');
  assert.strictEqual(show(null), '—');
  assert.strictEqual(show(''), '—');
  assert.strictEqual(show(0), '0', '0 是【真值】，⛔ 别把 0 也画成 —');
});

test('fmtNum / fmtMoney：千分位 · 四位小数（与后端 round(x,4) 同口径）', () => {
  assert.strictEqual(fmtNum(4216), '4,216');
  assert.strictEqual(fmtMoney(0.12345), '0.1235');
  assert.strictEqual(fmtMoney(0), '0.0000');
  assert.strictEqual(fmtNum(undefined), '—');
  assert.strictEqual(fmtMoney(null), '—');
});

/* ══════════════ 5 · 展示模型（🔴 键名抄自端点源码）══════════════ */

test('kvRows：overview 读 total_cost / total_tokens / total_calls（端点真给的键）', () => {
  const rows = kvRows('overview', { total_cost: 0.1234, total_tokens: 4216, total_calls: 9 });
  assert.deepStrictEqual(rows, [
    ['总花费（元，全时）', '0.1234'], ['总 token（全时）', '4,216'], ['调用次数', '9'],
  ]);
});

test('🔴 kvRows：budget 把【本人】与【全站】两套口径分成两行，⛔ 不合并', () => {
  const rows = kvRows('budget', {
    used_today: 100, daily_budget: 5000, remaining: 4900,
    global_daily_limit: 50000, global_used_today: 1234.5, global_remaining: 48765.5,
  });
  const labels = rows.map((r) => r[0]).join('|');
  assert.match(labels, /我 ·/); assert.match(labels, /全站 ·/);
  assert.strictEqual(rows.length, 6);
});

test('kvRows：memusage 的数是嵌套在 summary 里的（⛔ 别当顶层键读）', () => {
  const rows = kvRows('memusage', { summary: { total_tokens: 10, total_cost: 0.5, calls: 2 } });
  assert.deepStrictEqual(rows, [['进程内 token', '10'], ['进程内花费（元）', '0.5000'], ['进程内调用次数', '2']]);
  // ⛔ 没给 summary ⇒ 三格全 `—`，不许编 0
  assert.deepStrictEqual(kvRows('memusage', {}).map((r) => r[1]), ['—', '—', '—']);
});

test('kvRows：check 没传 tool_name 时,预估那格要说清"估不了",⛔ 不画 0.0000', () => {
  const rows = kvRows('check', { allowed: false, reason: '超预算', estimated_cost: null });
  assert.strictEqual(rows[0][1], '不允许');
  assert.match(rows[2][1], /估不了/);
  assert.match(kvRows('check', {}).map((r) => r[1]).join('|'), /—/);
});

test('tableOf：records / history / overview.by_purpose / monthly.by_purpose / estimates 各一张', () => {
  assert.strictEqual(tableOf('records', { records: [] }).cols.length, 7);
  assert.strictEqual(tableOf('recent', { recent_usage: [] }).cols.length, 5);
  assert.strictEqual(tableOf('history', { history: [] }).cols.length, 4);
  assert.strictEqual(tableOf('overview', { by_purpose: {} }).cols.length, 4);
  assert.strictEqual(tableOf('monthly', { by_purpose: [] }).cols.length, 5);
  assert.strictEqual(tableOf('estimates', { tool_estimates: {} }).cols.length, 2);
  assert.strictEqual(tableOf('intercepts', {}), null, '拦截那条是 KV，不是表格');
});

test('table2Of：只有月度报告有第二张表（按模型）', () => {
  assert.strictEqual(table2Of('monthly', { by_model: [] }).cols[0], '模型');
  assert.strictEqual(table2Of('records', { records: [] }), null);
});

test('dictRows：非对象 / 数组 / null 一律空（⛔ 不抛）', () => {
  assert.deepStrictEqual(dictRows(null), []);
  assert.deepStrictEqual(dictRows([]), []);
  assert.deepStrictEqual(dictRows('x'), []);
  assert.deepStrictEqual(dictRows({ a: 1 }), [['a', 1]]);
});

/* ══════════════ 6 · 截断与空态 ══════════════ */

test('🔴 truncationNotice：两种形状【分开】· ⛔ 不合并 · 没有就 null', () => {
  assert.strictEqual(truncationNotice({ records: [] }), null);
  assert.match(truncationNotice({ has_more: true }), /下一页/);
  assert.match(truncationNotice({ truncated: true }), /截断/);
  assert.notStrictEqual(truncationNotice({ has_more: true }), truncationNotice({ truncated: true }));
});

test('🔴 emptyReason：内存口径那条必须点名"重启会归零"，⛔ 不是"暂无数据"', () => {
  const s = emptyReason('memusage');
  assert.match(s, /内存/); assert.match(s, /重启/);
  assert.match(s, /不等于|⛔/);
  // 读库那条说"还没记账"，⛔ 不许把"重启归零"安到它头上
  const db = emptyReason('records');
  assert.doesNotMatch(db, /重启归零/);
  assert.match(db, /还没/);
});

test('estimatesEmptyReason：常量表为空是**配置**问题，⛔ 与运行无关', () => {
  assert.match(estimatesEmptyReason(), /配置/);
});

/* ══════════════ 7 · 浏览器侧：`RagCost` 这个全局真的存在吗 ══════════════ */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('把 cost.js 当【经典脚本】跑一遍 ⇒ window.RagCost 存在且接口齐全', () => {
  const src = fs.readFileSync(path.join(__dirname, 'cost.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  const w = sandbox.window;

  assert.strictEqual(typeof w.RagCost, 'object', 'cost.js 没挂 window.RagCost ⇒ 页面里全报 ReferenceError');
  for (const k of ['panelOf', 'buildRequest', 'memoryWarning', 'scopeNote', 'kvRows',
                   'tableOf', 'table2Of', 'truncationNotice', 'emptyReason', 'fmtMoney']) {
    assert.strictEqual(typeof w.RagCost[k], 'function', `window.RagCost.${k} 不是函数`);
  }
  assert.strictEqual(Object.keys(w.RagCost.PANELS).length, 10);
  assert.strictEqual(w.RagCost.NOT_EXPOSED.length, 2);
});
