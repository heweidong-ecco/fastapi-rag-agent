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
from langchain_openai import ChatOpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_CHAT
from search_tools import web_search
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage,SystemMessage
from datetime import datetime

# ==================== 初始化模型 ====================
llm = ChatOpenAI(
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0
)

# ==================== 定义工具 ====================
@tool
def calculator(expression: str) -> str:
    """计算数学表达式，例如 3*4-5/6。"""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算错误: {e}"

@tool
def date_today(query: str = "") -> str:
    """查询今天的日期、星期几。"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekdays[now.weekday()]}"


from browser_tools import fetch_webpage, fetch_webpage_html, screenshot_webpage
from code_executor import execute_python
# 新的的工具列表
tools = [
    web_search, calculator, date_today,
    fetch_webpage, fetch_webpage_html, screenshot_webpage,
    execute_python  # 新增
]

# 新增浏览器工具
tools.extend([fetch_webpage, fetch_webpage_html])

# 重新绑定工具到模型
llm_with_tools = llm.bind_tools(tools)



# 为每个工具创建模型实例（用于子图）
llm_search = ChatOpenAI(model=LLM_MODEL_CHAT, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)
llm_calc = ChatOpenAI(model=LLM_MODEL_CHAT, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)
llm_date = ChatOpenAI(model=LLM_MODEL_CHAT, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)

# ==================== 定义全局 State ====================
class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    intent: str  # 存储用户意图（search/calculator/date）
    final_output: str  # 存储最终回复
    user_name: str          # 新增：当前对话的用户名
    memory_space: str       # 新增：当前使用的记忆空间

# ==================== 创建 通用的“记忆注入”工具函数 ====================
from memory_store import search_user_memory

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

    def search_summarize(state: AgentState):
        """总结搜索结果"""
        raw = state["messages"][-1].content
        summary_prompt = f"请用一句话总结以下信息：{raw}"
        summary = llm_search.invoke([HumanMessage(content=summary_prompt)])
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
        query = state["messages"][-1].content
        # 使用简单 prompt 提取表达式
        extract_prompt = f"提取以下问题中的数学表达式，只返回表达式，不要其他内容：{query}"
        expression = llm_calc.invoke([HumanMessage(content=extract_prompt)])
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

    def translate_execute(state: AgentState):
        """执行翻译"""
        query = state["messages"][-1].content
        # 简单粗暴地翻译成英文
        prompt = f"请将以下内容翻译成英文，只输出翻译结果：\n\n{query}"
        result = llm.invoke([HumanMessage(content=prompt)])
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
    llm_react = ChatOpenAI(
        model=LLM_MODEL_CHAT,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=0
    )
    llm_react_with_tools = llm_react.bind_tools(tools)

    def agent_decide(state: AgentState):
        """决策节点：调用模型，让它决定是回复文本还是调用工具。"""
        # 构建基础 system prompt
        system_prompt = "你是一个能使用工具的智能助理。请根据用户需求自主调用工具完成任务。"

        # 注入长期记忆
        system_prompt = inject_memories_to_prompt(system_prompt, state)
        # 将 system prompt 和消息列表合并
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm_react_with_tools.invoke(messages)
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

    subgraph.add_node("agent", agent_decide)
    subgraph.add_node("tools", tool_execute)
    subgraph.set_entry_point("agent")
    subgraph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END}
    )
    subgraph.add_edge("tools", "agent")

    return subgraph.compile()

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
        intent = llm.invoke([HumanMessage(content=classify_prompt)])
        state["intent"] = intent.content.strip()
        return state

    # 2. 添加对话节点（简单聊天）
    def chat_node(state: AgentState):
        # 构建基础 system prompt
        system_prompt = "你是一个智能助理，请直接回答用户的问题。"

        # 注入长期记忆
        system_prompt = inject_memories_to_prompt(system_prompt, state)

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm.invoke(messages)
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