"""
工具健康检查与自动降级（通用版本）
通过 MCP Client 动态检测所有工具的可用性，无需为每个工具单独编写检查函数。
"""
import time
import os
from typing import Dict

HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
UNKNOWN = "unknown"

_tool_health: Dict[str, Dict] = {}

FALLBACK_MAP = {
    "web_search": "fallback_search",
    "fetch_webpage": "web_search",
}

# 为每种工具类型定义安全的测试参数
# 如果某个工具不在这个映射中，会跳过健康检查（标记为 UNKNOWN）
TEST_ARGS_MAP = {
    "calculator": {"expression": "1+1"},
    "date_today": {},
    "web_search": {"query": "test"},
    "fetch_webpage": {"url": "https://example.com"},
    "screenshot_webpage": {"url": "https://example.com"},
    "execute_python": {"code": "print('health check')"},
}

async def _check_tool_via_mcp(tool_name: str, test_args: dict) -> bool:
    """
    通过 MCP 协议检查某个工具的可用性。
    传入安全的测试参数，看工具是否能正常返回结果。
    """
    try:
        from agent_graph_advanced import call_mcp_tool
        result = await call_mcp_tool(tool_name, test_args)
        # 只要有返回结果（不包含明显的错误标记），就认为是健康的
        if result and "工具调用失败" not in result and "未找到工具" not in result:
            return True
        return False
    except Exception as e:
        print(f"通过 MCP 检查工具 {tool_name} 失败: {e}")
        return False

def update_tool_health(tool_name: str):
    """
    更新单个工具的健康状态（通用版本）。
    通过 MCP 协议进行探测，无需单独编写检查函数。
    """
    test_args = TEST_ARGS_MAP.get(tool_name)
    if test_args is None:
        # 如果没有定义测试参数，跳过该工具
        return

    old_health = _tool_health.get(tool_name, {}).get("status", UNKNOWN)
    
    # 使用 asyncio.run 在同步上下文中执行异步检查
    import asyncio
    try:
        is_healthy = asyncio.run(_check_tool_via_mcp(tool_name, test_args))
    except Exception as e:
        print(f"健康检查异常 ({tool_name}): {e}")
        is_healthy = False

    new_health = HEALTHY if is_healthy else UNHEALTHY

    _tool_health[tool_name] = {
        "status": new_health,
        "last_checked": time.time()
    }

    if old_health != new_health:
        status = "✅" if is_healthy else "❌"
        print(f"工具健康检查: {tool_name} {status} ({old_health} → {new_health})")

def get_tool_health(tool_name: str) -> str:
    if tool_name not in _tool_health:
        return UNKNOWN
    return _tool_health[tool_name]["status"]

def get_fallback_tool(tool_name: str) -> str:
    return FALLBACK_MAP.get(tool_name, "chat")

def run_health_check():
    """
    启动时运行一次全面的健康检查。
    自动遍历 TEST_ARGS_MAP 中定义的所有工具。
    """
    for tool_name in TEST_ARGS_MAP:
        update_tool_health(tool_name)