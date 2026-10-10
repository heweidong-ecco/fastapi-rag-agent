'use strict';
/* `ops.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/ops.test.js（已进 ci.yml 的 run 块，glob）

🔴 本文件**同时是那四条路径的守卫** —— 页面走 `RagOps.buildRequest()` 拼路径，
   于是 `app/tests/test_web_pages.py`（只扫页面源码里的**字面量**）对本页**空过**
   （与 `lab.js` / `cost.js` / `tools.js` / `system.js` 同一分工）。

🔴🔴 **本文件那两条路径判据与 `system.test.js` 长得【不一样】，那是有意的** ——
   `system.js` 有 **3 条在根路径上**（`/health` `/ready` `/metrics`），所以它钉的是
   "三条不带前缀 + 一条带"；本页**四条全在 `/api/v1` 下** ⇒ 可以照 `tools.test.js` 那条
   「**全部以 `/api/v1` 开头**」写。⛔ 别把两边抄混。
*/
const test = require('node:test');
const assert = require('node:assert');

const {
  PANELS, SOURCE_LABELS, SOURCE_BADGES, SOURCE_CLASSES,
  panelOf, sourceOf, sourceBadge, sourceClassOf,
  buildRequest,
  persistenceWarning, scopeNote,
  show, fmtNum, roleText, errorPayloadOf,
  kvRows, tableOf, truncationNotice, emptyReason, isEmpty,
} = require('./ops.js');

/* ══════════════ 1 · 🔴 路径：全带前缀，且【一条都不许带形参】══════════════ */

test('🔴 四条路径**全以 `/api/v1` 开头**（本页没有 `system.js` 那种根路径）', () => {
  for (const k of Object.keys(PANELS)) {
    assert.match(PANELS[k].path, /^\/api\/v1\/debug\//,
      `${k} 的 path 是 ${PANELS[k].path} —— 这四条全在 include_router(prefix="/api/v1") 底下`);
  }
  // ⚠️ 反证：任一条少写 `/api/v1` ⇒ 那条会 404，而**页面上不会报任何错**（只是永远打不开）
  assert.strictEqual(PANELS.cache.path, '/api/v1/debug/cache_stats');
  assert.strictEqual(PANELS.count.path, '/api/v1/debug/count');
  assert.strictEqual(PANELS.quota.path, '/api/v1/debug/quota');
  assert.strictEqual(PANELS.rate.path, '/api/v1/debug/rate_limit');
});

test('🔴🔴 四条路径里**⛔ 一条都不许有 `{...}` 形参** —— 这是 `DEC-141` 的整个前提', () => {
  // 2026-10-10 之前 quota / rate_limit 是 `/debug/quota/{user_name}`。
  // `DEC-141` 敢把它们从「要管理员」降到「登录即可」，**唯一理由就是那条路径被删掉了**
  // （spec 原话：那两条「可枚举用户名」）。⇒ 形参一旦回来，越权面就回来了。
  for (const k of Object.keys(PANELS)) {
    assert.doesNotMatch(PANELS[k].path, /[{}]/,
      `${k} 的 path 里出现了形参：${PANELS[k].path} ⇒ 越权面回来了，` +
      `而这一页的 4 个面板【没有任何输入框】能填它`);
  }
  // ⚠️ 真尺子在 `app/tests/test_debug_endpoints_self_only.py`（它查的是**路由表**）；
  //    本条是**前端这一侧**的对照，防"照着旧文档把形参写回来"。
});

test('四个面板都在，且分组正确（全站口径 2 + 我自己的 2）', () => {
  assert.deepStrictEqual(Object.keys(PANELS).sort(), ['cache', 'count', 'quota', 'rate']);
  assert.deepStrictEqual(
    Object.keys(PANELS).filter((k) => PANELS[k].group === 'global').sort(),
    ['cache', 'count'],
  );
  assert.deepStrictEqual(
    Object.keys(PANELS).filter((k) => PANELS[k].group === 'mine').sort(),
    ['quota', 'rate'],
  );
});

test('`panelOf` 未知 key 必须【抛错】（响亮 > 静默 —— `DEC-051` 那族）', () => {
  assert.throws(() => panelOf('nope'), /unknown panel/);
  assert.throws(() => sourceOf('nope'), /unknown panel/);
});

/* ══════════════ 2 · 🔴 四格【一个参数都不带】══════════════ */

test('🔴 `buildRequest`：四格全是 GET、且 **query 恒为空** —— 本页没有任何输入框', () => {
  for (const k of Object.keys(PANELS)) {
    const req = buildRequest(k);
    assert.strictEqual(req.method, 'GET', `${k} 应是 GET`);
    assert.deepStrictEqual(req.query, {}, `${k} 不该带任何 query`);
    assert.strictEqual(req.body, undefined, `${k} 不该有 body`);
  }
});

test('🔴 就算硬塞一个 `user_name` 进来，也**⛔ 不许拼进 query**（服务端根本不收）', () => {
  // 这一条防的是"照旧文档给它补一个输入框"：
  // 真拼上去了 ⇒ 服务端**静默忽略**（查的仍是调用者自己）⇒ 页面看起来正常、其实那框是假的。
  const req = buildRequest('quota', { user_name: 'someone_else' });
  assert.deepStrictEqual(req.query, {}, '本页⛔ 不许把任何值拼进 query');
});

/* ══════════════ 3 · 口径徽标（两态）══════════════ */

test('🔴 两种口径各有【自己的徽标与 class】，⛔ 不许长成一个样', () => {
  const used = new Set(Object.keys(PANELS).map((k) => sourceOf(k)));
  for (const s of used) {
    assert.ok(SOURCE_LABELS[s], `口径 ${s} 没有文案`);
    assert.ok(SOURCE_BADGES[s], `口径 ${s} 没有短名`);
    assert.ok(SOURCE_CLASSES[s], `口径 ${s} 没有 class`);
  }
  assert.strictEqual(new Set(Object.values(SOURCE_CLASSES)).size,
                     Object.keys(SOURCE_CLASSES).length, '两个口径共用了同一个 class');
  assert.strictEqual(used.size, 2, `本页应恰好用到 2 种口径，实测 ${used.size} 种`);
});

test('🔴 口径必须区分【Redis】与【真库】—— 它们对"这数还在不在"的答案不同', () => {
  assert.strictEqual(sourceOf('cache'), 'redis');
  assert.strictEqual(sourceOf('rate'), 'redis');
  assert.strictEqual(sourceOf('count'), 'db');
  assert.strictEqual(sourceOf('quota'), 'db');
});

/* ══════════════ 4 · 🔴 四格的警示语：本页的立意就在这几条 ══════════════ */

test('🔴 `cache` 那格必须写明「0 ⛔ 不是坏了」—— 这是施工单点名的那一条', () => {
  const s = persistenceWarning('cache');
  assert.match(s, /0/);
  assert.match(s, /不等于|不是坏/);
});

test('🔴 `count` 那格必须写明「平台重启会清空 ⇒ 数会变小，⛔ 不是丢数据事故」', () => {
  const s = persistenceWarning('count');
  assert.match(s, /重启/);
  assert.match(s, /平台限制|不是丢数据/);
});

test('🔴 `quota` 那格必须写明「单位是 token，⛔ 不是次数」', () => {
  const s = persistenceWarning('quota');
  assert.match(s, /token/);
  assert.match(s, /不是"次数"|不是次数/);
});

test('🔴 `rate` 那格必须写明「容量与速率是【代码常量】」—— ⛔ 别让人以为它们会变', () => {
  const s = persistenceWarning('rate');
  assert.match(s, /常量/);
  assert.match(s, /实时/);
});

test('`scopeNote`：四格说清的"这数是谁的"各不相同，⛔ 不许说反', () => {
  assert.match(scopeNote('cache'), /全站口径/);
  assert.match(scopeNote('count'), /全站口径/);
  assert.match(scopeNote('quota'), /你自己/);
  assert.match(scopeNote('rate'), /你自己/);
  const all = Object.keys(PANELS).map((k) => scopeNote(k));
  assert.strictEqual(new Set(all).size, all.length, '有两格说的是同一句话 ⇒ 等于没说');
});

/* ══════════════ 5 · 取值与格式化 ══════════════ */

test('🔴 `fmtNum(null)` 回 `—`，⛔ 【绝不】回 `0` —— `Number(null) === 0`', () => {
  for (const v of [null, undefined, '']) assert.strictEqual(fmtNum(v), '—');
  assert.strictEqual(fmtNum(0), '0', '⚠️ 真的 0 要照印（这条防的是"把 0 也吞了"）');
  assert.strictEqual(fmtNum(1234567), '1,234,567');
});

test('🔴 配额是「无限」时（字符串）**原样印**，⛔ 别去 `Number()` 成 NaN', () => {
  assert.strictEqual(fmtNum('无限'), '无限');
  assert.strictEqual(fmtNum('abc'), 'abc');
});

test('`roleText`：认得出的翻中文，**认不出的原样印**（⛔ 别吞成"未知"）', () => {
  assert.strictEqual(roleText('admin'), 'admin（管理员）');
  assert.strictEqual(roleText('free'), 'free（免费档）');
  assert.strictEqual(roleText('vip99'), 'vip99', '后端真说的话不许丢');
  assert.strictEqual(roleText(null), '—');
});

test('`show`：缺值画 `—`，真的 `0` 照印', () => {
  assert.strictEqual(show(null), '—');
  assert.strictEqual(show(undefined), '—');
  assert.strictEqual(show(''), '—');
  assert.strictEqual(show(0), '0');
});

/* ══════════════ 6 · 🔴 401 / 403 那支是【另一个形状】══════════════ */

test('🔴 `errorPayloadOf`：非 2xx 回的是 `{error, code, status_code}` —— 与 200 那支键完全不同', () => {
  const e = errorPayloadOf({ error: '仅管理员可执行此操作', code: 'FORBIDDEN', status_code: 403 });
  assert.deepStrictEqual(e, { message: '仅管理员可执行此操作', code: 'FORBIDDEN', statusCode: '403' });
  // 200 那几支**没有** error 键 ⇒ 认不出来（⛔ 别把正常响应当错误）
  assert.strictEqual(errorPayloadOf({ total_documents: 12 }), null);
  assert.strictEqual(errorPayloadOf({ cached_embeddings_count: 0 }), null);
  assert.strictEqual(errorPayloadOf(null), null);
});

test('🔴 `kvRows` 遇到错误形状要**切换成那三个键**，⛔ 不改按 200 那支读', () => {
  const err = kvRows('count', { error: '请提供 API Key 或 Bearer Token', code: 'AUTH_MISSING', status_code: 401 });
  assert.deepStrictEqual(err, [
    ['后端说', '请提供 API Key 或 Bearer Token'], ['错误码', 'AUTH_MISSING'], ['HTTP', '401'],
  ]);
  assert.deepStrictEqual(kvRows('count', { total_documents: 12 }), [['库里的文档总数', '12']]);
});

/* ══════════════ 7 · 展示模型：只读端点真给的键 ══════════════ */

test('🔴 `count` / `cache`：读的是端点真回的键名（`total_documents` / `cached_embeddings_count`）', () => {
  assert.deepStrictEqual(kvRows('count', { total_documents: 42 }), [['库里的文档总数', '42']]);
  assert.deepStrictEqual(kvRows('cache', { cached_embeddings_count: 7, sample_keys: [] }),
                         [['缓存的嵌入条数', '7']]);
});

test('🔴 `quota`：五个键逐条列出，`daily_limit` 标成 token', () => {
  const rows = kvRows('quota', {
    user_name: 'alice', role: 'free', daily_limit: 100000, remaining: 60000, used_today: 40000.25,
  });
  assert.deepStrictEqual(rows, [
    ['用户', 'alice'],
    ['角色', 'free（免费档）'],
    ['每日上限（token）', '100,000'],
    ['今日已用（token）', '40,000.25'],
    ['剩余（token）', '60,000'],
  ]);
});

test('🔴 `rate`：把「代码常量」那两格**在标签上就写明**，⛔ 别混在实时值里', () => {
  const rows = kvRows('rate', {
    user_name: 'alice', remaining_tokens: 17, capacity: 30, rate: 0.5,
  });
  assert.deepStrictEqual(rows, [
    ['用户', 'alice'],
    ['桶里还剩的令牌', '17'],
    ['桶容量（代码常量）', '30'],
    ['补充速率（代码常量）', '0.5'],
  ]);
  // ⚠️ 实时的那个**不许**带"常量"字样，常量的那两个**必须**带
  assert.doesNotMatch(rows[1][0], /常量/);
  assert.match(rows[2][0], /常量/);
  assert.match(rows[3][0], /常量/);
});

test('`cache` 的样本键列表：⛔ 原样印（那是 Redis 键名，⛔ 没有脱敏）', () => {
  const t = tableOf('cache', { cached_embeddings_count: 2, sample_keys: ['emb:aaa', 'emb:bbb'] });
  assert.deepStrictEqual(t.cols, ['样本键（最多 5 个）']);
  assert.deepStrictEqual(t.rows, [['emb:aaa'], ['emb:bbb']]);
});

/* ══════════════ 7b · 🔴🔴 空态判据（**点出来的真缺陷** · 2026-10-10）══════════════
 *
 * 开工时页面用的是别页那套判据：`kv 为空 且 表格为空 ⇒ 画空态`。
 * 而本页**四格永远画得出非空 kv**（空的那支也会画一行「0」）⇒ **那个条件一次都不成立**
 * ⇒ 施工单点名要的那句「缓存统计为 0 ≠ 坏了」**根本没露出来**（页面上只有一句 `0`
 * ＋ 一张只有表头、零行的表 ⇒ 读的人看到的就是"坏了"）。
 * ⚠️ 当时 11 条页面守卫 + 29 条 JS 用例**全绿** —— 它们判的是"有没有那句话"，
 *    ⛔ 一条都不判**它有没有被画出来**（本仓原话：「用例全绿证不了页面没坏」）。
 * ⇒ 下面这两组就是"画没画出来"的判据，⛔ 不再只靠截屏。
 */

test('🔴🔴 `tableOf`：**零行时必须回 `null`** —— 只有表头的空表看着就是坏了', () => {
  assert.strictEqual(tableOf('cache', { cached_embeddings_count: 0, sample_keys: [] }), null);
  assert.strictEqual(tableOf('cache', { sample_keys: null }), null);
  assert.strictEqual(tableOf('cache', {}), null);
  // ⚠️ 有行时**照常**回表（别一刀切成 null）
  assert.strictEqual(tableOf('cache', { sample_keys: ['emb:x'] }).rows.length, 1);
});

test('🔴🔴 `isEmpty`：本页四格的"算不算空" —— 空态提示条由它说了算', () => {
  // 真的空 ⇒ true（这两种正是 demo 上最常见的：缓存没热过 / 平台重启把库清了）
  assert.strictEqual(isEmpty('cache', { cached_embeddings_count: 0, sample_keys: [] }), true);
  assert.strictEqual(isEmpty('count', { total_documents: 0 }), true);
  // 缺键也算空（形状变了 ⇒ 那格没数据）
  assert.strictEqual(isEmpty('cache', {}), true);
  assert.strictEqual(isEmpty('count', {}), true);
  assert.strictEqual(isEmpty('quota', {}), true);
  assert.strictEqual(isEmpty('rate', {}), true);
  // 有数 ⇒ false
  assert.strictEqual(isEmpty('cache', { cached_embeddings_count: 86 }), false);
  assert.strictEqual(isEmpty('count', { total_documents: 129 }), false);
  assert.strictEqual(isEmpty('quota', { remaining: 0 }), false, '剩余 0 是【有数据】，不是空');
  assert.strictEqual(isEmpty('rate', { remaining_tokens: 0 }), false);
  assert.strictEqual(isEmpty('quota', { remaining: '无限' }), false, '「无限」是字符串 ⇒ ⛔ 不算空');
});

test('🔴 `isEmpty` 对【错误形状】必须回 false —— 错是错，⛔ 别被当成"空"', () => {
  // ⚠️ 认错了会把 401 画成"这一格没有数据（先跑一次）"，把真实拒绝藏起来
  assert.strictEqual(isEmpty('count', { error: '请提供 API Key', code: 'AUTH_MISSING', status_code: 401 }), false);
  assert.strictEqual(isEmpty('cache', null), true, 'null payload 仍是空');
});

test('🔴 四格的"算空"定义**不是同一个数** —— 别照抄别页的判据', () => {
  // cache/count 数的是**条数**；quota/rate 看的是**那两格在不在**
  // （它们的 0 是**有效值**：剩余 0 令牌 = 桶空了，那是要看见的，⛔ 不是"没数据"）
  assert.strictEqual(isEmpty('quota', { user_name: 'a', remaining: 0, daily_limit: 100 }), false);
  assert.strictEqual(isEmpty('count', { total_documents: 0 }), true);
});

test('展示模型遇到**空 payload** 不抛', () => {
  for (const k of Object.keys(PANELS)) {
    assert.doesNotThrow(() => kvRows(k, {}), `${k} 的 kvRows 在空 payload 上抛了`);
    assert.doesNotThrow(() => tableOf(k, {}), `${k} 的 tableOf 在空 payload 上抛了`);
    assert.doesNotThrow(() => kvRows(k, null), `${k} 的 kvRows 在 null 上抛了`);
  }
});

/* ══════════════ 8 · 截断与空态 ══════════════ */

test('🔴 截断两种形状【分开】(`has_more` 能翻页 vs `truncated` 丢失)，⛔ 不合并成一句', () => {
  assert.match(truncationNotice({ has_more: true }), /下一页/);
  assert.match(truncationNotice({ truncated: true }), /截断/);
  assert.notStrictEqual(truncationNotice({ has_more: true }), truncationNotice({ truncated: true }));
  assert.strictEqual(truncationNotice({}), null);
});

test('🔴 emptyReason：四格的"为什么空"⛔【不是同一句话】', () => {
  const reasons = Object.keys(PANELS).map((k) => emptyReason(k));
  assert.strictEqual(new Set(reasons).size, reasons.length,
    '有两格的空态说的是同一句话 ⇒ 等于没解释（`frontend/README.md` §四 第 8 条）');
});

test('🔴 `cache` 的空态必须说「0 ⛔ 不是坏了」—— 施工单点名的那一条', () => {
  const s = emptyReason('cache');
  assert.match(s, /不是坏/);
});

/* ══════════════ 9 · 结构型守卫：**渲染出去的文字⛔ 不许带 markdown 记号** ══════════════
 *
 * 🔴 与 `tools.test.js` / `system.test.js` 那条**同一个理由**（2026-10-10 截图才发现的真缺陷）：
 *    本页所有数据都是 `textContent` 灌进去的 ⇒ 文案里的标记会**原样印出来**。
 * ⚠️ **只扫 `**`，⛔ 不扫反引号** —— 本模块的模板字面量自己就用反引号，扫它必然误报。
 * ⚠️ **要剥掉注释再扫** —— 注释里大量用 `**`（给人读的 markdown），⛔ 不是渲染出去的文字。
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function stripComments(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

test('🔴 渲染出去的文字⛔ 不许带 markdown 记号（页面一律 textContent ⇒ 会原样印星号）', () => {
  const texts = [];
  for (const k of Object.keys(PANELS)) {
    for (const v of [persistenceWarning(k), scopeNote(k), emptyReason(k)]) {
      if (typeof v === 'string') texts.push(v);
    }
  }
  texts.push(...Object.values(SOURCE_LABELS), ...Object.values(SOURCE_BADGES));
  assert.ok(texts.length >= 12, `只取到 ${texts.length} 条渲染文案 —— 取样失效了`);
  const bad = texts.filter((t) => t.includes('**'));
  assert.deepStrictEqual(bad, [], `这些文案里带了 markdown ⇒ 页面上会原样印出星号：${JSON.stringify(bad)}`);

  const files = {
    'ops.js': fs.readFileSync(path.join(__dirname, 'ops.js'), 'utf8'),
    'web/ops.html': fs.readFileSync(path.join(__dirname, '..', 'web', 'ops.html'), 'utf8'),
  };
  for (const [name, src] of Object.entries(files)) {
    const hits = stripComments(src).split('\n')
      .map((line, i) => [i + 1, line]).filter(([, line]) => line.includes('**'));
    assert.deepStrictEqual(hits, [], `${name} 里（注释之外）出现了 **：${JSON.stringify(hits)}`);
  }
});

/* ══════════════ 10 · 浏览器侧：`RagOps` 这个全局真的存在吗 ══════════════ */

test('把 ops.js 当【经典脚本】跑一遍 ⇒ window.RagOps 存在且接口齐全', () => {
  const src = fs.readFileSync(path.join(__dirname, 'ops.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  const w = sandbox.window;

  assert.strictEqual(typeof w.RagOps, 'object', 'ops.js 没挂 window.RagOps ⇒ 页面里全报 ReferenceError');
  for (const k of ['panelOf', 'sourceOf', 'sourceBadge', 'sourceClassOf',
                   'buildRequest', 'persistenceWarning', 'scopeNote',
                   'kvRows', 'tableOf', 'errorPayloadOf', 'emptyReason']) {
    assert.strictEqual(typeof w.RagOps[k], 'function', `window.RagOps.${k} 不是函数`);
  }
  assert.strictEqual(Object.keys(w.RagOps.PANELS).length, 4);
});
