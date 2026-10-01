"""单次上限的接线回归（`B7` · `①b` Task 1）。

🔴 为什么不能只测常量值：常量对了、**没接上**，等于没有上限。
   本文件钉的是"构造点真的带上了 max_tokens"。
⚠️ 不碰 DB / Redis —— 只看构造出来的 AST / 对象属性。

📌 **本文件同时是"哪些构造点存在"的清单** ——
   ⚠️ 加新 `ChatOpenAI(...)` 而没进 `EXPECTED_MAX_TOKENS` ⇒ 第 2 条会红，
   **逼你当场决定它属于"答案"还是"中间步骤"**（而不是默认填一个）。
"""
import ast
import pathlib

import token_config

API = pathlib.Path(__file__).resolve().parent


def _chat_openai_sites():
    """扫 `api/*.py`（⛔ 不含 `test_*`），yield `(文件, 行号, max_tokens 那个关键字的 AST 节点 or None)`。

    ⚠️ 用 AST 而不是 grep：`ChatOpenAI(` 也会出现在**注释与 docstring** 里
       （本仓栽过 —— `docs/规范/开发规范.md` §3.1「批量替换后按位置核」）。
    """
    for p in sorted(API.glob("*.py")):
        if p.name.startswith("test_"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "ChatOpenAI":
                continue
            kw = next((k for k in node.keywords if k.arg == "max_tokens"), None)
            yield p.name, node.lineno, (kw.value if kw else None)


def test_no_chat_openai_without_max_tokens():
    """全仓**不许**再有"没给 max_tokens"的 `ChatOpenAI(...)`。

    ⇒ 这条失败时，**失败信息本身就是待办清单**（逐行给出文件:行号）。
    """
    offenders = [f"{f}:{ln}" for f, ln, v in _chat_openai_sites() if v is None]
    assert not offenders, (
        "这些 ChatOpenAI(...) 没设 max_tokens ⇒ 单次上限对它们不存在：\n  "
        + "\n  ".join(offenders)
    )


# 每个**含 ChatOpenAI 的文件**该接哪个常量 —— 这是 `①b` Task 1 的**分类裁定**，
# ⛔ 不是"从代码里推出来的规律"。理由见 `docs/specs/token_tracker.md` 的分类表。
EXPECTED_MAX_TOKENS = {
    # ---- 答案生成类：要完整答案 ⇒ 2000 ----
    "api_v1_rag.py": "MAX_TOKENS_ANSWER",              # :563 流式答案 · :726 WS agent
    "rag_pipeline.py": "MAX_TOKENS_ANSWER",            # answer_llm
    # ⚠️ 2026-10-01 补：**本行是计划里【漏掉】的那处**（`①b` Task 1 的 Files 清单没有它）。
    #    它是**离线评测脚本**：:127 生成"被评的答案"、:272 又当 RAGAS judge ⇒ 两处都是长输出。
    #    ⛔ 不接的话，守卫测试会红；接小（1024）则**judge 输出可能被截断 ⇒ 评分静默失真**。
    "evaluate_with_ragas.py": "MAX_TOKENS_ANSWER",
    # ---- 中间步骤类：planner / executor / 质检 / agent 各节点 ⇒ 1024 ----
    "agent_checkpointer.py": "MAX_TOKENS_AGENT",
    "agent_graph.py": "MAX_TOKENS_AGENT",
    "agent_graph_advanced.py": "MAX_TOKENS_AGENT",
    "agent_graph_advanced_learning.py": "MAX_TOKENS_AGENT",
    "plan_execute.py": "MAX_TOKENS_AGENT",             # planner / executor / quality_checker
}


def test_each_site_uses_the_agreed_budget():
    """⚠️ **只钉"有没有 max_tokens"不够** —— 全接成 `MAX_TOKENS_AGENT`(1024) 也能过第 1 条，
    但那会把**答案截断**（`token_config` 里写明：压到 1800 以下就开始截答案）。

    ⇒ 第 2 条钉**分类**：每个文件接的是不是裁定表里那个常量。
    """
    seen, wrong = set(), []
    for fname, lineno, value in _chat_openai_sites():
        seen.add(fname)
        got = getattr(value, "id", None) or getattr(value, "attr", None)
        want = EXPECTED_MAX_TOKENS.get(fname)
        if want is None:
            wrong.append(f"{fname}:{lineno} 用了 max_tokens={got}，但本文件【没进裁定表】"
                         f" ⇒ 请先决定它属于「答案」还是「中间步骤」")
        elif got != want:
            wrong.append(f"{fname}:{lineno} 接的是 {got}，裁定表要求 {want}")
    assert not wrong, "接线与裁定表不符：\n  " + "\n  ".join(wrong)

    # 反向：裁定表里列了、但代码里已经找不到构造点的 —— 表腐了，要清
    stale = sorted(set(EXPECTED_MAX_TOKENS) - seen)
    assert not stale, f"裁定表里的这些文件已无 ChatOpenAI 构造点，请从表中删掉：{stale}"


def test_the_two_budgets_are_distinct_and_answer_is_larger():
    """两个常量**不许相等** —— 相等意味着"分类"这件事被做没了（一处改两处一起变，看不出来）。"""
    assert token_config.MAX_TOKENS_ANSWER > token_config.MAX_TOKENS_AGENT, (
        "答案上限必须大于中间步骤上限：答案被截断是用户可见的质量事故，"
        "中间步骤被截断只是多跑一轮"
    )
