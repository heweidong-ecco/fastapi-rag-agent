'use strict';
/* `sse.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test api/static/js/sse.test.js（已接进 ci.yml 的 run 块） */
const test = require('node:test');
const assert = require('node:assert');

const {
  parseSseChunk, payloadKind, citationIndexes, splitCitations, resolveCitations,
  classifyExit, formatCost, formatSource, toggleOpen,
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

test('splitCitations 把正文切成「文本 / 引用编号」两种片段（渲染层用的就是它）', () => {
  assert.deepStrictEqual(
    splitCitations('甲[来源:2]乙'),
    [{ text: '甲' }, { index: 2 }, { text: '乙' }],
  );
  assert.deepStrictEqual(splitCitations('[来源:1, 3]'), [{ index: 1 }, { index: 3 }]);
  assert.deepStrictEqual(splitCitations('没有引用'), [{ text: '没有引用' }], '不许吐空片段');
  assert.deepStrictEqual(splitCitations(''), []);
});

test('citationIndexes 与 splitCitations 走的是同一个实现（⛔ 不是两处各写一份正则）', () => {
  // ⚠️ **这条能抓什么、抓不到什么，都说清楚**（本仓纪律：判据不许含糊通过）：
  //   ✅ 抓得住：**行为已漂移**的重复实现（实测：把 citationIndexes 换回一份内联正则、
  //      且只认 `[来源:1]` 不认 `[来源:1, 3]` ⇒ 本条红）。
  //   ⛔ **抓不住**：一份**逐字相同**的重复实现 —— 两份一样时，行为当然也一样。
  //      ⇒ 光靠它**挡不住"又抄一份"**。挡那件事的是下面那条 `前端只许有一份引用正则`（结构型）。
  for (const s of ['[来源:2]', '甲[来源:1, 3]乙[来源:2]', '[来源:9]没有引用', '']) {
    const fromSplit = splitCitations(s).filter((x) => x.index !== undefined).map((x) => x.index);
    const dedup = [];
    for (const n of fromSplit) if (!dedup.includes(n)) dedup.push(n);
    assert.deepStrictEqual(dedup, citationIndexes(s), `对不上：${s}`);
  }
});

// ---------- 结构型守卫：引用正则在整个前端【只许有一份】 ----------
//
// 🔴 为什么要有这条：`施工单` Task 8 的画渲染层原稿里写着「⛔ 不在这里写第二份正则」，
//    **然后在下一行就写了第二份**。⚠️ 光靠注释挡不住 —— 本仓原话：
//    **「有结构才执行，只有文字就漏」**。
//    两处一旦漂移：**画出来的编号与点开的编号不是同一批**，而页面上**不报任何错**
//    （用户看到的是"点了没反应"）。
const fs = require('node:fs');
const path = require('node:path');
const JS_DIR = __dirname;
const WEB_DIR = path.join(__dirname, '..', 'web');
// ⚠️ 针脚**分两段拼**，让本文件自身不包含那个连续子串 —— 否则这条守卫会被**自己**绊倒。
const NEEDLE = '来源' + '\\s*:';

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

test('尺子有读数：前端确实扫到了文件，且 sse.js 在里面', () => {
  // 🔴 本仓 `DEC-065`（空清单静默假通过）：下面那条拿**空集合**断言会一路绿着放行。
  const files = frontendSources();
  assert.ok(files.length >= 2, `只扫到 ${files.length} 个前端文件 —— 扫描本身失效了`);
  assert.ok(
    files.some((f) => f.endsWith(path.join('js', 'sse.js'))),
    `扫到的文件里没有 sse.js：${files.join(', ')}`,
  );
});

test('前端只许有一份引用正则（结构型：数的是【文件】，⛔ 不是"我记得没写第二份"）', () => {
  const hit = frontendSources().filter((f) => fs.readFileSync(f, 'utf8').includes(NEEDLE));
  assert.deepStrictEqual(
    hit.map((f) => path.relative(path.join(JS_DIR, '..', '..'), f)).map((f) => f.replace(/\\/g, '/')),
    ['static/js/sse.js'],
    '引用正则在别处又出现了一份 ⇒ 两处会漂移，而页面上不报错（表现是"点了没反应"）',
  );
});

// ---------- 浏览器侧：`RagSse` 这个全局对象真的存在吗 ----------
//
// 🔴 为什么要有这一节：`node --test` 走的是 `module.exports`，**浏览器走的是另一条路**
//    （经典脚本 ⇒ 全局）。2026-10-06 施工时实测：`sse.js` 当时**只挂了 `module.exports`**，
//    于是 `chat.html` 里每一处 `RagSse.xxx` 都会 `ReferenceError`，而
//    **node 用例全绿、页面加载时也不报**（`RagSse` 第一次被用到是在答案开始流之后）。
//    ⇒ 造一个**假 window**，把源文件真跑一遍。
const vm = require('node:vm');

function loadInBrowserLikeSandbox() {
  const src = fs.readFileSync(path.join(JS_DIR, 'sse.js'), 'utf8');
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return sandbox.window;
}

test('把 sse.js 当【经典脚本】跑一遍 ⇒ window.RagSse 存在且接口齐全（浏览器走的就是这条路）', () => {
  const w = loadInBrowserLikeSandbox();
  assert.strictEqual(typeof w.RagSse, 'object', 'sse.js 没有挂 window.RagSse ⇒ 页面里 RagSse.xxx 全报 ReferenceError');
  for (const k of ['parseSseChunk', 'payloadKind', 'citationIndexes', 'splitCitations',
                   'resolveCitations', 'classifyExit', 'formatCost',
                   'formatSource', 'toggleOpen']) {
    assert.strictEqual(typeof w.RagSse[k], 'function', `window.RagSse.${k} 不是函数`);
  }
});

test('chat.html 用到的每一个 RagSse.* 都真的存在（⛔ 别等页面在用户面前报 ReferenceError）', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'chat.html'), 'utf8');
  const used = [...new Set([...html.matchAll(/RagSse\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]))];
  // 🔴 先证明尺子有读数（本仓 `DEC-065`：空集合断言会一路绿着放行）
  assert.ok(used.length >= 4, `只从 chat.html 里认出 ${used.length} 个 RagSse.* —— 扫描失效了`);
  const api = loadInBrowserLikeSandbox().RagSse;
  for (const name of used) {
    assert.strictEqual(typeof api[name], 'function', `chat.html 用了 RagSse.${name}，但 sse.js 没提供它`);
  }
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

// ---------- 引用卡片：卡片头 / 就地展开（`DEC-089` · 硬门 B 的另外两句） ----------
//
// 🔴 为什么这两件抽进本文件：硬门 B 的判定有三句，其中两句是
//    「再点能跳到原文位置」与「点开能看到 chunk id + 相似度分」—— 它们**能写成命令**
//    （本仓立场：写不出命令的，就是还没核过）。DOM 怎么挂仍留在 `chat.html`（手工验）。

test('formatSource 拼出卡片头：[编号] 来源 · chunk id · 相似度', () => {
  const out = formatSource({ index: 1, source: 'handbook.md', id: 812, similarity: 0.8312 });
  assert.strictEqual(out.title, '[1] handbook.md');
  assert.strictEqual(out.meta, 'id=812 · 相似度 0.831');
});

test('formatSource 缺字段画 —，⛔ 不许把 undefined / NaN 画到页面上', () => {
  // ⚠️ 这不是假想：非流式那条链（`answer_with_citations.py`）的上下文里**没有** similarity
  //    ⇒ 它会诚实地传 `None` 过来。页面显示 `undefined` 会被读成"这个功能坏了"。
  const out = formatSource({ index: 2, source: 'b.md' });
  assert.strictEqual(out.meta, 'id=— · 相似度 —');
  for (const v of Object.values(out)) {
    assert.ok(!/undefined|NaN|null/.test(v), `卡片头里出现了 ${v}`);
  }
});

test('formatSource：相似度 0 与「没有相似度」是两件事（⛔ 别都画成 —）', () => {
  // 同 `formatCost` 的立场：`null` ⇒ `—`（"不知道"），`0` ⇒ 真值。
  assert.strictEqual(
    formatSource({ index: 3, source: 'c.md', similarity: 0 }).meta, 'id=— · 相似度 0.000');
  assert.strictEqual(
    formatSource({ index: 3, source: 'c.md', similarity: null }).meta, 'id=— · 相似度 —');
});

test('toggleOpen：没展开就展开、点同一条收起、点另一条换内容（= 判定里的「再点」）', () => {
  assert.strictEqual(toggleOpen(null, 1), 1, '第一次点 ⇒ 展开');
  assert.strictEqual(toggleOpen(1, 1), null, '🔴 再点同一条 ⇒ 收起（本仓 2026-10-06 裁的「甲」）');
  assert.strictEqual(toggleOpen(1, 2), 2, '点另一条 ⇒ 换内容，⛔ 不是同时开着两张卡片');
});

test('卡片头只许有一份实现（结构型：数的是【文件】，⛔ 不是"我记得没写第二份"）', () => {
  // 🔴 与上面那条「引用正则只许有一份」同型：两处一旦漂移，页面上的编号与卡片里的数
  //    不是同一批，而**页面上不报任何错**（本仓原话：「有结构才执行，只有文字就漏」）。
  const hit = frontendSources()
    .filter((f) => fs.readFileSync(f, 'utf8').includes('相似度'))
    .map((f) => path.relative(path.join(JS_DIR, '..', '..'), f).replace(/\\/g, '/'));
  assert.deepStrictEqual(hit, ['static/js/sse.js'],
    '「相似度」在别处又出现了一份 ⇒ 卡片头有两套格式，会漂移');
});
