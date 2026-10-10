'use strict';
/* 运维探针页的**纯逻辑**：四个面板的路径/方法/口径 + 结果归一 + 格式化。
 * ⛔ 本文件不碰 DOM、不发请求 —— 与 `panel.js` / `lab.js` / `cost.js` / `tools.js` / `system.js` 同一形状。
 *
 * 🔴 本页两件最容易写错的事（都在下面各自那一段里）：
 *    ① **四格都【不带参数】** —— 2026-10-10（`DEC-141`）把两条的 `{user_name}` 路径参数删了，
 *       现在**只查调用者自己** ⇒ 这一页**没有任何输入框**
 *    ② **口径只有两态**（Redis / 真库）—— 但其中两格里的 `capacity` / `rate`
 *       是【代码常量】而不是实时值 ⇒ 要单独标出来（⛔ 别一律当"实时")
 */

/* ══════════════ 1 · 四个面板（规格 §2.12 的 4 条）══════════════
 *
 * 🔴 为什么这 4 条能被访客点开（而 2026-10-10 之前不能）：
 *    它们是 `Depends(require_admin)`（`DEC-065`），⇒ 访客拿普通 key 点开**4 格全 403**。
 *    而规格 §3.7 明写这页承载「**限流真的生效**」这条证据、且「**看不见 = 等于没做**」。
 *    ⇒ `DEC-141` 把**越权面本身删掉**（两条的 `{user_name}` 路径参数没了、永远查自己），
 *      4 条改挂 `get_current_user_hybrid`（登录即可）。⛔ **不是**"放宽管理员校验"。
 *
 * ⚠️ **`capacity` / `rate` 是代码常量**（`billing/token_config.py` 的
 *    `USER_LIMIT_CAPACITY` / `USER_LIMIT_RATE`）—— 桶里**剩多少**才是实时的。
 *
 * ⚠️ **`quota` 的数字单位是 token，⛔ 不是"次数"**（`DEC-046` 换过口径，**字段名一个字没改**）。
 */
const PANELS = {
  cache: { path: '/api/v1/debug/cache_stats', name: '缓存键统计',   method: 'GET', source: 'redis', group: 'global' },
  count: { path: '/api/v1/debug/count',       name: '文档总数',     method: 'GET', source: 'db',    group: 'global' },
  quota: { path: '/api/v1/debug/quota',       name: '我的日配额',   method: 'GET', source: 'db',    group: 'mine' },
  rate:  { path: '/api/v1/debug/rate_limit',  name: '我的限流桶',   method: 'GET', source: 'redis', group: 'mine' },
};

/** 口径徽标的**文案**（页面标题上那个角标的 title）—— ⛔ 别在 HTML 里再抄一遍。 */
const SOURCE_LABELS = {
  redis: 'Redis 里现在的样子 —— ⛔ 不是进程内存',
  db:    '真库（读行）—— 不是缓存',
};

/** 口径徽标的**短名**（印在角标上，一句话以内）。 */
const SOURCE_BADGES = { redis: 'Redis', db: '真库' };

/** 口径徽标的 class（`ops.html` 的 `<style>` 里定义 —— 两态两色，⛔ 不许长成一个样）。 */
const SOURCE_CLASSES = { redis: 'src-redis', db: 'src-db' };

/** 取一个面板的定义。⛔ 未知 key **抛错**（响亮 > 静默 —— `DEC-051` 那族）。 */
function panelOf(key) {
  const p = PANELS[key];
  if (!p) throw new Error(`unknown panel: ${key}`);
  return p;
}

function sourceOf(key) { return panelOf(key).source; }
function sourceBadge(key) { return SOURCE_BADGES[sourceOf(key)]; }
function sourceClassOf(key) { return SOURCE_CLASSES[sourceOf(key)]; }

/* ══════════════ 2 · 请求形状 ══════════════
 *
 * 🔴🔴 **四格【一个参数都不带】** —— 这是本页最容易被"顺手"改坏的一处：
 *    2026-10-10 之前那两条是 `/debug/quota/{user_name}`，**参数在路径上**；
 *    `DEC-141` 之后**路径里已经没有那个位置了**。
 *    ⚠️ 别照别的页面的习惯给它补一个 `user_name` 输入框 —— 服务端**根本不收**，
 *      而页面**不会报错**（参数被静默忽略，查的仍是调用者自己）。
 *    ⚠️ 同族的坑见 `tools.js` / `system.js`：那两页有 POST 但参数在 query；
 *      本页更简单 —— **GET，且无参**。
 */
function buildRequest(key, values) {
  const p = panelOf(key);
  void values;                       // ⚠️ 收这个形参只为与另几页同形；本页**没人用它**
  return { path: p.path, method: p.method, query: {} };
}

/* ══════════════ 3 · 口径与警示 ══════════════
 *
 * ⚠️ 四格**各说各的**，⛔ 不是同一句 —— 它们踩的坑不一样。
 * ⛔ 这些话会**原样印到页面上**（`textContent`）⇒ **不许带 markdown 记号**（本文件有守卫钉着）。
 */

/**
 * 该面板要不要挂一条"**这一格最容易被误读成什么**"的警示条。
 * 🔴 四格里有三格挂的是**归因**（把"看起来像故障"的现象归到真原因上）——
 *    那是本页存在的理由：它摆的全是**看起来像坏了、其实正常**的数。
 */
function persistenceWarning(key) {
  if (key === 'cache') {
    return '这一格读的是 Redis（emb: 开头的键）。⚠️ 看到 0 ⛔ 不等于缓存坏了 —— '
         + '一条 embedding 都还没被缓存过就自然是 0（先跑一次检索再回来看）。';
  }
  if (key === 'count') {
    return '这一格直查 documents 的 count(*)，是【全站口径】。⚠️ 平台重启会清空数据 ⇒ '
         + '这个数会变小，那是平台限制、⛔ 不是丢数据事故。';
  }
  if (key === 'quota') {
    return '⚠️ 数字单位是 token，⛔ 不是"次数" —— 2026-10-03 换过口径，而'
         + '字段名（daily_limit / remaining）一个字都没改，⛔ 别按字面读成"还能问几次"。';
  }
  return '🔴 这一格有四分之三不是"实时"的：剩多少令牌是实时的，而'
       + '桶容量与补充速率是【代码里的常量】—— 它们不会因为你用得猛而变。';
}

/**
 * 该面板"这一格的数是【谁的】"。
 * 🔴 与上面那条**分工不同**：上面说"这数从哪来"，这条说"这数属于谁"。
 */
function scopeNote(key) {
  if (key === 'cache') return '这一格是【全站口径】—— Redis 里所有嵌入缓存键，⛔ 不分是谁请求的。';
  if (key === 'count') return '这一格是【全站口径】—— 整个知识库里有多少篇文档，⛔ 不是"你传了几篇"。';
  if (key === 'quota') {
    return '这一格是【你自己的】—— 服务端只认调用者，⛔ 查不了别人（路径里已经放不下别人的名字了）。';
  }
  return '这一格是【你自己的】—— 你这个用户的令牌桶；⛔ 同上，看不到别人的桶。';
}

/* ══════════════ 4 · 取值与格式化 ══════════════ */

/** 🔴 缺值一律画 `—`，⛔ **绝不编 0**（本仓立场：不许印没有数据源的数）。 */
function show(v) {
  if (v === undefined || v === null || v === '') return '—';
  return String(v);
}

function _finiteOrNull(v) {
  if (v === undefined || v === null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** ⚠️ `daily_limit` 可能是字符串「无限」（预算为 `inf` 时）⇒ 那时**原样印**，⛔ 别去 `Number()`。 */
function fmtNum(v) {
  const n = _finiteOrNull(v);
  return n === null ? show(v) : n.toLocaleString('en-US');
}

/** 角色名 → 中文。⛔ 认不出的**原样印**（别吞成"未知" —— 那会丢掉后端真说的话）。 */
function roleText(r) {
  if (r === 'admin') return 'admin（管理员）';
  if (r === 'free') return 'free（免费档）';
  if (r === 'pro') return 'pro（专业档）';
  if (r === undefined || r === null || r === '') return '—';
  return String(r);
}

/**
 * 🔴 非 2xx 时后端回的**是另一个形状**（`{error, code, status_code}`）——
 *    它**没有** `cached_embeddings_count` / `total_documents` 那些键。
 *    ⇒ 页面要先认这个形状，⛔ 别硬按 200 那支读（那会画出一排 `—`，看起来像"后端回了空")。
 */
function errorPayloadOf(p) {
  if (!p || typeof p !== 'object') return null;
  if (typeof p.error !== 'string') return null;
  return { message: p.error, code: show(p.code), statusCode: show(p.status_code) };
}

/* ══════════════ 5 · 每个面板的展示模型 ══════════════
 *
 * 🔴 每一条都**只读它自己那个端点真给的键** —— 键**从 `app/routing/api_v1.py` 抄**。
 *    拼错键不会报错，只会画一排 `—`（本仓前科：`DEC-047`）。
 */

function kvRows(key, p) {
  const payload = p || {};

  // 🔴 先认**错误形状** —— 401 / 403 那支与 200 那支**键完全不同**
  const err = errorPayloadOf(payload);
  if (err) {
    return [['后端说', err.message], ['错误码', err.code], ['HTTP', err.statusCode]];
  }

  switch (key) {
    case 'cache':
      return [['缓存的嵌入条数', fmtNum(payload.cached_embeddings_count)]];
    case 'count':
      return [['库里的文档总数', fmtNum(payload.total_documents)]];
    case 'quota':
      return [
        ['用户', show(payload.user_name)],
        ['角色', roleText(payload.role)],
        ['每日上限（token）', fmtNum(payload.daily_limit)],
        ['今日已用（token）', fmtNum(payload.used_today)],
        ['剩余（token）', fmtNum(payload.remaining)],
      ];
    case 'rate':
      return [
        ['用户', show(payload.user_name)],
        ['桶里还剩的令牌', fmtNum(payload.remaining_tokens)],
        ['桶容量（代码常量）', fmtNum(payload.capacity)],
        ['补充速率（代码常量）', fmtNum(payload.rate)],
      ];
    default:
      return [];
  }
}

/** 表格型面板：`{cols, rows}`；不是表格 ⇒ `null`。
 *
 * 🔴🔴 **一行都没有时也回 `null`**（2026-10-10 点出来的 · 见 `isEmpty` 上面那段）。
 *    ⛔ 别把它改回"照画一张只有表头的表" —— 那在读的人眼里**就是坏了**。
 */
function tableOf(key, p) {
  const payload = p || {};
  if (errorPayloadOf(payload)) return null;
  if (key === 'cache') {
    // 🔴 `sample_keys` 是**最多 5 个**样本键 —— 逐条列出来。
    //    ⚠️ **它是 Redis 的键名，原样回**（⛔ 没有脱敏）⇒ 页面**照原样显示**，不做解释性加工。
    const keys = Array.isArray(payload.sample_keys) ? payload.sample_keys : [];
    if (!keys.length) return null;          // 🔴 空表不画（改见上）
    return { cols: ['样本键（最多 5 个）'], rows: keys.map((k) => [show(k)]) };
  }
  return null;
}

/**
 * 🔴🔴 **这一格的数据"是不是空的"** —— 空态提示条该不该出来，**由它说了算**。
 *
 * ## 为什么必须单独有这么一条（2026-10-10 **点出来**的真缺陷）
 *
 * 开工时页面用的是别页那套判据：`kv 为空 且 表格为空 ⇒ 画空态`。
 * 而本页**四格全部**都会画出非空的 `kv`（哪怕端点是空的那支）：
 * · `cache` 回 `{cached_embeddings_count: 0, sample_keys: []}` ⇒ kv 有一行「缓存的嵌入条数 0」
 * · `quota` 回什么都会有那 5 行（缺的键画 `—`）
 * ⇒ **那个条件永远不成立 ⇒ 空态提示条一次都不会出现。**
 *
 * 🔴 后果**正好打在施工单点名的那一条上**：要求写「**缓存统计为 0 ≠ 坏了** ⇒ 必须解释为什么空」，
 *    而实际页面上**只有一句 `0`**、外加一张**只有表头、零行**的空表 ——
 *    读的人看到的**就是"坏了"**，⛔ 恰恰是这条要求要防的。
 * ⚠️ 而当时 **11 条页面守卫 + 29 条 JS 用例全绿** —— 它们判的是"`emptyReason` 有没有那句话"，
 *    ⛔ **一条都不判它有没有被画出来**（本仓原话：「**用例全绿证不了页面没坏**」）。
 *    ⇒ 所以这条判据现在**是可单测的纯逻辑**（在 `ops.test.js` 里），⛔ 不再只靠截屏。
 *
 * ⚠️ 四格「算空」的定义**各不相同** —— 它们空的原因不一样（见 `emptyReason`）。
 */
function isEmpty(key, p) {
  const payload = p || {};
  if (errorPayloadOf(payload)) return false;      // 错就是错，⛔ 别当成"空"

  /** 「压根没这个值」—— ⚠️ **⛔ 不是「不是数字」**：`remaining` 可以是字符串「无限」。 */
  const blank = (v) => v === undefined || v === null || v === '';
  /** 「数出来是 0」—— ⚠️ 用 `Number()` 而**不是** `_finiteOrNull`：
   *  后者对 `'无限'` / `'abc'` 也回 `null` ⇒ 会把**有数据**的那格判成空。 */
  const isZero = (v) => !blank(v) && Number(v) === 0;

  switch (key) {
    case 'cache': return blank(payload.cached_embeddings_count) || isZero(payload.cached_embeddings_count);
    case 'count': return blank(payload.total_documents) || isZero(payload.total_documents);
    // ⚠️ 这两格看的是「**那两个键在不在**」，⛔ 不是「数是不是 0」——
    //    `remaining = 0` 是**有效值**（桶空了 / 额度用完了），那正是要看见的，⛔ 不是"没数据"。
    case 'quota': return blank(payload.remaining);
    case 'rate':  return blank(payload.remaining_tokens);
    default: return false;
  }
}

/** 截断提示（`test_truncation_declared.py` 那道门管的两种形状）。 */
function truncationNotice(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.has_more === true) return '还有下一页。';
  if (payload.truncated === true) return `结果被截断了 —— 服务端一共有 ${payload.total} 条。`;
  return null;
}

/**
 * 空态必须解释**为什么空**（`frontend/README.md` §四 第 8 条）。
 * 🔴 四格的"为什么空"**⛔ 不是同一句话** —— 而这**正是本页的立意**：
 *    这一页摆的全是"**看起来像坏了、其实正常**"的数。
 */
function emptyReason(key) {
  switch (key) {
    case 'cache':
      return '缓存里现在是 0 条 —— ⛔ 它不是坏了：还没有 embedding 被缓存过就自然是 0'
           + '（先跑一次检索，或看看是不是本来就没缓存过）。';
    case 'count':
      return '库里的文档总数是 0 —— 那说明当前库里没有文档（⚠️ 平台重启清空数据后就是这个样子），'
           + '⛔ 不是这条接口坏了。';
    case 'quota':
      return '没读到配额字段 —— 它在服务端固定回 user_name / role / daily_limit / remaining / used_today，'
           + '不该空 ⇒ 多半是返回形状变了，先核后端。';
    case 'rate':
      return '没读到限流桶字段 —— 它在服务端固定回 remaining_tokens / capacity / rate，'
           + '不该空 ⇒ 多半是返回形状变了，先核后端。';
    default:
      return '这一格现在没有数据 —— 要么还没跑过，要么来源本身就是空的（⛔ 不等于坏了）。';
  }
}

const RagOps = {
  PANELS, SOURCE_LABELS, SOURCE_BADGES, SOURCE_CLASSES,
  panelOf, sourceOf, sourceBadge, sourceClassOf,
  buildRequest,
  persistenceWarning, scopeNote,
  show, fmtNum, roleText, errorPayloadOf,
  kvRows, tableOf, truncationNotice, emptyReason, isEmpty,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = RagOps;                       // Node（`node --test` / `require`）
}
if (typeof window !== 'undefined') {
  window.RagOps = RagOps;                        // 浏览器（`<script src>` 之后就是全局）
}
