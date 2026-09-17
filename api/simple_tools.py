"""
简单工具集：不依赖外部服务的独立工具（**面向 LLM 的工具外壳**）。

⚠️ 2026-09-17 重构 ⑥ 切开点 3：**两个函数的逻辑已搬到 `simple_tools_impl.py`**
（纯 stdlib，可脱离 langchain 单测）。本文件只剩一层 `@tool` 外壳。
⚠️ `import simple_tools` 仍会拉 **langchain**；**只想用逻辑就 import `simple_tools_impl`**。
"""
from langchain_core.tools import tool

from simple_tools_impl import calculator_impl, date_today_impl

__all__ = ["calculator", "date_today", "SIMPLE_TOOLS"]


@tool
def calculator(expression: str) -> str:
    """
    计算一个数学表达式，例如 3*4-5/6。
    输入的必须是纯数学表达式。
    """
    # ⚠️ 上面的 docstring 是**给 LLM 读的工具描述**，故留在本层。
    return calculator_impl(expression)


@tool
def date_today(query: str = "") -> str:
    """
    查询今天的日期、星期几。
    忽略查询参数。
    """
    # ⚠️ 上面的 docstring 是**给 LLM 读的工具描述**，故留在本层。
    return date_today_impl()


# 工具列表（方便 MCP Server 批量导入）
SIMPLE_TOOLS = [calculator, date_today]
