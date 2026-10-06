'use strict';
/* `sse.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test api/static/js/sse.test.js（已接进 ci.yml 的 run 块） */
const test = require('node:test');
const assert = require('node:assert');

const {
  parseSseChunk, payloadKind, citationIndexes, resolveCitations, classifyExit, formatCost,
} = require('./sse.js');

test('parseSseChunk 只吐【完整】的帧，半截留在 rest 里', () => {
  const one = 'data: {"content": "你"}\n\n';
  const half = 'data: {"content": "好"}\n\n' + 'data: {"content": "世';
  let out = parseSseChunk(one);
  assert.deepStrictEqual(out.payloads, [{ content: '你' }]);
  assert.strictEqual(out.rest, '');

  out = parseSseChunk(half);
  assert.deepStrictEqual(out.payloads, [{ content: '好' }]);
  assert.strictEqual(out.rest, 'data: {"content": "世', '半截帧不许被解析');
});

test('parseSseChunk 认得 [DONE] 哨兵', () => {
  const out = parseSseChunk('data: [DONE]\n\n');
  assert.deepStrictEqual(out.payloads, ['[DONE]']);
});

test('parseSseChunk 把多帧按 \\n\\n 切开', () => {
  const buf = 'data: {"content": "a"}\n\ndata: {"content": "b"}\n\n';
  assert.deepStrictEqual(parseSseChunk(buf).payloads, [{ content: 'a' }, { content: 'b' }]);
});

test('payloadKind 认得五种帧', () => {
  assert.strictEqual(payloadKind('[DONE]'), 'done');
  assert.strictEqual(payloadKind({ content: 'x' }), 'content');
  assert.strictEqual(payloadKind({ sources: [] }), 'sources');
  assert.strictEqual(payloadKind({ usage: {} }), 'usage');
  assert.strictEqual(payloadKind({ error: 'boom' }), 'error');
  assert.strictEqual(payloadKind({ something: 1 }), 'unknown');
});

test('citationIndexes 认单个、多个、重复、空', () => {
  assert.deepStrictEqual(citationIndexes('答案[来源:2]'), [2]);
  assert.deepStrictEqual(citationIndexes('甲[来源:1, 3]乙'), [1, 3]);
  assert.deepStrictEqual(citationIndexes('[来源:2][来源:2]'), [2], '重复的只留一个');
  assert.deepStrictEqual(citationIndexes('没有引用'), []);
});

test('resolveCitations 把编号映射成【sources 数组里的那一条】', () => {
  const sources = [
    { index: 1, source: 'a.md', content: '甲文' },
    { index: 2, source: 'b.md', content: '乙文' },
  ];
  const got = resolveCitations('答案[来源:2]', sources);
  assert.strictEqual(got.length, 1);
  assert.strictEqual(got[0].index, 2);
  assert.strictEqual(got[0].source, 'b.md', '🔴 必须按 index 找，⛔ 不是按数组下标');
  assert.strictEqual(got[0].content, '乙文');
});

test('resolveCitations 按 index 而不是数组顺序（乱序也要对）', () => {
  const sources = [
    { index: 2, source: 'b.md', content: '乙文' },
    { index: 1, source: 'a.md', content: '甲文' },
  ];
  assert.strictEqual(resolveCitations('[来源:1]', sources)[0].source, 'a.md');
});

test('resolveCitations 对不存在的编号【不抛】、只是跳过', () => {
  assert.deepStrictEqual(resolveCitations('[来源:9]', [{ index: 1, source: 'a' }]), []);
});

test('classifyExit 四种出口分得开', () => {
  assert.strictEqual(classifyExit({ sawDone: true, sawError: false, aborted: false }), 'done');
  assert.strictEqual(classifyExit({ sawDone: false, sawError: true, aborted: false }), 'error');
  assert.strictEqual(classifyExit({ sawDone: false, sawError: false, aborted: true }), 'aborted');
  assert.strictEqual(classifyExit({ sawDone: false, sawError: false, aborted: false }), 'incomplete');
});

/* 🔴 2026-10-06 施工时补的一条 —— ⛔ 起草时没有，是【反证检验】跑出来的空缺：
   上面那四条**每个都只置一个标志为真** ⇒ 「两个同时为真时谁赢」**没有任何尺子**。
   实测：把 `aborted` 与 `sawError` 的顺序对调 ⇒ **11 pass / 0 fail，一条都不红**。
   ⚠️ 这不是假想：先收到 `error` 帧、用户随后点「停止」⇒ 两个都为真（可到达）。
   优先级按 `DEC-085` §3.3 状态机取「用户动作优先」：点了停止就是**已中断**。 */
test('classifyExit：aborted 与 error 同时为真时，用户动作优先（DEC-085 §3.3 状态机）', () => {
  assert.strictEqual(classifyExit({ sawDone: false, sawError: true, aborted: true }), 'aborted');
  assert.strictEqual(classifyExit({ sawDone: true, sawError: false, aborted: true }), 'aborted',
    '点了停止就不再是「完成」—— ⛔ 别让收尾的 [DONE] 把已中断洗成完成');
});

test('classifyExit：有 error 帧就没有 done（本仓 RAG 端点【故意】不发 [DONE]）', () => {
  assert.strictEqual(classifyExit({ sawDone: false, sawError: true, aborted: false }), 'error');
});

test('formatCost 是 6 位小数且带 $', () => {
  assert.strictEqual(formatCost(0.0123456), '$0.012346');
  assert.strictEqual(formatCost(0), '$0.000000');
  assert.strictEqual(formatCost(null), '—');
});
