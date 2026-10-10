'use strict';
/* `tools.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/tools.test.js（已进 ci.yml 的 run 块，glob）

🔴 本文件**同时是那七条路径 `/api/v1` 前缀的守卫** —— 页面走 `RagTools.buildRequest()` 拼路径，
   于是 `app/tests/test_web_pages.py`（只扫页面源码里的**字面量**）对本页**空过**
   （与 `lab.js` / `cost.js` / `trace.js` 同一分工）。 */
const test = require('node:test');
const assert = require('node:assert');

const {
  PANELS, SOURCE_LABELS, SOURCE_BADGES, SOURCE_CLASSES, DEFAULT_MEMORY_SPACE,
  panelOf, sourceOf, sourceBadge, sourceClassOf,
  buildRequest, missingRequired,
  persistenceWarning, scopeNote,
  show, fmtNum, fmtEpoch, healthText, dictRows, rowsOf, schemaParams,
  kvRows, tableOf, table2Of, table3Of,
  truncationNotice, emptyReason,
} = require('./tools.js');

/* ══════════════ 1 · 路径与面板数 ══════════════ */

test('🔴 七个面板的 path【全部带 `/api/v1`】—— 少前缀页面就 100% 404（`DEC-094`）', () => {
  const keys = Object.keys(PANELS);
  assert.strictEqual(keys.length, 7, `规格 §2.7(5) + §2.8(2) = 7，实际 ${keys.length}`);
  for (const k of keys) {
    assert.match(PANELS[k].path, /^\/api\/v1\//, `${k} 的 path 没带 /api/v1：${PANELS[k].path}`);
  }
});

test('七个 key 与页面上的 `data-tools` 逐个对得上（名字写错 ⇒ 面板静默不跑）', () => {
  assert.deepStrictEqual(
    Object.keys(PANELS).sort(),
    ['available', 'health', 'mcp', 'memadd', 'memsearch', 'refresh', 'versions'],
  );
});

test('🔴 工具那 5 格 + 记忆那 2 格，分组不许串（`scopeNote` 靠它说"这数是谁的"）', () => {
  const tools = Object.keys(PANELS).filter((k) => PANELS[k].group === 'tools').sort();
  const mem = Object.keys(PANELS).filter((k) => PANELS[k].group === 'memory').sort();
  assert.deepStrictEqual(tools, ['available', 'health', 'mcp', 'refresh', 'versions']);
  assert.deepStrictEqual(mem, ['memadd', 'memsearch']);
});

test('`panelOf` 未知 key 必须【抛错】（响亮 > 静默 —— `DEC-051` 那族）', () => {
  assert.throws(() => panelOf('nope'), /unknown panel/);
  assert.throws(() => sourceOf('nope'), /unknown panel/);
});

/* ══════════════ 2 · 🔴 本页最容易写错的一处：记忆接口的参数在 query ══════════════ */

test('🔴 `memory/add`：**POST 但参数在 query**，⛔ 不是 JSON body', () => {
  // 判据来自运行中 app 的 openapi：content in=query required=True · memory_space in=query default='default'
  const req = buildRequest('memadd', { content: '我喜欢喝美式', memory_space: 'demo' });
  assert.strictEqual(req.method, 'POST');
  assert.strictEqual(req.path, '/api/v1/agent/memory/add');
  assert.strictEqual(req.query.content, '我喜欢喝美式');
  assert.strictEqual(req.query.memory_space, 'demo');
  // ⛔ 返回里根本没有 body 这个键 —— 有就说明有人又去发 JSON 了
  assert.strictEqual(req.body, undefined, 'buildRequest 不许回 body：这两条端点的参数在 query 上');
});

test('🔴 `memory/search`：同样在 query；`query` 是那个**参数名**（不是"查询串"那个意思）', () => {
  const req = buildRequest('memsearch', { query: '咖啡', memory_space: 'demo' });
  assert.strictEqual(req.method, 'GET');
  assert.strictEqual(req.path, '/api/v1/agent/memory/search');
  assert.strictEqual(req.query.query, '咖啡');
});

test('记忆空间不填 ⇒ 兜底 `default`，且与服务端默认值【逐字一致】', () => {
  assert.strictEqual(DEFAULT_MEMORY_SPACE, 'default');
  assert.strictEqual(buildRequest('memadd', { content: 'x' }).query.memory_space, 'default');
  assert.strictEqual(buildRequest('memsearch', { query: 'x' }).query.memory_space, 'default');
});

test('⛔ 空的必填项【不拼上去】—— 拼成 `?content=` 会让服务端把它当成一次真空写入', () => {
  const req = buildRequest('memadd', { content: '', memory_space: 'default' });
  assert.strictEqual(req.query.content, undefined);
});

test('🔴 工具那 5 格【一个参数都不带】—— 多塞不会报错，但会让人以为它们也收参数', () => {
  for (const k of ['available', 'health', 'refresh', 'versions', 'mcp']) {
    const req = buildRequest(k, { content: 'x', query: 'y', days: 3 });
    assert.deepStrictEqual(req.query, {}, `${k} 不该带任何 query 参数，实际 ${JSON.stringify(req.query)}`);
  }
});

test('`missingRequired`：空必填项要**在发请求之前**挡住（发了必 422，会被读成"后端坏了"）', () => {
  assert.match(missingRequired('memadd', { content: '' }), /内容/);
  assert.match(missingRequired('memsearch', { query: '   ' }), /关键词/);
  assert.strictEqual(missingRequired('memadd', { content: '有' }), null);
  assert.strictEqual(missingRequired('memsearch', { query: '有' }), null);
  assert.strictEqual(missingRequired('health', {}), null, '工具那几格没有必填项');
});

/* ══════════════ 3 · 口径徽标（本页最要紧的一半）══════════════ */

test('🔴 五种口径各有【自己的徽标与 class】，⛔ 不许长成一个样', () => {
  const used = new Set(Object.keys(PANELS).map((k) => sourceOf(k)));
  for (const s of used) {
    assert.ok(SOURCE_LABELS[s], `口径 ${s} 没有文案`);
    assert.ok(SOURCE_BADGES[s], `口径 ${s} 没有短名`);
    assert.ok(SOURCE_CLASSES[s], `口径 ${s} 没有 class`);
  }
  assert.strictEqual(new Set(Object.values(SOURCE_CLASSES)).size,
                     Object.keys(SOURCE_CLASSES).length, '两个口径共用了同一个 class');
  // 本页真的用到了这几种 —— 空集合断言会一路绿着放行
  assert.ok(used.size >= 4, `本页只用到 ${used.size} 种口径，核对一下 PANELS`);
});

test('🔴 「进程内存」那几格必须挂警示条并点名"重启归零"', () => {
  const s = persistenceWarning('health');
  assert.match(s, /内存/);
  assert.match(s, /重启/);
  assert.match(s, /归零/);
  assert.match(persistenceWarning('refresh'), /重启/);
});

test('🔴 `const`（代码常量）⛔【不挂】警示条 —— 挂了就是狼来了', () => {
  assert.strictEqual(persistenceWarning('versions'), null);
  assert.strictEqual(sourceClassOf('versions'), 'src-const');
});

test('🔴 `mixed` 那条必须把"表还在、状态没了"说清楚（否则会读成整格都归零）', () => {
  const s = persistenceWarning('available');
  assert.match(s, /常量/);
  assert.match(s, /内存/);
  assert.match(s, /重启/);
});

test('🔴 `disk`（Mem0）必须写明"平台重启**同样**会丢" —— 别让人以为落盘就安全了', () => {
  const s = persistenceWarning('memadd');
  assert.match(s, /重启/);
  assert.match(s, /丢/);
  assert.strictEqual(persistenceWarning('memadd'), persistenceWarning('memsearch'));
});

test('🔴 `live`（真调 MCP）必须写明「不是缓存」+「慢/可能因环境起不来」', () => {
  const s = persistenceWarning('mcp');
  assert.match(s, /不是读缓存/, '要写明它不是读缓存 —— 否则读的人会以为这格也是"上次体检留下的"');
  assert.match(s, /慢/);
  assert.match(s, /环境/);
});

test('`scopeNote`：工具那几格是**系统能力**、记忆那两格是**你自己的**，⛔ 不许说反', () => {
  const t = scopeNote('health');
  assert.match(t, /系统能力/);
  assert.match(t, /不是/);
  assert.match(t, /你的数/, '工具那几格必须把"这不是某个人的数"说出口');
  const m = scopeNote('memadd');
  assert.match(m, /你自己/);
  assert.match(m, /看不到别人/);
});

/* ══════════════ 4 · 格式化（两个能静默出错的坑）══════════════ */

test('🔴 `fmtNum(null)` 回 `—`，⛔ 【绝不】回 `0` —— `Number(null) === 0`', () => {
  for (const v of [null, undefined, '']) {
    assert.strictEqual(fmtNum(v), '—', `fmtNum(${JSON.stringify(v)}) 不许编 0`);
  }
  assert.strictEqual(fmtNum(0), '0', '⚠️ 真的 0 要照印（这条防的是"把 0 也吞了"）');
  assert.strictEqual(fmtNum(1234567), '1,234,567');
});

test('🔴 `fmtEpoch` 必须 ×1000 —— 忘了就显示 1970，而**不报任何错**', () => {
  const s = fmtEpoch(1700000000);
  assert.match(s, /^2023-/, `epoch 秒没换算成毫秒 ⇒ 得到 ${s}`);
  assert.doesNotMatch(s, /1970/);
});

test('`fmtEpoch` 缺值一律 `—`，⛔ 不编时间', () => {
  for (const v of [null, undefined, '']) assert.strictEqual(fmtEpoch(v), '—');
});

test('`healthText`：认得出的翻中文，**认不出的原样印**（⛔ 别吞成"未知"）', () => {
  assert.strictEqual(healthText('healthy'), '正常');
  assert.strictEqual(healthText('unhealthy'), '不健康');
  assert.strictEqual(healthText('degraded'), 'degraded', '后端真说的话不许丢');
  assert.strictEqual(healthText(null), '—');
});

test('`schemaParams`：认得出就列参数名，认不出回空串，⛔ 不抛', () => {
  assert.strictEqual(schemaParams({ properties: { a: {}, b: {} } }), 'a, b');
  assert.strictEqual(schemaParams({}), '');
  assert.strictEqual(schemaParams(null), '');
  assert.strictEqual(schemaParams('nope'), '');
});

test('`dictRows` / `rowsOf`：不是那个形状就当空，⛔ 不抛、也⛔ 不把数组当对象', () => {
  assert.deepStrictEqual(dictRows({ a: 1 }), [['a', 1]]);
  assert.deepStrictEqual(dictRows([1, 2]), []);
  assert.deepStrictEqual(dictRows(null), []);
  assert.deepStrictEqual(rowsOf({ xs: [1] }, 'xs'), [1]);
  assert.deepStrictEqual(rowsOf({ xs: 1 }, 'xs'), []);
});

/* ══════════════ 5 · 展示模型：只读**真存在**的键 ══════════════ */

test('`available`：三个计数 + 一张可用表 + **不健康单独一张表**（坏消息不混进好消息）', () => {
  const payload = {
    healthy_tools: [{ name: 'calculator', description: '算数', version: '1.0' }],
    unhealthy_tools: ['web_search'],
    total: 2,
  };
  assert.deepStrictEqual(kvRows('available', payload), [
    ['可用（含未体检过的）', '1'], ['不健康（已被剔除）', '1'], ['合计', '2'],
  ]);
  const t1 = tableOf('available', payload);
  assert.deepStrictEqual(t1.cols, ['工具', '版本', '说明']);
  assert.deepStrictEqual(t1.rows, [['calculator', '1.0', '算数']]);
  const t2 = table2Of('available', payload);
  assert.deepStrictEqual(t2.rows, [['web_search']]);
  // ⛔ 别的面板没有第二张表
  assert.strictEqual(table2Of('health', payload), null);
});

test('`health`：`tools` 是**字典**（工具名 → 状态/上次体检），⛔ 不是数组', () => {
  const payload = { tools: { calculator: { status: 'healthy', last_checked: 1700000000 } } };
  const t = tableOf('health', payload);
  assert.deepStrictEqual(t.cols, ['工具', '状态', '上次体检']);
  assert.strictEqual(t.rows[0][0], 'calculator');
  assert.strictEqual(t.rows[0][1], '正常');
  assert.match(t.rows[0][2], /^2023-/);
  assert.deepStrictEqual(kvRows('health', payload), [['体检表里的工具条数', '1']]);
  // refresh 与 health 同形（同一个 `_tool_health`）
  assert.deepStrictEqual(tableOf('refresh', payload), t);
});

test('`versions`：`tool_versions` 是字典', () => {
  const t = tableOf('versions', { tool_versions: { stats: '1.0', mcp: '2.0' } });
  assert.deepStrictEqual(t.cols, ['工具', '版本']);
  assert.deepStrictEqual(t.rows, [['stats', '1.0'], ['mcp', '2.0']]);
});

test('`mcp`：读 `tools[].inputSchema`（⚠️ 契约键名是驼峰，⛔ 不是 `input_schema`）', () => {
  const payload = { tools: [{ name: 'stats', description: '统计', inputSchema: { properties: { xs: {} } } }], total: 1 };
  const t = tableOf('mcp', payload);
  assert.deepStrictEqual(t.cols, ['工具（MCP 上的名字）', '参数', '说明']);
  assert.deepStrictEqual(t.rows, [['stats', 'xs', '统计']]);
  assert.deepStrictEqual(kvRows('mcp', payload), [['MCP 报上来的工具条数', '1']]);
});

test('`memadd` / `memsearch`：读的是端点真给的键', () => {
  const a = kvRows('memadd', { status: 'added', content: '我喜欢喝美式', memory_space: 'demo' });
  assert.deepStrictEqual(a, [['结果', 'added'], ['写进了哪个记忆空间', 'demo'], ['写进去的内容', '我喜欢喝美式']]);
  const s = kvRows('memsearch', { query: '咖啡', memories: ['a', 'b'], memory_space: 'demo' });
  assert.deepStrictEqual(s, [['检索词', '咖啡'], ['记忆空间', 'demo'], ['命中条数', '2']]);
  assert.deepStrictEqual(table3Of('memsearch', { memories: ['a', 'b'] }).rows, [['a'], ['b']]);
  assert.strictEqual(table3Of('memadd', {}), null);
});

test('展示模型遇到**空 payload** 不抛，回一排 `—` 或空表', () => {
  for (const k of Object.keys(PANELS)) {
    assert.doesNotThrow(() => kvRows(k, {}), `${k} 的 kvRows 在空 payload 上抛了`);
    assert.doesNotThrow(() => tableOf(k, {}), `${k} 的 tableOf 在空 payload 上抛了`);
    assert.strictEqual(kvRows(k, null).length >= 0, true);
  }
});

/* ══════════════ 6 · 截断与空态 ══════════════ */

test('🔴 截断两种形状【分开】(`has_more` 能翻页 vs `truncated` 丢失)，⛔ 不合并成一句', () => {
  assert.match(truncationNotice({ has_more: true }), /下一页/);
  assert.match(truncationNotice({ truncated: true }), /截断/);
  assert.notStrictEqual(truncationNotice({ has_more: true }), truncationNotice({ truncated: true }));
  assert.strictEqual(truncationNotice({}), null);
});

test('🔴 emptyReason：内存口径那格必须点名"重启归零 + 只有登记过的工具才进体检表"', () => {
  const s = emptyReason('health');
  assert.match(s, /内存/);
  assert.match(s, /TEST_ARGS_MAP/);
  assert.match(s, /不等于/);
});

test('🔴 emptyReason：七格的"为什么空"⛔【不是同一句话】', () => {
  const reasons = Object.keys(PANELS).map((k) => emptyReason(k));
  assert.strictEqual(new Set(reasons).size, reasons.length,
    '有两格的空态说的是同一句话 ⇒ 等于没解释（`frontend/README.md` §四 第 8 条）');
});

test('`mcp` 的空态必须说是【环境】问题，⛔ 不是"工具没了"', () => {
  const s = emptyReason('mcp');
  assert.match(s, /环境/);
  assert.doesNotMatch(s, /工具都没了/);
});

/* ══════════════ 7 · 结构型守卫：**渲染出去的文字⛔ 不许带 markdown 记号** ══════════════
 *
 * 🔴 为什么必须有这条（**2026-10-10 截图才发现的真缺陷**）：
 *    本页所有数据都是 `textContent` 灌进去的（⛔ 不用 innerHTML）⇒ 文案里的
 *    `**强调**` 会**原样印成星号**、`` `代码` `` 会**原样印成反引号**。
 *    ⚠️ 而**当时 34 条用例全绿** —— 它们判的是"有没有这句话 / 是不是这句话"，
 *    **一条都不判它长什么样**。本仓原话：「**用例全绿证不了页面没坏**」（`frontend/README.md` §十一）。
 *    ⇒ 所以补这条**结构**判据：**凡是会被渲染出去的字符串，⛔ 不许出现 `**`**。
 *
 * ⚠️ **只扫 `**`，⛔ 不扫反引号** —— 本模块的**模板字面量**本身就用反引号（`` `unknown panel: ${key}` ``），
 *    扫它必然误报。而 `**` 在本仓的 JS 里**没有任何合法用途**（不做幂运算）⇒ 它是干净的针脚。
 * ⚠️ **要剥掉注释再扫** —— 注释里大量用 `**`（那是给人读的 markdown），⛔ 不是渲染出去的文字。
 */
function stripComments(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')          // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, '')         // 块注释（含 <style> 里的 CSS）
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');    // 行注释（⚠️ 避开 `https://` 那种）
}

test('🔴 渲染出去的文字⛔ 不许带 markdown 记号（页面一律 textContent ⇒ 会原样印星号）', () => {
  // ① 行为面：把模块**能渲染出去的**字符串全部取出来验一遍（这条不依赖扫描，最结实）
  const texts = [];
  for (const k of Object.keys(PANELS)) {
    for (const v of [persistenceWarning(k), scopeNote(k), emptyReason(k),
                     missingRequired(k, {}), missingRequired(k, { content: '', query: '' })]) {
      if (typeof v === 'string') texts.push(v);
    }
  }
  texts.push(...Object.values(SOURCE_LABELS), ...Object.values(SOURCE_BADGES));
  assert.ok(texts.length >= 30, `只取到 ${texts.length} 条渲染文案 —— 取样失效了`);
  const bad = texts.filter((t) => t.includes('**'));
  assert.deepStrictEqual(bad, [], `这些文案里带了 markdown 的 ** ⇒ 页面上会原样印出星号：${JSON.stringify(bad)}`);

  // ② 源码面：本模块与页面里，**注释之外**也不许出现 `**`
  const files = {
    'tools.js': fs.readFileSync(path.join(__dirname, 'tools.js'), 'utf8'),
    'web/tools.html': fs.readFileSync(path.join(__dirname, '..', 'web', 'tools.html'), 'utf8'),
  };
  for (const [name, src] of Object.entries(files)) {
    const hits = stripComments(src).split('\n')
      .map((line, i) => [i + 1, line]).filter(([, line]) => line.includes('**'));
    assert.deepStrictEqual(hits, [], `${name} 里（注释之外）出现了 **：${JSON.stringify(hits)}`);
  }
});

/* ══════════════ 8 · 浏览器侧：`RagTools` 这个全局真的存在吗 ══════════════ */

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('把 tools.js 当【经典脚本】跑一遍 ⇒ window.RagTools 存在且接口齐全', () => {
  const src = fs.readFileSync(path.join(__dirname, 'tools.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  const w = sandbox.window;

  assert.strictEqual(typeof w.RagTools, 'object', 'tools.js 没挂 window.RagTools ⇒ 页面里全报 ReferenceError');
  for (const k of ['panelOf', 'sourceOf', 'sourceBadge', 'sourceClassOf', 'buildRequest',
                   'missingRequired', 'persistenceWarning', 'scopeNote', 'kvRows', 'tableOf',
                   'table2Of', 'table3Of', 'truncationNotice', 'emptyReason', 'fmtEpoch']) {
    assert.strictEqual(typeof w.RagTools[k], 'function', `window.RagTools.${k} 不是函数`);
  }
  assert.strictEqual(Object.keys(w.RagTools.PANELS).length, 7);
});
