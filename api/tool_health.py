"""
工具健康检查（通用版本）
通过 MCP Client 动态检测所有工具的可用性，无需为每个工具单独编写检查函数。

⚠️ **降级不在这里** —— 见 `api/mcp_server.py` 的 `list_tools()`：
   它把 `UNHEALTHY` 的工具**移出工具清单**（那是当前实际生效的降级机制）。

🔴 2026-09-20 删（§三·B9 · 业务方裁「删代码 + 把 docstring 改成实话」）：
   本文件原先自称「工具健康检查**与自动降级**」，并带一份 `FALLBACK_MAP` + `get_fallback_tool()`。
   实测那套是**双重死代码**：
     ① **全仓零调用**（`grep -rn 'get_fallback_tool|FALLBACK_MAP' api/` 除定义处 0 次）
     ② **连它引用的名字也不存在** —— `fallback_search`、`chat` 全仓都无定义
        ⇒ **就算接上线，它返回的也是一个不存在的工具名。**
   ⇒ 它不是"预留的能力"，是**一段从来没能工作过的代码**。
   真正的降级是"**把不健康的工具移出清单**"，不是"换一个备用工具"—— 已在上方写明。
"""
import time
import os
from typing import Dict

HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
UNKNOWN = "unknown"

_tool_health: Dict[str, Dict] = {}

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

async def update_tool_health(tool_name: str):
    """
    更新单个工具的健康状态（通用版本）。
    通过 MCP 协议进行探测，无需单独编写检查函数。
    """
    test_args = TEST_ARGS_MAP.get(tool_name)
    if test_args is None:
        # 如果没有定义测试参数，跳过该工具
        return

    old_health = _tool_health.get(tool_name, {}).get("status", UNKNOWN)

    # 直接 await 异步检查（避免在事件循环内使用 asyncio.run 导致 RuntimeError）
    try:
        is_healthy = await _check_tool_via_mcp(tool_name, test_args)
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

# 🔴 2026-09-20 删（§三·B9）：此处原有
#       def get_fallback_tool(tool_name: str) -> str:
#           return FALLBACK_MAP.get(tool_name, "chat")
#    —— 它**零调用**，且引用的 `fallback_search` / `chat` **全仓都不存在**。
#    降级（把不健康工具移出清单）在 `mcp_server.py` 的 `list_tools()` 里，不在本文件。

async def run_health_check():
    """
    启动时运行一次全面的健康检查。
    自动遍历 TEST_ARGS_MAP 中定义的所有工具。
    """
    for tool_name in TEST_ARGS_MAP:
        await update_tool_health(tool_name)