"""
MCP Server：使用工厂函数自动注册所有工具
"""
import os
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 导入所有工具（从各自独立的模块）
from simple_tools import calculator, date_today  # 新增导入
from search_tools import web_search
from browser_tools import fetch_webpage, screenshot_webpage
from code_executor import execute_python

# 导入工厂函数
from mcp_tool_factory import create_mcp_tool_definition, create_mcp_tool_handler

# 创建 MCP Server 实例
server = Server("agent-tools")

# 将所有工具放入一个列表（新增工具只需在这里加一行！）
# 新增 工具列表（为每个工具可指定版本号）
TOOLS = [
    {"func": calculator, "version": "1.0.0"},
    {"func": date_today, "version": "1.0.0"},
    {"func": web_search, "version": "2.0.0"},  # 已升级到 v2
    {"func": fetch_webpage, "version": "1.0.0"},
    {"func": screenshot_webpage, "version": "1.0.0"},
    {"func": execute_python, "version": "1.5.0"},  # 已迭代多次
]
''' 原工具列表，不带版本号。
# 将所有工具放入一个列表（新增工具只需在这里加一行！）
TOOLS = [
    calculator,
    date_today,
    web_search,
    fetch_webpage,
    screenshot_webpage,
    execute_python,
]
'''

# 工具定义和处理器由工厂函数自动生成（不再需要手动维护映射表）
# 新增 版本号
TOOLS_DEFINITION = {
    tool["func"].name: create_mcp_tool_definition(tool["func"], version=tool["version"])
    for tool in TOOLS
}
TOOL_HANDLERS = {
    tool["func"].name: create_mcp_tool_handler(tool["func"])
    for tool in TOOLS
}
''' 原代码，不包含版本号。
TOOLS_DEFINITION = {tool.name: create_mcp_tool_definition(tool) for tool in TOOLS}
TOOL_HANDLERS = {tool.name: create_mcp_tool_handler(tool) for tool in TOOLS}
'''

# 增加健康检查过滤。
from tool_health import get_tool_health, UNHEALTHY
# 注册工具列表接口
@server.list_tools()
async def list_tools() -> list[Tool]:
    """返回所有可用工具的清单（自动过滤不健康的工具）"""
    tools = []
    for tool_def in TOOLS_DEFINITION.values():
        tool_name = tool_def["name"]
        
        # 检查工具健康状态
        health = get_tool_health(tool_name)
        
        if health == UNHEALTHY:
            print(f"工具 {tool_name} 不健康，已从工具列表中移除")
            continue  # 跳过不健康的工具
        
        tools.append(Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            inputSchema=tool_def["inputSchema"]
        ))
    return tools

# 注册工具调用接口
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """接收工具调用请求，转发给实际工具并返回结果"""
    if name not in TOOL_HANDLERS:
        raise ValueError(f"未知工具: {name}")

    handler = TOOL_HANDLERS[name]
    result = handler(arguments)
    return [TextContent(type="text", text=str(result))]

# MCP Server 启动入口
async def run_mcp_server():
    """启动 MCP Server"""
    print(f"MCP Server 启动中... 已注册 {len(TOOLS)} 个工具")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(run_mcp_server())