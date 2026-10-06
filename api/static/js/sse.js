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

/** 从答案正文里取出引用编号：`[来源:2]` / `[来源:1, 3]` ⇒ [2] / [1, 3]（去重、保序）。 */
function citationIndexes(text) {
  const out = [];
  const re = /\[来源\s*:\s*([0-9]+(?:\s*,\s*[0-9]+)*)\]/g;
  let m;
  while ((m = re.exec(text || '')) !== null) {
    for (const piece of m[1].split(',')) {
      const n = parseInt(piece.trim(), 10);
      if (!Number.isNaN(n) && !out.includes(n)) out.push(n);
    }
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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    DONE_SENTINEL, parseSseChunk, payloadKind, citationIndexes, resolveCitations,
    classifyExit, formatCost,
  };
}
