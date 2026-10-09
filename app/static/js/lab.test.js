'use strict';
/* `lab.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/lab.test.js（已接进 ci.yml 的 run 块，glob）

🔴 本文件**同时是那五个 `/api/v1` 前缀的守卫** —— 页面走 `RagLab.buildRequest()` 拼路径，
   于是 `app/tests/test_web_pages.py`（它只扫页面源码里的**字面量**）对本页**空过**。
   ⇒ 前缀的尺子只能在这里（与 `trace.js` 的 `buildPath` 同一分工）。 */
const test = require('node:test');
const assert = require('node:assert');

const {
  PANELS, PIPELINE_MODES, panelOf, clampTopK, buildRequest,
  docsOf, rowOf, rowsOf, timingRows, stageRows, answerOf,
  envLimitHint, emptyReason,
} = require('./lab.js');

/* ══════════════ 1 · 五条路径带不带 `/api/v1`（`DEC-094` 那个事故）══════════════ */

test('🔴 五个面板的 path【全部带 `/api/v1`】—— 少前缀页面就 100% 404', () => {
  // 反证：把任一个 path 的 `/api/v1` 去掉 ⇒ 本条立刻红。
  const keys = Object.keys(PANELS);
  assert.strictEqual(keys.length, 5, `应有 5 个面板（规格 §2.2），实际 ${keys.length}`);
  for (const k of keys) {
    assert.match(PANELS[k].path, /^\/api\/v1\//, `${k} 的 path 没带 /api/v1：${PANELS[k].path}`);
  }
});

test('🔴 五个面板的「分数字段名」各不相同的那三条必须钉对（⛔ 猜错不报错，只画一列空）', () => {
  assert.strictEqual(panelOf('pg').score, 'similarity');
  assert.strictEqual(panelOf('rerank').score, 'rerank_score');
  assert.strictEqual(panelOf('hybrid').score, 'rrf_score');
  assert.strictEqual(panelOf('rewrite').score, 'rrf_score');   // rewrite 也走 RRF 融合
  assert.strictEqual(panelOf('pipeline').score, 'rrf_score');
});

test('🔴 panelOf：未登记的 key 必须【抛错】，⛔ 不许静默回落', () => {
  // 静默回落 = 页面上少一个面板，而**没有任何东西会红**（本仓「响亮 > 静默」那族 · `DEC-051`）。
  assert.throws(() => panelOf('nope'), /unknown panel/);
});

/* ══════════════ 2 · 请求形状 ══════════════ */

test('buildRequest：只回 `{path, body, query}`，且 body 带 question/top_k', () => {
  const r = buildRequest('pg', { question: '净利润是多少', top_k: 5 });
  assert.strictEqual(r.path, '/api/v1/rag/pg_search');
  assert.deepStrictEqual(r.body, { question: '净利润是多少', top_k: 5 });
});

test('🔴 buildRequest：**只有** rewrite 与 pipeline 带 thread_id —— ⛔ 别给五条都塞', () => {
  // 另三条端点签名里**没有** thread_id 形参。塞进去 FastAPI 会忽略（不报错），
  // 但那会让读的人以为"这三条也按会话计费" ⇒ **撒谎**。
  const vals = { question: 'x', top_k: 3, thread_id: 'abc' };
  assert.deepStrictEqual(buildRequest('pg', vals).query, {});
  assert.deepStrictEqual(buildRequest('hybrid', vals).query, {});
  assert.deepStrictEqual(buildRequest('rerank', vals).query, {});
  assert.deepStrictEqual(buildRequest('rewrite', vals).query, { thread_id: 'abc' });
  assert.deepStrictEqual(buildRequest('pipeline', vals).query, { thread_id: 'abc' });
});

test('buildRequest：thread_id 缺省回落 "default"（端点声明就是 Query("default", min_length=1)）', () => {
  assert.deepStrictEqual(buildRequest('rewrite', { question: 'x' }).query, { thread_id: 'default' });
  assert.deepStrictEqual(buildRequest('rewrite', { question: 'x', thread_id: '' }).query, { thread_id: 'default' });
});

test('🔴 buildRequest：mode 只属于 pipeline，且是四个枚举之一（⛔ 非法值回落默认）', () => {
  assert.strictEqual(buildRequest('pg', { question: 'x', mode: 'fast' }).body.mode, undefined);
  assert.deepStrictEqual(PIPELINE_MODES, ['fast', 'accurate', 'accurate_norerank', 'full']);
  for (const m of PIPELINE_MODES) {
    assert.strictEqual(buildRequest('pipeline', { question: 'x', mode: m }).body.mode, m);
  }
  assert.strictEqual(buildRequest('pipeline', { question: 'x', mode: 'fst' }).body.mode, 'accurate_norerank');
  assert.strictEqual(buildRequest('pipeline', { question: 'x' }).body.mode, 'accurate_norerank');
});

test('🔴 buildRequest：generate_answer / citations 只在【真勾了】的时候才带 —— ⛔ 不默认开（它真花钱）', () => {
  assert.strictEqual(buildRequest('pipeline', { question: 'x' }).body.generate_answer, undefined);
  assert.strictEqual(buildRequest('pipeline', { question: 'x' }).body.citations, undefined);

  const on = buildRequest('pipeline', { question: 'x', generate_answer: true, citations: true }).body;
  assert.strictEqual(on.generate_answer, true);
  assert.strictEqual(on.citations, true);

  // ⚠️ 没勾"生成答案"却勾了"引用" ⇒ **不带 citations**（后端那条引用分支只在 generate_answer 为真时走）。
  const orphan = buildRequest('pipeline', { question: 'x', generate_answer: false, citations: true }).body;
  assert.strictEqual(orphan.generate_answer, undefined);
  assert.strictEqual(orphan.citations, undefined);
});

test('🔴 clampTopK：夹进 1..20（端点声明 ge=1, le=20）；非法值回落 3，⛔ 不回落 0', () => {
  assert.strictEqual(clampTopK(5), 5);
  assert.strictEqual(clampTopK('7'), 7);
  assert.strictEqual(clampTopK(0), 3);
  assert.strictEqual(clampTopK(-4), 3);
  assert.strictEqual(clampTopK(999), 20, '超上限要夹到 20，⛔ 不是原样送出去吃 422');
  assert.strictEqual(clampTopK(''), 3);
  assert.strictEqual(clampTopK(undefined), 3);
  assert.strictEqual(clampTopK('abc'), 3);
});

/* ══════════════ 3 · 结果归一 ══════════════ */

test('rowOf：按面板取各自的分数字段', () => {
  assert.strictEqual(rowOf('pg', { content: 'a', source: 's', similarity: 0.81 }).score, 0.81);
  assert.strictEqual(rowOf('hybrid', { content: 'a', rrf_score: 0.0323 }).score, 0.0323);
  assert.strictEqual(rowOf('rerank', { content: 'a', rerank_score: -1.5 }).score, -1.5);
});

test('🔴 rowOf：分数字段缺了 ⇒ `null`（页面画 `—`），⛔ **绝不编 0**', () => {
  // 本仓立场：「不许印没有数据源的数」（`DEC-093` 那两格恒为 `--` 的死卡的前科）。
  const r = rowOf('rerank', { content: 'a', rrf_score: 0.03 });   // 只给了 rrf，没给 rerank
  assert.strictEqual(r.score, null, '缺 rerank_score 却编了个 0 ⇒ 页面会印一个假的相似度');
  assert.strictEqual(rowOf('pg', {}).score, null);
  assert.strictEqual(rowOf('pg', { similarity: '' }).score, null);
});

test('rowOf：`from` / `id` 缺了就 null，内容一律转成字符串安全值', () => {
  const r = rowOf('hybrid', { content: 'a', rrf_score: 0.1 });
  assert.strictEqual(r.from, null);
  assert.strictEqual(r.id, null);
  assert.strictEqual(rowOf('pg', {}).content, '');
  assert.strictEqual(rowOf('pg', { content: 123 }).content, '', 'content 不是字符串 ⇒ 走空串，⛔ 不 String(123) 印个数字出来');
});

test('rowsOf / docsOf：`docs` 不是数组 ⇒ 空数组（⛔ 不抛、不返回 undefined）', () => {
  assert.deepStrictEqual(docsOf(null), []);
  assert.deepStrictEqual(docsOf({}), []);
  assert.deepStrictEqual(docsOf({ docs: 'nope' }), []);
  assert.strictEqual(rowsOf('pg', { docs: [{ content: 'a', similarity: 0.5 }] }).length, 1);
  assert.deepStrictEqual(rowsOf('pg', null), []);
});

/* ══════════════ 4 · 管线专有（timing / pipeline / answer）══════════════ */

test('timingRows：非管线端点没有 timing ⇒ `[]`；有就翻成人话名', () => {
  assert.deepStrictEqual(timingRows({ docs: [] }), []);
  assert.deepStrictEqual(timingRows(null), []);
  const rows = timingRows({ timing: { rewrite_ms: 12.5, total_ms: 300 } });
  assert.deepStrictEqual(rows, [['查询改写', 12.5], ['合计', 300]]);
});

test('stageRows：`pipeline` 块 → 开关清单（⚠️ 是"开没开"，⛔ 不是耗时）', () => {
  assert.deepStrictEqual(stageRows({ docs: [] }), []);
  const rows = stageRows({ pipeline: { rewrite_enabled: true, bm25_enabled: false } });
  assert.deepStrictEqual(rows, [
    ['查询改写', true], ['查询扩展', false], ['BM25 关键词', false], ['Cross-Encoder 精排', false],
  ]);
});

test('answerOf：没勾生成答案就是空串（⛔ 别拿空串当"答不出来"）', () => {
  assert.strictEqual(answerOf({ docs: [] }), '');
  assert.strictEqual(answerOf(null), '');
  assert.strictEqual(answerOf({ answer: '净利润 1 亿。' }), '净利润 1 亿。');
});

/* ══════════════ 5 · 环境限制（`DEC-034`）· 空态 ══════════════ */

test('🔴 envLimitHint：**只有** rerank + 5xx 才说是环境限制 —— ⛔ 别拿它盖 401/429', () => {
  // 401 是 key 不对、429 是额度 —— 那两样⛔ 不是"演示机没装 torch"。
  assert.match(envLimitHint('rerank', 500), /环境限制/);
  assert.match(envLimitHint('rerank', 503), /环境限制/);
  assert.strictEqual(envLimitHint('rerank', 401), null);
  assert.strictEqual(envLimitHint('rerank', 429), null);
  assert.strictEqual(envLimitHint('rerank', 200), null);
  assert.strictEqual(envLimitHint('pg', 500), null, '纯向量检索不吃 torch，别把它的 500 也说成环境限制');
});

test('🔴 envLimitHint 那句必须【把归因指向环境】，⛔ 不是"功能坏了"', () => {
  const s = envLimitHint('rerank', 500);
  assert.match(s, /不是功能坏了/);
});

test('emptyReason：必须【解释为什么空】，且点名"不是接口坏了"', () => {
  const s = emptyReason('pg');
  assert.ok(s.length > 20, '空态理由太短 ⇒ 等于没解释');
  assert.match(s, /知识库/);
  assert.match(s, /不是接口坏了|⛔/);
  assert.throws(() => emptyReason('nope'), /unknown panel/);
});

/* ══════════════ 6 · 浏览器侧：`RagLab` 这个全局真的存在吗 ══════════════
 *
 * 🔴 `node --test` 走 `module.exports`，**浏览器走的是另一条路**（经典脚本 ⇒ 全局）。
 *    `sse.js` 有过前科：那时只挂了 `module.exports` ⇒ 页面里每一处 `RagSse.xxx`
 *    都 `ReferenceError`，而 **node 用例全绿、页面加载时也不报**。`panel.test.js` 同款。
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('把 lab.js 当【经典脚本】跑一遍 ⇒ window.RagLab 存在且接口齐全', () => {
  const src = fs.readFileSync(path.join(__dirname, 'lab.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  const w = sandbox.window;

  assert.strictEqual(typeof w.RagLab, 'object', 'lab.js 没挂 window.RagLab ⇒ 页面里全报 ReferenceError');
  for (const k of ['panelOf', 'buildRequest', 'rowsOf', 'timingRows', 'stageRows', 'answerOf',
                   'envLimitHint', 'emptyReason', 'clampTopK']) {
    assert.strictEqual(typeof w.RagLab[k], 'function', `window.RagLab.${k} 不是函数`);
  }
  assert.strictEqual(Object.keys(w.RagLab.PANELS).length, 5);
});
