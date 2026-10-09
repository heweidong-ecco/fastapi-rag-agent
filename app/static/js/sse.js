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
 * 熔断卡片上「怎么联系」那一行的落点 —— **现为真联系入口**（2026-10-08 业务方给定）。
 *
 * 🔴 **沿革**（⛔ 别把这一行读成"从来就是这个值"）：
 *   · **2026-10-06**：`'（待设置 —— 联系入口尚未确定）'` —— 那串**自曝没填**。
 *   · **2026-10-07**：业务方先给 `example@mail.com` ⇒ 🔴 **核出 `mail.com` 是真实运营的
 *     邮件服务商**（用户照抄发信会**真的寄到一个陌生人邮箱里**）⇒ 当场改判成
 *     `example@example.com` —— **RFC 2606 保留域，公网永不解析**。📄 `DEC-095`。
 *   · ✅ **2026-10-08**：业务方**给出真入口** ⇒ 现值即它。
 *     `N13` 的判据原文就是「**换成一串【真】地址那天，本条才该关**」⇒ **本条已结清**。
 *
 * ⚠️ **保留域（`example.com` / `example.net` / `.invalid` / `.test`）在这一行
 *    从此【不该】再出现** —— 它们是**占位符**，而本行要的是**真能联系上人**的地址。
 * ⚠️ 🔴 **本值没有用例钉** —— `app/static/js/sse.test.js` 只钉「四件事的**键**都在、且非空」
 *    ⇒ **改这个值不会有任何用例红**。**动这一行之前先想清楚**（这条不是提醒，是事实）。
 */
const BREAKER_CONTACT = '3058906131@qq.com';

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
/* ══════════════ 6 · 六条链的调用契约（刀 2 · 2026-10-09）══════════════
 *
 * 🔴 **为什么要有这一块**：6 条链的**请求形状不是同一套**，而**走错一步只会在服务端 422，
 *    前端不报任何错**（拿到 422 走进普通错误分支，用户看到的是"没反应"）。
 *
 * | 链 | 形状 | 问题那个键 |
 * |---|---|---|
 * | `rag_stream` | **JSON body** | `question`（+ **必须** `citations: true`） |
 * | 5 条 `/agent/<链>/stream` | **query 参数** | `question` |
 * | 🔴 `plan_execute` | query 参数 | **`goal`** |
 *
 * 📌 **表里的形状是 2026-10-09 从 `app.openapi()` 逐条核出来的**，⛔ 不是照文档抄的。
 * ⚠️ **`rag_stream` 的 `citations: true` 非传不可**（`DEC-085 §3.3`）：后端默认 `False`
 *    ⇒ 不传就**根本没有 `sources` 帧** ⇒ 引用卡片永远不出现，而**不报错**。
 * ⚠️ 那 5 条**没有 `citations` 参数**（它们的引用是另一套），⛔ 别顺手一起传。
 */
const CHAINS = {
  rag_stream: {
    label: 'RAG 检索 + 引用',
    path: '/api/v1/rag/stream_search',
    qkey: 'question',
    jsonBody: true,
  },
  langgraph_chat: {
    label: 'LangGraph Agent（带人工审批）',
    path: '/api/v1/agent/langgraph_chat/stream',
    qkey: 'question',
  },
  advanced_chat: {
    label: '进阶 Agent（学习型）',
    path: '/api/v1/agent/advanced_chat/stream',
    qkey: 'question',
  },
  memory_chat: {
    label: '带记忆的 Agent',
    path: '/api/v1/agent/memory_chat/stream',
    qkey: 'question',
  },
  mcp_chat: {
    label: 'MCP 工具 Agent',
    path: '/api/v1/agent/mcp_chat/stream',
    qkey: 'question',
  },
  plan_execute: {
    // 🔴 它的问题那个键叫 **`goal`** —— 端点的形参就是 `goal: str`
    //    ⇒ 传 `question` 会 **422**，而前端只会说"出错"，⛔ 不会告诉你是谁传错了。
    label: '先计划、再执行',
    path: '/api/v1/agent/plan_execute/stream',
    qkey: 'goal',
  },
};

const CHAIN_KEYS = Object.keys(CHAINS);

/**
 * 给一条链拼出 `fetch` 要的 `{url, init}`。
 *
 * ⚠️ **`apiKey` 由调用方传进来** —— 本文件是**纯逻辑**（⛔ 不碰 DOM / `localStorage`），
 *    与 `sse.js` 其余部分同一条规矩。
 *
 * @param {string} chainKey `CHAIN_KEYS` 里的某一个
 * @param {string} question 用户那句话（⛔ 空串会被后端 422，调用方先挡）
 * @param {string} threadId 会话 id
 * @param {string} [apiKey] 有就带上 `X-API-Key`
 * @returns {{url: string, init: {method: string, headers: object, body?: string}}}
 */
function buildRequest(chainKey, question, threadId, apiKey) {
  const chain = CHAINS[chainKey];
  if (!chain) {
    // 🔴 **响亮 > 静默**：写错链名就让它当场炸，⛔ 别回落成某一条默认链 ——
    //    回落的表现是"页面没反应"，而**没有任何东西会红**。
    throw new Error(`unknown chain: ${chainKey}`);
  }

  const params = new URLSearchParams();
  params.set(chain.qkey, question);
  params.set('thread_id', threadId);
  const url = `${chain.path}?${params.toString()}`;

  const headers = {};
  if (apiKey) headers['X-API-Key'] = apiKey;

  const init = { method: 'POST', headers };
  if (chain.jsonBody) {
    // ⚠️ 只有真正带 body 的那条才设 Content-Type —— 没 body 却声明 json
    //    在某些代理/框架下会被当成"畸形请求"。
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify({ [chain.qkey]: question, citations: true });
  }
  return { url, init };
}

/* ══════════════ 7 · 「答案与原文重合的那几段」（刀 2 · §7.1①）══════════════
 *
 * 🔴 **先说清它【不是】什么**：它 **⛔ 不是"服务端给的命中区间"** ——
 *    `sources` 帧里**没有**任何位置字段（只有 `index` / `source` / `content` / `similarity`）。
 *    本仓立场：「**⛔ 不许印没有数据源的东西**」⇒ 所以选了一条**真算得出来**的替代：
 *    **答案与这段原文【逐字重合】的片段** —— 那正是「这句话确实是从这段抄来的」的证据。
 *
 * ⚠️ **找不到重合 ⇒ 返回空数组，页面就什么都不高亮** —— ⛔ 不假装高亮了一段。
 * ⚠️ 算法是 O(n·m) 的最长公共子串扫描（语料是几百字，够用；⛔ 别拿去跑长文）。
 *
 * @param {string} text 原文（`sources[i].content`）
 * @param {string} other 拿来找重合的文本（这里是**答案正文**）
 * @param {number} minLen 多短算"太短、别高亮"（中文建议 ≥ 6 —— 否则「保修期」这种词会满屏标黄）
 * @returns {Array<{start: number, end: number}>} 按位置排序、互不重叠
 */
function overlapRanges(text, other, minLen) {
  const a = String(text == null ? '' : text);
  const b = String(other == null ? '' : other);
  const n = a.length, m = b.length;
  if (!n || !m) return [];
  const min = Math.max(1, Number(minLen) || 1);

  // dp[j] = 以 a[i-1] 与 b[j-1] 结尾的最长公共后缀长度（滚动数组）
  const dp = new Array(m + 1).fill(0);
  const found = [];
  for (let i = 1; i <= n; i++) {
    let prev = 0;
    for (let j = 1; j <= m; j++) {
      const carry = dp[j];
      if (a[i - 1] === b[j - 1]) {
        dp[j] = prev + 1;
        // ⚠️ 这里会把"长命中的每一个后缀"都收进来 ⇒ 后面必须去重（否则会标出一堆互相嵌套的黄块）
        if (dp[j] >= min) found.push([i - dp[j], i]);
      } else {
        dp[j] = 0;
      }
      prev = carry;
    }
  }
  if (!found.length) return [];

  // 长优先、同长靠左 —— 贪心挑【互不重叠】的；被包住的那些自然落选
  found.sort((x, y) => (y[1] - y[0]) - (x[1] - x[0]) || x[0] - y[0]);
  const picked = [];
  for (const [s, e] of found) {
    if (picked.some(([ps, pe]) => s < pe && ps < e)) continue;
    picked.push([s, e]);
  }
  picked.sort((x, y) => x[0] - y[0]);
  return picked.map(([s, e]) => ({ start: s, end: e }));
}

/* ══════════════ 8 · 「按了停止，它停在哪」（刀 2 · §7.1②）══════════════
 *
 * 🔴 **它⛔ 不是"已用 N token"** —— 取消那一瞬后端**拿不到 usage**
 *    （`DEC-084`：usage 只在**最后一帧**回来，而我们提前 `aclose()` ⇒ **那帧到不了**）。
 *    本仓立场：「⛔ **不许印没有数据源的数**」⇒ 这一行只给**说得出处**的两样：
 *    ① **已经生成了多少字**（本地数得出来）② **未计费 + 原因**。
 *
 * ⚠️ **别"顺手"把它改成 token 数** —— 那会让人以为这一轮花了钱，而账上根本没有那一笔。
 */
function stoppedNotice(generated) {
  const n = String(generated == null ? '' : generated).replace(/\s/g, '').length;
  return `已生成 ${n} 字 · 中断未计费（取消时那一帧 usage 到不了）`;
}

const RagSse = {
  DONE_SENTINEL, parseSseChunk, payloadKind, citationIndexes, splitCitations,
  resolveCitations, classifyExit, formatCost, formatSource, toggleOpen, breakerCard,
  refusalNotice,
  CHAINS, CHAIN_KEYS, buildRequest, overlapRanges, stoppedNotice,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagSse;                       // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagSse = RagSse;                        // 浏览器（`<script src>` 之后就是全局）
}
