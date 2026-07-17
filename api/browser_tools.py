"""
浏览器自动化工具：基于 Playwright
"""

"""
Playwright
1. 无头模式 vs 有头模式
当前我们使用 headless=True（无头模式），浏览器在后台运行，不显示窗口。
在调试时可以设置为 headless=False，观察浏览器的实际操作过程。
2. 并发注意事项
Playwright的sync_playwright()是同步API。
在高并发场景下，建议使用async_playwright()异步API，
配合asyncio.to_thread或直接用异步版本，避免阻塞事件循环。
3. 资源管理
每次调用都会启动一个新的浏览器实例。在生产环境中，应该使用连接池或复用浏览器实例来降低资源消耗。
4. 优化建议：
按需调用：只在 Agent 判断确实需要阅读完整网页时才调用 Playwright，不要每次对话都启动浏览器。
超时控制：设置合理的超时时间（如 15 秒），避免网页加载过慢导致任务挂起。
内容截断：获取的网页文本限制长度（如 3000 字符），减少 Token 消耗。
连接池（未来）：在高并发场景下，可以使用连接池复用浏览器实例，避免频繁启动和关闭。

这里暂时，不做版本更改。
"""
from langchain_core.tools import tool
from playwright.sync_api import sync_playwright


@tool
def fetch_webpage(url: str) -> str:
    """
    打开一个网页，获取其完整的文本内容。
    适用于需要阅读网页文章、新闻、文档等场景。
    输入是一个完整的URL（如 https://example.com）。
    """
    with sync_playwright() as p:
        # 启动无头浏览器（后台运行，不显示窗口）
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
            # 获取页面的纯文本内容
            text = page.inner_text("body")
            # 简单清洗：限制长度，去除过多空白
            text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
            if len(text) > 3000:
                text = text[:3000] + "\n... (内容过长，已截断)"
            return text
        except Exception as e:
            return f"获取网页失败: {str(e)}"
        finally:
            browser.close()


@tool
def fetch_webpage_html(url: str) -> str:
    """
    获取网页的原始HTML内容。
    适用于需要分析网页结构、提取特定标签信息的场景。
    输入是一个完整的URL。
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
            html = page.content()
            if len(html) > 5000:
                html = html[:5000] + "\n... (内容过长，已截断)"
            return html
        except Exception as e:
            return f"获取网页HTML失败: {str(e)}"
        finally:
            browser.close()

import os
import time

@tool
def screenshot_webpage(url: str) -> str:
    """
    打开一个网页并将其保存为截图（PNG格式）。
    适用于需要查看网页视觉呈现、捕获动态图表或保存页面状态的场景。
    返回截图文件的本地路径。
    """
    # 确保截图保存目录存在
    screenshot_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    # 生成带时间戳的文件名
    timestamp = int(time.time())
    safe_filename = f"screenshot_{timestamp}.png"
    filepath = os.path.join(screenshot_dir, safe_filename)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
            # 截取整个页面
            page.screenshot(path=filepath, full_page=True)
            return f"网页截图已保存到: {filepath}"
        except Exception as e:
            return f"网页截图失败: {str(e)}"
        finally:
            browser.close()
            