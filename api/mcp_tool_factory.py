"""
MCP 工具工厂：将 LangChain @tool 函数自动封装为 MCP 标准接口
"""
import asyncio
from typing import Dict, Any
from mcp.types import Tool

# 新增：version 版本号
def create_mcp_tool_definition(tool_func,version: str = "1.0.0") -> Dict:
    """
    从 @tool 函数自动生成 MCP 工具定义。
    
    参数:
        tool_func: LangChain 的 @tool 装饰的函数
        version: 工具版本号，默认 "1.0.0"

    返回:
        符合 MCP 标准的工具定义字典，包含 name, description, inputSchema, version
    """
    # 从 LangChain 的 BaseTool 中提取元数据
    tool_name = tool_func.name
    tool_description = tool_func.description
    
    # 从函数的类型提示中自动构建 inputSchema
    props = {}
    required = []
    
    if hasattr(tool_func, 'args_schema') and tool_func.args_schema:
        schema = tool_func.args_schema.schema()
        for prop_name, prop_info in schema.get("properties", {}).items():
            props[prop_name] = {
                "type": prop_info.get("type", "string"),
                "description": prop_info.get("description", prop_name)
            }
            required = schema.get("required", [])
    else:
        # 如果没有显式的 args_schema，默认一个空的 input 参数
        props = {
            "input": {"type": "string", "description": "工具输入"}
        }
        required = ["input"]
    
    return {
        "name": tool_name,
        "description": tool_description,
        "version": version,  # 新增：版本号
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": required
        }
    }

def create_mcp_tool_handler(tool_func):
    """
    从 @tool 函数自动生成 MCP 工具调用处理器。
    
    参数:
        tool_func: LangChain 的 @tool 装饰的函数
    
    返回:
        一个可调用的函数，接收 arguments 字典，返回字符串结果。
        如果工具调用失败，返回结构化的错误信息，不会抛出异常。
    """
    async def handler(arguments: dict) -> str:
        """工具调用处理器（带错误处理）。

        🔴 2026-09-20 **改成 async + 丢线程**（依赖/环境漂移的连带问题）:
           MCP server（`mcp_server.py:71-79` 的 `call_tool`）**是 async 服务**，
           而它原先**同步**调用本处理器 ⇒ **同步工具就在 MCP server 的事件循环里跑**
           ⇒ `browser_tools` 的同步 Playwright 直接报
           `It looks like you are using Playwright Sync API inside the asyncio loop.`
           ⇒ `fetch_webpage` / `screenshot_webpage` **永远 unhealthy**（健康检查 4/6 而非 6/6）。

          ⚠️ **同一个 bug 有两个入口**:先前只修了 **FastAPI 端点**那条，
             而健康检查走的是 **MCP** 这条 ⇒ "修好了"但工具健康检查照旧。
             回归测试:`api/test_agent_repairs.py::test_mcp_tool_handler_runs_sync_tool_off_the_event_loop`
        """
        try:
            # 🔴 2026-09-20 修:此前是
            #      `input_obj = tool_func.args_schema(**arguments)`
            #      `result = tool_func.invoke(input_obj)`
            #    —— 把 **pydantic 实例**喂给 `StructuredTool.invoke()`，而它要的是 **dict**
            #    ⇒ `TypeError: calculator() missing 1 required positional argument`。
            #    实测对比(同一个真工具):
            #      · `calculator.invoke({"expression":"1+1"})`  → ✅ '2'
            #      · `calculator.invoke(args_schema(**{...}))`  → ❌ TypeError
            #    ⚠️ 后果被健康检查放大:它的判据是"结果里含『工具调用失败』⇒ unhealthy"
            #       ⇒ 这个 bug 让 **6 个工具全标红**，与传输层修没修好无关。
            #    回归测试:api/test_agent_repairs.py::test_mcp_tool_handler_passes_dict_to_invoke
            # ⚠️ 丢到线程里跑 —— 工具可能是**同步**的（如 browser_tools 的 Playwright
            #    同步 API），直接在事件循环里执行会炸（见上面的注释）。
            result = await asyncio.to_thread(tool_func.invoke, arguments)
            return str(result)
        except Exception as e:
            # 捕获所有异常，返回结构化的错误信息，避免 Agent 崩溃
            error_msg = (
                f"工具调用失败\n"
                f"工具名称: {tool_func.name}\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误详情: {str(e)}\n"
                f"请检查输入参数是否正确，或稍后重试。"
            )
            return error_msg
    
    return handler
