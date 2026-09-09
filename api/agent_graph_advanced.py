"""
升级版：api/agent_graph_advanced_1.0.0.py
Agent 图（集成 MCP Client）
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
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage,SystemMessage
from datetime import datetime
from token_tracker import record_usage
# 新增 预估消耗的前置检查
from token_tracker import check_token_budget
# 工具调用前插入预算检查 Token预算
from token_tracker import check_budget_before_call
from token_tracker import check_multilevel_budget

# ==================== 导入 MCP Client ====================
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ==================== 定义全局 State ====================
class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    intent: str  # 存储用户意图（search/calculator/date）
    final_output: str  # 存储最终回复
    user_name: str          # 新增：当前对话的用户名
    memory_space: str       # 新增：当前使用的记忆空间
    thread_id: str          # 新增：当前会话的 thread_id

# ==================== 初始化模型 ====================
llm = ChatOpenAI(
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0
)
# ==================== 导入 长期记忆Mem0 模块 ====================
from memory_store import search_user_memory

def inject_memories_to_prompt(original_prompt: str, state: AgentState) -> str:
    """
    检索相关长期记忆，并将其注入到 Prompt 开头。
    如果检索不到，则返回原始 Prompt。         
    """
    user_name = state.get("user_name", "default_user")
    memory_space = state.get("memory_space", "default")
    
    # 从消息列表中提取用户查询
    messages = state.get("messages", [])
    if messages:
        user_query = messages[-1].content
    else:
        user_query = ""

    user_id = f"{user_name}:{memory_space}"
    memories = search_user_memory(user_id, user_query)

    if memories:
        memory_text = "\n".join(memories)
        enhanced_prompt = f"""以下是与用户相关的长期记忆，请参考这些信息来个性化你的回答：
{memory_text}

{original_prompt}"""
        return enhanced_prompt
    return original_prompt

# ==================== MCP Client 连接管理 ====================
# _mcp_session 是一个全局单例，所有请求共享同一个会话，
# 并发阻塞：全局单例是同步的，一个请求正在调用工具时，另一个请求必须等待。
# 状态污染：不同用户的调用可能互相影响。
# 新增会话池 ，避免并发阻塞，和状况污染
"""
MCP Client 连接管理（会话池版本）
"""
import asyncio
from typing import List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 会话池配置
POOL_MIN_SIZE = 2      # 最小空闲会话数
POOL_MAX_SIZE = 10     # 最大会话数
_semaphore = asyncio.Semaphore(POOL_MAX_SIZE)  # 并发控制

# 会话池
_session_pool: List[ClientSession] = []
_pool_lock = asyncio.Lock()

async def initialize_pool():
    """启动时预创建最小数量的会话"""
    for _ in range(POOL_MIN_SIZE):
        session = await create_mcp_session()
        async with _pool_lock:
            _session_pool.append(session)
    print(f"MCP 会话池已初始化，当前大小: {len(_session_pool)}")

async def create_mcp_session():
    """创建新的 MCP 会话"""
    server_params = StdioServerParameters(
        command="python",
        args=["api/mcp_server.py"]
    )
    transport = await stdio_client(server_params)
    session = await ClientSession(transport[0], transport[1])
    await session.initialize()
    return session

async def get_mcp_session():
    """
    从池中获取一个 MCP 会话。
    如果池中有空闲会话，直接返回；
    如果池为空且未达到上限，创建新会话；
    如果达到上限，等待其他会话归还。
    """
    async with _semaphore:  # 控制最大并发数
        async with _pool_lock:
            if _session_pool:
                return _session_pool.pop()
        
        # 池为空，创建新会话
        return await create_mcp_session()

async def release_mcp_session(session: ClientSession):
    """
    归还会话到池中。
    不关闭会话，保持连接复用。
    """
    async with _pool_lock:
        if len(_session_pool) < POOL_MAX_SIZE:
            _session_pool.append(session)
        else:
            # 池已满，关闭多余会话
            await session.close()

async def close_all_sessions():
    """关闭所有会话（应用退出时调用）"""
    async with _pool_lock:
        for session in _session_pool:
            await session.close()
        _session_pool.clear()
    print("所有 MCP 会话已关闭")

async def get_mcp_tools():
    """通过 MCP Client 获取所有可用工具"""
    session = await get_mcp_session()
    tools = await session.list_tools()
    return tools

# 新增工具调用缓存
"""
MCP Client 工具调用缓存
"""
import hashlib
import json
import redis
import os
from functools import wraps

# 复用现有的 Redis 客户端（与 cache.py 相同配置）
# 从 config 导入 host/port，以正确应用本地开发时 localhost 的覆盖
from config import REDIS_HOST, REDIS_PORT
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

# 缓存过期时间（不同类型工具有不同时效性）
CACHE_TTL_MAP = {
    "date_today": 3600,        # 日期缓存 1 小时
    "web_search": 300,          # 搜索结果缓存 5 分钟
    "calculator": 86400,        # 数学计算结果缓存 24 小时
    "fetch_webpage": 600,       # 网页内容缓存 10 分钟
    "screenshot_webpage": 3600, # 截图缓存 1 小时
    "execute_python": 0,        # 代码执行不缓存（每次都可能不同）
}

def get_cache_key(tool_name: str, arguments: dict) -> str:
    """生成缓存键"""
    # 对参数排序，保证相同参数生成相同键
    sorted_args = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    raw = f"mcp_tool:{tool_name}:{sorted_args}"
    return hashlib.md5(raw.encode()).hexdigest()

async def call_mcp_tool_with_cache(tool_name: str, arguments: dict) -> str:
    """带缓存的 MCP 工具调用"""
    ttl = CACHE_TTL_MAP.get(tool_name, 60)  # 默认缓存 60 秒
    
    # 如果 TTL 为 0，跳过缓存（如代码执行器）
    if ttl == 0:
        return await call_mcp_tool(tool_name, arguments)
    
    # 检查缓存
    cache_key = get_cache_key(tool_name, arguments)
    cached = redis_client.get(cache_key)
    if cached:
        return f"{cached}\n[缓存命中]"
    
    # 调用工具
    result = await call_mcp_tool(tool_name, arguments)
    
    # 存入缓存
    redis_client.set(cache_key, result, ex=ttl)
    
    return result

async def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """通过 MCP Client 调用工具"""
    session = await get_mcp_session()
    result = await session.call_tool(tool_name, arguments)
    # 结果是一个 Content 列表，提取文本内容
    if result.content:
        return result.content[0].text
    return "工具返回了空结果"

# ==================== 工具执行节点（通过 MCP Client） ====================
# ==================== tools 节点（保持原有逻辑） ====================
# 新增 工具调用时记录轨迹
from tool_visualizer import record_tool_start, record_tool_end,record_agent_decision
async def tool_execute(state: AgentState):
    """执行节点：通过 MCP Client 调用工具"""
    last_message = state["messages"][-1]
    tool_messages = []
    user_name = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")

    for tc in last_message.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]

        # 记录工具调用开始
        record_tool_start(tool_name, tool_args, thread_id)

        # ===== 多级预算检查 =====
        allowed, reason = check_multilevel_budget(
            user_name=user_name,
            thread_id=thread_id,
            tool_name=tool_name
        )
        if not allowed:
            tool_msg = ToolMessage(
                content=f"⚠️ 预算拦截：{reason}\n请等待预算重置或联系管理员提升额度。",
                tool_call_id=tc["id"],
                name=tool_name
            )
            tool_messages.append(tool_msg)
            continue

        # 通过 MCP Client 调用工具
        # 新增 带缓存的调用。
        result = await call_mcp_tool_with_cache(tool_name, tool_args)

        # 记录工具调用结束（成功状态；原代码在此误记录为“未找到工具”错误）
        record_tool_end(tool_name, result, thread_id, "success")

        tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"], name=tool_name)
        tool_messages.append(tool_msg)

    return {"messages": tool_messages}

# ==================== 动态绑定工具到模型 ====================
async def get_llm_with_mcp_tools():
    """获取绑定了 MCP 工具的 LLM 实例"""
    tools = await get_mcp_tools()
    # 将 MCP 工具列表转换为 LangChain 能理解的格式
    langchain_tools = []
    for mcp_tool in tools:
        langchain_tools.append({
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": mcp_tool.inputSchema
        })
    return llm.bind_tools(langchain_tools)

# ==================== 构建图 ====================
def build_mcp_agent():
    workflow = StateGraph(AgentState)

    # ==================== chat_node：兜底对话节点 ====================
    async def chat_node(state: AgentState):
        """处理不需要工具调用的直接对话，或工具调用完成后的最终总结"""
        # 构建带记忆注入的 system prompt
        system_prompt = "你是一个智能助理，请直接回答用户的问题。"
        # 导入长期记忆mem0模块
        system_prompt = inject_memories_to_prompt(system_prompt, state)

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm.invoke(messages)
        
         # 预估本次调用消耗（经验值：决策通常消耗200-500 tokens）
        user_name = state.get("user_name", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {
                "final_output": "今日Token预算已用完，请明天再试。",
                "messages": [AIMessage(content="今日Token预算已用完，请明天再试。")]
            }
        
        # 新增 统计 Token 消耗
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            record_usage(
                model="qwen-turbo",
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                purpose="answer_generation",
                user_name=state.get("user_name", "unknown"),
                thread_id=state["thread_id"],   # 从 state 获取
            )
        
        return {
            "final_output": response.content,
            "messages": [response]
        }
    # ==================== agent_decide 节点（保持原有逻辑） ====================
    # 定义 agent_decide 节点（异步版本，动态绑定工具）
    async def agent_decide(state: AgentState):
        llm_with_tools = await get_llm_with_mcp_tools()
        response = llm_with_tools.invoke(state["messages"])
        # 记录决策过程
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                record_agent_decision(state["thread_id"], {
                    "type": "tool_decision",
                    "tool_name": tc["name"],
                    "arguments": tc["args"],
                    "reasoning": response.content if hasattr(response, "content") else "",
                })
        # 预估本次调用消耗（经验值：决策通常消耗200-500 tokens）
        user_name = state.get("user_name", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {
                "final_output": "今日Token预算已用完，请明天再试。",
                "messages": [AIMessage(content="今日Token预算已用完，请明天再试。")]
            }
        # 新增 统计 Token 消耗
        # 在 agent_decide 节点中调用 record_usage 时，传入 tool_name 和 tool_args
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            # 检查是否有工具调用
            tool_name = None
            tool_args = None
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_name = response.tool_calls[0]["name"]
                tool_args = response.tool_calls[0]["args"]
            
            record_usage(
                model="qwen-turbo",
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                purpose="agent_decision",
                user_name=state.get("user_name", "unknown"),
                thread_id=state.get("thread_id", "unknown"),
                tool_name=tool_name,
                tool_args=tool_args,
            )
        return {"messages": [response]}


    # ==================== 路由函数 ====================
    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        # 不需要工具时，去 chat_node 生成最终答案
        return "chat"

     # ==================== 注册节点 ====================
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    workflow.add_node("chat", chat_node)
    workflow.set_entry_point("agent")
    # 条件路由：需要工具 → tools，不需要工具 → chat
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "chat": "chat"})
    
    # tools 执行完后，回到 agent 继续判断（可能需要更多工具，也可能直接去 chat）
    workflow.add_edge("tools", "agent")
    # chat 节点执行完后，结束
    workflow.add_edge("chat", END)

    return workflow.compile(checkpointer=MemorySaver())

# 全局实例
mcp_agent = build_mcp_agent()
