"""
简单工具的**纯 stdlib 内核**（无 langchain 依赖）。

从 `simple_tools.py` 切出（重构计划 ⑥ 切开点 3）。目的：让这两个函数的逻辑
可在**只有标准库**的环境里被导入和测试 —— 此前它们住在 `simple_tools.py` 里，
而那个文件在**模块层** `from langchain_core.tools import tool`。

⚠️ **依赖方向单向**：本模块**只 import 标准库**（`datetime`）。
`simple_tools.py` 引用本模块；**本模块绝不反向引用**它。

📌 函数名带 `_impl` 后缀是**故意的** —— 提醒读者：**这不是给 LLM 看的工具**。
面向 LLM 的工具描述（docstring）留在 `simple_tools.py` 的 `@tool` 那一层。
"""
from datetime import datetime


def calculator_impl(expression: str) -> str:
    """计算一个数学表达式（纯逻辑，无 langchain 依赖）。"""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算错误: {e}"


def date_today_impl() -> str:
    """返回今天的日期与星期几（纯逻辑，无 langchain 依赖）。"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    weekday_str = weekdays[now.weekday()]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekday_str}"
