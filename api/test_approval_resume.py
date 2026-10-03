"""接管后续跑（`B6`）—— 硬门 D 的最后一段。

🔴 **核心判据**（`通用/四硬门 §3-D`）：**接管后会话【上下文连续】** —— 不是重开一轮。

⚠️ **用假图替掉 `agent_graph`**：真图要调 LLM ⇒ 那会让这条测试变成"要联网、要花钱"。
   本文件测的是【接线与语义】，⛔ 不是模型质量。
   ⇒ **无 marker，纯离线，进 CI。**

📌 为什么非要钉住 `invoke(None, …)` 这个形状：
   传 `None` = **从 checkpoint 继续**；传 `{"messages": [HumanMessage(q)]}` = **重开一轮**。
   两者的**接口返回长得一模一样**（都是 `{"status": "approved", "answer": …}`）
   ⇒ 只有静态钉住调用形状，才拦得住"看着一切正常、其实上下文断了"。
"""
import asyncio

import api_v1_agent as m
from langchain_core.messages import AIMessage


class _FakeGraph:
    """假图：**记录被怎么调用**，并按剧本返回一个像样的 result。"""

    def __init__(self, next_node=("approval",)):
        self.calls = []
        self.configs = []
        # `approve_agent_action` 读 `current_state.next` 判定"图停没停在审批点"
        self._state = type("S", (), {"next": next_node})()

    def get_state(self, config):
        return self._state

    def update_state(self, config, values=None):
        self.calls.append(("update_state", values))

    def invoke(self, arg, config):
        self.calls.append(("invoke", arg))
        self.configs.append(config)
        return {"messages": [AIMessage(content="续跑后的最终答案")]}

    # --- 断言助手 ---
    def updates(self):
        return [v for (k, v) in self.calls if k == "update_state"]

    def invoked_with(self):
        return [a for (k, a) in self.calls if k == "invoke"]


def _approve(monkeypatch, fake, **kw):
    """装上假图，同步跑一遍端点（本仓没有 pytest-asyncio，异步只能手跑）。

    ⚠️ 用 `monkeypatch` 而**不是** `m.agent_graph = fake`：
       直接赋模块属性**不会还原** ⇒ 假图会泄漏到**同一次 pytest 会话的其它文件**里
       （别的用例 import 的是同一个模块对象）。那种污染**不报错**，只会让别处莫名变绿/变红。
    """
    monkeypatch.setattr(m, "agent_graph", fake)
    kw.setdefault("thread_id", "t1")
    kw.setdefault("approved", True)
    kw.setdefault("user_name", "admin")
    return asyncio.run(m.approve_agent_action(**kw))


# ==================== ① 续跑形状（回归守卫） ====================

def test_resume_invokes_with_none_not_a_new_message(monkeypatch):
    """🔴 **续跑必须 `invoke(None, config)`**。

    ⚠️ **这条钉的是【现有】正确行为，不是新功能** —— 改 `edited_answer` 之前它就该绿。
       留着它是因为**改错的方向太容易发生**（顺手改成"喂一条新消息"），而**返回看着没差别**。

    ⛔ 若某天有人改成 `invoke({"messages": [HumanMessage(question)]}, …)`，
       那就是**重开一轮** —— 上下文断了，而**接口返回一切正常**。
    """
    fake = _FakeGraph()
    _approve(monkeypatch, fake)
    assert fake.invoked_with() == [None], (
        f"续跑没有用 None 续跑（= 从 checkpoint 继续）：{fake.calls}"
    )


# ==================== ② 续跑用的是**这条**会话（回归守卫） ====================

def test_resume_uses_the_requested_thread_id(monkeypatch):
    """续跑必须带上**请求里那个** `thread_id`。

    🔴 **为什么这半条不比上面弱**：`invoke(None, config)` 只有在 `config` 指向**同一个 thread**
       时才等于"接着上次跑"。若 config 里的 thread_id 被写错 / 写死 / 丢掉，
       图会**从空状态重开**，或**接到别人的会话上** —— 两种都**不会报错**。
       ⇒ `None` 那半条保证"是续跑"，这半条保证"续的是**这一条**"。

    ⚠️ 也是**钉现有行为**的守卫（改动前就该绿）。
    """
    fake = _FakeGraph()
    _approve(monkeypatch, fake, thread_id="thread-abc")
    assert fake.configs, "一次都没 invoke"
    got = [c.get("configurable", {}).get("thread_id") for c in fake.configs]
    assert got == ["thread-abc"], f"续跑用的不是请求里的 thread_id：{got}"


# ==================== ③ 改写后提交（B6 的新东西） ====================

def test_edit_note_is_written_into_state(monkeypatch):
    """人工改写后提交：**改的那句要进 state**，⛔ 否则"改了等于没改"。

    ⚠️ 为什么必须走 `update_state` 而不是"直接把答案当返回值吐出去"：
       后者会让**后续节点看不到这个改写**（它不在 messages 里）——
       我们这条链上审批之后还要去 `tools` ⇒ 改写必须进**状态**，不能只在**响应**里。
    """
    fake = _FakeGraph()
    _approve(monkeypatch, fake, edited_answer="人工改过的答案")
    assert any("人工改过的答案" in str(v) for v in fake.updates()), (
        f"edited_answer 没有被写进 state：{fake.updates()}"
    )


def test_edited_answer_is_an_ai_message_not_a_human_one(monkeypatch):
    """写进去的必须是 **`AIMessage`**，⛔ 不是 `HumanMessage`。

    ⚠️ 用 `HumanMessage` 会把"人改的答案"伪装成"用户新提的问题" ⇒
       模型下一轮会把它当**输入**再答一遍，而不是当**已给出的结论**。
    """
    fake = _FakeGraph()
    _approve(monkeypatch, fake, edited_answer="人工改过的答案")
    pushed = [msg for v in fake.updates()
              if isinstance(v, dict) for msg in v.get("messages", [])]
    assert pushed, f"改写没有任何消息进 state：{fake.updates()}"
    assert all(isinstance(msg, AIMessage) for msg in pushed), (
        f"改写用的不是 AIMessage：{[type(x).__name__ for x in pushed]}"
    )


def test_edited_answer_is_ignored_when_rejected(monkeypatch):
    """**拒绝时带 `edited_answer` ⇒ 不许写进 state**（那条路是"别做了"，不是"按我说的做"）。

    🔴 这是**反面**用例：只测"批准时会写"会漏掉"拒绝时也写了"——
       而那种错**不报任何错**，只是让模型收到一条自相矛盾的 state。
    """
    fake = _FakeGraph()
    _approve(monkeypatch, fake, approved=False, edited_answer="人工改过的答案")
    assert not any("人工改过的答案" in str(v) for v in fake.updates()), (
        f"拒绝分支把 edited_answer 也写进去了：{fake.updates()}"
    )


# ==================== ④ 没停在审批点时（回归守卫） ====================

def test_not_at_approval_point_does_not_invoke(monkeypatch):
    """图没停在审批点 ⇒ 早退（`status: error`）∧ **⛔ 一次都不许 invoke**。

    ⚠️ 若这里 invoke 了，就是**从任意状态硬接着跑** ⇒ 可能把一条已经跑完的会话再跑一遍。
    """
    fake = _FakeGraph(next_node=())
    out = _approve(monkeypatch, fake, thread_id="never-stopped")
    assert out.get("status") == "error", out
    assert fake.invoked_with() == [], f"没停在审批点却 invoke 了：{fake.calls}"
