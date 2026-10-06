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

// 🔴 2026-10-06 施工实测·订正⑨ —— **本文件此前【没有】`RagSse` 这个对象。**
//    起草时 Task 6 的 Interfaces 写着「Produces（全局对象 `RagSse`，浏览器）」，而实现只有
//    末尾那段 `module.exports` ⇒ 顶层函数确实成了全局，但**没有一个叫 `RagSse` 的东西**。
//    ⇒ `chat.html` 里每一处 `RagSse.xxx` 都会 `ReferenceError: RagSse is not defined`。
//    ⚠️ **`node --test` 抓不到它**（用例只走 `module.exports`），页面加载时也**不报**
//       （`RagSse` 第一次被用到是在**答案真的开始流**之后）—— 实测见施工单 Task 8。
//    ⇒ 现在两侧都挂，且下面有两条用例钉住（浏览器那侧用 `node:vm` 造一个假 window 来测）。
const RagSse = {
  DONE_SENTINEL, parseSseChunk, payloadKind, citationIndexes, splitCitations,
  resolveCitations, classifyExit, formatCost, formatSource, toggleOpen,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagSse;                       // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagSse = RagSse;                        // 浏览器（`<script src>` 之后就是全局）
}
