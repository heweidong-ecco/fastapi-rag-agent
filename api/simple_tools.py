"""
简单工具集：不依赖外部服务的独立工具
"""
from langchain_core.tools import tool
from datetime import datetime


@tool
def calculator(expression: str) -> str:
    """
    计算一个数学表达式，例如 3*4-5/6。
    输入的必须是纯数学表达式。
    """
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算错误: {e}"


@tool
def date_today(query: str = "") -> str:
    """
    查询今天的日期、星期几。
    忽略查询参数。
    """
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    weekday_str = weekdays[now.weekday()]
    return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekday_str}"


# 工具列表（方便 MCP Server 批量导入）
SIMPLE_TOOLS = [calculator, date_today]