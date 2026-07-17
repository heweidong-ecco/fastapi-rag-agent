"""
工具健康检查与自动降级
"""
import time
from typing import Dict, Callable

# 工具健康状态
HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
UNKNOWN = "unknown"

# 工具健康状态存储
_tool_health: Dict[str, Dict] = {}

# 工具降级映射表：当某个工具不可用时，用哪个工具替代
FALLBACK_MAP = {
    "web_search": "fallback_search",      # 阿里百炼搜索不可用时，降级为直接LLM回答
    "fetch_webpage": "web_search",        # Playwright不可用时，降级为普通搜索
}

def check_search_api_health() -> bool:
    """检查阿里百炼搜索API是否可用"""
    try:
        from openai import OpenAI
        import os
        client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=5
        )
        # 发送一个轻量测试请求
        response = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            extra_body={"enable_search": False}  # 只测试模型连通性，不触发搜索
        )
        return True
    except Exception:
        return False

def check_playwright_health() -> bool:
    """检查Playwright是否可用"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False

def check_calculator_health() -> bool:
    """检查计算器工具是否可用"""
    try:
        # 执行一个简单的测试计算
        result = eval("1 + 1")
        return result == 2
    except Exception:
        return False

def check_date_today_health() -> bool:
    """检查日期工具是否可用"""
    try:
        from datetime import datetime
        now = datetime.now()
        # 只要能成功获取当前日期时间，就认为工具可用
        return now.year > 2020  # 一个基本的时间合理性检查
    except Exception:
        return False
    
def update_tool_health(tool_name: str):
    """更新工具健康状态，同时清空相关缓存"""
    old_health = get_tool_health(tool_name)
    """更新单个工具的健康状态"""
    if tool_name == "web_search":
        is_healthy = check_search_api_health()
    elif tool_name == "fetch_webpage":
        is_healthy = check_playwright_health()
    elif tool_name == "calculator":
        is_healthy = check_calculator_health()
    elif tool_name == "date_today":
        is_healthy = check_date_today_health()
    else:
        return # 其他工具暂不检查

    _tool_health[tool_name] = {
        "status": HEALTHY if is_healthy else UNHEALTHY,
        "last_checked": time.time()
    }
    status = "✅" if is_healthy else "❌"
    print(f"工具健康检查: {tool_name} {status}")

def get_tool_health(tool_name: str) -> str:
    """获取工具健康状态"""
    if tool_name not in _tool_health:
        return UNKNOWN
    return _tool_health[tool_name]["status"]

def get_fallback_tool(tool_name: str) -> str:
    """获取工具的降级备选"""
    return FALLBACK_MAP.get(tool_name, "chat")  # 默认降级为直接对话

def run_health_check():
    """启动时运行一次全面的健康检查"""
    for tool_name in ["web_search", "fetch_webpage","calculator", "date_today"]:
        update_tool_health(tool_name)