"""
简单工具的**纯 stdlib 内核**（无 langchain 依赖）。

从 `simple_tools.py` 切出（重构计划 ⑥ 切开点 3）。目的：让这两个函数的逻辑
可在**只有标准库**的环境里被导入和测试 —— 此前它们住在 `simple_tools.py` 里，
而那个文件在**模块层** `from langchain_core.tools import tool`。

⚠️ **依赖方向单向**：本模块**只 import 标准库**（`datetime`）。
`simple_tools.py` 引用本模块；**本模块绝不反向引用**它。

⚠️ **2026-10-03 例外（DEC-049）**：多了一个 `from safe_math import calculate`。
   它**不破坏上面那条不变量** —— `safe_math` 自己也**只用标准库**（`ast` / `math` / `operator`），
   没有任何 langchain 依赖。**这是本模块唯一允许的外部依赖，⛔ 别再往里加第二个。**

📌 函数名带 `_impl` 后缀是**故意的** —— 提醒读者：**这不是给 LLM 看的工具**。
面向 LLM 的工具描述（docstring）留在 `simple_tools.py` 的 `@tool` 那一层。
"""
from datetime import datetime

from safe_math import calculate  # DEC-049：⛔ 别改回 `eval`（理由见 `api/safe_math.py`）


def calculator_impl(expression: str) -> str:
    """计算一个数学表达式（纯逻辑，无 langchain 依赖）。"""
    # ⚠️ 返回值形状**与改前逐字一致**：成功 `str(结果)`；失败 `计算错误: {原因}`。
    #    `test_impl_modules.py` 断言了 `1/0` 那条要含 `division by zero` —— 已保留。
    return calculate(expression)


def date_today_impl() -> str:
    """返回今天的日期与星期几（纯逻辑，无 langchain 依赖）。"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    weekday_str = weekdays[now.weekday()]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekday_str}"
