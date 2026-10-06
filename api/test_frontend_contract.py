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
