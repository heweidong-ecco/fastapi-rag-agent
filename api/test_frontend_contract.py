"""前端可消费性的**行为判据**（`DEC-085` 契约 A / B）。

## 🔴 为什么单开一个文件

这两条契约是【跨层】的 —— 后端发出去的帧，要能**唯一地**还原成前端要的东西
（引用编号 / 本轮花费）。钉在 `api_v1_rag.py` 自己的测试里会去调私有闭包；
钉在前端里就得造假后端。这里用 **真端点函数 + 真 `sse.sse_stream` 骨架** 跑一遍，
再**只看它吐出来的帧**（`api/test_rag_billing_wiring.py` 的 `_drive_stream` 是同款手法）。

## 🔴 桩打在【DB 边界】，⛔ 不打在 `record_from_response` 上

`api/test_rag_billing_wiring.py` 是桩 `rag_mod.record_from_response` 的 —— 那是对的，
它测的是"**这次调用记了几笔**"。**本文件不一样**：契约 B 的判据是
「**记账了才出帧、没记账就不出帧**」。若把 `record_from_response` 桩掉，
这条判据就变成**同义反复**（我问"记账了吗"，答的是我自己写死的那个桩）。

⇒ 这里桩 `token_tracker.record_usage` —— 即**只拦"往库里写"那一步**：
   `record_from_response` 仍然**真跑**（真读 `usage_metadata`，那正是 `DEC-072` 的判据），
   只有落库被接住。这样"有没有记账"是**真被问出来的**。
"""
import asyncio
import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk


class _PromptCapturingLLM:
    """流式桩：吐正文块 → 末帧 `content=''` 且**带 usage**，并记下收到的 messages。

    ⚠️ 末帧的形状是**照真服务刻的**（`DEC-084` 的探针实测：usage 挂在**最后一帧**、
       而那一帧**没有正文**）⇒ `_StreamUsageTap` 才需要"把每块 `+` 起来"。
    """

    model_name = "fake-answer-model"

    def __init__(self, texts=("答", "案"), usage=None):
        self._texts = texts
        self._usage = usage or {"input_tokens": 21, "output_tokens": 5, "total_tokens": 26}
        self.seen_messages = None

    async def astream(self, messages):
        self.seen_messages = messages
        for t in self._texts:
            yield AIMessageChunk(content=t)
        yield AIMessageChunk(content="", usage_metadata=self._usage)


# 🔴 `search_similar` 返回的是 **4 元组**（`id, content, source, similarity`）——
#    见 `api/api_v1_rag.py` 里 `r[0]..r[3]` 的映射。⛔ 别写成 dict（那会让被测代码 KeyError）。
DOCS = [
    (11, "第一篇的正文", "a.md", 0.9),
    (22, "第二篇的正文", "b.md", 0.8),
    (33, "第三篇的正文", "c.md", 0.7),
]


@pytest.fixture
def rag_env(monkeypatch):
    """把 `stream_search` 的外部依赖短路，**只留真实骨架 + 真实记账接线**在被测路径上。"""
    import api_v1_rag as rag_mod
    import token_tracker as tt

    # 🔴 全部打在 **`rag_mod` 自己身上** —— 因为 `api_v1_rag.py` 用的是
    #    `from db import get_db` / `from cache import get_chat_history` 这种**直接绑定**
    #    （见 `api/api_v1_rag.py:44` 与 `:64`）。⛔ 打 `db.get_db` / `cache.redis_client`
    #    是**空操作**：那些名字在 import 期就被复制进 `api_v1_rag` 的命名空间了
    #    ⇒ 改源模块它**看不见**。
    #    ⚠️ 这是"桩了个寂寞"的经典形状 —— 桩没生效、用例走了真路径、然后**假绿**。
    monkeypatch.setattr(rag_mod, "get_chat_history", lambda *a, **k: [])
    monkeypatch.setattr(rag_mod, "persist_turn", lambda *a, **k: None)   # 留痕不是本文件的被测对象
    monkeypatch.setattr(rag_mod, "check_session_token_budget", lambda *a, **k: (True, ""))
    monkeypatch.setattr(rag_mod, "circuit", lambda *a, **k: (True, ""))
    monkeypatch.setattr(rag_mod, "get_embedding", lambda text: [0.0] * 8)
    monkeypatch.setattr(rag_mod, "search_similar", lambda *a, **k: list(DOCS))

    # 🔴 只拦"落库"这一步（见模块 docstring）。`record_from_response` 保持**真跑**。
    recorded = []
    monkeypatch.setattr(tt, "record_usage", lambda *a, **k: recorded.append((a, k)))
    return SimpleNamespace(rag=rag_mod, recorded=recorded)


def drive(rag_env, llm, **kw):
    """直接调端点函数、把帧**全部拉完**，返回 `(帧列表, llm)`。"""
    from schemas import QuestionRequest

    req = QuestionRequest(question="你好", **kw)

    async def go():
        resp = await rag_env.rag.stream_search(req, thread_id="t-front", user_name="alice")
        return [f async for f in resp.body_iterator]

    return asyncio.run(go()), llm


def payloads_of(frames):
    """把 SSE 文本帧解成 payload 列表；`[DONE]` 原样保留成字符串。

    ⚠️ **必须 JSON 解码**：本端点 `ensure_ascii=True` ⇒ 中文是 `\\uXXXX`，
       ⛔ 直接做子串匹配恒为假（`test_rag_billing_wiring.py` 第一版就栽在这 —— 假红）。
    """
    out = []
    for f in frames:
        if not f.startswith("data: "):
            continue
        body = f[len("data: "):].strip()
        out.append("[DONE]" if body == "[DONE]" else json.loads(body))
    return out


# ==================== 契约 A：`sources` 帧补 `index` 与 `content` ====================


def test_sources_index_is_the_same_i_as_the_prompt_numbering(monkeypatch, rag_env):
    """🔴 契约 A 的核心不变量：帧里的 `index` 与 prompt 里 `[文档{i}来源：…]` 的 `i` **同源**。

    ⚠️ **推导型**：从**同一轮**同时取 prompt 与 `sources` 帧，逐条比对 ——
       ⛔ 不是把 `1,2,3` 写死（那样两处各写一遍编号时**照样绿**）。
    """
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    frames, _ = drive(rag_env, llm, citations=True)
    payloads = payloads_of(frames)

    sources = next(p["sources"] for p in payloads if isinstance(p, dict) and "sources" in p)
    system_prompt = llm.seen_messages[0]["content"]
    numbered = re.findall(r"\[文档(\d+)来源：([^\]\n]+)\]", system_prompt)

    assert numbered, "prompt 里没有 [文档N来源：…] —— 引用模式没生效，本用例没测到东西"
    assert [s["index"] for s in sources] == [int(n) for n, _ in numbered]
    assert [s["source"] for s in sources] == [src for _, src in numbered]


def test_sources_content_is_the_full_text_not_the_preview(monkeypatch, rag_env):
    """契约 A：`content` 是**全文**，`content_preview` 仍是 100 字——**两个都在**。"""
    long_doc = (77, "甲" * 250, "long.md", 0.9)
    monkeypatch.setattr(rag_env.rag, "search_similar", lambda *a, **k: [long_doc])
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm, citations=True)[0])
    s = next(p["sources"] for p in payloads if isinstance(p, dict) and "sources" in p)[0]

    assert s["content"] == "甲" * 250, "content 必须是全文"
    assert s["content_preview"] == "甲" * 100, "content_preview 仍是 100 字（老前端还在用它）"
    assert s["index"] == 1


def test_citations_false_sends_no_sources_frame(monkeypatch, rag_env):
    """反面守卫：`citations` 默认 `False`（`api/schemas.py:16`）⇒ 不发 `sources` 帧。"""
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm)[0])
    assert not any(isinstance(p, dict) and "sources" in p for p in payloads), \
        "没传 citations=true 就不该有 sources 帧 —— 前端必须显式传它"


def test_answer_with_citations_sources_carry_the_same_shape(monkeypatch):
    """契约 A 的**第二出口**（非流式）：形状必须与流式那份逐字同构。"""
    import answer_with_citations as awc

    monkeypatch.setattr(awc, "record_from_response", lambda *a, **k: True)

    class _LLM:
        model_name = "fake-answer-model"

        def invoke(self, messages):
            return AIMessage(
                content="答案 [来源:2]",
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            )

    _answer, sources = awc.generate_answer_with_citations(
        [{"id": 1, "content": "甲" * 150, "source": "a.md"},
         {"id": 2, "content": "乙" * 150, "source": "b.md"}],
        "问句", _LLM(), user_name="alice", thread_id="t-front",
    )

    assert [s["index"] for s in sources] == [1, 2]
    assert sources[1]["content"] == "乙" * 150
    assert sources[1]["content_preview"] == "乙" * 100
    assert sources[1]["id"] == 2


# ============ 契约 A·追加：`sources` 帧补 `similarity`（`DEC-089`） ============
#
# 🔴 起因：硬门 B 的证真那句要求「点开能看到 **chunk id + 相似度分**」。
#    `id` 早在帧里（契约 A），`similarity` 这一条**数据本来就在手上**
#    （`api_v1_rag.py` 里 `contexts` 的 `r[3]`）—— 只是没人往帧里放。


def test_sources_carry_similarity_for_the_citation_card(monkeypatch, rag_env):
    """🔴 帧里必须带 `similarity`，且**是检索出来的那个值**。

    ⚠️ **推导型**：期望值取自本文件顶上那份 `DOCS`（= 检索桩的出处），
       ⛔ 不是写死 `0.9` —— 写死的话，值被换掉时两处会一起错、用例照样绿。
    """
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm, citations=True)[0])
    sources = next(p["sources"] for p in payloads if isinstance(p, dict) and "sources" in p)

    assert [s["similarity"] for s in sources] == [doc[3] for doc in DOCS], \
        "sources 帧里的 similarity 与检索结果对不上（卡片会显示一个编出来的分）"


def test_sources_similarity_is_a_number_not_a_string(monkeypatch, rag_env):
    """反面守卫：`similarity` 是**数字**，⛔ 不是字符串/None。

    ⚠️ 前端 `formatSource` 会对它做 `toFixed` —— 传字符串过去会得到 `NaN`，
       而页面上**不报错**（只会显示一个看不懂的东西）。
       🔴 本仓栽过同款：`json.dumps` 出来的 `"0.9"` 与 `0.9` 在肉眼上几乎一样。
    """
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm, citations=True)[0])
    sources = next(p["sources"] for p in payloads if isinstance(p, dict) and "sources" in p)

    for s in sources:
        assert isinstance(s["similarity"], (int, float)) and not isinstance(s["similarity"], bool), \
            f"similarity 不是数字：{s['similarity']!r}"


def test_both_sources_exits_have_the_same_key_set(monkeypatch, rag_env):
    """🔴 把「两个出口形状必须一样」从**注释**变成**用例**（`DEC-089`）。

    ⚠️ 原状：`answer_with_citations.py` 的注释写着「⛔ 改一边忘另一边 ⇒ 两个出口的形状
       悄悄分叉，而两边各自的用例都是绿的」—— 而那件事**当时没有任何尺子**。

    🔴 2026-10-06 施工时**实测**（判据是命令，⛔ 不是"我觉得应该抓得住"）：
       - 改动前全文：`7 passed`（基线）
       - **只给流式那侧加上 `similarity`**、再把本条摘掉：
         `-k 'not both_sources_exits'` ⇒ **9 passed, 1 deselected**
         ⇒ 连同上面新写的两条 `similarity` 用例一起，**一条红都没有** ——
         这句「分叉了」在**当时是被静默放行的**。
       - 加上本条 ⇒ **1 failed, 9 passed**，且报的正是 `Extra items in the left set: 'similarity'`。
       ⇒ 结论：这条尺子**在今天之前不存在**，而缺它的代价就是"改一边忘另一边"零成本。
    """
    import answer_with_citations as awc

    # 出口①：流式帧
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)
    payloads = payloads_of(drive(rag_env, llm, citations=True)[0])
    stream_src = next(p["sources"] for p in payloads if isinstance(p, dict) and "sources" in p)[0]

    # 出口②：非流式（`/rag/search?generate_answer=true&citations=true` 走的就是它）
    monkeypatch.setattr(awc, "record_from_response", lambda *a, **k: True)

    class _LLM:
        model_name = "fake-answer-model"

        def invoke(self, messages):
            return AIMessage(content="答案 [来源:1]", usage_metadata={
                "input_tokens": 1, "output_tokens": 1, "total_tokens": 2})

    _answer, sources = awc.generate_answer_with_citations(
        [{"id": 11, "content": "甲", "source": "a.md"}], "问句", _LLM(),
        user_name="alice", thread_id="t-front",
    )

    assert set(stream_src.keys()) == set(sources[0].keys()), \
        f"两个出口的 sources 形状分叉了：流式 {sorted(stream_src)} vs 非流式 {sorted(sources[0])}"


# ==================== 契约 B：末尾的 `usage` 汇总帧 ====================
#
# 🔴 一条贯穿三节的判据：**记账了才出帧**。
#    帧不是"再算一遍"，是**把已经写进账本的那笔念回来** —— 两者同源。


def test_usage_frame_is_last_and_after_sources(monkeypatch, rag_env):
    """🔴 契约 B 的帧序：`content… → [DONE] → sources → usage`（usage **最后**）。

    ⚠️ `[DONE]` 排在 `sources` 之前是本端点的**线上契约**（前端按它适配）——
       本用例把三段一起钉住，⛔ 不许"顺手整理成先 sources 再 [DONE]"。
    """
    llm = _PromptCapturingLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm, citations=True)[0])

    assert payloads[-1] != "[DONE]", "usage 必须排在 [DONE] 之后"
    assert isinstance(payloads[-1], dict) and "usage" in payloads[-1], "最后一帧必须是 usage"

    kinds = ["done" if p == "[DONE]" else
             ("sources" if "sources" in p else
              ("usage" if "usage" in p else
               ("error" if "error" in p else "content")))
             for p in payloads]
    assert kinds[-3:] == ["done", "sources", "usage"], f"帧序不对：{kinds}"


def test_usage_frame_reports_the_numbers_that_were_billed(monkeypatch, rag_env):
    """🔴 契约 B 的同源判据：帧里的数 = 账本里的数。

    ⚠️ 本用例**不桩** `record_from_response`（只桩了落库那一步）——
       所以它同时钉住「**记账了才出帧**」：没记成的话 `record` 返回 None，帧根本不出现。

    🔴 `cost_usd` 的期望值从 `PRICING` **现推**，⛔ 不是拿 `tt.compute_cost(...)` 当期望
       —— 那是拿函数和自己比（同义反复）。本仓 2026-10-06 在 Task 2 栽过一次，见
       `api/test_token_tracker_cost_helpers.py` 同款注释。
    """
    import token_tracker as tt

    llm = _PromptCapturingLLM(
        usage={"input_tokens": 1200, "output_tokens": 800, "total_tokens": 2000}
    )
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm)[0])
    # ⚠️ **按内容找帧，⛔ 不取 `payloads[-1]`** —— 「它在最后」是上面那条用例的事；
    #    这里不写死位置，两条用例才各量一件事（否则位置一错，两条一起红，分不清是哪种坏）。
    usage = next(p["usage"] for p in payloads if isinstance(p, dict) and "usage" in p)

    assert usage["model"] == "fake-answer-model", "🔴 从 llm 对象取，⛔ 不许写死"
    assert usage["prompt_tokens"] == 1200
    assert usage["completion_tokens"] == 800
    pricing = tt.PRICING.get("fake-answer-model", tt._DEFAULT_PRICING)
    expected_cost = (1200 / 1000) * pricing["prompt"] + (800 / 1000) * pricing["completion"]
    assert usage["cost_usd"] == expected_cost


def test_no_usage_frame_when_nothing_was_billed(monkeypatch, rag_env):
    """🔴 反面守卫：**没记账 ⇒ 不许出帧**（两者同源）。

    ⚠️ 本用例在 Task 3 动工**之前就是绿的**（现状本来就不出帧）⇒
       **"它现在绿"证明不了它在测那件事**。只有反证检验（把 `if payload is not None:`
       改成无条件 yield）让它**变红**，才算数。见施工单 Step 6 ②。
    """
    class _NoUsageLLM(_PromptCapturingLLM):
        async def astream(self, messages):
            self.seen_messages = messages
            for t in self._texts:
                yield AIMessageChunk(content=t)
            # ⛔ 末帧**不带** usage_metadata —— 模拟"服务没回用量"

    llm = _NoUsageLLM()
    monkeypatch.setattr(rag_env.rag, "get_llm_stream", lambda: llm)

    payloads = payloads_of(drive(rag_env, llm)[0])
    assert not any(isinstance(p, dict) and "usage" in p for p in payloads), \
        "一笔账都没记，就不该有 usage 帧 —— 出了帧等于在报一个编出来的数"
    assert payloads[-1] == "[DONE]"
