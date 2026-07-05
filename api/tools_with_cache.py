import time
from tool_cache import cached_tool

@cached_tool(expire_seconds=300)
def get_weather(city: str) -> str:
    """模拟天气查询（耗时2秒）"""
    time.sleep(2)
    return f"{city}当前温度25°C，晴"

@cached_tool(expire_seconds=600)
def calculator(expression: str) -> str:
    """计算器工具（模拟耗时0.5秒）"""
    time.sleep(0.5)
    try:
        return str(eval(expression))
    except Exception as e:
        return f"计算错误: {e}"