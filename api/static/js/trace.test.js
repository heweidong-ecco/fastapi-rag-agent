'use strict';
/* `trace.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test api/static/js/trace.test.js（已接进 ci.yml 的 run 块） */
const test = require('node:test');
const assert = require('node:assert');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const {
  formatYuan, formatMs, formatInt, formatWhen, parseWhen,
  summarizeCost, summarizeTrace, summarizeDecisions, emptyTraceReason,
  buildPath, buildCostPath, readThreadId,
} = require('./trace.js');

// ==================== ① formatYuan —— 金额一律 4 位小数（单位：元） ====================

test('formatYuan 四位小数', () => {
  assert.strictEqual(formatYuan(0.013569), '¥0.0136');
  assert.strictEqual(formatYuan(0), '¥0.0000');
  assert.strictEqual(formatYuan(12.5), '¥12.5000');
});

test('formatYuan 缺值回 -- 而不是 ¥0.0000', () => {
  // 🔴 这一条是**故意的**：`¥0.0000` 与"真的没花钱"长得一模一样。
  //    ⛔ 缺值不许伪装成零（本页上一版的「总花费」卡就是这么骗了人一整轮）。
  for (const v of [null, undefined, '', 'abc', NaN]) {
    assert.strictEqual(formatYuan(v), '--', `${String(v)} 应回 --`);
  }
});

// ==================== ② formatMs / formatInt ====================

test('formatMs 秒与毫秒分界', () => {
  assert.strictEqual(formatMs(0), '0ms');
  assert.strictEqual(formatMs(123.4), '123ms');
  assert.strictEqual(formatMs(999), '999ms');
  assert.strictEqual(formatMs(1000), '1.0s');
  assert.strictEqual(formatMs(12345), '12.3s');
});

test('formatMs / formatInt 缺值回 --', () => {
  assert.strictEqual(formatMs(null), '--');
  assert.strictEqual(formatMs(undefined), '--');
  assert.strictEqual(formatInt(null), '--');
  assert.strictEqual(formatInt(4216), '4216');
});

// ==================== ③ 时间：🔴 缺时区标记一律回 -- ====================

test('parseWhen 认得出这一串带不带时区', () => {
  assert.ok(parseWhen('2026-09-20T09:16:22.280863+00:00'), '+00:00 应认');
  assert.ok(parseWhen('2026-09-20T09:16:22Z'), 'Z 应认');
  assert.ok(parseWhen('2026-09-20T17:16:22+08:00'), '+08:00 应认');
});

test('parseWhen 拒绝不带时区的时间戳', () => {
  /* 🔴 **本文件最要紧的一条**。
     `token_usage_logs.created_at` 是 TIMESTAMP（无时区），PG 容器是 Etc/UTC。
     后端若忘了标区，`new Date("2026-09-20T09:16:22")` 会被 JS **当成浏览器本地时间**
     ⇒ 东八区用户看到的时刻静默早 8 小时，**且不报任何错**。
     ⇒ 这里宁可显示 `--`（看得见的缺失），也不显示一个错时刻（看不见的错误）。 */
  assert.strictEqual(parseWhen('2026-09-20T09:16:22'), null, '不带区的时间戳必须拒绝');
  assert.strictEqual(parseWhen('2026-09-20T09:16:22.280863'), null, '不带区的必须拒绝');
  assert.strictEqual(formatWhen('2026-09-20T09:16:22'), '--');
  assert.strictEqual(formatWhen(null), '--');
  assert.strictEqual(formatWhen(''), '--');
  assert.strictEqual(formatWhen(1234567890), '--', '⛔ 不接数字时间戳（那是另一种口径）');
});

test('parseWhen 解出的是【绝对时刻】，与本机时区无关', () => {
  // ⚠️ 断言用的是 getTime()（绝对毫秒）—— 换台时区不同的机器跑照样绿。
  //    这正是它比"比字符串"强的地方：字符串依赖本机时区，会随 CI 机器变。
  const d = parseWhen('2026-09-20T09:16:22.280+00:00');
  assert.strictEqual(d.getTime(), Date.UTC(2026, 8, 20, 9, 16, 22, 280));

  // 同一时刻的两种写法必须解出同一个瞬间（东八区写法 = UTC 写法 + 8h）
  assert.strictEqual(
    parseWhen('2026-09-20T17:16:22+08:00').getTime(),
    parseWhen('2026-09-20T09:16:22+00:00').getTime(),
  );
});

test('formatWhen 按本机时区渲染（不是 UTC）', () => {
  // ⚠️ 断言写成"与本机 getHours() 一致"⇒ 换时区跑也成立（比死磕一个字符串稳）
  const iso = '2026-09-20T09:16:22.280+00:00';
  const d = parseWhen(iso);
  const expected = d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0') + ' ' +
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0') + ':' +
    String(d.getSeconds()).padStart(2, '0');
  assert.strictEqual(formatWhen(iso), expected);
});

// ==================== ④ summarizeCost —— 合计来自服务端，页面不自己求和 ====================

const COST_JSON = {
  thread_id: 'default',
  items: [
    { purpose: 'answer_generation', model: 'qwen-turbo', prompt_tokens: 100, completion_tokens: 84,
      total_tokens: 184, cost: 0.0008, created_at: '2026-09-20T09:16:22.280863+00:00' },
    { purpose: 'agent_decision', model: 'qwen-turbo', prompt_tokens: 900, completion_tokens: 100,
      total_tokens: 1000, cost: 0.0030, created_at: '2026-09-20T09:16:21.059600+00:00' },
  ],
  total: { count: 50, total_tokens: 4216, total_cost: 0.013569 },
  truncated: true,
};

test('summarizeCost 直接用服务端的合计，⛔ 不把 rows 加起来', () => {
  /* 🔴 明细有 LIMIT（`token_tracker._BREAKDOWN_LIMIT`）⇒ 页面自己求和会让"总花费"
     在笔数多时**静默变小**且不报错。服务端那两条 SQL 才是唯一权威。
     ⇒ 这里故意给一个**和 rows 对不上**的 total（0.013569 vs 两行之和 0.0038），
       断言拿到的是**服务端那个**。
     （反证检验：把实现改成 `rows.reduce(...)` ⇒ 本条立刻红。） */
  const out = summarizeCost(COST_JSON);
  assert.strictEqual(out.totalCost, 0.013569);
  assert.strictEqual(out.totalTokens, 4216);
  assert.strictEqual(out.count, 50);
  assert.strictEqual(out.rows.length, 2);
  assert.notStrictEqual(out.totalCost, out.rows.reduce((s, r) => s + r.cost, 0));
});

test('summarizeCost 报截断', () => {
  assert.strictEqual(summarizeCost(COST_JSON).truncated, true);
  // 条数对得上 ⇒ 不许报截断（否则页面永远挂个假警告）
  const full = { items: COST_JSON.items, total: { count: 2, total_tokens: 1184, total_cost: 0.0038 } };
  assert.strictEqual(summarizeCost(full).truncated, false);
});

test('summarizeCost 对空响应与畸形响应都不炸', () => {
  for (const bad of [null, undefined, {}, { items: null }]) {
    const out = summarizeCost(bad);
    assert.strictEqual(out.ok, false);
    assert.deepStrictEqual(out.rows, []);
    assert.strictEqual(out.totalCost, 0);
  }
  const empty = summarizeCost({ items: [], total: { count: 0, total_tokens: 0, total_cost: 0 } });
  assert.strictEqual(empty.ok, true);
  assert.strictEqual(empty.count, 0);
});

test('summarizeCost 每行都带格式化好的时间', () => {
  const out = summarizeCost(COST_JSON);
  assert.notStrictEqual(out.rows[0].when, '--', '带区的时间应当渲染出来');
  assert.strictEqual(out.rows[0].purpose, 'answer_generation');
});

test('summarizeCost 对缺字段的行给占位，不给 undefined', () => {
  const out = summarizeCost({ items: [{ }], total: { count: 1, total_tokens: 0, total_cost: 0 } });
  assert.strictEqual(out.rows[0].purpose, '(未标用途)');
  assert.strictEqual(out.rows[0].model, '--');
  assert.strictEqual(out.rows[0].when, '--');
});

// ==================== ⑤ summarizeTrace —— 追踪轴 ====================

test('summarizeTrace 认得出"没找到"（服务端用 error 键表示）', () => {
  const out = summarizeTrace({ error: '未找到线程 default 的执行轨迹' });
  assert.strictEqual(out.hasTrace, false);
  assert.strictEqual(out.notFound, true);
  assert.strictEqual(out.error, '未找到线程 default 的执行轨迹');
  assert.deepStrictEqual(out.steps, []);
});

test('summarizeTrace 正常轨迹', () => {
  const out = summarizeTrace({
    trace: {
      thread_id: 'default', user_query: '北京天气', duration_ms: 1234.5,
      tool_calls: [
        { tool_name: 'search', status: 'success', duration_ms: 120, result: 'ok', arguments: { q: 'x' } },
        { tool_name: 'calc', status: 'error', duration_ms: 5, error_message: '炸了' },
      ],
      agent_decisions: [], final_output: '答案',
      total_tokens: 0, total_cost: 0,
    },
    requested_by: 'admin',
  });
  assert.strictEqual(out.hasTrace, true);
  assert.strictEqual(out.threadId, 'default');
  assert.strictEqual(out.toolCount, 2);
  assert.strictEqual(out.steps[0].name, 'search');
  assert.strictEqual(out.steps[1].status, 'error');
  assert.strictEqual(out.steps[1].errorMessage, '炸了');
  assert.strictEqual(out.finalOutput, '答案');
});

test('summarizeTrace 对空工具调用与畸形输入都不炸', () => {
  assert.deepStrictEqual(summarizeTrace(null).steps, []);
  assert.strictEqual(summarizeTrace(null).hasTrace, false);
  const t = summarizeTrace({ trace: { thread_id: 'x' } });
  assert.strictEqual(t.toolCount, 0);
  assert.strictEqual(t.durationMs, null);
});

test('summarizeDecisions 不假设决策的形状', () => {
  // `tool_visualizer.record_agent_decision` 收的是调用方给的任意 dict ⇒ 只做摘要
  const out = summarizeDecisions([{ action: 'retry', n: 2 }, 'plain', null, { big: 'x'.repeat(200) }]);
  assert.strictEqual(out.length, 4);
  assert.match(out[0].text, /action=retry/);
  assert.strictEqual(out[1].text, 'plain');
  assert.ok(out[3].text.length < 120, '长值要截断，别把页面撑爆');
  assert.deepStrictEqual(summarizeDecisions(null), []);
});

// ==================== ⑥ emptyTraceReason —— 空的时候必须解释为什么 ====================

test('有轨迹时不返回任何理由', () => {
  assert.strictEqual(emptyTraceReason({ hasTrace: true }), null);
});

test('🔴 有成本记录但没轨迹 ⇒ 必须把两条真原因都解释出来', () => {
  /* 靶子没变：**花钱了却没轨迹，页面必须解释清楚**（那是唯一能阻止
     "看起来整个功能坏了"的东西）。
     🔴 但 **2026-10-08（`N16`）改过文案** —— 旧文案写的是「走的是检索链，而本仓目前
     **只有 Agent 链**会写轨迹」，而 `N16` 之后 `/rag/stream_search` **也建轨迹了**
     ⇒ 那句**变成了假话**。旧的断言 `assert.match(s, /检索链/)` 是那句假话的**翻版**
     ⇒ 留着它会把假话**钉死**，所以一并改掉。
     ⚠️ 本条的靶子是「**有没有解释清楚**」，⛔ 不是「页面上有没有出现某三个字」。 */
  const s = emptyTraceReason({ hasTrace: false, costCount: 6 });
  assert.match(s, /6 笔模型调用记录/, '要点出"确实发生过"的那个证据');
  assert.match(s, /不建轨迹/, '要说清"那条链不建轨迹"这条原因');
  assert.match(s, /重启/, '也要给出"重启即空"这条原因（两种都可能，页面分不出来）');
  assert.match(s, /stream_search/, '要点出【哪些】链会建，⛔ 不是含糊说"有些链"');
  assert.match(s, /下半页/, '要说清成本账是完整的 —— 别让人以为整个功能坏了');
});

test('一点记录都没有 ⇒ 要点出"重启即空"', () => {
  const s = emptyTraceReason({ hasTrace: false, costCount: 0 });
  assert.match(s, /重启/);
  assert.match(s, /内存/);
  assert.match(s, /PostgreSQL|不受重启影响/);
});

test('读轨迹本身失败 ⇒ 直接说是失败，不编原因', () => {
  const s = emptyTraceReason({ hasTrace: false, error: '401 Unauthorized' });
  assert.match(s, /401 Unauthorized/);
  assert.doesNotMatch(s, /检索链|重启/, '读失败不该被说成"没走过这条路"');
});

// ==================== ⑦ URL 构造 ====================

test('buildPath / buildCostPath 会编码 thread_id', () => {
  assert.strictEqual(buildPath('default'), '/api/v1/agent/trace/default');
  assert.strictEqual(buildCostPath('default'), '/api/v1/agent/trace/default/cost');
  assert.strictEqual(buildPath('a b'), '/api/v1/agent/trace/a%20b');
  assert.strictEqual(buildPath('a&b'), '/api/v1/agent/trace/a%26b', '⛔ 不编码会被当成两个参数');
  assert.strictEqual(buildPath('#x'), '/api/v1/agent/trace/%23x');
});

test('readThreadId 缺省与空串都回 default', () => {
  assert.strictEqual(readThreadId('?thread_id=abc'), 'abc');
  assert.strictEqual(readThreadId('?thread_id='), 'default');
  assert.strictEqual(readThreadId(''), 'default');
  assert.strictEqual(readThreadId('?other=1'), 'default');
  assert.strictEqual(readThreadId('?thread_id=%20%20'), 'default', '纯空白也算没填');
  assert.strictEqual(readThreadId('?thread_id=%20abc%20'), 'abc', '两边空白要 trim');
});

// ==================== ⑧ 双挂载：两样都得挂上 ====================

test('window.RagTrace 挂得上（⛔ 少这一行页面就 ReferenceError）', () => {
  // 本仓没有打包器 ⇒ 页面用 <script src> 直接加载，只能靠 window 上的全局。
  // ⚠️ 这个用例与 `node --test` 的 require 走的是**两条不同的路** ——
  //    只测 require 的话，页面照样是坏的。
  const src = fs.readFileSync(path.join(__dirname, 'trace.js'), 'utf8');
  const sandbox = { window: {}, module: undefined };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);

  assert.ok(sandbox.window.RagTrace, 'window.RagTrace 没挂上 —— 页面会 ReferenceError');
  for (const fn of ['formatYuan', 'formatMs', 'formatWhen', 'parseWhen', 'summarizeCost',
                    'summarizeTrace', 'emptyTraceReason', 'buildPath', 'buildCostPath',
                    'readThreadId']) {
    assert.strictEqual(typeof sandbox.window.RagTrace[fn], 'function', `缺 ${fn}`);
  }
});
