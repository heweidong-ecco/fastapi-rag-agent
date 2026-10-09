'use strict';
/* 检索实验室的**纯逻辑**：五条检索接口的请求形状 / 结果归一 / 环境限制提示 / 空态。
 * ⛔ 本文件不碰 DOM、不发请求 —— 与 `panel.js` / `trace.js` 同一形状（经典脚本 + 条件导出）。
 *
 * 🔴 为什么单独一个文件：**这五个入口的名字与落点必须只有一份**。
 *    本仓前科两次：`DEC-089`（引用正则写两处必然漂移）· `DEC-094`
 *    （`approvals.html` 4 条 URL 少 `/api/v1` ⇒ **页面 100% 打不开，而三层判据一条都不红**）。
 *    ⚠️ `api/test_web_pages.py` 只查**页面源码里的字面量** ⇒ **走 helper 的页面它【空过】**。
 *    ⇒ 所以下面这五个 `/api/v1/...` 前缀，靠**本文件的 node 用例**盯着（`lab.test.js`）。
 *
 * ⚠️ 形状说明：本仓【没有 package.json】⇒ Node 把 .js 当 CommonJS ⇒ 不能用 import/export。
 *    所以下面是**经典脚本**（浏览器 <script src> 直接用），末尾条件导出给 Node 的 require。
 */

/* ══════════════ 1 · 五个面板（规格 §2.2 的 5 条检索接口）══════════════
 *
 * 🔴 `path` **必须带 `/api/v1`** —— `DEC-094` 那个事故就是少前缀。
 * 🔴 `score` = 该接口返回的**分数字段名**，三条链**各不相同**：
 *      · `pg_search`      ⇒ `similarity`（余弦，0–1）
 *      · `hybrid`/`rewrite` ⇒ `rrf_score`（RRF 融合分，约 1/(60+rank)，很小 —— ⛔ 别拿 0.7 当阈值）
 *      · `rerank`         ⇒ `rerank_score`（Cross-Encoder logits，可正可负）
 *      · `pipeline`       ⇒ `rrf_score`（开精排时那批还会多一个 `rerank_score`，仍按 rrf 排）
 *    ⇒ **页面不许自己猜字段名** —— 猜错了不报错，只是画出一列空的（本仓最恨的形态）。
 * ⚠️ `needsTorch`：见 `envLimitHint`。
 */
const PANELS = {
  pg:       { path: '/api/v1/rag/pg_search',      score: 'similarity',   name: '纯向量检索' },
  hybrid:   { path: '/api/v1/rag/hybrid_search',  score: 'rrf_score',    name: '混合检索（向量 + BM25 + RRF）' },
  rerank:   { path: '/api/v1/rag/rerank_search',  score: 'rerank_score', name: 'Cross-Encoder 精排', needsTorch: true },
  rewrite:  { path: '/api/v1/rag/rewrite_search', score: 'rrf_score',    name: '查询改写 + 混合检索' },
  pipeline: { path: '/api/v1/rag/search',         score: 'rrf_score',    name: '综合检索（四模式）' },
};

/** `/rag/search` 的 `mode` 是**受限枚举**（`api/api_v1_rag.py` 的 `SearchMode`）⇒ 只能这四个。 */
const PIPELINE_MODES = ['fast', 'accurate', 'accurate_norerank', 'full'];
const MODE_LABELS = {
  fast: 'fast · 最快',
  accurate: 'accurate · 最准（要 torch）',
  accurate_norerank: 'accurate_norerank（默认）',
  full: 'full · 覆盖最全',
};

/** `/rag/search` 响应里 `timing` 各段的**人话名**（⛔ 别在页面上现编）。 */
const TIMING_LABELS = {
  rewrite_ms: '查询改写', search_ms: '多路检索', rerank_ms: '重排', total_ms: '合计',
};

/** `pipeline` 块里那几个开关的**人话名**（⚠️ 与 `timing` 不是一回事，⛔ 别混）。 */
const STAGE_LABELS = {
  rewrite_enabled: '查询改写', expand_enabled: '查询扩展',
  bm25_enabled: 'BM25 关键词', rerank_enabled: 'Cross-Encoder 精排',
};

/** 取一个面板的定义。⛔ 未知 key **抛错**（响亮 > 静默 —— `DEC-051` 那族：
 *  静默回落会让页面上**少一个面板而不报错**）。 */
function panelOf(key) {
  const p = PANELS[key];
  if (!p) throw new Error(`unknown panel: ${key}`);
  return p;
}

/* ══════════════ 2 · 请求形状 ══════════════ */

/** 把 `top_k` 夹进**端点声明的范围**（`api/schemas.py` 的 `QuestionRequest.top_k: ge=1, le=20`）。
 *  ⚠️ 夹在这里而不是"让服务端回 422" —— 用户敲错一个数不该看到一条 422。
 *  ⛔ 非法值（空 / 非数 / <1）**回落 3**（= schema 的默认值），⛔ 不回落 0。 */
function clampTopK(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 1) return 3;
  return Math.min(20, Math.trunc(n));
}

/**
 * 一次面板运行 → `{ path, body, query }`。
 *
 * 🔴 **只有 `rewrite` 与 `pipeline` 带 `thread_id`** —— 那两条端点的签名里有它
 *    （`Query("default", min_length=1)`，`B8` 会话级额度要用）；另三条**没有这个形参**。
 *    ⚠️ 给所有面板都塞 `thread_id` 不会报错（FastAPI 忽略多余 query）——
 *    但那会**撒谎**：读的人以为这三条也按会话计费。⛔ 别"统一一下"。
 * 🔴 `mode` 只属于 `pipeline`；`generate_answer` / `citations` 只在**要生成答案时**才带
 *    —— `citations` 只有在 `generate_answer` 为真时才有效（后端 `answer_with_citations` 那条分支）。
 */
function buildRequest(key, values) {
  const p = panelOf(key);
  const v = values || {};

  const body = { question: v.question, top_k: clampTopK(v.top_k) };

  if (key === 'pipeline') {
    body.mode = PIPELINE_MODES.indexOf(v.mode) >= 0 ? v.mode : 'accurate_norerank';
    if (v.generate_answer) {
      // 🔴 真调 LLM（花钱）—— 只在真勾了的时候带，⛔ 不默认开。
      body.generate_answer = true;
      body.citations = !!v.citations;
    }
  }

  const query = {};
  if (key === 'rewrite' || key === 'pipeline') {
    query.thread_id = v.thread_id || 'default';
  }

  return { path: p.path, body, query };
}

/* ══════════════ 3 · 结果归一 ══════════════ */

function docsOf(payload) {
  return (payload && Array.isArray(payload.docs)) ? payload.docs : [];
}

/**
 * 把一条命中归一成页面要画的几格。
 * 🔴 **分数字段按面板取**；缺了就 `null` —— 页面画 `—`。
 *    ⛔ **绝不编 0**（本仓立场：「不许印没有数据源的数」——`DEC-093` 那两格死卡的前科）。
 */
function rowOf(key, doc) {
  const d = doc || {};
  const field = panelOf(key).score;
  const raw = d[field];
  const missing = raw === undefined || raw === null || raw === '';
  return {
    id: (d.id === undefined || d.id === null) ? null : d.id,
    content: typeof d.content === 'string' ? d.content : '',
    source: (d.source === undefined || d.source === null) ? '' : String(d.source),
    score: missing ? null : raw,
    from: (d.from === undefined || d.from === null) ? null : String(d.from),
  };
}

function rowsOf(key, payload) {
  return docsOf(payload).map((d) => rowOf(key, d));
}

/** `/rag/search` 的 `timing` → `[[人话名, 毫秒], …]`。⚠️ 非管线端点没有它 ⇒ `[]`。 */
function timingRows(payload) {
  const t = payload && payload.timing;
  if (!t || typeof t !== 'object') return [];
  return Object.keys(t).map((k) => [TIMING_LABELS[k] || k, t[k]]);
}

/** `/rag/search` 的 `pipeline` 块 → `[[人话名, 开没开], …]`（⚠️ 是开关，⛔ 不是耗时）。 */
function stageRows(payload) {
  const p = payload && payload.pipeline;
  if (!p || typeof p !== 'object') return [];
  return Object.keys(STAGE_LABELS).map((k) => [STAGE_LABELS[k], p[k] === true]);
}

/** 管线勾了「生成答案」时才会有的正文（⛔ 没勾就是空串，别拿它当"答不出来"）。 */
function answerOf(payload) {
  return (payload && typeof payload.answer === 'string') ? payload.answer : '';
}

/* ══════════════ 4 · 环境限制（🔴 说清"这是环境"，⛔ 不是"坏了"）══════════════
 *
 * `reranker` 要跑 Cross-Encoder，而**演示镜像里没装 torch 系**（`DEC-034`）⇒
 * 创空间那台机器上 `rerank_search` 大概率起不来。
 * 🔴 业务方口径（规格 §3.6）：错态要**说清是环境限制**，让人把它**归给平台/环境**
 *    —— ⛔ 不是当成我们的 bug。
 * ⚠️ 只认 5xx：**401/429 不是环境限制**（那是 key / 额度），别拿这条去盖它们。
 */
function envLimitHint(key, status) {
  const p = panelOf(key);
  if (p.needsTorch && status >= 500) {
    return '精排要跑 Cross-Encoder（torch），而演示镜像里没装 torch 系（DEC-034）'
         + '⇒ 这条在演示机上大概率跑不了。这是【环境限制】，⛔ 不是功能坏了。';
  }
  return null;
}

/** 空态必须解释**为什么空**（`frontend/README.md` §四 第 8 条）。 */
function emptyReason(key) {
  panelOf(key);   // 未知 key ⇒ 抛（与其它入口同款）
  return '这条返回了 0 条。5 条接口都只检索【你自己名下】的文档'
       + '⇒ 空 = 这个用户名下没有命中的文档，⛔ 不是接口坏了。'
       + '先去「知识库」传一篇，再回来问同一个问题。';
}

const RagLab = {
  PANELS, PIPELINE_MODES, MODE_LABELS, TIMING_LABELS, STAGE_LABELS,
  panelOf, clampTopK, buildRequest,
  docsOf, rowOf, rowsOf, timingRows, stageRows, answerOf,
  envLimitHint, emptyReason,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagLab;                       // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagLab = RagLab;                        // 浏览器（`<script src>` 之后就是全局）
}
