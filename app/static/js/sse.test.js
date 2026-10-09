'use strict';
/* `sse.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/sse.test.js（已接进 ci.yml 的 run 块） */
const test = require('node:test');
const assert = require('node:assert');

const {
  parseSseChunk, payloadKind, citationIndexes, splitCitations, resolveCitations,
  classifyExit, formatCost, formatSource, toggleOpen, breakerCard, refusalNotice,
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

test('payloadKind 认得六种帧', () => {
  assert.strictEqual(payloadKind('[DONE]'), 'done');
  assert.strictEqual(payloadKind({ content: 'x' }), 'content');
  assert.strictEqual(payloadKind({ sources: [] }), 'sources');
  assert.strictEqual(payloadKind({ usage: {} }), 'usage');
  assert.strictEqual(payloadKind({ error: 'boom' }), 'error');
  assert.strictEqual(payloadKind({ no_answer: true }), 'no_answer');
  // ⚠️ 认不出的帧仍然落到 'unknown' —— 老前端遇到新帧就是这条路
  //    （`chat.html` 对 'unknown' **什么都不做**）⇒ 后端加帧天然向后兼容。
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

// ============ 剥注释：让「禁子串」守卫盯着【代码】，⛔ 不是字节（`N14` · 2026-10-08） ============
//
// 🔴 原先那条守卫是 `readFileSync(f).includes(REFUSE)` —— **整份文件扫，注释也算**，
//    而它的靶子其实是**行为**（前端不许自己认拒答）。
//    2026-10-06 施工时当场撞上：我把那句拒答语写进 `chat.html` 的**注释**当例证 ⇒ 守卫红
//    ⇒ **我把注释改写掉了**。⇒ **同一块石头还在原地**：下一个写注释解释这条守卫的人，
//    会**再红一次**（而红了之后最省事的做法，还是把注释改掉 —— 那就是**每次都要有人白查一遍**）。
//    📄 `docs/复盘/2026-10-06-守卫的靶子没定准.md`（本条的正式出处）。

// ⚠️ 针脚**分两段拼** —— 理由同上面那条 `NEEDLE`：让本文件自身不含那个连续子串。
//    🔴 `N14` 起它挂在**模块作用域**（下面 `refusalOwners` 也要用它）。
const REFUSE = '无法' + '回答';

/** 剥掉注释 —— 只剥**三种**，取【保守】策略。
 *
 * ⛔ **有意不剥行尾 `//` 注释**：剥它要区分 `https://` 里的 `//`（那需要一个真词法器）。
 *    而"剥错"的方向是**守卫变瞎**（假绿）—— 比多报一次**糟得多**。
 *    `N14` 的事故是一整块注释，本剥法覆盖得到。
 * ⛔ **剥的是注释，不是字符串**：把串拆成 `'无法' + '回答'` 那种**代码**照旧会命中 ——
 *    那属于**故意规避**，⛔ 不是本守卫要解决的问题（本守卫防的是**漂移**）。
 */
function stripComments(text) {
  return String(text)
    .replace(/<!--[\s\S]*?-->/g, '')      // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, '')     // JS 块注释
    .replace(/^[ \t]*\/\/.*$/gm, '');     // JS【整行】注释
}

/** 纯逻辑：给定一组 `{name, text}`，回「谁在【代码】里认了拒答」。
 *
 * ⚠️ 拆出来是为了**能拿夹具测** —— 否则只能拿真仓的文件测，而真仓的文件**不会为了测它而变脏**。
 */
function refusalOwners(sources) {
  return sources
    .filter((s) => stripComments(s.text).includes(REFUSE))
    .map((s) => s.name);
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
                   'formatSource', 'toggleOpen', 'breakerCard', 'refusalNotice']) {
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
    // ⚠️ **这里原本断言的是 `typeof === 'function'`** —— 2026-10-09（刀 2）**放宽成"必须存在"**：
    //    那一版页面上开始用 `RagSse.CHAINS`（对象）与 `RagSse.CHAIN_KEYS`（数组），
    //    它们在页面里**完全合法**，却被那条断言判红。
    //    🔴 **门要测的是"会不会 ReferenceError"**，而"是不是函数"只是它的**代理量** ——
    //    ⛔ 代理量把合法用法一起挡掉，就是靶子定窄了（本仓 `N14` 那一族的又一面）。
    //    ⚠️ 放宽**不削弱它**：名字写错照样 `undefined` ⇒ 照样红。
    assert.notStrictEqual(api[name], undefined, `chat.html 用了 RagSse.${name}，但 sse.js 没提供它`);
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

// ---------- 熔断提示卡片：`R3.2`「明确卡片」的四件事 ----------
//
// 🔴 为什么抽进本文件：`R3.2` 的验收原文是「卡片上写清四件事 ——
//    **现状 / 这不是故障 / 何时恢复 / 怎么联系**」（`施工单-本项目.md` §要求 R3）。
//    这四件里**三件是常量**，只有「何时恢复」随**熔断的两种**变 —— 而它**能写成命令**。
//
// 🔴 为什么非分两种不可（改这一刀之前**页面上的真缺陷**）：
//    `chat.html` 原先 429 只写一句「今日额度已用完 / 会话额度已用完」——
//    **把两种恢复条件完全不同的熔断混成了一句**：
//      · 全站日级（`B11`）⇒ 全站共享，你**做什么都救不回来**，只能等跨天
//      · 会话级（`B8`）  ⇒ 是你**自己这个 thread** 的今日用量 ⇒ **开个新会话立刻能继续**
//    两者 `code` **都是 `QUOTA_EXCEEDED`**（`app/core/exceptions.py` 就一个枚举）⇒
//    **靠前端从 `code` 分不出是哪种**，所以后端补了 `scope` 字段（`DEC-090`）。

const _FOUR = ['现状', '这不是故障', '何时恢复', '怎么联系'];

function _rows(card) {
  return Object.fromEntries(card.items.map((it) => [it.k, it.v]));
}

test('breakerCard：四件事一件不少，且⛔ 一行都不许空', () => {
  const card = breakerCard('global', '今日全站额度已用完（已使用 1000000 / 上限 1000000 tokens）');
  assert.deepStrictEqual(card.items.map((it) => it.k), _FOUR,
    'R3.2 的四件事必须原样都在、且顺序固定（卡片是照着念的）');
  for (const [k, v] of Object.entries(_rows(card))) {
    assert.ok(typeof v === 'string' && v.trim().length > 0, `「${k}」是空的 —— 卡片上会是一块空白`);
  }
  assert.ok(card.title.trim().length > 0, '卡片没标题');
});

test('breakerCard：后端原文案【原样】进「现状」，⛔ 不自己重编一句', () => {
  // 🔴 原文案里带着「已使用 X / 上限 Y tokens」—— 那正是 `R3.1` 要的「可识别」那半。
  //    前端重编 = 两处各写一份数字口径 ⇒ 会漂移，且**页面上不报错**。
  const why = '今日全站额度已用完（已使用 1000000 / 上限 1000000 tokens），请明日再试';
  assert.strictEqual(_rows(breakerCard('global', why))['现状'], why);
})

test('breakerCard(global)：何时恢复 = 等跨天，⛔ 不许说"开新会话"（那样说就是骗人）', () => {
  const v = _rows(breakerCard('global', 'x'))['何时恢复'];
  assert.ok(/明日|自然日/.test(v), `全站级的恢复口径是跨天，实测拿到：${v}`);
  assert.ok(!/新会话/.test(v), '全站共享，开新会话一样吃 429 —— ⛔ 别给一个做不到的出路');
});

test('breakerCard(session)：何时恢复 = 开新会话立刻可继续（`chat.html` 有「＋ 新会话」按钮）', () => {
  const v = _rows(breakerCard('session', '本会话预算已用完（已使用 50000 tokens，会话上限 50000 tokens）'))['何时恢复'];
  assert.ok(/新会话/.test(v), `会话级是可自救的，实测拿到：${v}`);
  assert.ok(!/明日/.test(v),
    '🔴 会话级不是"明日恢复" —— 「开新会话立刻能继续」才是实话；这正是改前那句混话的错');
});

test('breakerCard：认不出的 scope（含缺字段）⇒「何时恢复」画 —，⛔ 不猜一个口径', () => {
  // ⚠️ 这不是假想：中间件的限流 429 也走同一个 `error` 分支，它**没有** scope。
  //    猜成 global 会让「明日起恢复」出现在一个**根本没有日级额度**的场合。
  for (const s of [undefined, null, '', 'unknown']) {
    const rows = _rows(breakerCard(s, 'x'));
    assert.strictEqual(rows['何时恢复'], '—', `scope=${JSON.stringify(s)} 时不该编一个恢复口径`);
    assert.strictEqual(rows['现状'], 'x', '认不出 scope ⛔ 不代表可以把后端原话也丢掉');
  }
});

test('改前那句「混两种」的话已从 chat.html 删掉（结构型：数的是【文件】，⛔ 不是"我记得删了"）', () => {
  // 🔴 与「引用正则只许有一份」同型。那句话**不报错**、只是把两种恢复条件说成一种 ⇒
  //    页面上看着一切正常，只有真被熔断的人被引到错误的处置上。
  // 针脚分两段拼，让本文件自身不含那个连续子串（否则这条守卫会被**自己**绊倒）。
  const MERGED = '今日额度已用完' + ' / 会话额度已用完';
  const hit = frontendSources()
    .filter((f) => fs.readFileSync(f, 'utf8').includes(MERGED))
    .map((f) => path.relative(path.join(JS_DIR, '..', '..'), f).replace(/\\/g, '/'));
  assert.deepStrictEqual(hit, [], `那句把两种熔断混起来的话还在：${hit.join(', ')}`);
});

// ---------- 无据拒答的提示条：`F4` ① · 硬门 B 的**第二半** ----------
//
// 🔴 为什么抽进本文件：与 `breakerCard` 同一条理由 —— 这是**能写成命令**的那部分
//    （"这句话说的是不是实话"）。DOM 怎么挂留在 `chat.html`。
//
// 🔴 后端**只给信号**（一帧 `{"no_answer": true}`），⛔ **不把这句文案塞进帧里**：
//    文案属于**呈现层**；塞进帧就变成又一份要两边同步的契约（本仓已栽过同型事故）。
//    ⚠️ 于是判据（"这轮算不算拒答"）**只有后端那一份** —— 见下面那条结构型守卫。

test('refusalNotice：说的是「资料里没有」，⛔ 不许说成"检索失败 / 出错了"', () => {
  const n = refusalNotice();
  const text = n.title + n.body;
  // 这句必须指向**知识库**：用户能做的是换问法 / 补文档。
  assert.ok(/资料|文档/.test(text), `没提到"资料/文档" ⇒ 读的人会以为是系统坏了：${text}`);
  // ⛔ 说成故障 = 让用户去重启、重试、找人修 —— 全是无用功。
  assert.ok(!/出错|故障|失败|异常|坏了/.test(text), `把无据拒答说成了故障：${text}`);
});

test('refusalNotice：⛔ 不许暗示"等一会儿/重试就好"（那是做不到的承诺）', () => {
  // 🔴 拒答是**检索＋上下文**的结论，原样重问不会变。⛔ 别把它写成限流那种「稍后再试」——
  //    那是另一种状态（`breakerCard` 管）的出路，两者混起来会把人引到错误的处置上。
  //
  // ⚠️ 2026-10-06 施工实测：本条第一版写的是 `/稍后|再试|重试|刷新/`，**它误伤了真话** ——
  //    提示语里的「先上传相关文档**再试**」是**做得到的**出路（先有动作，才有"再试"）。
  //    ⇒ 那是**尺子歪了**，不是文案错：本条的靶子是「等一会儿它自己就好了」那个**假承诺**，
  //      ⛔ 不是"再试"这两个字。收窄成下面这组（都指向"时间会解决"，而时间不会）。
  const text = refusalNotice().title + refusalNotice().body;
  assert.ok(!/稍后|重试|刷新|多试|过一会儿|等一会/.test(text),
    `把无据拒答当成了限流类问题（暗示"等/重试就好"）：${text}`);
});

test('stripComments：三种注释里的那串【都不算】', () => {
  // 🔴 `N14` 的正身：注释里写它是**允许**的（那正是在解释这条守卫）。
  const src = stripComments(
    '<p>ok</p><!-- ' + REFUSE + ' 当例证 -->\n' +
    '/* 块注释里的 ' + REFUSE + ' */\n' +
    '   // 整行注释里的 ' + REFUSE + '\n' +
    'const keep = 1;\n',
  );
  assert.ok(!src.includes(REFUSE), `注释没被剥干净：${JSON.stringify(src)}`);
  assert.ok(src.includes('const keep = 1;'), '剥过头了 —— 把代码也吃掉了');
});

test('🔴 反证：代码里的那串【要算】—— 防「剥多了 ⇒ 守卫变瞎」', () => {
  // ⚠️ 这条是**取反检验**：把「剥注释」做过头（比如按整行丢），下面这条会**静默变绿**。
  //    没有它，「剥干净了」与「把守卫剥瞎了」在输出上**长得一样**。
  assert.deepStrictEqual(
    refusalOwners([
      { name: 'a.js', text: 'if (t.includes("' + REFUSE + '")) {}' },
      { name: 'b.html', text: '<!-- ' + REFUSE + ' -->' },
    ]),
    ['a.js'],
  );
});

test('前端 ⛔ 不许自己认拒答 —— 判据只有后端一份（结构型：数的是【文件】）', () => {
  // 🔴 与「引用正则只许有一份」同型。拒答那句在 `api_v1_rag.py` 的 prompt 里。
  //    前端若也写一份去认，两处一旦漂移：**后端发了帧、前端却按另一套判**，
  //    或者反过来 —— 而**页面上不报任何错**。
  // 🔴 `N14`（2026-10-08）：靶子是【代码】，⛔ 不是字节 —— 走 `stripComments`，**注释不算**。
  //    ⚠️ 上面那条「引用正则」守卫（用 `NEEDLE`）**没有**跟着改：它的针脚是
  //    `来源\s*:` 那种**正则字面量**形状，**解释性文字里不会自然出现**；
  //    而本条那句是**中文白话**，写注释时**极易**被引到。⇒ 风险不同，⛔ **不顺手一起改**。
  assert.deepStrictEqual(
    refusalOwners(frontendSources().map((f) => ({
      name: path.relative(path.join(JS_DIR, '..', '..'), f).replace(/\\/g, '/'),
      text: fs.readFileSync(f, 'utf8'),
    }))),
    [],
    '前端自己认起拒答来了 —— 判据只该在后端一处，前端只认帧',
  );
});

/* ══════════════ 刀 2：「6 条链」的调用契约 ══════════════
 *
 * 🔴 为什么这几条非要钉（2026-10-09 **逐条从 OpenAPI 核出来的**，⛔ 不是照文档抄的）：
 *   6 条链的**请求形状【不是同一套】** —— 走错一步就是 **422**，
 *   而**前端不报任何错**（拿到 422 只会走进普通错误分支，用户看到"没反应"）。
 *
 *   | 链 | 形状 | 键 |
 *   |---|---|---|
 *   | `/rag/stream_search` | **JSON body** | `question` + `citations: true` |
 *   | 5 条 `/agent/<链>/stream` | **query 参数**（`question: str` 裸参数 = query） | `question` |
 *   | 🔴 `plan_execute` | query 参数 | **`goal`** ← ⛔ 不是 question |
 *
 * ⚠️ **写这一块时【当场踩了一个坑，而且踩了两遍】**：原稿那行写的是「5 条 `/agent/<星号>/stream`」——
 *    **星号紧挨斜杠**这两个字符连在一起，就是**块注释的结束符** ⇒ **提前把注释收掉了** ⇒
 *    后半段变成代码 ⇒ `SyntaxError: Unexpected identifier 'question'`（整份文件加载失败，一条都不跑）。
 *    🔴 **第二遍更值得记**：我在这段注释里**解释这个坑**时，又把那两个字符原样写进了注释 ⇒
 *    **同一个错误当场复发**（报 `Invalid regular expression: missing /`）。
 *    ⚠️ 这是本仓「**注释里的字面会反噬**」那一族的**第三个变体**
 *    （前两个：**判据里写的字面数到了判据自己** · **`/<星号>` 被当成 CSS 注释开头、吃掉半个页面**）。
 *    ⇒ **注释里写路径时，通配符换成 `<链>`；解释这个坑时，⛔ 别把那两个字符拼出来。**
 *
 * 📌 取法（可打印）：`cd app && ../venv/bin/python -c "from main import app; …"` 读 `app.openapi()`。
 */
const RagSse = require('./sse.js');

test('6 条链都在，且每条都指向 /api/v1 下的一个流式端点', () => {
  assert.ok(Array.isArray(RagSse.CHAIN_KEYS), 'CHAIN_KEYS 不是数组');
  assert.strictEqual(RagSse.CHAIN_KEYS.length, 6, `应有 6 条链，实际 ${RagSse.CHAIN_KEYS.length}`);
  for (const k of RagSse.CHAIN_KEYS) {
    const { url } = RagSse.buildRequest(k, '问', 'tid');
    assert.ok(url.startsWith('/api/v1/'), `${k} 的 url 没带 /api/v1 前缀：${url}`);
    assert.ok(url.includes('tid'), `${k} 的 url 没带上 thread_id：${url}`);
  }
});

test('🔴 plan_execute 的键是 goal，⛔ 不是 question（传错就是 422，而前端不报错）', () => {
  const { url } = RagSse.buildRequest('plan_execute', '做个计划', 'tid');
  const q = new URL(url, 'http://x').searchParams;
  assert.strictEqual(q.get('goal'), '做个计划');
  assert.strictEqual(q.get('question'), null, 'plan_execute ⛔ 不接受 question');
});

test('5 条 agent 链走【query 参数】，⛔ 不带 body', () => {
  for (const k of RagSse.CHAIN_KEYS.filter((x) => x !== 'rag_stream')) {
    const { url, init } = RagSse.buildRequest(k, '问一句', 'tid');
    const q = new URL(url, 'http://x').searchParams;
    assert.ok(q.get('question') || q.get('goal'), `${k} 把问题丢了`);
    assert.strictEqual(init.body, undefined, `${k} ⛔ 不该带 body（它的 question 是 query 参数）`);
  }
});

test('rag_stream 走【JSON body】，且必须显式 citations:true（不传就根本没有 sources 帧）', () => {
  const { url, init } = RagSse.buildRequest('rag_stream', '问一句', 'tid');
  assert.ok(url.includes('/api/v1/rag/stream_search'), url);
  assert.ok(init.body, 'rag_stream 必须有 body');
  const body = JSON.parse(init.body);
  assert.strictEqual(body.question, '问一句');
  assert.strictEqual(body.citations, true);
});

test('🔴 已知的链名写错 ⇒ 【抛错】，⛔ 不静默回落（回落 = 页面 422 而没人知道）', () => {
  assert.throws(() => RagSse.buildRequest('langgraph', 'q', 't'), /unknown chain/);
});

test('thread_id 与问题都要【编码】（问题里会有 & 与空格）', () => {
  const { url } = RagSse.buildRequest('mcp_chat', 'a&b c', 'x/y');
  assert.ok(!/[\s]/.test(url), `url 里有未编码的空格：${url}`);
  const q = new URL(url, 'http://x').searchParams;
  assert.strictEqual(q.get('question'), 'a&b c');
  assert.strictEqual(q.get('thread_id'), 'x/y');
});

/* ══════════════ 刀 2 · §7.1①：把「答案与原文重合的那几段」找出来 ══════════════
 *
 * 🔴 **为什么不做成"服务端给命中区间"**：`sources` 帧里**没有**任何位置字段
 *    （只有 `index` / `source` / `content` / `similarity`）⇒ 服务端**没给命中区间**。
 *    本仓立场是「**⛔ 不许印没有数据源的东西**」，所以选了一条**真的算得出来**的：
 *    **答案里与这段原文逐字重合的片段** —— 那正是"这句话确实是从这段抄来的"的证据。
 *
 * ⚠️ 找不到重合 ⇒ **返回空数组**，页面**就什么都不高亮**（⛔ 不假装高亮了一段）。
 */
test('overlapRanges：找得出【答案与原文逐字重合】的片段', () => {
  const chunk = '保修期自签收之日起计算，标准为十二个月。撞机属人为损坏。';
  const answer = '根据资料，保修期自签收之日起计算，标准为十二个月。';
  const r = RagSse.overlapRanges(chunk, answer, 6);
  assert.strictEqual(r.length, 1);
  assert.strictEqual(chunk.slice(r[0].start, r[0].end), '保修期自签收之日起计算，标准为十二个月。');
});

test('overlapRanges：重合短于 minLen ⇒ 不返回（⛔ 别把"的"这种单字也标高亮）', () => {
  const r = RagSse.overlapRanges('保修期十二个月', '另外还有三年', 6);
  assert.deepStrictEqual(r, []);
});

test('overlapRanges：多段重合按【位置排序】且【互不重叠】', () => {
  const chunk = 'AAAAAA是保修期，BBBBBB是保修期';
  const r = RagSse.overlapRanges(chunk, 'AAAAAA与BBBBBB', 4);
  const texts = r.map((x) => chunk.slice(x.start, x.end));
  assert.deepStrictEqual(texts, ['AAAAAA', 'BBBBBB']);
  for (let i = 1; i < r.length; i++) assert.ok(r[i].start >= r[i - 1].end, '区间重叠了');
});

test('overlapRanges：空输入 / 空原文 ⇒ 空数组，⛔ 不炸', () => {
  assert.deepStrictEqual(RagSse.overlapRanges('', 'abc', 3), []);
  assert.deepStrictEqual(RagSse.overlapRanges('abc', '', 3), []);
  assert.deepStrictEqual(RagSse.overlapRanges(null, null, 3), []);
});

/* ══════════════ 刀 2 · §7.1②：按「停止」之后，说清【停在哪】 ══════════════
 *
 * 🔴 **它⛔ 不能是"已用 N token"** —— 取消那一瞬后端**根本拿不到 usage**
 *    （`DEC-084`：usage 只在**最后一帧**回来，而我们提前 `aclose()` ⇒ 那帧**到不了**）。
 *    本仓立场：「⛔ **不许印没有数据源的数**」⇒ 给一条**说得出处**的话：
 *    **已经生成了多少字**（本地数得出来）+ **明写"未计费、原因是什么"**。
 */
test('stoppedNotice：数的是【已生成多少字】，并明写"未计费"及原因', () => {
  const s = RagSse.stoppedNotice('保修 期自签 收之日起');
  // ⚠️ 去空格后是 **9** 个字（保·修·期·自·签·收·之·日·起）——
  //    我第一版在这里写的是 7（**数错了**），是这条用例当场把数错抓出来的。
  assert.match(s, /已生成 9 字/, `字数不对：${s}`);
  assert.match(s, /中断|取消/);
  assert.match(s, /未计费/);
});

test('stoppedNotice：一个字都没生成 ⇒ 也要说清（⛔ 别画成"停了但什么都没发生"）', () => {
  const s = RagSse.stoppedNotice('');
  assert.match(s, /0/);
  assert.match(s, /未计费/);
});

test('🔴 stoppedNotice：⛔ 不许出现 "token" 这个数（那个数拿不到，写了就是编）', () => {
  const s = RagSse.stoppedNotice('随便写点什么');
  assert.doesNotMatch(s, /\d+\s*token/i, `不该给 token 数（拿不到）：${s}`);
  assert.doesNotMatch(s, /undefined|NaN/, s);
});
