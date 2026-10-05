"""RAG 侧每条真调 LLM 的通路必须【先拦后记】。

## 🔴 为什么需要它

`grep -c record_usage api/api_v1_rag.py` ⇒ **0**（`rag_pipeline.py` / `answer_with_citations.py` 同为 0）。
⇒ RAG 侧**每个成功的请求都在免费跑**：端点上的 **B8 会话上限** / **B11 全站熔断**
读的计数器，它**从不写** ⇒ **对 RAG 链等于不存在**。

与 `DEC-072` 修过的 Agent 侧**完全同型** —— 那边的原话是「**门在，锁坏了**」：
门**挂在正确的位置**（端点确实调了 `check_session_token_budget`），
而**门后面的计量表没接上**（从没往 `token_usage_logs` 写一行）。
本文件钉的就是**那张表**。

📄 裁定 ⇒ `docs/decisions/DEC-073-RAG侧关闭零记账的LLM通路.md`
📄 起因 ⇒ `DEC-053` §遗留·2（`B3` 当时核出、**有意没做**）

## ⚠️ 两条必须一起读的话

1. **上半是【形状】判据**（AST），**下半是【行为】判据**（假对象驱动，断言
   `record_usage` 真的收到**对的** `user_name` / `purpose` / `model`）。
   > **两者缺一都不够**：形状能过而参数写错（记成 `"unknown"`、`purpose` 抄错）；
   > 行为能过而某个调用点又被人摘了守卫（覆盖面漏）。
2. **它红了不要删它** —— 红的意思是「这条 RAG 通路又开始免费跑了」。
   若你**有意**摘掉某条通路的记账，先改 `DEC-073` 的范围表，**再**改本文件。

## 为什么用 AST，⛔ 不用 grep

本仓这些模块的注释与 docstring 里**大量出现** `record_usage` / `check_token_budget`
这些词（`query_rewriter.py:78` 那个**从不被调用的 import** 就是活证据）
⇒ grep 会把「注释里提到」当成「代码里调了」。同款理由见 `api/test_billing_wiring.py` 文件头。
"""
import ast
import asyncio
import pathlib
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

import answer_with_citations as awc
import query_rewriter as qr
import rag_pipeline as rp

_API = pathlib.Path(__file__).parent


# ══════════════════════════════════════════════════════════════════
# 下半 · 行为判据（Task 1：query_rewriter 的两条通路）
# ══════════════════════════════════════════════════════════════════

class _FakeCompletion:
    """裸 `openai.OpenAI` 的响应 —— 带 `.usage`，**没有** `usage_metadata`（这是真的）。

    🔴 这个「没有」是本轮的关键事实：`record_from_response` 的判据是
       `usage_metadata`（`DEC-072` §「判据必须是 usage_metadata」），
       对**裸客户端**的响应**恒为 False** ⇒ 用它记账会**静默一笔不记**。
       ⛔ 所以 `query_rewriter` 必须走 `record_usage`。
    """

    def __init__(self, content: str):
        self.model = "fake-rewrite-model"
        self.choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ]
        self.usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)


def _fake_client(content: str):
    """假 `openai.OpenAI` —— 只实现 `client.chat.completions.create`。"""
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: _FakeCompletion(content))
        )
    )


@pytest.fixture
def no_cache(monkeypatch):
    """关掉 Redis 缓存早退 —— 否则第二次同样的调用根本不碰 LLM，测不到记账。"""
    monkeypatch.setattr(qr.redis_client, "get", lambda *a, **k: None)
    monkeypatch.setattr(qr.redis_client, "set", lambda *a, **k: None)


def test_rewrite_query_records_real_usage_and_identity(monkeypatch, no_cache):
    """改写调了一次 LLM ⇒ 必须记**恰好一笔**，且身份是**真值**。"""
    recorded = []
    monkeypatch.setattr(qr, "record_usage", lambda **kw: recorded.append(kw) or True)
    monkeypatch.setattr(qr, "client", _fake_client("改写后的问题"))

    out = qr.rewrite_query("改写前", user_name="alice")

    assert out == "改写后的问题"
    assert len(recorded) == 1, "调了一次 LLM 就该记且只记一笔"
    kw = recorded[0]
    assert kw["user_name"] == "alice", "🔴 ⛔ 不许记成 'unknown'（那是假记账）"
    assert kw["purpose"] == "query_rewrite"
    assert kw["model"] == "fake-rewrite-model", "🔴 model 从响应取，⛔ 不写死"
    assert (kw["prompt_tokens"], kw["completion_tokens"]) == (11, 7)


def test_expand_query_records_real_usage_and_identity(monkeypatch, no_cache):
    recorded = []
    monkeypatch.setattr(qr, "record_usage", lambda **kw: recorded.append(kw) or True)
    monkeypatch.setattr(qr, "client", _fake_client("变体一\n变体二\n变体三"))

    out = qr.expand_query("原问题", num_variants=3, user_name="bob")

    assert "原问题" in out
    assert len(recorded) == 1
    assert recorded[0]["user_name"] == "bob"
    assert recorded[0]["purpose"] == "query_expand"


def test_cache_hit_does_not_record(monkeypatch):
    """🔴 命中缓存 ⇒ **没调 LLM** ⇒ **不该记一笔**（记了就是往账本写假数）。"""
    recorded = []
    monkeypatch.setattr(qr, "record_usage", lambda **kw: recorded.append(kw) or True)
    monkeypatch.setattr(qr.redis_client, "get", lambda *a, **k: "缓存里的改写")
    monkeypatch.setattr(qr, "client", _fake_client("不该被用到"))

    assert qr.rewrite_query("q", user_name="alice") == "缓存里的改写"
    assert recorded == []


def test_empty_rewrite_still_records(monkeypatch, no_cache):
    """🔴 「改写成空 ⇒ 回退原问题」那条早退分支**也要先记账** —— 钱已经花了。"""
    recorded = []
    monkeypatch.setattr(qr, "record_usage", lambda **kw: recorded.append(kw) or True)
    monkeypatch.setattr(qr, "client", _fake_client("   "))

    assert qr.rewrite_query("原问题", user_name="alice") == "原问题"   # 回退了
    assert len(recorded) == 1, "回退不等于没花钱 ⇒ 这一笔必须记上"


@pytest.mark.parametrize("fn,args", [
    ("rewrite_query", ("q",)),
    ("expand_query", ("q",)),
])
def test_missing_identity_raises_instead_of_recording_unknown(fn, args):
    """🔴 漏传身份必须**当场炸** —— ⛔ 不许静默记成 `"unknown"`（`DEC-072` 的反例）。"""
    with pytest.raises(TypeError):
        getattr(qr, fn)(*args)


# ══════════════════════════════════════════════════════════════════
# 共用 AST 工具（Task 2 / Task 4 复用）
# ══════════════════════════════════════════════════════════════════

def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _called_names(fn):
    """函数**自己**调到的名字 —— ⛔ **不下钻到它内部定义的嵌套函数 / lambda**。

    🔴 语义必须与 `test_billing_wiring._own_called_names` **逐字同款**。
       若下钻，一个"工厂函数里套着节点函数"的形状会因为**内层**调了守卫
       而被判为「已拦已记」—— **而它自己那个 LLM 调用点仍然裸奔**。
       那是**假通过**，比漏报更坏。
    """
    names = set()

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue                      # ⛔ 别人的函数，不归我
            if isinstance(child, ast.Call):
                f = child.func
                names.add(getattr(f, "id", None) or getattr(f, "attr", None))
            walk(child)

    walk(fn)
    return names


# ══════════════════════════════════════════════════════════════════
# Task 2 · 形状判据：两条 RAG 端点必须【两道闸】都在
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("func_name", ["unified_search", "rewrite_search_api"])
def test_rag_endpoints_gate_both_session_and_global(func_name):
    """🔴 这两条端点**此前零闸** —— 而它们默认就会真调 LLM。

    * `unified_search`（`/rag/search`）默认 mode `accurate_norerank` ⇒ **默认就调改写**
    * `rewrite_search_api`（`/rag/rewrite_search`）**无条件**调改写 + 扩展

    ⇒ 单条请求**无上限**；且 `B8` 会话上限 / `B11` 全站熔断读的计数器它们从不写
    ⇒ **对这两条链等于不存在**。

    ⚠️ **两道都要，⛔ 不能只加一道**：`/rag/stream_search` 的现状就是两道并列
    （`:620` B8 + `:625` B11），注释写着「**与 B8 并列，⛔ 别合并（B8 按会话 / B11 按全站）**」。
    """
    tree = ast.parse((_API / "api_v1_rag.py").read_text(encoding="utf-8"))
    fn = _fn(tree, func_name)
    assert fn is not None, (
        f"api_v1_rag.py 里找不到 {func_name}() —— 端点被改名/删掉了？"
        "  那要同步改本文件的参数化列表与 `DEC-073` 的范围表"
    )
    names = _called_names(fn)
    assert "check_session_token_budget" in names, f"{func_name} 缺 B8 会话闸"
    assert "circuit" in names, f"{func_name} 缺 B11 全站熔断"
    assert "global_key" in names, f"{func_name} 调了 circuit 却没给 global_key()"


# ══════════════════════════════════════════════════════════════════
# Task 3 · 行为判据：答案生成那两条分支也要记真账
# ══════════════════════════════════════════════════════════════════

class _FakeChatModel:
    """最小 `ChatOpenAI`：`invoke(messages) -> AIMessage(带 usage_metadata)`。

    🔴 它**必须**返回 `AIMessage`（⛔ 不是 `str`）—— 因为 `record_from_response`
       的判据是 `usage_metadata`（`DEC-072`），而**只有消息对象才有它**。
    """

    def __init__(self, text: str = "答案 [来源:1]"):
        self._text = text
        self.seen = None

    def invoke(self, messages, **kw):
        self.seen = messages
        return AIMessage(
            content=self._text,
            usage_metadata={"input_tokens": 30, "output_tokens": 9, "total_tokens": 39},
            response_metadata={"model_name": "fake-answer-model"},
        )


def test_citations_answer_records_with_identity(monkeypatch):
    """`citations=True` 那条分支（`/rag/search?generate_answer=true&citations=true`）。"""
    recorded = []
    monkeypatch.setattr(
        awc, "record_from_response",
        lambda llm, resp, purpose, **kw: recorded.append((purpose, kw, resp)) or True,
    )
    llm = _FakeChatModel()
    answer, sources = awc.generate_answer_with_citations(
        [{"id": 1, "content": "正文", "source": "s.md"}], "问句", llm,
        user_name="alice", thread_id="t-1",
    )
    assert answer == "答案 [来源:1]"
    assert sources and sources[0]["source"] == "s.md"
    assert len(recorded) == 1
    purpose, kw, _resp = recorded[0]
    assert purpose == "answer_generation"
    assert kw["user_name"] == "alice", "🔴 ⛔ 不许是 'unknown'"
    assert kw["thread_id"] == "t-1"


def test_citations_answer_hands_a_message_with_usage_to_billing(monkeypatch):
    """🔴 回归钉子：`StrOutputParser` 会把 `AIMessage` **剥成 `str`** ⇒ `usage_metadata` 丢光
    ⇒ 记账**静默收不到数**（而测试全绿）。这条钉住"传去记账的是消息本体"。"""
    seen = []
    monkeypatch.setattr(awc, "record_from_response",
                        lambda llm, resp, purpose, **kw: seen.append(resp) or True)
    awc.generate_answer_with_citations(
        [{"id": 1, "content": "正文", "source": "s.md"}], "问句", _FakeChatModel(),
        user_name="alice",
    )
    assert len(seen) == 1
    assert getattr(seen[0], "usage_metadata", None), (
        "🔴 传去记账的必须是【带 usage_metadata 的消息】—— 接了 StrOutputParser 就只剩 str"
    )


def test_plain_answer_branch_records_with_identity(monkeypatch):
    """`citations=False` 那条分支（`/rag/search?generate_answer=true` 默认形态）。"""
    monkeypatch.setattr(rp, "get_embedding", lambda text, model=None: [0.0] * 1536)

    async def fake_search(_emb, top_k=3, user_id=None):
        return [{"id": 1, "content": "正文", "source": "s.md", "similarity": 0.9}]

    monkeypatch.setattr(rp, "search_similar_async", fake_search)

    recorded = []
    monkeypatch.setattr(
        rp, "record_from_response",
        lambda llm, resp, purpose, **kw: recorded.append((purpose, kw, resp)) or True,
    )

    pipeline = rp.RAGPipeline(enable_rewrite=False, enable_expand=False,
                              enable_bm25=False, enable_rerank=False)
    pipeline.answer_llm = _FakeChatModel("普通答案")

    out = asyncio.run(pipeline.search_async(
        "问句", top_k=1, generate_answer=True, citations=False, user_id="alice",
    ))

    assert out["answer"] == "普通答案"
    assert len(recorded) == 1, "生成答案调了一次 LLM ⇒ 必须记且只记一笔"
    purpose, kw, resp = recorded[0]
    assert purpose == "answer_generation"
    assert kw["user_name"] == "alice", "🔴 ⛔ 不许是 'unknown'"
    assert getattr(resp, "usage_metadata", None), "同上：必须是消息本体，不是 str"


def test_no_answer_generation_means_no_record(monkeypatch):
    """`generate_answer=False` ⇒ **没调 LLM** ⇒ **不该记一笔**（记了就是往账本写假数）。"""
    monkeypatch.setattr(rp, "get_embedding", lambda text, model=None: [0.0] * 1536)

    async def fake_search(_emb, top_k=3, user_id=None):
        return [{"id": 1, "content": "正文", "source": "s.md", "similarity": 0.9}]

    monkeypatch.setattr(rp, "search_similar_async", fake_search)
    recorded = []
    monkeypatch.setattr(rp, "record_from_response",
                        lambda *a, **k: recorded.append(a) or True)

    pipeline = rp.RAGPipeline(enable_rewrite=False, enable_expand=False,
                              enable_bm25=False, enable_rerank=False)
    asyncio.run(pipeline.search_async("问句", top_k=1, generate_answer=False, user_id="alice"))
    assert recorded == []


# ══════════════════════════════════════════════════════════════════
# Task 4 · 形状判据（AST）—— 防「下一个人又摘掉守卫」
# ══════════════════════════════════════════════════════════════════

_RAG_LLM_FILES = ["query_rewriter.py", "rag_pipeline.py", "answer_with_citations.py"]
_BILL_NAMES = {"record_usage", "record_from_response"}


def _is_rag_llm_call(node):
    """RAG 侧两类真花钱的调用点：

    * **裸客户端**：`client.chat.completions.create(...)`（`query_rewriter` 独有）
    * **LangChain**：`llm.invoke(...)` / `self.answer_llm.invoke(...)`

    ⚠️ 判据是「对象名以 `llm` 开头或结尾」—— 本仓取名恰好干净。
       ⛔ 别放宽成「任何 `.invoke`」：工具也叫 `.invoke()`，会把不调 LLM 的函数误判成漏记。
    """
    f = node.func
    if not isinstance(f, ast.Attribute):
        return False
    if f.attr not in ("create", "invoke", "stream", "astream", "ainvoke"):
        return False
    if "chat.completions" in ast.unparse(f):
        return True
    v = f.value
    if isinstance(v, ast.Name):
        return v.id.startswith("llm")
    if isinstance(v, ast.Attribute):                  # `self.answer_llm`
        return v.attr.startswith("llm") or v.attr.endswith("llm")
    return False


def _innermost_llm_functions(tree):
    """每个 LLM 调用点**只归给最内层**包住它的函数（同一调用点不会被内外两层各报一次）。"""
    found = {}

    def visit(node, cur):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cur = node
            found.setdefault(id(node), [node, []])
        if cur is not None and isinstance(node, ast.Call) and _is_rag_llm_call(node):
            found[id(cur)][1].append(node)
        for child in ast.iter_child_nodes(node):
            visit(child, cur)

    visit(tree, None)
    return [v for v in found.values() if v[1]]


@pytest.mark.parametrize("filename", _RAG_LLM_FILES)
def test_every_rag_llm_site_bills(filename):
    """**每个**调 LLM 的函数必须有一笔记账。

    ⚠️ **红了不要删** —— 它红的意思是「这条 RAG 通路又开始免费跑了」。
    """
    tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
    offenders = []
    for fn, sites in _innermost_llm_functions(tree):
        if not (_called_names(fn) & _BILL_NAMES):
            offenders.append(
                f"  {filename}:{fn.lineno} {fn.name}() —— LLM 调用点 "
                f"行{[s.lineno for s in sites]}，一笔不记"
            )
    assert not offenders, (
        f"{filename} 里有函数调了 LLM 却**不记账**：\n" + "\n".join(offenders)
        + "\n  ⇒ 这些调用对配额等于不存在（守卫读的计数器它从不写），而**所有测试照样全绿**。"
    )


@pytest.mark.parametrize("filename", _RAG_LLM_FILES)
def test_no_llm_usage_is_swallowed_by_string_output_parser(filename):
    """🔴 `StrOutputParser` 把 `AIMessage` **剥成 `str`** ⇒ `usage_metadata` 丢光
    ⇒ `record_from_response` **静默跳过**（`DEC-072` 判据：必须有 `usage_metadata`）。

    ⚠️ **必须扫整份文件，⛔ 不能挂在 `_innermost_llm_functions()` 上。**
       本测试第一版就是那么写的，**自证时发现它是假守卫**：
       改坏的形态是 `(PROMPT | llm | StrOutputParser()).invoke(...)` ——
       这里的 `f.value` 是个 `BinOp`（`|` 链），`_is_rag_llm_call` **认不出它是 LLM 调用**
       ⇒ 那个函数根本没进循环 ⇒ 断言**空转通过**。
       这正是本仓 `DEC-066`「**守卫的形状盲区**」那一族：
       **守卫的判据建立在"能先认出调用"之上 ⇒ 认不出的形态它一律放过。**
       ⇒ 判据改成「这份文件里**不许出现** `StrOutputParser()` 调用」——**不依赖任何前置识别**。
       （本仓的既有约定就是"取消息本体"；真需要例外，加显式豁免并**附一条能打印的理由**。）
    """
    tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
    bad = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "StrOutputParser"
    ]
    assert not bad, (
        f"{filename} 里出现了 `StrOutputParser()` 调用（行 {[n.lineno for n in bad]}）——\n"
        "  它会把 `AIMessage` 剥成 `str`，`usage_metadata` 随之丢光 ⇒ 记账**静默收不到数**。\n"
        "  ⇒ 改为直调 `llm.invoke(messages)` 取消息本体（`DEC-073`）。"
    )


def test_query_rewriter_uses_record_usage_not_record_from_response():
    """🔴 本模块是**全仓唯一**用裸 `openai.OpenAI` 的地方 ⇒ 响应带 `.usage`，
    **没有** `usage_metadata` ⇒ 用 `record_from_response` 会**恒返回 `False` 静默不记**
    （`test_token_budget_hookup.py::test_does_not_record_on_the_old_wrong_attribute` 钉的就是这个坑）。"""
    tree = ast.parse((_API / "query_rewriter.py").read_text(encoding="utf-8"))
    names = set()
    for fn, _sites in _innermost_llm_functions(tree):
        names |= _called_names(fn)
    assert "record_usage" in names, "query_rewriter 的 LLM 调用点没有记账"
    assert "record_from_response" not in names, (
        "query_rewriter 用的是裸 OpenAI（响应只有 .usage）"
        "—— `record_from_response` 对它**恒 False 静默不记**，⛔ 用错了比不记还坏"
    )

