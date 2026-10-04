"""
LangGraph 进阶示例：多分支路由与子图协作
"""
import os
import json
import asyncio
from typing import TypedDict, List, Annotated
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from llm_factory import make_llm   # ①b Task 5：model / api_key / base_url / max_tokens 的唯一落点
from search_tools import web_search
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage,SystemMessage
from langchain_core.runnables import RunnableConfig   # B1：节点要靠它把回调接进模型调用
from datetime import datetime
from safe_math import calculate  # DEC-049：`calculator` 的求值实现 —— ⛔ 别改回 `eval`
# 🔴 2026-10-04（`DEC-072`）：本图**6 个节点调 LLM，全都既不拦也不记** —— 是三条链里最大的
#    那个口子（`/agent/advanced_chat` 与它的 `/stream` 都走这张图）。
#    `record_from_response` 是三张图共用的**唯一记账实现**，⛔ 别在本文件里另抄 6 份取用量。
from token_tracker import check_token_budget, record_from_response, BUDGET_EXCEEDED_MSG

# ==================== 初始化模型 ====================
# ⚠️ 角色 = 「模型轴 chat」+「长度轴 agent(1024)」—— 见 `api/llm_factory.py` 的模块 docstring。
llm = make_llm("chat", "agent")

# ==================== 定义工具 ====================
@tool
def calculator(expression: str) -> str:
    """计算数学表达式，例如 3*4-5/6。"""
    # 🔴 DEC-049：⛔ 不许改回 `eval` —— 理由与实测见 `api/agent_graph.py` 同名处 / `api/safe_math.py`。
    return calculate(expression)

@tool
def date_today(query: str = "") -> str:
    """查询今天的日期、星期几。"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekdays[now.weekday()]}"


# 🔴 2026-09-20（业务方裁「乙」）：**LLM 工具表改为从 MCP 注册表【派生】—— 单一事实源。**
#
#    此前这里是一份**手工维护**的列表，与 `mcp_server.TOOLS` **各写各的** ⇒ 漂移：
#      · `mcp_server.TOOLS`   **6** 个
#      · 本文件的 `tools`     **7** 个（多一个 `fetch_webpage_html`）
#    而 `mcp_server.TOOL_HANDLERS` 是**从 `TOOLS` 生成的** ⇒ 多出来的那个工具
#    **永远取不到 handler** ⇒ 走到那一步只回一句「未找到工具: fetch_webpage_html」，
#    **不报错、不 500** —— 是**静默失败**。
#
#    ⚠️ **为什么不选"把它加进 MCP 就好"**：`fetch_webpage_html` **同样依赖 Playwright/Chromium**
#       （`browser_tools.py:3` 模块级 import + `p.chromium.launch()`），而**本仓任何部署方式
#       都不装浏览器**（`api/Dockerfile` / `docker-compose.yml` 都没有 `playwright install`）
#       ⇒ 加进去它**也永远 unhealthy**，只是把「4/6」变成「4/7」。
#
#    ⇒ 改为**派生**：两表**结构上不可能再漂** —— 以后加工具只需在 `mcp_server.TOOLS` 加一行。
#    ⚠️ **这是一次【工具 schema 变更】，须在 PR 里显式声明**：LLM 现在看到的
#       `calculator` / `date_today` 是 `simple_tools` 那份（**实现与本文件原版逐字等价**，
#       但 **docstring 更详细** —— 多出「输入的必须是纯数学表达式」/「忽略查询参数」两句）。
#    回归测试:api/test_agent_repairs.py::test_llm_tool_table_is_sourced_from_mcp_registry
from mcp_server import TOOLS as _MCP_TOOLS

tools = [t["func"] for t in _MCP_TOOLS]

# 🔴 2026-09-20 另删掉了一行 `tools.extend([fetch_webpage, fetch_webpage_html])` ——
#    上面那个列表**已经包含**这两个工具 ⇒ 加了之后**各出现两次** ⇒
#    `llm_react.bind_tools(tools)` 发给 LLM 时被拒：
#      `openai.BadRequestError: 400 - 'Tool names must be unique.'`
#    ⇒ **3 代 Agent 的 REACT 分支 100% 500**。
#    ⚠️ 它此前**测不出来** —— `/agent/advanced_chat` 会先在 mem0 那一步 500（bug 1），
#       根本走不到 REACT 分支;**修好 bug 1 才把它暴露出来**。
#    回归测试:api/test_agent_repairs.py::test_react_tool_list_has_no_duplicate_names
#    📌 **本文件下面仍保留自带的 `calculator` / `date_today`** —— 它们被**子图节点**
#       直接 `.invoke()`（`:145` / `:160`）。⇒ 与 `mcp_server.TOOLS` 里那两个**同名不同对象**。
#       实现逐字等价，**当前无害**；但属"重复定义"，已登记为清理项（`docs/待办登记…` §三）。

# 重新绑定工具到模型
llm_with_tools = llm.bind_tools(tools)



# 为每个工具创建模型实例（用于子图）
# ⚠️ 三个都 = 「模型轴 chat」+「长度轴 agent(1024)」，与上面的 `llm` 同角色。
llm_search = make_llm("chat", "agent")
llm_calc = make_llm("chat", "agent")
llm_date = make_llm("chat", "agent")

# ==================== 定义全局 State ====================
class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    intent: str  # 存储用户意图（search/calculator/date）
    final_output: str  # 存储最终回复
    user_name: str          # 新增：当前对话的用户名
    memory_space: str       # 新增：当前使用的记忆空间
    # 🔴 2026-10-04（`DEC-072`）：本图此前**没有这个键** ⇒ 6 个调用点记账时取不到会话。
    #    ⚠️ **由端点注入**（`api_v1_agent.py` 的 `/agent/advanced_chat` 与它的 `/stream`），
    #       一律 `.get(..., "unknown")` 读。
    #    ⚠️ 子图（search/calc/date/translate/react）与本图**共用同一个 `AgentState`** ⇒
    #       父图的 `thread_id` 会流进子图节点，⛔ 不必逐个子图再注入一次。
    thread_id: str

# ==================== 创建 通用的“记忆注入”工具函数 ====================
# ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：此处的 `from memory_store import search_user_memory`
#    与文件下方**逐字重复**，且下面那份在它之前从未被使用 ⇒ 删此处、保留下方。

def inject_memories_to_prompt(original_prompt: str, state: AgentState) -> str:
    """
    检索相关长期记忆，并将其注入到 Prompt 开头。
    如果检索不到，则返回原始 Prompt。
    """
    user_name = state.get("user_name", "default_user")
    memory_space = state.get("memory_space", "default")
    user_query = state["messages"][-1].content

    user_id = f"{user_name}:{memory_space}"
    memories = search_user_memory(user_id, user_query)

    if memories:
        memory_text = "\n".join(memories)
        enhanced_prompt = f"""以下是与用户相关的长期记忆，请参考这些信息来个性化你的回答：
{memory_text}

{original_prompt}"""
        return enhanced_prompt
    return original_prompt


# ==================== 创建子图（搜索研究部门） ====================
def create_search_subgraph():
    """
    搜索子图：执行搜索 -> 总结搜索结果 -> 返回
    这是一个独立的图，有自己的节点和流程。
    """
    subgraph = StateGraph(AgentState)

    def search_execute(state: AgentState):
        """执行搜索"""
        query = state["messages"][-1].content
        result = web_search.invoke(query)
        return {"messages": [AIMessage(content=f"搜索原始结果：{result[:500]}")]}

    def search_summarize(state: AgentState, config: RunnableConfig):
        """总结搜索结果

        🔴 **`B1`（2026-10-04）：改真流式** —— 声明 `config` 并把它转发给 `.stream()`，
           这是 `astream(stream_mode="messages")` 出不出 token 的**唯一条件**（`DEC-050`）。
           ⛔ 本文件所有节点**都是同步的**，别改成 `async def`：同步的 `graph.invoke()`
           （`/agent/advanced_chat` 走的就是它）会当场抛 `TypeError`。
        """
        # 🔴 2026-10-04（`DEC-072`）：拦在 `.stream()` **之前** —— 放之后钱已花，只能丢结果。
        #    ⚠️ 这是**子图节点**：`user_name` / `thread_id` 由父图经共用 `AgentState` 流进来。
        user_name = state.get("user_name", "unknown")
        thread_id = state.get("thread_id", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {"final_output": BUDGET_EXCEEDED_MSG}

        raw = state["messages"][-1].content
        summary_prompt = f"请用一句话总结以下信息：{raw}"
        # ⚠️ `+` 聚合（`AIMessageChunk.__add__`），⛔ 不是 `content +=`。
        # 🔴 **遍历【所有】块**，⛔ 不跳空 `content` —— `usage_metadata` 挂在**最后一块**上
        #    （provider 行为）。跳过它 ⇒ 下面那句记账**静默失效**，而接口一切正常。
        summary = None
        for chunk in llm_search.stream([HumanMessage(content=summary_prompt)], config=config):
            summary = chunk if summary is None else summary + chunk
        record_from_response(
            llm_search, summary, "answer_generation",
            user_name=user_name, thread_id=thread_id,
        )
        return {"final_output": summary.content}

    subgraph.add_node("search_execute", search_execute)
    subgraph.add_node("search_summarize", search_summarize)
    subgraph.set_entry_point("search_execute")
    subgraph.add_edge("search_execute", "search_summarize")
    subgraph.add_edge("search_summarize", END)

    return subgraph.compile()

# ==================== 创建子图（计算器部门） ====================
def create_calculator_subgraph():
    """计算器子图"""
    subgraph = StateGraph(AgentState)

    def calc_execute(state: AgentState):
        """从用户消息中提取表达式并计算"""
        # 🔴 2026-10-04（`DEC-072`）：拦在 `llm_calc.invoke()` **之前**。
        user_name = state.get("user_name", "unknown")
        thread_id = state.get("thread_id", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {"final_output": BUDGET_EXCEEDED_MSG}

        query = state["messages"][-1].content
        # 使用简单 prompt 提取表达式
        extract_prompt = f"提取以下问题中的数学表达式，只返回表达式，不要其他内容：{query}"
        expression = llm_calc.invoke([HumanMessage(content=extract_prompt)])
        # 🔴 记账 —— `purpose="query_rewrite"`：这一步产出的**不是给用户的答案**，
        #    而是喂给 `calculator` 工具的**规整后的输入**（真答案 `42` 来自工具，见 `STREAMABLE_NODES` 那张表）。
        #    ⚠️ 别改成 `answer_generation`：那会让"这一步是什么角色"在账面上失真。
        record_from_response(
            llm_calc, expression, "query_rewrite",
            user_name=user_name, thread_id=thread_id,
        )
        result = calculator.invoke(expression.content)
        return {"final_output": result}

    subgraph.add_node("calc_execute", calc_execute)
    subgraph.set_entry_point("calc_execute")
    subgraph.add_edge("calc_execute", END)

    return subgraph.compile()

# ==================== 创建子图（日期部门） ====================
def create_date_subgraph():
    """日期子图"""
    subgraph = StateGraph(AgentState)

    def date_execute(state: AgentState):
        result = date_today.invoke("")
        return {"final_output": result}

    subgraph.add_node("date_execute", date_execute)
    subgraph.set_entry_point("date_execute")
    subgraph.add_edge("date_execute", END)

    return subgraph.compile()

# ==================== 新增翻译子图（日期部门） ====================
# 因为翻译功能是直接调用大模型llm，不需要定义python函数脚本实现翻译功能，所以不用使用tool函数定义工具。
def create_translate_subgraph():
    """
    翻译子图：将用户输入翻译成英文。
    如果用户指定了目标语言，则翻译成对应语言（此处简化为英文）。
    """
    subgraph = StateGraph(AgentState)

    def translate_execute(state: AgentState, config: RunnableConfig):
        """执行翻译（`B1` · 2026-10-04 改真流式 —— 译文本就是答案 ⇒ 该流）"""
        # 🔴 2026-10-04（`DEC-072`）：拦在 `.stream()` **之前**。
        user_name = state.get("user_name", "unknown")
        thread_id = state.get("thread_id", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {"final_output": BUDGET_EXCEEDED_MSG}

        query = state["messages"][-1].content
        # 简单粗暴地翻译成英文
        prompt = f"请将以下内容翻译成英文，只输出翻译结果：\n\n{query}"
        # ⚠️ 同 `search_summarize`：同步 `.stream()` + 转发 `config` + `+` 聚合所有块。
        result = None
        for chunk in llm.stream([HumanMessage(content=prompt)], config=config):
            result = chunk if result is None else result + chunk
        record_from_response(
            llm, result, "answer_generation",
            user_name=user_name, thread_id=thread_id,
        )
        return {"final_output": result.content}

    subgraph.add_node("translate_execute", translate_execute)
    subgraph.set_entry_point("translate_execute")
    subgraph.add_edge("translate_execute", END)

    return subgraph.compile()

# ==================== 新增 ReAct 子图：用来执行子图是否需要循环，====================
# 循环的作用是如果用户提出的问题需要多个工具的调用就需要ReAct模式[思考-行动-思考]的循环思考模型，
# 这里的ReAct作为内部子图的思考动作来执行，这就是子图功能的强大，可以通过子图在内部嵌套各种的思考模型和功能，
def create_react_subgraph():
    """
    ReAct 子图：能自主调用工具的通用任务处理部门。
    内部包含 agent 节点和 tools 节点，形成一个循环。
    """
    subgraph = StateGraph(AgentState)

    # 为子图单独绑定工具的模型
    # ⚠️ 角色 = 「模型轴 chat」+「长度轴 agent(1024)」。
    llm_react = make_llm("chat", "agent")
    llm_react_with_tools = llm_react.bind_tools(tools)

    def agent_decide(state: AgentState, config: RunnableConfig):
        """决策节点：调用模型，让它决定是回复文本还是调用工具。

        🔴 **`B1`（2026-10-04）：改真流式**（声明 `config` + 转发 `.stream()`，`DEC-050`）。
           ⚠️ **`+` 聚合在这里是【必须】的**：`tool_calls` 是碎片化到达的，只拼 `content`
           会让本子图的 `should_continue` 判不出 `"tools"` ⇒ **工具永远不会被执行**，
           而 `summarize` 照样写出 `final_output`（看着像正常回答）。
        """
        # 🔴 2026-10-04（`DEC-072`）：拦在 `.stream()` **之前**。
        #    ⚠️ 超预算时**必须返回 AIMessage、⛔ 不能只写 `final_output`** ——
        #       本子图的出口是 `should_continue` 读 `messages[-1].tool_calls`：
        #       给一条**没有 tool_calls** 的消息 ⇒ 走 `END` ⇒ 由 `summarize` 把它的文本
        #       落成 `final_output`（那条边见 `add_conditional_edges` 的 `{END: "summarize"}`）。
        user_name = state.get("user_name", "unknown")
        thread_id = state.get("thread_id", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {"messages": [AIMessage(content=BUDGET_EXCEEDED_MSG)]}

        # 构建基础 system prompt
        system_prompt = "你是一个能使用工具的智能助理。请根据用户需求自主调用工具完成任务。"

        # 注入长期记忆
        system_prompt = inject_memories_to_prompt(system_prompt, state)
        # 将 system prompt 和消息列表合并
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = None
        for chunk in llm_react_with_tools.stream(messages, config=config):
            response = chunk if response is None else response + chunk
        # 🔴 记账。⚠️ 这是**循环节点**（`tools` ⇒ `agent`）—— 每一轮**各记一笔**，
        #    这正是要的：循环 N 轮就花 N 次钱。
        record_from_response(
            llm_react_with_tools, response, "agent_decision",
            user_name=user_name, thread_id=thread_id,
        )
        return {"messages": [response]}
    # 工具执行节点现在只需一行核心逻辑
    from mcp_server import TOOL_HANDLERS

    def tool_execute(state: AgentState):
        last_message = state["messages"][-1]
        tool_messages = []

        for tc in last_message.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]

            # 从 MCP Server 的处理器中查找工具
            handler = TOOL_HANDLERS.get(tool_name)
            if handler:
                result = handler(tool_args)
            else:
                result = f"未找到工具: {tool_name}"

            tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"], name=tool_name)
            tool_messages.append(tool_msg)

        return {"messages": tool_messages}
    

    def should_continue(state: AgentState):
        """路由函数：检查最后一条消息是否包含tool_calls。"""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    def summarize(state: AgentState):
        """收尾节点：把最后一条消息的文本落成 `final_output`。

        🔴 2026-09-20 补（第 9 个依赖漂移之外的缺陷）:
          本子图原先**只有 agent / tools 两个节点、没有任何节点写 `final_output`**,
          而端点读的是 `api_v1_agent.py` 的 `result.get("final_output", "处理完成")`
          ⇒ **走 REACT 意图时永远返回占位串「处理完成」**（其余四个子图都写了）。
          实测复现:`POST /agent/advanced_chat?question=帮我规划…三步计划`
          → `{"answer":"处理完成","intent":"REACT"}`。
          ⚠️ 它此前**测不出来** —— 先是 mem0 那道 500、后是工具重名那道 400,
             REACT 分支根本走不到底。**修好前面两个才把它暴露出来。**
          回归测试:`api/test_agent_repairs.py::test_react_subgraph_sets_final_output`
        """
        last = state["messages"][-1]
        return {"final_output": getattr(last, "content", "") or ""}

    subgraph.add_node("agent", agent_decide)
    subgraph.add_node("tools", tool_execute)
    subgraph.add_node("summarize", summarize)
    subgraph.set_entry_point("agent")
    subgraph.add_conditional_edges(
        "agent",
        should_continue,
        # ⚠️ 原本这里是 `{..., END: END}` —— 直接结束就没有节点能写 final_output。
        {"tools": "tools", END: "summarize"}
    )
    subgraph.add_edge("tools", "agent")
    subgraph.add_edge("summarize", END)

    return subgraph.compile()

# ==================== 流式白名单（B1 · 2026-10-04）====================
# 🔴 **`B1`：可流节点名单放在【图模块里】，⛔ 端点不许自己抄一份字面量**（理由见
#    `api/agent_graph.py` 同名常量处 —— 一个名字两个来源必然漂移，而漂移是**静默**的）。
# ⚠️ 必须放在**模块级**（⛔ 不能放进 `build_advanced_agent()`）：端点是按
#    `agent_graph_advanced_learning.STREAMABLE_NODES` 取的，函数体里的是局部名。
#
# 🔴🔴 **这张名单是「6 个调 LLM 的节点里只有 4 个该流」那条判断的落点** ——
#    它**⛔ 读代码推不出来**（要同时知道「这个节点的 LLM 输出是什么角色」＋「答案最终从哪来」）。
#    完整对照表 ⇒ `docs/specs/agent_graph_advanced_learning.md` 的 ⭐ 节。
#
# | 节点 | 调什么 | 该流？| 为什么 |
# |---|---|---|---|
# | `chat` | `llm` | ✅ | 就是答案 |
# | `search_summarize` | `llm_search` | ✅ | 一句话总结 = 答案 |
# | `translate_execute` | `llm` | ✅ | 译文 = 答案 |
# | `agent`（react 子图内层名） | `llm_react_with_tools` | ✅ | 答案 + `tool_calls` |
# | ⛔ `supervisor` | `llm` | ❌ | 输出是**路由词**（`SEARCH`/`CALCULATOR`/…）—— 流出去 = 答案前面先蹦一个 `SEARCH` |
# | ⛔ `calc_execute` | `llm_calc` | ❌ | 它**只提取表达式**（`6*7`）；真答案 `42` 来自 `calculator` **工具**，不是 LLM |
#
# ⚠️ 另有 **2 个节点根本不调 LLM** 因而无字可流：`date_execute`（纯工具）、`summarize`（只搬运）。
# 🔴 由此得出的一条**必须知道、别误判成 bug 的事实**：**CALC 与 DATE 两个分支本来就一个字都流不出来**
#    —— 用户会一直等到最后一帧汇总里的 `answer`。那是设计如此，⛔ 别为了"看起来也在流"
#    把 `calc_execute` 的提取过程放出来（那是中间产物，不是答案）。
STREAMABLE_NODES = frozenset({
    "chat",
    "search_summarize",
    "translate_execute",
    "agent",     # ⚠️ 子图**内层**名 —— `meta["langgraph_node"]` 报的就是它，⛔ 不是 `react_dept:agent`
})


# ==================== 构建主图 ====================
from memory_store import search_user_memory
def build_advanced_agent():
    workflow = StateGraph(AgentState)

    # 1. 添加主管节点（大脑）
    def supervisor(state: AgentState):
        """分析用户意图，决定路由方向（增强版：注入长期记忆mem0）"""
        user_query = state["messages"][-1].content

        # 从 Mem0 检索相关记忆（user_id 从 state 或配置中获取，这里先写死示例）
        user_name = state.get("user_name", "default_user")
        memory_space = state.get("memory_space", "default")
        # 构建 Mem0 的 user_id
        user_id = f"{user_name}:{memory_space}"
        # 从 Mem0 检索相关记忆
        memories = search_user_memory(user_id, user_query)

        # 构建包含记忆的上下文
        memory_context = ""
        if memories:
            memory_context = "\n用户相关记忆：\n" + "\n".join(memories)
        
        classify_prompt = f"""分析以下用户请求，只返回一个单词表示意图：
- 如果需要搜索、查资料、了解新闻 → SEARCH
- 如果需要数学计算 → CALCULATOR
- 如果询问日期时间 → DATE
- 如果需要翻译文本 → TRANSLATE
- 其他复杂问题 → REACT

{memory_context}
用户请求：{user_query}
意图："""
        # 🔴 2026-10-04（`DEC-072`）：拦在 `llm.invoke()` **之前**。
        #    🔴🔴 **超预算时【必须】给 `intent`** —— `route_by_intent` 读的是 `state["intent"]`
        #        （`:423`）。少了它，langgraph 会当场 `KeyError: 'intent'` ⇒ **500**，
        #        而不是一句"预算用完了"。给 `"CHAT"` ⇒ 落到兜底分支 `chat_node`，
        #        而 `chat_node` 自己的守卫也会拦下（同一个人、同样的额度）⇒
        #        **最终不调任何模型**，用户看到的就是那句话术。
        #    ⚠️ 这与参照图 `agent_graph_advanced.py:333` 的写法**不同**是**有意的**——
        #       那张图的路由函数不读 `intent`，所以它不需要给。
        if not check_token_budget(state.get("user_name", "unknown"), estimated_tokens=500):
            return {"intent": "CHAT", "final_output": BUDGET_EXCEEDED_MSG}

        intent = llm.invoke([HumanMessage(content=classify_prompt)])
        # ⚠️ 记账放在 `state["intent"] = …` **之前**：下面那行是**改 state 本身**（不是返回增量），
        #    这里插在它前面只是为了读起来清楚，两者无依赖。
        record_from_response(
            llm, intent, "agent_decision",
            user_name=state.get("user_name", "unknown"),
            thread_id=state.get("thread_id", "unknown"),
        )
        state["intent"] = intent.content.strip()
        return state

    # 2. 添加对话节点（简单聊天）
    def chat_node(state: AgentState, config: RunnableConfig):
        """兜底对话节点（`B1` · 2026-10-04 改真流式）。

        ⚠️ 它是**默认落点**：`route_by_intent` 是**精确匹配**的，模型多吐一个句号
           （`REACT。`）就静默落到这里 ⇒ **这条分支的流式体验 = 大多数请求的体验**。
        """
        # 🔴 2026-10-04（`DEC-072`）：拦在 `.stream()` **之前**。
        #    ⚠️ 这一处**不只是"漏记"** —— 它是 `supervisor` 超预算时的**落点**（见 `supervisor` 注释）：
        #       这里的守卫是"那条路不花钱"的**第二道保证**，⛔ 别因为它看着冗余就删。
        user_name = state.get("user_name", "unknown")
        thread_id = state.get("thread_id", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {"final_output": BUDGET_EXCEEDED_MSG}

        # 构建基础 system prompt
        system_prompt = "你是一个智能助理，请直接回答用户的问题。"

        # 注入长期记忆
        system_prompt = inject_memories_to_prompt(system_prompt, state)

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        # ⚠️ 同族写法：同步 `.stream()` + 转发 `config` + `+` 聚合所有块。
        response = None
        for chunk in llm.stream(messages, config=config):
            response = chunk if response is None else response + chunk
        record_from_response(
            llm, response, "answer_generation",
            user_name=user_name, thread_id=thread_id,
        )
        return {"final_output": response.content}

    # 3. 编译子图
    search_subgraph = create_search_subgraph()
    calc_subgraph = create_calculator_subgraph()
    date_subgraph = create_date_subgraph()
    translate_subgraph = create_translate_subgraph()
    react_subgraph = create_react_subgraph()

    # 4. 添加节点
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("chat", chat_node)
    workflow.add_node("search_dept", search_subgraph)
    workflow.add_node("calc_dept", calc_subgraph)
    workflow.add_node("date_dept", date_subgraph)
    workflow.add_node("translate_dept", translate_subgraph)
    workflow.add_node("react_dept", react_subgraph)

    workflow.set_entry_point("supervisor")

    # 5. 多分支条件路由
    def route_by_intent(state: AgentState):
        intent = state["intent"]
        if intent == "SEARCH": return "search_dept"
        elif intent == "CALCULATOR": return "calc_dept"
        elif intent == "DATE": return "date_dept"
        elif intent == "TRANSLATE": return "translate_dept"
        elif intent == "REACT": return "react_dept"
        else: return "chat" # chat 作为最终兜底

    workflow.add_conditional_edges("supervisor", route_by_intent, {
        "search_dept": "search_dept",
        "calc_dept": "calc_dept",
        "date_dept": "date_dept",
        "translate_dept": "translate_dept",
        "react_dept":"react_dept",
        "chat": "chat"
    })

    # 子图和对话节点执行完后，都走向结束
    workflow.add_edge("search_dept", END)
    workflow.add_edge("calc_dept", END)
    workflow.add_edge("date_dept", END)
    workflow.add_edge("translate_dept", END)
    # 添加 ReAct 子图到结束的边
    workflow.add_edge("react_dept", END)
    workflow.add_edge("chat", END)

    return workflow.compile(checkpointer=MemorySaver())