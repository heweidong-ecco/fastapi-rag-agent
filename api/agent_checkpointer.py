'''# 查看当前状态
current_state = checkpointer_agent.get_state(config)
print(current_state.values["messages"])

# 查看状态历史
state_history = list(checkpointer_agent.get_state_history(config))
for snapshot in state_history:
    print(f"步骤: {snapshot.next}, 消息数: {len(snapshot.values['messages'])}")
'''

"""
带 Checkpointer 持久化的 LangGraph Agent
(支持 SQLite 持久化)
(支持 Redis 持久化)
"""
import os
from typing import TypedDict, List, Annotated
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver  # 新增
# 新增,RedisSaver 版本不兼容问题还没解决，现在暂时不用
# from langgraph.checkpoint.redis import RedisSaver  
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from datetime import datetime

# ==================== 初始化模型 ====================
llm = ChatOpenAI(
    model="qwen-turbo",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
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

search_tool = DuckDuckGoSearchRun()
tools = [search_tool, calculator, date_today]
llm_with_tools = llm.bind_tools(tools)

# ==================== 定义 State ====================
class AgentState(TypedDict):
    messages: Annotated[List, operator.add]

# ==================== 定义节点 ====================
from token_tracker import record_usage #Token统计模块
def agent_decide(state: AgentState):
    response = llm_with_tools.invoke(state["messages"])
    # 统计 Token
    if hasattr(response, "usage"):
        record_usage(
            model="qwen-turbo",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            purpose="query_rewrite",
        )
    return {"messages": [response]}

def tool_execute(state: AgentState):
    last_message = state["messages"][-1]
    tool_messages = []
    for tc in last_message.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]
        if tool_name == "search":
            result = search_tool.invoke(tool_args["query"])
        elif tool_name == "calculator":
            result = calculator.invoke(tool_args)
        elif tool_name == "date_today":
            result = date_today.invoke(tool_args)
        else:
            result = f"未找到工具: {tool_name}"
        tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"], name=tool_name)
        tool_messages.append(tool_msg)

    return {"messages": tool_messages}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# ==================== 构建图（支持选择 Checkpointer 后端） ====================
# ======= 下面的的是混合经典的典型架构：混合架构后端，目前学习阶段，暂时用不到 =======
'''
# ======= 支持 MemorySaver SqliteSaver RedisSaver 混合架构后端 =======
# 典型架构：API 实例写 Redis，后台任务定期将过期数据迁移到 SQLite/PostgreSQL。
# 混合架构示例
from langgraph.checkpoint.redis import RedisSaver
from langgraph.checkpoint.sqlite import SqliteSaver

class HybridCheckpointer:
    def __init__(self):
        self.hot_store = RedisSaver.from_conn_string("redis://localhost:6379/0")
        ⭐️，这里要修改保存地址，单sqlite，本地保存地址是：agent_history.db，混合架构是：archive.db
        self.cold_store = SqliteSaver.from_conn_string("./archive.db")
    
    def put(self, config, checkpoint, metadata):
        # 写入热存储
        self.hot_store.put(config, checkpoint, metadata)
        # 异步写入冷存储（简化示例，实际应用使用任务队列）
        self.cold_store.put(config, checkpoint, metadata)
'''
# ======= 支持 MemorySaver SqliteSaver RedisSaver 自主选择架构后端 =======
def build_checkpointer_agent(backend: str = "memory"): # 默认memory即MemorySaver
    workflow = StateGraph(AgentState)
    # ... 添加节点和边的代码保持不变 ...

    # 根据后端选择 Checkpointer
    if backend == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver
        db_path = os.path.join(os.path.dirname(__file__), "agent_history.db")
        checkpointer = SqliteSaver.from_conn_string(db_path)
    elif backend == "redis":
        # 从环境变量获取 Redis 连接信息
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        # 新增,RedisSaver 版本不兼容问题还没解决，现在暂时不用
        # checkpointer = RedisSaver.from_conn_string(redis_url)
    else:  # 默认 memory
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)

# 全局实例（可通过环境变量 AGENT_CHECKPOINT_BACKEND 切换）
backend = os.getenv("AGENT_CHECKPOINT_BACKEND", "memory")
checkpointer_agent = build_checkpointer_agent(backend=backend)
'''支持 SqliteSaver 和 MemorySaver 后端的代码
def build_checkpointer_agent(use_sqlite: bool = True):
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    # 创建 Checkpointer
    if use_sqlite:
        # SQLite 持久化，保存在本地文件中
        db_path = os.path.join(os.path.dirname(__file__), "agent_history.db")
        checkpointer = SqliteSaver.from_conn_string(db_path)
    else:
        checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer)

# 全局实例（默认使用 SQLite）
checkpointer_agent = build_checkpointer_agent(use_sqlite=True)
'''
'''支持 MemorySaver 后端的代码
# ==================== 构建图（关键：传入 checkpointer） ====================
def build_checkpointer_agent():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    # 创建 Checkpointer（内存版，后续可换成 SqliteSaver）
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)

# 全局实例
checkpointer_agent = build_checkpointer_agent()
'''