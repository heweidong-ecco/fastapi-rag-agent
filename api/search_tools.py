"""
搜索工具：**真正抓取**必应中文的搜索结果页（2026-09-21 重写 · N19）

> ## 🔴 为什么重写
>
> 此前这里是**调 LLM 的 `enable_search` 扩展**，并把模型返回的内容**当成搜索结果**返回。
> **实测（2026-09-21）证明它根本没在搜索**：
>
> | 查询 | 返回 |
> |---|---|
> | `2026年 诺贝尔物理学奖` | `<tool_call>{"name":"search",...}</tool_call>` ← **原始 tool_call 文本** |
> | `今天北京天气` | 「北京今天（**2026年3月18日**）…晴转多云…14℃」 ← **编的**（当天是 **2026-09-21**，差半年） |
> | `Python 是什么` | `<context>我需要了解用户所说的…` ← **模型的思考草稿** |
>
> **根因**：`enable_search` 是**阿里百炼私有扩展**，而本机 `.env` 走的是 DeepSeek ⇒ **被静默忽略**；
> 而兜底只写在 `except` 里 —— **那次调用返回的是 200，兜底永远不触发**
> ⇒ 于是把**未标记的模型输出**当搜索结果返回了。
>
> ⚠️ **三条里最危险的是天气那条**：格式漂亮、语气笃定、**日期全错** —— 调用方会直接采信。
> 📌 这类「**看起来能用、其实不能用**」正是本仓反复在防的形态。
>
> ## 现在怎么做
>
> **抓 `cn.bing.com/search` 的结果页并解析**
> （`httpx` + `beautifulsoup4` + `lxml` —— **三个都是本仓已有依赖，0 新增**）：
>
>   · **这个文件里不再有任何 LLM 客户端** ⇒ **结构上不可能再返回"模型编的内容"**
>   · **不需要 API key / 注册 / 额度** —— 那是**公开网页**，不是 API
>   · **不需要 chrome / 浏览器** —— 搜索结果页是**服务端渲染**的
>     （浏览器只在抓 **JS 渲染**的页面时才必要 —— 那是 `browser_tools`，已按 N13 摘掉）
>
> ## ⛔ 硬要求：**解析不到结果就如实报失败**
>
> 抓 HTML 是**逆向做法**，**必应改版就会坏**。坏掉那天**必须明说"搜不到"**，
> ⛔ **不许悄悄退回"让模型编一个"** —— 那正是这次重写要根除的病。
> ⇒ 由 `api/test_search_tools.py` 守着（含"本文件不许出现 LLM 客户端"的**结构判据**）。
"""
import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

# 🔴 2026-09-21（§十四 · ③-a）：**单次搜索的 HTTP 超时（秒）**。
#    ⚠️ 与 `execute_python` 的 5 秒**不是一回事**：那是**沙箱执行**的上限（子进程硬杀），
#       这是**网络往返**的上限。也没上限的话，一次卡住会把整条调用链挂住。
SEARCH_TIMEOUT_SECONDS = 20

# 用**必应中文**（`cn.bing.com`）—— 2026-09-21 实测，本机网络下它是唯一直接可达的：
#   `cn.bing.com` HTTP 200 ✅ ／ `google.com`、`duckduckgo.com` **完全不通** ❌
BING_SEARCH_URL = "https://cn.bing.com/search"

# 必应结果条目的 class。⚠️ **这是逆向来的** —— 必应改版这里就会失效，
# 届时 `_parse_bing_results` 会返回空，`web_search` **如实报失败**（不会静默变瞎）。
BING_RESULT_SELECTOR = "li.b_algo"

# 带一个正常的浏览器 UA —— 裸请求容易被判定为机器人
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 交给 LLM 的条数上限（多了会冲上下文）
MAX_RESULTS = 8


def _parse_bing_results(html: str) -> list:
    """从必应结果页 HTML 解析出 `[{title, url, snippet}]`。

    ⚠️ **解析不到就返回空列表** —— **不猜、不编**。调用方据此**如实报失败**。
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    for li in soup.select(BING_RESULT_SELECTOR):
        h2 = li.find("h2")
        a = (h2.find("a") if h2 else None) or li.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        url = a.get("href", "")
        caption = li.select_one(".b_caption")
        snippet = caption.get_text(" ", strip=True) if caption else ""
        if title and url:
            out.append({"title": title, "url": url, "snippet": snippet})
    return out


@tool
def web_search(query: str) -> str:
    """搜索互联网上的实时信息（必应中文）。

    适用于需要获取实时信息、新闻、资料等场景。输入是搜索关键词或问题。

    返回的是**网页搜索结果的标题 / 链接 / 摘要**（**不是**直接答案）——
    请据此再判断、或再抓取具体页面。

    ⚠️ **如果返回以「搜索失败」开头**，说明这次**没搜到**（网络不通 / 页面结构变了 / 被反爬拦住）。
    那种情况下请**如实告诉用户"暂时搜不到"**，
    ⛔ **不要拿你自己的知识假装成搜索结果** —— 那会让人以为这是查到的。
    """
    try:
        resp = httpx.get(
            BING_SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=SEARCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        return (
            f"搜索失败：无法访问搜索引擎（{type(e).__name__}: {e}）。\n"
            f"⛔ 这是**如实报告**：本次【没有】搜到任何东西，"
            f"也**没有**用模型知识替代 —— 请勿把这段当成搜索结果。"
        )

    items = _parse_bing_results(resp.text)
    if not items:
        return (
            "搜索失败：结果页里【解析不到任何条目】—— 可能是必应页面结构变了，或被反爬拦截。\n"
            "⛔ 这是**如实报告**：本次【没有】搜到任何东西，"
            "也**没有**用模型知识替代 —— 请勿把这段当成搜索结果。"
        )

    lines = [f"搜索「{query}」的结果（共 {len(items[:MAX_RESULTS])} 条）："]
    for i, it in enumerate(items[:MAX_RESULTS], 1):
        lines.append(f"{i}. {it['title']}")
        lines.append(f"   {it['url']}")
        if it["snippet"]:
            lines.append(f"   {it['snippet'][:300]}")
    return "\n".join(lines)
