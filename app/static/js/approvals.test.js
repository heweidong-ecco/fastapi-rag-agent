'use strict';
/* `approvals.js` 的用例 —— ⛔ 零 npm 依赖（只 node:test + node:assert）。
   跑法：node --test app/static/js/approvals.test.js（已接进 ci.yml 的 run 块） */
const test = require('node:test');
const assert = require('node:assert');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const {
  messageText, summarizeToolCalls, formatElapsed, nextPollDelay,
  buildContextQuery, buildApprovePayload, pagerState,
} = require('./approvals.js');

// ==================== ① messageText：content 可能是 str / list / 别的 ====================

test('messageText 处理字符串', () => {
  assert.strictEqual(messageText({ content: '你好' }), '你好');
});

test('messageText 处理多模态 parts（🔴 后端 §3.1 ① 明写 content 可能是 list）', () => {
  const msg = { content: [
    { type: 'text', text: '看图' },
    { type: 'image_url', image_url: { url: 'http://x/1.png' } },
  ] };
  assert.strictEqual(messageText(msg), '看图[image_url]');
});

test('messageText 对 null / undefined 给空串（⛔ 别渲染出 "undefined"）', () => {
  assert.strictEqual(messageText({ content: null }), '');
  assert.strictEqual(messageText(undefined), '');
  assert.strictEqual(messageText({}), '');
});

test('messageText 对非字符串非数组降级成 String()（⛔ 不许抛）', () => {
  assert.strictEqual(messageText({ content: 42 }), '42');
});

// ==================== ② summarizeToolCalls：与后端同一句话 ====================

test('summarizeToolCalls 合并连续同名并计数', () => {
  assert.strictEqual(summarizeToolCalls([{ name: 'web_search' }]), 'web_search');
  assert.strictEqual(
    summarizeToolCalls([{ name: 'a' }, { name: 'a' }, { name: 'b' }]),
    'a×2、b');
});

test('summarizeToolCalls 空 ⇒ 与后端同一句占位', () => {
  assert.strictEqual(summarizeToolCalls([]), '(无工具调用)');
  assert.strictEqual(summarizeToolCalls(undefined), '(无工具调用)');
});

// ==================== ③ formatElapsed ====================

test('formatElapsed 一分钟以内 =「刚刚」', () => {
  assert.strictEqual(formatElapsed(0), '刚刚');
  assert.strictEqual(formatElapsed(59), '刚刚');
});

test('formatElapsed 分钟 / 小时', () => {
  assert.strictEqual(formatElapsed(60), '1 分钟');
  assert.strictEqual(formatElapsed(59 * 60 + 59), '59 分钟');
  assert.strictEqual(formatElapsed(3600), '1 小时 0 分');
  assert.strictEqual(formatElapsed(3 * 3600 + 25 * 60), '3 小时 25 分');
});

test('formatElapsed 拿到坏值给「—」，⛔ 别显示 NaN', () => {
  assert.strictEqual(formatElapsed(NaN), '—');
  assert.strictEqual(formatElapsed(-1), '—');
  assert.strictEqual(formatElapsed(undefined), '—');
});

// ==================== ④ nextPollDelay：裁定 5 ====================

test('nextPollDelay 只在可见时轮询', () => {
  assert.strictEqual(nextPollDelay('visible'), 5000);
  assert.strictEqual(nextPollDelay('hidden'), null);
  assert.strictEqual(nextPollDelay(undefined), null);
});

// ==================== ⑤ 两个载荷构造 ====================

test('buildContextQuery 必带 thread_id；owner 可选', () => {
  assert.strictEqual(buildContextQuery('default', null), 'thread_id=default');
  assert.strictEqual(buildContextQuery('default', 'alice'), 'thread_id=default&owner=alice');
});

test('buildApprovePayload：批准不带改写 / 带改写', () => {
  assert.strictEqual(
    buildApprovePayload('default', 'alice', 'approve', ''),
    'thread_id=default&approved=true&owner=alice');
  assert.strictEqual(
    buildApprovePayload('default', null, 'approve', '答案是 42'),
    'thread_id=default&approved=true&edited_answer=%E7%AD%94%E6%A1%88%E6%98%AF+42');
});

test('🔴 buildApprovePayload：拒绝时 ⛔ 不许带 edited_answer', () => {
  // 后端本来就会忽略它（"拒绝的语义是别做了"）⇒ 带上就是在发一个**假信号**
  const q = buildApprovePayload('default', null, 'reject', '随便写点');
  assert.strictEqual(q, 'thread_id=default&approved=false');
  assert.ok(!q.includes('edited_answer'));
});

// ==================== ⑥ 🔴 浏览器侧必须真的挂上 window.RagApprovals ====================

test('脚本在【浏览器】环境下把 RagApprovals 挂到 window 上', () => {
  // ⚠️ 这条是 sse.js 施工实测的教训：只挂 module.exports ⇒ 页面里每个
  //    `RagApprovals.xxx` 都会 ReferenceError，而【node --test 抓不到】、
  //    页面加载时也不报（第一次用到是在数据回来之后）。
  const src = fs.readFileSync(path.join(__dirname, 'approvals.js'), 'utf8');
  const sandbox = { window: {}, module: undefined };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);

  assert.ok(sandbox.window.RagApprovals, 'window.RagApprovals 没挂上 —— 页面会 ReferenceError');
  for (const fn of ['messageText', 'summarizeToolCalls', 'formatElapsed',
                    'nextPollDelay', 'buildContextQuery', 'buildApprovePayload']) {
    assert.strictEqual(typeof sandbox.window.RagApprovals[fn], 'function', `缺 ${fn}`);
  }
});

// ==================== ⑦ pagerState：分页的纯逻辑（`frontend/README.md` §六） ====================

test('pagerState 首页：没有上一页，offset 从 0 开始', () => {
  const s = pagerState({ offset: 0, limit: 50, hasMore: true, count: 50 });
  assert.strictEqual(s.page, 1);
  assert.strictEqual(s.hasPrev, false);
  assert.strictEqual(s.hasNext, true);
  assert.strictEqual(s.prevOffset, 0);
  assert.strictEqual(s.nextOffset, 50);
});

test('pagerState 中间页：两边都有', () => {
  const s = pagerState({ offset: 100, limit: 50, hasMore: true, count: 50 });
  assert.strictEqual(s.page, 3);
  assert.strictEqual(s.hasPrev, true);
  assert.strictEqual(s.prevOffset, 50);
  assert.strictEqual(s.nextOffset, 150);
});

test('pagerState 末页：hasMore=false ⇒ 没有下一页', () => {
  const s = pagerState({ offset: 100, limit: 50, hasMore: false, count: 12 });
  assert.strictEqual(s.hasNext, false);
});

test('pagerState 页码用【向下取整 +1】，⛔ 不是四舍五入', () => {
  // offset=120、limit=50 ⇒ 第 3 页（floor(120/50)+1 = 3），不是第 2 也不是第 3.4
  assert.strictEqual(pagerState({ offset: 120, limit: 50, hasMore: false }).page, 3);
});

test('🔴 pagerState：`hasMore` 缺失 ⇒ 必须 false —— 「没告诉你有更多」⛔ 不等于「有更多」', () => {
  const s = pagerState({ offset: 0, limit: 50 });
  assert.strictEqual(s.hasNext, false);
});

test('🔴 pagerState：⛔ 不许拿 `count === limit` 当「还有更多」', () => {
  // 服务端明说 hasMore=false（正好一整页、后面没有了）⇒ 就算 count===limit 也不许显示下一页
  const s = pagerState({ offset: 0, limit: 50, hasMore: false, count: 50 });
  assert.strictEqual(s.hasNext, false, 'count===limit 被当成了「还有更多」—— 那是猜的，不是服务端说的');
});

test('pagerState：limit 非法（0/负/NaN）⇒ 不炸，且⛔ 不给出会打转的 nextOffset', () => {
  for (const bad of [0, -5, NaN, undefined]) {
    const s = pagerState({ offset: 0, limit: bad, hasMore: true });
    assert.ok(Number.isInteger(s.nextOffset) && s.nextOffset > 0,
      `limit=${bad} 时应回落到一个安全值，实得 nextOffset=${s.nextOffset}`);
    assert.strictEqual(s.page, 1);
  }
});

test('pagerState：prevOffset ⛔ 不许为负', () => {
  assert.strictEqual(pagerState({ offset: 10, limit: 50, hasMore: false }).prevOffset, 0);
});

test('pagerState：带人读的页码标签', () => {
  assert.strictEqual(pagerState({ offset: 0, limit: 50, hasMore: false }).label, '第 1 页');
  assert.strictEqual(pagerState({ offset: 50, limit: 50, hasMore: false }).label, '第 2 页');
});
