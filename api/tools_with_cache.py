import time
from tool_cache import cached_tool
from safe_math import calculate  # DEC-049：⛔ 别改回 `eval`（理由见 `api/safe_math.py`）

@cached_tool(expire_seconds=300)
def get_weather(city: str) -> str:
    """模拟天气查询（耗时2秒）"""
    time.sleep(2)
    return f"{city}当前温度25°C，晴"

@cached_tool(expire_seconds=600)
def calculator(expression: str) -> str:
    """计算器工具（模拟耗时0.5秒）"""
    time.sleep(0.5)
    # 🔴 DEC-049：⛔ 不许改回 `eval` —— 理由与实测见 `api/agent_graph.py` 同名处 / `api/safe_math.py`。
    # ⚠️ 本处**在生产里不可达**（`api_v1.py:36` 导入了 `calculator` 但全文件只用这一次）
    #    ⇒ 收口是为了"别留第 6 份拷贝"，不是因为这条路能被走到。
    return calculate(expression)