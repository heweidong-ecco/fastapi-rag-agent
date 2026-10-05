"""
Agent 图（集成 MCP Client）
LangGraph 进阶示例：多分支路由与子图协作
"""
import os
import json
import asyncio
from typing import TypedDict, List, Annotated, Optional
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from llm_factory import make_llm   # ①b Task 5：model / api_key / base_url / max_tokens 的唯一落点
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage,SystemMessage
from langchain_core.runnables import RunnableConfig   # B1：节点要靠它把回调接进模型调用
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
    # 🔴 2026-10-05（`S13`）：本轮的预算拦截原因（`None` = 没被拦）。
    #
    # **它是「拦没拦住」通往【端点层】的唯一通道** —— 端点据此回 429 / error 帧。
    # ⛔ **别拿末条 `ToolMessage` 的中文文案当判据**（那是子串判据，`plan_execute` 的 `S10`
    #    刚把同型写法清掉：改一个字的措辞就静默失效，工具正文里恰好出现那四个字就误判）。
    #
    # ⚠️ 它**没有**挂 `operator.add`（不像 `messages`）⇒ **last-write-wins + 落 checkpoint**
    #    ⇒ **必须每轮清零**（`agent_decide` 开头），否则上一轮被拦会让下一轮的**正常提问**
    #    也返回 429。📌 守卫：`api/test_budget_hard_intercept.py::test_上一轮的拦截标志不会串到下一轮`
    budget_intercept: Optional[str]

# ==================== 初始化模型 ====================
# 🔴 2026-10-01 补（🅗 `S12`）：本处原先**没有 `timeout` / `max_retries`** ——
#    同型问题 `plan_execute.py:70-76` 早就修过，**这里漏了**。
#    ⇒ **没 timeout = 上游挂了就一起挂着**；而 SDK 默认 `max_retries=2`
#      ⇒ 一次失败**静默重试 2 次、烧 3 倍额度**，可这条链上本来就带 token 预算检查。
# ⚠️ **秒数【不抄】 `plan_execute` 的 30/20/15**：那三处是**单步**（planner / executor / 质检各一次），
#    这里是**多轮工具对话**（`:345` 每次 invoke 一轮，且带 MCP 工具 schema）。
#    ⇒ 取 planner 的两倍 = **60s**：① 输出上限 1024，比 planner 那份 JSON 长；
#      ② 工具 schema 更大 ⇒ 首 token 更慢。
#    📌 **这个 60 是我的判断，不是业务裁定** —— 要改就改这一个数（就这一处用）。
AGENT_LLM_TIMEOUT = 60
# ⚠️ 角色 = 「模型轴 chat」+「长度轴 agent(1024)」—— 见 `api/llm_factory.py` 的模块 docstring。
#    ⚠️ `timeout` / `max_retries` 走 `make_llm` 的 `**extra` 透传（⛔ 本处不再自己写 model/max_tokens）。
llm = make_llm(
    "chat", "agent",
    timeout=AGENT_LLM_TIMEOUT,       # S12
    max_retries=1,                   # S12：⛔ 不用 SDK 默认的 2（会烧 3 倍额度）
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
# 曾经的方案是「`_mcp_session` 全局单例，所有请求共享同一个会话」，它有两个毛病：
#   并发阻塞：全局单例是同步的，一个请求正在调用工具时，另一个请求必须等待。
#   状态污染：不同用户的调用可能互相影响。
#
# ⚠️ 2026-09-20 修（原下一行写的是「**新增会话池**，避免并发阻塞，和状况污染」）：
#    那条路**走过、又被推翻了** —— 见下面这段 docstring：会话池**从未真正生效、且架构上不可行**，
#    现已**移除**，改为**单 task 自开自关**。⇒ 原注释描述的方案**不是当前实现**，已改写。
"""
MCP Client 连接管理（**单 task 自开自关**版）

🔴 2026-09-20：**会话池已移除** —— 它不是在"修 bug"，而是把一个
   **从来没真正生效、且架构上不可行**的机制拆掉。两条证据：
   ① **它没在生效**：`initialize_pool()` **无任何调用方**（`main.py` 不调它，
      成功启动日志里「MCP 会话池已初始化」**0 次**）；`release_mcp_session()` /
      `close_all_sessions()` 也**零调用方** ⇒ 实际行为一直是
      "每次调用新建一个会话、用完不归还"。
   ② **它不可行**：`stdio_client` 基于 **anyio**，其 cancel scope 要求
      「**进入与退出在同一个 task**」。池化的生命周期天然跨 task
      （启动 task 建 · 请求 task 用 · 归还 task 关）⇒ 实测报
      `RuntimeError: Attempted to exit cancel scope in a different task than
      it was entered in`，**并让应用启动直接失败**
      （`Application startup failed. Exiting.`）。
      ⚠️ 那比原来的缺陷更糟：原来是"应用能跑、只是 MCP 健康检查挂"。

   ⇒ 现在的契约：**谁调用，谁在【自己这个 task 内】把会话开出来、用完关掉。**
   （代价：每次调用起一个 MCP 子进程。本仓的工具调用量下可接受；
     要复用会话，得上 HTTP/SSE transport —— 那是另一个方案，见 DEC-017。）

   回归测试：`api/test_agent_repairs.py::test_call_mcp_tool_keeps_session_lifecycle_inside_one_task`
"""
# 🔴 2026-09-20:此处原先**重复 import 了一遍** `asyncio` / `mcp` / `stdio_client`
#    （本文件 :8 与 :27-28 已经有了）—— 已删除。`sys` / `asynccontextmanager` /
#    `Path` 是本段新增、别处没有，故只补这三个。
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ⚠️ MCP server 脚本的**绝对**路径 —— 锚在本文件旁边，**与 CWD 无关**。
_MCP_SERVER_SCRIPT = Path(__file__).resolve().with_name("mcp_server.py")


@asynccontextmanager
async def mcp_session():
    """在**当前 task 内**开一个 MCP 会话，并保证退出时关掉。

    ⚠️ `command` 必须是**当前解释器**(`sys.executable`) —— 裸 `"python"` 会落到
       系统 python，而它**没有本仓依赖**，MCP server 起不来。

    ⚠️ server 脚本路径必须**锚在模块自身位置**，不能写 `"api/mcp_server.py"` ——
       那是**相对 CWD** 的：本仓起服务的姿势是 `cd api && uvicorn main:app`，
       从 `api/` 看它解析成 `api/api/mcp_server.py`（**不存在**）⇒ 子进程起不来
       ⇒ 6 个工具全 unhealthy（报 `ExceptionGroup: unhandled errors in a TaskGroup`，
       子异常还被 tool_health 的 except 吞掉，**看不出真因**）。
       实测对照（同一次调用，只换 cwd）:仓库根 → `2`；`api/` → TaskGroup 异常。
       回归测试:`api/test_agent_repairs.py::test_mcp_server_path_does_not_depend_on_cwd`
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(_MCP_SERVER_SCRIPT)]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def get_mcp_tools():
    """通过 MCP Client 获取所有可用工具"""
    async with mcp_session() as session:
        return await session.list_tools()

# 新增工具调用缓存
"""
MCP Client 工具调用缓存
"""
import hashlib
# ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：此处的 `import json` / `import os`
#    与文件头（`:5`/`:6`）**重复** ⇒ 删这两行。⚠️ 同段的 `hashlib`/`redis`/`functools`
#    **不是重复**（文件头没有），**必须留**。
import redis
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
    """通过 MCP Client 调用工具。

    ⚠️ 会话在本函数**自己的 task 内**开、用、关（见 `mcp_session` 的说明）——
    不要改回从池里取，那会跨 task 并让应用起不来。
    """
    async with mcp_session() as session:
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
    """执行节点：通过 MCP Client 调用工具。

    🔴 2026-10-05（`S13`）：**预算拦截从"软"变"硬"**。

    **改前**：被拦时只塞一条 `ToolMessage` 就 `continue` ⇒ 图照常往下走
    ⇒ `/agent/mcp_chat` **HTTP 200**，只有 **LLM 自己**看得见那句"⚠️ 预算拦截"
    ⇒ 「预算拦住了」这句话**只对 LLM 成立**（本文件 spec 的 ⚠️③）。

    **改后**：被拦 ⇒ ① 照旧答满本轮的 `ToolMessage`（**序列必须合法**：
    带 `tool_calls` 的 `AIMessage` 后面少一条回应，真 provider 直接 400）
    ② 在 state 上写 `budget_intercept` ⇒ 端点层据此回 **429 / error 帧**。

    ⛔ **别改成在这里 `raise`**（哪怕它看着更"硬"）—— 实测会把 checkpoint 留成
    `next=('tools',)` + 一条**没人回答**的 `AIMessage(tool_calls)` ⇒ **那个 thread 从此废掉**。
    📄 实测输出与备选评估 ⇒ `docs/decisions/DEC-078`。
    ⚠️ `record_tool_end` 在**被拦这条路上仍然不写**（追踪里留一条"开了没结束"）——
    这与改前**一字不差**（原来 `continue` 也不写），⛔ 不是本批引入的回归。
    """
    last_message = state["messages"][-1]
    tool_messages = []
    user_name = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")
    budget_intercept = None

    for tc in last_message.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]

        # 记录工具调用开始
        record_tool_start(tool_name, tool_args, user_name, thread_id)

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
            # ⚠️ **继续跑完这一轮的所有 tool_call**（⛔ 不是 `break`）：本轮有 3 个工具调用，
            #    只答 2 个 ⇒ 那条 `AIMessage` 悬着 ⇒ 下一轮进来必 400。
            #    拦截是"这一轮都别做了"，但不做的**每一条都要留下回应**。
            budget_intercept = reason
            continue

        # 通过 MCP Client 调用工具
        # 新增 带缓存的调用。
        result = await call_mcp_tool_with_cache(tool_name, tool_args)

        # 记录工具调用结束（成功状态；原代码在此误记录为“未找到工具”错误）
        record_tool_end(tool_name, result, user_name, thread_id, "success")

        tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"], name=tool_name)
        tool_messages.append(tool_msg)

    out = {"messages": tool_messages}
    # ⚠️ **只在被拦时写**这个键 —— 清零**只有一个地方**（`agent_decide` 开头）。
    #    "谁能改它"保持单一来源，才讲得清"什么时候它是可信的"。
    if budget_intercept is not None:
        out["budget_intercept"] = budget_intercept
    return out

# ==================== 动态绑定工具到模型 ====================
async def get_llm_with_mcp_tools():
    """获取绑定了 MCP 工具的 LLM 实例。

    🔴 2026-09-20 修（依赖漂移）:此前写的是 `for mcp_tool in tools:` —— 而
       `mcp 1.30.0` 的 `list_tools()` 返回的是 **`ListToolsResult`**（列表在 `.tools`），
       **不是列表本身**。直接遍历它 ⇒ pydantic 模型迭代出的是 **(key, value) 元组**
       ⇒ `AttributeError: 'tuple' object has no attribute 'name'`
       ⇒ `/agent/mcp_chat`（三代）**500**。
       回归测试:`api/test_agent_repairs.py::test_get_llm_with_mcp_tools_unpacks_list_tools_result`
    """
    tools_result = await get_mcp_tools()
    # 将 MCP 工具列表转换为 LangChain 能理解的格式
    langchain_tools = []
    for mcp_tool in tools_result.tools:
        langchain_tools.append({
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": mcp_tool.inputSchema
        })
    return llm.bind_tools(langchain_tools)

# ==================== 流式白名单（B1 · 2026-10-04）====================
# 🔴 **`B1`：可流节点名单放在【图模块里】，⛔ 端点不许自己抄一份字面量**（理由见
#    `api/agent_graph.py` 同名常量处 —— 一个名字两个来源必然漂移，而漂移是**静默**的）。
# ⚠️ 必须放在**模块级**（⛔ 不能放进 `build_mcp_agent()`）：端点是按
#    `agent_graph_advanced.STREAMABLE_NODES` 取的，函数体里的是局部名，外面拿不到。
# ⛔ `tools` **不在**里面：它不调 LLM（无字可流），且会把 `ToolMessage` 当"新消息"发出来。
STREAMABLE_NODES = frozenset({
    "agent",   # 决策节点：答案 + `tool_calls`（`DEC-050` 那个「多轮」场景的主角）
    "chat",    # 兜底对话节点：**最终答案就是它生成的** ⇒ 不流它，流式端点等于白开
})


# ==================== 构建图 ====================
def build_mcp_agent():
    workflow = StateGraph(AgentState)

    # ==================== chat_node：兜底对话节点 ====================
    async def chat_node(state: AgentState, config: RunnableConfig):
        """处理不需要工具调用的直接对话，或工具调用完成后的最终总结

        🔴 **`B1`（2026-10-04）：改真流式** —— 本节点是 `async`，所以走 `astream` 并把
           `config` 转发下去（`DEC-050`：声明 `config` + 转发，是出不出 token 的**唯一条件**）。
           ⛔ **别照抄** `agent_graph.py` / `agent_checkpointer.py` 那两处 —— 那两处是**同步**
           节点、用同步 `.stream()`；这里改成同步会阻塞事件循环。
        """
        # 构建带记忆注入的 system prompt
        system_prompt = "你是一个智能助理，请直接回答用户的问题。"
        # 导入长期记忆mem0模块
        system_prompt = inject_memories_to_prompt(system_prompt, state)

        # ⚠️ 预算检查必须在 llm.invoke() **之前** —— 放在之后的话钱已经花了，只能丢弃结果、拦不住
        #    （2026-09-16 上移；见 docs/decisions/DEC-002）
        # 预估本次调用消耗（经验值：决策通常消耗200-500 tokens）
        user_name = state.get("user_name", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {
                "final_output": "今日Token预算已用完，请明天再试。",
                "messages": [AIMessage(content="今日Token预算已用完，请明天再试。")]
            }

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        # 🔴 B1：真流式（`astream` + 转发 `config`）。 ⚠️ 用 `+` 聚合（`AIMessageChunk.__add__`），
        #    ⛔ 不是 `content +=` —— 那会丢掉碎片化的 `tool_calls`。
        # 🔴 **必须遍历【所有】块**，⛔ 不许跳过 `content` 为空的块：provider 把
        #    `usage_metadata` 挂在**最后一块**（`content=''`）上（实测，`探针-流式与记账.py`）
        #    ⇒ 跳过它，**下面那段记账静默失效**，而接口一切正常。
        response = None
        async for chunk in llm.astream(messages, config=config):
            response = chunk if response is None else response + chunk

        # 新增 统计 Token 消耗
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            record_usage(
                # ⚠️ 2026-10-01 修（🅗 S4）：原写死 `"qwen-turbo"`，而 `.env` 里实际是 DeepSeek
                #    ⇒ `token_usage_logs.cost` 按**错的单价**记 ⇒ 连带 `MAX_THREAD_COST`（元）也判错。
                #    改从对象取（照抄 `plan_execute.py:154` 的写法）。
                model=getattr(llm, "model_name", None) or getattr(llm, "model", "unknown"),
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
    async def agent_decide(state: AgentState, config: RunnableConfig):
        """决策节点（`B1` · 2026-10-04 改真流式）。

        ⚠️ 与 `chat_node` 同一条：**async 节点用 `astream` + 转发 `config`**。
        ⚠️ **`+` 聚合在这里是【必须】的，不是风格问题**：`tool_calls` 是碎片化到达的，
           只拼 `content` 会把它们丢掉 ⇒ `should_continue` 判不出 `"tools"`
           ⇒ 直接跳去 `chat` 出最终答案，**工具永远不会被执行**，而接口一切正常。
        """
        # 🔒 2026-10-05（`S13`）：**每一轮开头清零**上轮的预算拦截标志。
        #
        # 为什么必须有这一句：`budget_intercept` 是**普通 state 键**
        # （⛔ 没挂 `operator.add`）⇒ **last-write-wins + 落 checkpoint**
        # ⇒ 不清零的话，"上一轮被拦"会让**下一轮不需要工具的正常提问也返回 429**。
        #
        # ⚠️ 为什么放在**入口节点**：本图 `set_entry_point("agent")` ⇒ 每轮第一个跑的就是它
        #    ⇒ 这是唯一一个"每轮必然经过"的地方（`tools` 未必跑到）。
        #    📌 守卫：`api/test_budget_hard_intercept.py::test_上一轮的拦截标志不会串到下一轮`
        #       （**删掉这一句它必红**）。
        # ⚠️ **本节点的两个出口都要带上它** —— 只带一个的话，走另一个出口的那一轮会留着上轮的值。
        cleared = {"budget_intercept": None}

        # ⚠️ 预算检查必须在 invoke() **之前** —— 放在之后钱已经花了，只能丢弃结果、拦不住
        #    （2026-09-16 上移；见 docs/decisions/DEC-002）
        # 预估本次调用消耗（经验值：决策通常消耗200-500 tokens）
        user_name = state.get("user_name", "unknown")
        if not check_token_budget(user_name, estimated_tokens=500):
            return {
                **cleared,
                "final_output": "今日Token预算已用完，请明天再试。",
                "messages": [AIMessage(content="今日Token预算已用完，请明天再试。")]
            }

        llm_with_tools = await get_llm_with_mcp_tools()
        # 🔴 B1：真流式 —— 同 `chat_node`（`astream` + `config`，`+` 聚合遍历所有块）。
        response = None
        async for chunk in llm_with_tools.astream(state["messages"], config=config):
            response = chunk if response is None else response + chunk
        # 记录决策过程
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                record_agent_decision(user_name, state["thread_id"], {
                    "type": "tool_decision",
                    "tool_name": tc["name"],
                    "arguments": tc["args"],
                    "reasoning": response.content if hasattr(response, "content") else "",
                })
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
                # ⚠️ 2026-10-01 修（🅗 S4）：同上 —— 别再写死模型名。
                #    记**实际被调用的那个对象**（`:345` 调的是 `llm_with_tools`）。
                #    实测 `llm.bind_tools(...)` 后 `.model_name` 仍是 `deepseek-v4-flash`。
                model=getattr(llm_with_tools, "model_name", None)
                or getattr(llm_with_tools, "model", "unknown"),
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                purpose="agent_decision",
                user_name=state.get("user_name", "unknown"),
                thread_id=state.get("thread_id", "unknown"),
                tool_name=tool_name,
                tool_args=tool_args,
            )
        # ⚠️ `cleared` 是**另一个出口也要带**的（见本节点开头那段）—— ⛔ 别只留这一处。
        return {**cleared, "messages": [response]}


    # ==================== 路由函数 ====================
    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        # 不需要工具时，去 chat_node 生成最终答案
        return "chat"

    def after_tools(state: AgentState):
        """`S13`：被预算拦下 ⇒ **本轮到此为止**（⛔ 不回 `agent`）。

        ⚠️ 改前是 `add_edge("tools", "agent")` **无条件**回 `agent` —— 被拦之后
        `agent` 会**再调一次同一个工具**、再被拦一次 …直到撞上递归上限。
        🔴 实测（改动前）：被拦的那一轮直接
        `GraphRecursionError: Recursion limit of 25 reached`
        —— 且那是在**已经判定"没钱了"之后**又白白烧了十几轮 LLM。
        📌 守卫：`api/test_budget_hard_intercept.py::test_被拦时图在tools之后直接结束不回agent`
        """
        return "blocked" if state.get("budget_intercept") else "continue"

     # ==================== 注册节点 ====================
    workflow.add_node("agent", agent_decide)
    workflow.add_node("tools", tool_execute)
    workflow.add_node("chat", chat_node)
    workflow.set_entry_point("agent")
    # 条件路由：需要工具 → tools，不需要工具 → chat
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "chat": "chat"})
    
    # tools 执行完后，回到 agent 继续判断（可能需要更多工具，也可能直接去 chat）。
    # 🔴 2026-10-05（`S13`）：**被预算拦下那一轮例外** —— 直接 `END`（理由见 `after_tools`）。
    workflow.add_conditional_edges(
        "tools", after_tools, {"blocked": END, "continue": "agent"})
    # chat 节点执行完后，结束
    workflow.add_edge("chat", END)

    return workflow.compile(checkpointer=MemorySaver())

# 全局实例
mcp_agent = build_mcp_agent()
