'use strict';
/* 对话页的**纯逻辑**：帧解析 / 引用映射 / 出口判定。⛔ 本文件不碰 DOM、不发请求。
 *
 * 🔴 为什么单独一个文件：硬门 B / C 标着「最容易假完成」，而本仓立场是
 *    「写不出命令的，就是还没核过」。这几条是**能写成命令**的那部分 ⇒ 抽出来用 node --test 钉住。
 *    DOM 渲染 / 滚动 / 按钮态留在 chat.html 里，仍靠 DevTools 手工（见 DEC-085 §六·3）。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ Node 把 .js 当 CommonJS ⇒ 不能用 import/export。
 *    所以下面是**经典脚本**（浏览器 <script src> 直接用），末尾条件导出给 Node 的 require。
 */

const DONE_SENTINEL = '[DONE]';

/** 把收到的缓冲区切成**完整的** SSE 帧；不完整的尾巴原样留在 rest 里。 */
function parseSseChunk(buffer) {
  const parts = buffer.split('\n\n');
  const rest = parts.pop();                     // 最后一段可能是半截
  const payloads = [];
  for (const block of parts) {
    const line = block.split('\n').find((l) => l.startsWith('data: '));
    if (line === undefined) continue;           // 心跳/注释行（以 ':' 开头）跳过
    const body = line.slice('data: '.length).trim();
    if (body === DONE_SENTINEL) { payloads.push(DONE_SENTINEL); continue; }
    try {
      payloads.push(JSON.parse(body));
    } catch (e) {
      // 🔴 解析不了的帧**跳过**，⛔ 不让它把整条流带崩 —— 服务端加一个未知帧
      //    不该让用户白等一场（前端宁可少显示一帧）。⚠️ 但要打到控制台，别静默。
      console.warn('[sse] 解不出的帧已跳过：', body);
    }
  }
  return { payloads, rest };
}

/** 给一帧 payload 分类。`[DONE]` 是字符串哨兵，⛔ 不是对象。 */
function payloadKind(payload) {
  if (payload === DONE_SENTINEL) return 'done';
  if (payload && typeof payload === 'object') {
    if ('error' in payload) return 'error';
    if ('usage' in payload) return 'usage';
    if ('sources' in payload) return 'sources';
    // 🔴 `F4` ①（`DEC-091`）：无据拒答的信号帧。⚠️ 认不出的帧落到 `'unknown'`，
    //    而 `chat.html` 对 `'unknown'` **什么都不做** ⇒ 老前端遇到这一帧天然兼容（不炸、不误画）。
    if ('no_answer' in payload) return 'no_answer';
    if ('content' in payload) return 'content';
  }
  return 'unknown';
}

/**
 * 把正文切成**有序**片段：`{text}` 是普通文本，`{index}` 是一个引用编号。
 * 渲染层（`chat.html`）用它把 `[来源:2]` 换成可点开的 `<span>`。
 *
 * 🔴 **本函数是引用正则的【唯一一份】** —— `citationIndexes` 由它推导，
 *    页面渲染也走它。⛔ 别在 `chat.html` 里再写一份同款正则：
 *    两处一旦漂移，**画出来的编号与点开的编号不是同一批**，而页面上**不报任何错**
 *    （表现就是"点了没反应"）。本仓已记过同型事故（两处各写一遍 ⇒ 静默错位）。
 * ⚠️ 不吐空片段：没有引用时返回 `[{text: 全文}]`，空串返回 `[]`。
 */
function splitCitations(text) {
  const s = text || '';
  const out = [];
  const re = /\[来源\s*:\s*([0-9]+(?:\s*,\s*[0-9]+)*)\]/g;
  let last = 0, m;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) out.push({ text: s.slice(last, m.index) });
    for (const piece of m[1].split(',')) {
      const n = parseInt(piece.trim(), 10);
      if (!Number.isNaN(n)) out.push({ index: n });
    }
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push({ text: s.slice(last) });
  return out;
}

/** 从答案正文里取出引用编号：`[来源:2]` / `[来源:1, 3]` ⇒ [2] / [1, 3]（去重、保序）。 */
function citationIndexes(text) {
  const out = [];
  for (const seg of splitCitations(text)) {
    if (seg.index !== undefined && !out.includes(seg.index)) out.push(seg.index);
  }
  return out;
}

/**
 * 把正文里的引用编号映射成 `sources` 帧里的那几条。
 *
 * 🔴 **必须按 `sources[i].index` 找，⛔ 不是按数组下标** ——
 *    prompt 让模型吐的编号与帧里的 `index` 同源（`DEC-085` 契约 A），
 *    而数组顺序是**另一个**东西；按下标硬猜的话，谁插一项就静默错位。
 * ⚠️ 编号在 `sources` 里找不到 ⇒ **跳过**，⛔ 不抛（模型偶尔会吐一个不存在的号）。
 */
function resolveCitations(text, sources) {
  const byIndex = new Map((sources || []).map((s) => [s.index, s]));
  return citationIndexes(text)
    .map((i) => byIndex.get(i))
    .filter((s) => s !== undefined)
    .map((s) => ({ index: s.index, source: s.source, content: s.content, hit: true }));
}

/**
 * 一次请求怎么收的场。
 *
 * ⚠️ `sawError` **与** `sawDone` 都要看：本仓 RAG 端点**故意**在出错时**不发** `[DONE]`
 *    （`api_v1_rag.py:_on_error` 的 docstring 写明了），所以"没有 [DONE]"本身
 *    既可能是出错、也可能是用户点了停止 —— 要靠 aborted 分流。
 */
function classifyExit({ sawDone, sawError, aborted }) {
  if (aborted) return 'aborted';
  if (sawError) return 'error';
  if (sawDone) return 'done';
  return 'incomplete';
}

/** 费用显示。`null`/`undefined` ⇒ `—`（⛔ 别显示 `$0.000000`，那是在说"这轮不要钱"）。 */
function formatCost(costUsd) {
  if (costUsd === null || costUsd === undefined) return '—';
  return '$' + Number(costUsd).toFixed(6);
}

/** 缺值统一画成 `—`。⚠️ `0` **不是**缺值（见 `formatSource`）—— 所以判的是 `== null`。 */
function dashIfMissing(v) {
  return (v === null || v === undefined) ? '—' : String(v);
}

/**
 * 引用卡片的**卡片头**（`DEC-089` · 硬门 B 的证真那句）。
 *
 * 🔴 为什么抽到本文件：判定要求「点开能看到 **chunk id + 相似度分**」——
 *    那是**能写成命令**的一句（本仓立场：写不出命令的，就是还没核过）。
 *    ⛔ DOM 不进本文件；这里只把 `sources` 帧里的一条拼成两行文字。
 *
 * ⚠️ 缺字段画 `—`，⛔ 不许把 `undefined` / `NaN` 漏到页面上 ——
 *    非流式那条链（`answer_with_citations.py`）的上下文里**没有** `similarity`，
 *    它会**诚实地**传 `None` 过来。页面上一个 `undefined` 会被读成"这功能坏了"。
 * ⚠️ 但 `similarity: 0` 与"没有相似度"是**两件事**（同 `formatCost` 的立场）：
 *    前者是**真值**，画 `0.000`；后者才是 `—`。
 *
 * @returns {{title: string, meta: string}}
 */
function formatSource(src) {
  const s = src || {};
  const sim = s.similarity;
  const simText = (sim === null || sim === undefined) ? '—' : Number(sim).toFixed(3);
  return {
    title: '[' + dashIfMissing(s.index) + '] ' + dashIfMissing(s.source),
    meta: 'id=' + dashIfMissing(s.id) + ' · 相似度 ' + simText,
  };
}

/**
 * 「再点」的语义（`DEC-089` · 硬门 B 的另一句「再点能跳到原文位置」）。
 *
 * 本仓 2026-10-06 裁定走「**甲 · 就地展开/收起**」：卡片挂在该条回答**下面**，
 * 点引用展开、**再点同一条收起**、点另一条则换内容（⛔ 不是同时开着两张）。
 * ⇒ 页面上只需要记「当前开着哪一条」这一个数，本函数给出它的**下一个值**。
 *
 * @param {number|null} current 当前展开的引用编号（`null` = 都收着）
 * @param {number} clicked 刚点的那一条
 * @returns {number|null}
 */
function toggleOpen(current, clicked) {
  return current === clicked ? null : clicked;
}

/**
 * 🔴 **仍是占位，⛔ 不是真联系入口** —— 上公网前**必须**换掉。
 *
 * 🔴 这个值由**业务方 2026-10-07 当场裁定**：`example@example.com`。
 *    · 选它的理由：`example.com` 是 **RFC 2606 保留域，公网永不解析**
 *      ⇒ 寄到这儿**永远投不出去**，⛔ 不会误投给一个真人。
 *    · ⚠️ 反过来说，`mail.com` 那种**真实运营**的域**不能**当占位地址用 ——
 *      用户照抄发信会真的寄到一个陌生人邮箱里。
 *    ⚠️ 改这一行之前写的是「（待设置 —— 联系入口尚未确定）」—— 那串**自曝没填**；
 *      换成地址之后**看着像真的**，⇒ **本条因此【没有】结清**，仍在
 *      `docs/待办总表.md` 的 `N13` 里挂着。⛔ **别把这次改动静默读成"联系入口已经有了"。**
 *
 * 📌 已登记进 `docs/待办总表.md`，免得它**静默上线**。
 */
const BREAKER_CONTACT = 'example@example.com';

/**
 * 熔断提示卡片的**四件事**（`R3.2` · `DEC-090`）。
 *
 * 🔴 `R3.2` 的验收原文：「卡片上写清四件事 —— **现状 / 这不是故障 / 何时恢复 / 怎么联系**」
 *    （`施工单-本项目.md` §要求 R3）。四件里三件是常量，**只有「何时恢复」随 `scope` 变**。
 *
 * 🔴 为什么 `scope` 非得由后端给：两种熔断的 `ErrorCode` **都是 `QUOTA_EXCEEDED`**
 *    ⇒ 前端不看文案**分不出**是哪种，而两者恢复条件**完全不同**：
 *      · `global`（全站日级 · `B11`）⇒ 全站共享，**做什么都救不回来**，只能等跨天；
 *      · `session`（会话级 · `B8`）  ⇒ 是**你自己这个 thread** 的今日用量
 *        ⇒ **开个新会话立刻能继续**（`chat.html` 有「＋ 新会话」按钮，这句是真做得到的）。
 *
 * ⚠️ 认不出的 `scope`（含缺字段）⇒「何时恢复」画 `—`，⛔ **不猜一个口径** ——
 *    中间件的限流 429 也走同一条 `error` 分支，它**没有** scope；猜成 `global`
 *    会让「明日起恢复」出现在一个**根本没有日级额度**的场合。
 *
 * ⚠️ 「现状」用**后端原话**（里面有「已使用 X / 上限 Y tokens」）⇒ ⛔ 不在这里重编一句
 *    （重编 = 数字口径有两份，会漂移，且**页面上不报错**）。
 *
 * ⛔ DOM 不进本文件 —— 这里只给文字，怎么挂留在 `chat.html`。
 *
 * @param {string} scope `"global"` / `"session"` / 认不出的值
 * @param {string} message 后端 429 响应体里的 `error`
 * @returns {{title: string, items: Array<{k: string, v: string}>}}
 */
function breakerCard(scope, message) {
  const recovery = {
    global: '明日起自动恢复（额度按自然日重置 · 全站共享 · ⛔ 无法提前）',
    session: '开一个新会话立刻可继续（额度按会话计 · 跨天也会重置）',
  }[scope] || '—';
  return {
    title: '额度已用完',
    items: [
      { k: '现状', v: (message === null || message === undefined) ? '—' : String(message) },
      { k: '这不是故障', v: '额度上限是成本控制，不是服务坏了；超出后一律拒绝，⛔ 不是变慢。' },
      { k: '何时恢复', v: recovery },
      { k: '怎么联系', v: BREAKER_CONTACT },
    ],
  };
}

/**
 * 无据拒答时的那条提示（`F4` ① · 硬门 B 的**第二半** · `DEC-091`）。
 *
 * 🔴 后端**只给信号**（一帧 `{"no_answer": true}`），**文案在这里** —— 理由与 `breakerCard` 同源：
 *    文案属于**呈现层**；塞进帧就变成又一份要两边同步的契约。
 *    ⇒ 判据（「这轮算不算拒答」）**只有后端那一份**，前端只认帧（`sse.test.js` 有一条结构型守卫）。
 *
 * ⚠️ 措辞的两条硬约束（都有用例钉着）：
 *    ① **必须指向"资料/文档"** —— 用户能做的只有「换问法」或「先上传相关文档」；
 *       说成"出错/检索失败"会让人去重启、重试、找人修，全是无用功。
 *    ② ⛔ **不许暗示"稍后再试"** —— 无据拒答是**检索＋上下文**的结论，重问同一句不会变；
 *       「稍后再试」是**限流**那种状态的出路（那是 `breakerCard` 管的另一件事）。
 *
 * ⚠️ ⛔ 别说「检索不到片段」 —— 那是**假话**：实测（2026-10-06 spike）拒答那一轮的
 *    `sources` 帧里**照样有 3 条**片段（相似度 0.07–0.77）。真实情况是
 *    **检索到的片段里没有能回答这个问题的内容**，⛔ 不是"检索不到东西"。
 *
 * @returns {{title: string, body: string}}
 */
function refusalNotice() {
  return {
    title: '知识库中没有相关资料',
    body: '回答这个问题需要的信息不在已上传的文档里。换个问法，或先上传相关文档再试。',
  };
}

// 🔴 2026-10-06 施工实测·订正⑨ —— **本文件此前【没有】`RagSse` 这个对象。**
//    起草时 Task 6 的 Interfaces 写着「Produces（全局对象 `RagSse`，浏览器）」，而实现只有
//    末尾那段 `module.exports` ⇒ 顶层函数确实成了全局，但**没有一个叫 `RagSse` 的东西**。
//    ⇒ `chat.html` 里每一处 `RagSse.xxx` 都会 `ReferenceError: RagSse is not defined`。
//    ⚠️ **`node --test` 抓不到它**（用例只走 `module.exports`），页面加载时也**不报**
//       （`RagSse` 第一次被用到是在**答案真的开始流**之后）—— 实测见施工单 Task 8。
//    ⇒ 现在两侧都挂，且下面有两条用例钉住（浏览器那侧用 `node:vm` 造一个假 window 来测）。
const RagSse = {
  DONE_SENTINEL, parseSseChunk, payloadKind, citationIndexes, splitCitations,
  resolveCitations, classifyExit, formatCost, formatSource, toggleOpen, breakerCard,
  refusalNotice,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagSse;                       // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagSse = RagSse;                        // 浏览器（`<script src>` 之后就是全局）
}
