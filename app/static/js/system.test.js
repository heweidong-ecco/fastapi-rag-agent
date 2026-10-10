'use strict';
/* `system.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/system.test.js（已进 ci.yml 的 run 块，glob）

🔴 本文件**同时是那四条路径的守卫** —— 页面走 `RagSystem.buildRequest()` 拼路径，
   于是 `app/tests/test_web_pages.py`（只扫页面源码里的**字面量**）对本页**空过**
   （与 `lab.js` / `cost.js` / `tools.js` / `trace.js` 同一分工）。

🔴🔴 **⚠️ 本文件那两条路径判据与 `tools.test.js` 长得【不一样】，那是有意的** ——
   本页 **3 条在根路径上**（`/health` `/ready` `/metrics`），
   ⛔ **不能照抄 `tools.test.js` 的「全部以 `/api/v1` 开头」**（照抄会把对的写成错的）。 */
const test = require('node:test');
const assert = require('node:assert');

const {
  PANELS, SOURCE_LABELS, SOURCE_BADGES, SOURCE_CLASSES,
  panelOf, sourceOf, sourceBadge, sourceClassOf, isRaw,
  buildRequest, missingRequired,
  persistenceWarning, scopeNote,
  show, fmtNum, healthText, rawPreview, dictRows, errorPayloadOf,
  kvRows, tableOf, truncationNotice, emptyReason,
} = require('./system.js');

/* ══════════════ 1 · 路径与面板数 ══════════════ */

test('🔴🔴 四条路径【哪条带 `/api/v1`、哪条不带】—— 本页最要紧的一条', () => {
  // 规格 §2.9 的 execute_code 在 /api/v1 下；§2.13 那三条【就是根路径】。
  assert.strictEqual(PANELS.exec.path, '/api/v1/agent/execute_code');
  assert.strictEqual(PANELS.health.path, '/health');
  assert.strictEqual(PANELS.ready.path, '/ready');
  assert.strictEqual(PANELS.metrics.path, '/metrics');
  // ⚠️ 反证：只要有人"顺手统一"给后三条加上 /api/v1 ⇒ 下面这条红
  for (const k of ['health', 'ready', 'metrics']) {
    assert.doesNotMatch(PANELS[k].path, /^\/api\/v1/,
      `${k} 的 path 挂在根路径上，⛔ 不该有 /api/v1 前缀（那是 include_router 的 prefix，这三条不在它下面）`);
  }
});

test('四个面板都在，且分组正确（执行器 1 + 系统 3）', () => {
  assert.deepStrictEqual(Object.keys(PANELS).sort(), ['exec', 'health', 'metrics', 'ready']);
  assert.strictEqual(panelOf('exec').group, 'exec');
  assert.deepStrictEqual(
    Object.keys(PANELS).filter((k) => PANELS[k].group === 'system').sort(),
    ['health', 'metrics', 'ready'],
  );
});

test('`panelOf` 未知 key 必须【抛错】（响亮 > 静默 —— `DEC-051` 那族）', () => {
  assert.throws(() => panelOf('nope'), /unknown panel/);
  assert.throws(() => sourceOf('nope'), /unknown panel/);
});

/* ══════════════ 2 · 🔴 `execute_code` 的参数在 query ══════════════ */

test('🔴 `execute_code`：**POST 但参数在 query**，⛔ 不是 JSON body', () => {
  // 判据来自运行中 app 的 openapi：code in=query required=True
  const req = buildRequest('exec', { code: 'print(6*7)' });
  assert.strictEqual(req.method, 'POST');
  assert.strictEqual(req.path, '/api/v1/agent/execute_code');
  assert.strictEqual(req.query.code, 'print(6*7)');
  assert.strictEqual(req.body, undefined, 'buildRequest 不许回 body：这条端点的参数在 query 上');
});

test('⛔ 空的必填项【不拼上去】—— 拼成 `?code=` 会让服务端把它当成一次真空执行', () => {
  assert.strictEqual(buildRequest('exec', { code: '' }).query.code, undefined);
});

test('🔴 那三条 GET **一个参数都不带** —— 多塞不会报错，但会让人以为它们也收参数', () => {
  for (const k of ['health', 'ready', 'metrics']) {
    assert.deepStrictEqual(buildRequest(k, { code: 'x' }).query, {}, `${k} 不该带任何 query`);
    assert.strictEqual(buildRequest(k, {}).method, 'GET');
  }
});

test('`missingRequired`：空代码要**在发请求之前**挡住（发了必 422，会被读成"后端坏了"）', () => {
  assert.match(missingRequired('exec', { code: '   ' }), /代码/);
  assert.strictEqual(missingRequired('exec', { code: 'print(1)' }), null);
  assert.strictEqual(missingRequired('metrics', {}), null, '那三条没有必填项');
});

/* ══════════════ 3 · 🔴 `/metrics` 是 text/plain，⛔ 不许 JSON.parse ══════════════ */

test('🔴 `isRaw`：**只有 metrics 那一格**是原文 —— 判据钉在面板定义上', () => {
  assert.strictEqual(isRaw('metrics'), true);
  for (const k of ['exec', 'health', 'ready']) {
    assert.strictEqual(isRaw(k), false, `${k} 回的是 JSON，⛔ 不该被当原文`);
  }
});

test('🔴 `rawPreview` 截断时必须【报出总行数】—— 否则读的人不知道少了多少', () => {
  const text = Array.from({ length: 100 }, (_, i) => `line${i}`).join('\n');
  const r = rawPreview(text, 10);
  assert.strictEqual(r.lines.length, 10);
  assert.strictEqual(r.shown, 10);
  assert.strictEqual(r.total, 100);
  assert.strictEqual(r.truncated, true);
  // 短的 ⇒ 不截断
  const s = rawPreview('a\nb', 10);
  assert.deepStrictEqual([s.total, s.truncated], [2, false]);
  // ⛔ 空输入不抛
  assert.deepStrictEqual(rawPreview('', 10), { lines: [], shown: 0, total: 0, truncated: false });
  assert.deepStrictEqual(rawPreview(null, 10).total, 0);
});

/* ══════════════ 4 · 503 那支是【另一个形状】══════════════ */

test('🔴 `errorPayloadOf`：非 2xx 回的是 `{error, code, status_code}` —— 与 200 那支键完全不同', () => {
  const e = errorPayloadOf({ error: '服务尚未就绪，请稍后重试', code: 'SERVICE_UNAVAILABLE', status_code: 503 });
  assert.deepStrictEqual(e, { message: '服务尚未就绪，请稍后重试', code: 'SERVICE_UNAVAILABLE', statusCode: '503' });
  // 200 那两支**没有** error 键 ⇒ 认不出来（⛔ 别把正常响应当错误）
  assert.strictEqual(errorPayloadOf({ status: 'healthy', checks: {} }), null);
  assert.strictEqual(errorPayloadOf({ status: 'ready' }), null);
  assert.strictEqual(errorPayloadOf(null), null);
});

test('🔴 `kvRows` 遇到错误形状要**切换成那三个键**，⛔ 不改按 200 那支读', () => {
  const err = kvRows('health', { error: '服务尚未就绪，请稍后重试', code: 'X', status_code: 503 });
  assert.deepStrictEqual(err, [['后端说', '服务尚未就绪，请稍后重试'], ['错误码', 'X'], ['HTTP', '503']]);
  // 正常那支
  assert.deepStrictEqual(kvRows('health', { status: 'healthy', checks: {} }), [['总体', '正常']]);
});

/* ══════════════ 5 · 口径徽标 ══════════════ */

test('🔴 两种口径各有【自己的徽标与 class】，⛔ 不许长成一个样', () => {
  const used = new Set(Object.keys(PANELS).map((k) => sourceOf(k)));
  for (const s of used) {
    assert.ok(SOURCE_LABELS[s], `口径 ${s} 没有文案`);
    assert.ok(SOURCE_BADGES[s], `口径 ${s} 没有短名`);
    assert.ok(SOURCE_CLASSES[s], `口径 ${s} 没有 class`);
  }
  assert.strictEqual(new Set(Object.values(SOURCE_CLASSES)).size,
                     Object.keys(SOURCE_CLASSES).length, '两个口径共用了同一个 class');
  assert.ok(used.size >= 2, `本页只用到 ${used.size} 种口径，核对一下 PANELS`);
});

test('🔴 `metrics` 那一格必须挂「进程内存 · 重启归零」—— 指标注册表就在进程里', () => {
  assert.strictEqual(sourceClassOf('metrics'), 'src-mem');
  const s = persistenceWarning('metrics');
  assert.match(s, /进程/);
  assert.match(s, /重启/);
  assert.match(s, /归零/);
});

test('🔴 `ready` 那一格必须写明「刚启动 10 秒内必然 503，那是设计」', () => {
  const s = persistenceWarning('ready');
  assert.match(s, /10 秒/);
  assert.match(s, /503/);
  assert.match(s, /不是坏了|不是坏/);
});

test('🔴 `health` 那一格必须写明「不检查 embedding API」—— 否则全绿会被读成"全都好"', () => {
  const s = persistenceWarning('health');
  assert.match(s, /embedding/);
  assert.match(s, /不检查/);
});

test('🔴 `exec` 那一格必须写明「跑在无网硬化容器里」+ 有上限（业务方点的那条）', () => {
  const s = persistenceWarning('exec');
  assert.match(s, /无网/);
  assert.match(s, /容器/);
  assert.match(s, /上限/);
});

test('`scopeNote`：四格说清的"这数是谁的"各不相同，⛔ 不许说反', () => {
  assert.match(scopeNote('exec'), /你自己/);
  assert.match(scopeNote('metrics'), /全站口径/);
  assert.match(scopeNote('health'), /系统自身/);
  const all = Object.keys(PANELS).map((k) => scopeNote(k));
  assert.strictEqual(new Set(all).size, all.length, '有两格说的是同一句话 ⇒ 等于没说');
});

/* ══════════════ 6 · 取值与格式化 ══════════════ */

test('🔴 `fmtNum(null)` 回 `—`，⛔ 【绝不】回 `0` —— `Number(null) === 0`', () => {
  for (const v of [null, undefined, '']) assert.strictEqual(fmtNum(v), '—');
  assert.strictEqual(fmtNum(0), '0', '⚠️ 真的 0 要照印（这条防的是"把 0 也吞了"）');
  assert.strictEqual(fmtNum(1234567), '1,234,567');
});

test('`healthText`：认得出的翻中文，**认不出的原样印**（⛔ 别吞成"未知"）', () => {
  assert.strictEqual(healthText('healthy'), '正常');
  assert.strictEqual(healthText('unhealthy'), '不健康');
  assert.strictEqual(healthText('ready'), '就绪');
  assert.strictEqual(healthText('degraded'), 'degraded', '后端真说的话不许丢');
  assert.strictEqual(healthText(null), '—');
});

test('`dictRows`：不是那个形状就当空，⛔ 不抛、也⛔ 不把数组当对象', () => {
  assert.deepStrictEqual(dictRows({ a: 1 }), [['a', 1]]);
  assert.deepStrictEqual(dictRows([1, 2]), []);
  assert.deepStrictEqual(dictRows(null), []);
});

/* ══════════════ 7 · 展示模型 ══════════════ */

test('`health`：`checks` **逐项列出来**，⛔ 别只画一个"总体"（那会把哪一项挂了藏起来）', () => {
  const payload = { status: 'unhealthy', checks: { database: 'ok', redis: 'error: refuse', embedding_api: 'deferred to external monitoring' } };
  const t = tableOf('health', payload);
  assert.deepStrictEqual(t.cols, ['依赖', '结果']);
  assert.deepStrictEqual(t.rows, [
    ['database', 'ok'], ['redis', 'error: refuse'], ['embedding_api', 'deferred to external monitoring'],
  ]);
  assert.deepStrictEqual(kvRows('health', payload), [['总体', '不健康']]);
});

test('`ready` / `exec`：只读端点真给的键', () => {
  assert.deepStrictEqual(kvRows('ready', { status: 'ready' }), [['状态', '就绪']]);
  assert.deepStrictEqual(kvRows('exec', { code: 'print(1)', result: '1' }),
                         [['你发出去的代码', 'print(1)'], ['执行结果', '1']]);
  assert.deepStrictEqual(kvRows('metrics', {}), [], '那一格是原文，⛔ 不做 kv');
});

test('✅ 执行出错的 `result` 也**照印**（后端把报错当字符串回，⛔ 不许吞掉）', () => {
  const r = kvRows('exec', { code: 'open("/etc/passwd")', result: '执行错误: __import__ not found' });
  assert.match(r[1][1], /执行错误/);
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

test('`exec` 的空态必须说「形状变了，先核后端」—— ⛔ 不是"你没写代码"', () => {
  const s = emptyReason('exec');
  assert.match(s, /核后端/);
});

/* ══════════════ 9 · 结构型守卫：**渲染出去的文字⛔ 不许带 markdown 记号** ══════════════
 *
 * 🔴 与 `tools.test.js` 那条**同一个理由**（2026-10-10 截图才发现的真缺陷）：
 *    本页所有数据都是 `textContent` 灌进去的 ⇒ 文案里的 `**强调**` 会**原样印成星号**。
 *    ⚠️ 而当时用例全绿 —— 它们判的是"有没有这句话"，**一条都不判它长什么样**。
 *    📌 **本文件自己写的时候就又犯了一次**（`system.js` 首稿 11 处）—— 所以这条不是形式。
 * ⚠️ **只扫 `**`，⛔ 不扫反引号** —— 本模块的模板字面量自己就用反引号，扫它必然误报。
 * ⚠️ **要剥掉注释再扫** —— 注释里大量用 `**`（给人读的 markdown），⛔ 不是渲染出去的文字。
 */
function stripComments(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

test('🔴 渲染出去的文字⛔ 不许带 markdown 记号（页面一律 textContent ⇒ 会原样印星号）', () => {
  const texts = [];
  for (const k of Object.keys(PANELS)) {
    for (const v of [persistenceWarning(k), scopeNote(k), emptyReason(k),
                     missingRequired(k, {}), missingRequired(k, { code: '  ' })]) {
      if (typeof v === 'string') texts.push(v);
    }
  }
  texts.push(...Object.values(SOURCE_LABELS), ...Object.values(SOURCE_BADGES));
  assert.ok(texts.length >= 16, `只取到 ${texts.length} 条渲染文案 —— 取样失效了`);
  const bad = texts.filter((t) => t.includes('**'));
  assert.deepStrictEqual(bad, [], `这些文案里带了 markdown 的 ** ⇒ 页面上会原样印出星号：${JSON.stringify(bad)}`);

  const files = {
    'system.js': fs.readFileSync(path.join(__dirname, 'system.js'), 'utf8'),
    'web/system.html': fs.readFileSync(path.join(__dirname, '..', 'web', 'system.html'), 'utf8'),
  };
  for (const [name, src] of Object.entries(files)) {
    const hits = stripComments(src).split('\n')
      .map((line, i) => [i + 1, line]).filter(([, line]) => line.includes('**'));
    assert.deepStrictEqual(hits, [], `${name} 里（注释之外）出现了 **：${JSON.stringify(hits)}`);
  }
});

/* ══════════════ 10 · 浏览器侧：`RagSystem` 这个全局真的存在吗 ══════════════ */

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('把 system.js 当【经典脚本】跑一遍 ⇒ window.RagSystem 存在且接口齐全', () => {
  const src = fs.readFileSync(path.join(__dirname, 'system.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  const w = sandbox.window;

  assert.strictEqual(typeof w.RagSystem, 'object', 'system.js 没挂 window.RagSystem ⇒ 页面里全报 ReferenceError');
  for (const k of ['panelOf', 'sourceOf', 'sourceBadge', 'sourceClassOf', 'isRaw',
                   'buildRequest', 'missingRequired', 'persistenceWarning', 'scopeNote',
                   'kvRows', 'tableOf', 'rawPreview', 'errorPayloadOf', 'emptyReason']) {
    assert.strictEqual(typeof w.RagSystem[k], 'function', `window.RagSystem.${k} 不是函数`);
  }
  assert.strictEqual(Object.keys(w.RagSystem.PANELS).length, 4);
});
