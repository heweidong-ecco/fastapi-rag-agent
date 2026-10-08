"""
简单工具集：不依赖外部服务的独立工具（**面向 LLM 的工具外壳**）。

⚠️ 2026-09-17 重构 ⑥ 切开点 3：**两个函数的逻辑已搬到 `simple_tools_impl.py`**
（纯 stdlib，可脱离 langchain 单测）。本文件只剩一层 `@tool` 外壳。
⚠️ `import simple_tools` 仍会拉 **langchain**；**只想用逻辑就 import `simple_tools_impl`**。
"""
from langchain_core.tools import tool

from simple_tools_impl import calculator_impl, date_today_impl
from tool_cache import cached_tool

__all__ = ["calculator", "date_today", "SIMPLE_TOOLS"]

# 🔴 2026-10-08（批① 工具缓存收口 · `DEC-105`）：**缓存包在 `@tool` 这一层**。
# ⚠️ **名字必须显式给 `name=`** —— `cached_tool` 缺省用 `func.__name__`
#    （= `calculator_impl`），而 `TTL_BY_TOOL` 的键是**工具名**（`calculator`）≠ 函数名。
# 🔴 ⛔ **`tool_cache` 绝不许 import 进 `simple_tools_impl`** ——
#    那个文件的不变量是「**只 import 标准库**」（写在它文件头）；缓存是**外壳**的事。
_cached_calculator = cached_tool(name="calculator")(calculator_impl)
_cached_date_today = cached_tool(name="date_today")(date_today_impl)


@tool
def calculator(expression: str) -> str:
    """
    计算一个数学表达式，例如 3*4-5/6。
    输入的必须是纯数学表达式。
    """
    # ⚠️ 上面的 docstring 是**给 LLM 读的工具描述**，故留在本层。
    return _cached_calculator(expression)


@tool
def date_today(query: str = "") -> str:
    """
    查询今天的日期、星期几。
    忽略查询参数。
    """
    # ⚠️ 上面的 docstring 是**给 LLM 读的工具描述**，故留在本层。
    #
    # ⚠️ `date_today` 的 TTL 是 **0**（`TTL_BY_TOOL`）⇒ 这一层包装**看着多余**，
    #    但**故意留着**：它让「这个工具走不走缓存」由 `TTL_BY_TOOL` **一处**说了算，
    #    而不是"有的工具根本没包、有的是 TTL=0"两种形状混着。
    return _cached_date_today()


# 工具列表（方便 MCP Server 批量导入）
SIMPLE_TOOLS = [calculator, date_today]
