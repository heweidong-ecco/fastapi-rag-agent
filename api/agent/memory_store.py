"""
长期记忆模块：基于 Mem0 的记忆存储与检索
"""
import os
from mem0 import Memory
from core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_FAST

# 初始化 Mem0 客户端
# Mem0 支持本地模式（数据存储在本地文件）和云端模式，这里使用本地模式进行开发
# 注意：mem0ai>=2.0 的 Memory.__init__ 只接受 MemoryConfig 对象，不再接受 dict，
# 需使用 Memory.from_config(dict) 构造。
mem0_client = Memory.from_config(
    # 本地模式配置，数据存储在当前目录下的 .mem0 文件夹中
    {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": "./.mem0/qdrant",
                "collection_name": "mem0",
            }
        },
        "llm": {
            "provider": "openai",
            "config": {
                "api_key": LLM_API_KEY,
                "model": LLM_MODEL_FAST,
                "openai_base_url": LLM_BASE_URL,
            }
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "model": "text-embedding-v2",
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            }
        }
    }
)


def add_user_memory(user_id: str, content: str):
    """
    添加一条用户记忆。
    Mem0 会自动提取关键信息、去重、并更新已有记忆。
    """
    mem0_client.add(content, user_id=user_id)


def search_user_memory(user_id: str, query: str, top_k: int = 3) -> list[str]:
    """
    搜索与当前查询相关的用户记忆。
    返回相关记忆的文本列表。
    """
    # 🔴 2026-09-20 修（依赖漂移）:此前写的是 `search(query, user_id=…, limit=…)`。
    #    mem0 **2.0.20** 的签名是 `search(query, *, top_k=20, filters=None, …)` ——
    #    ① `user_id` 不再是顶层参数（要走 `filters`）② `limit` 已改名 `top_k`。
    #    线上实测报错:`ValueError: Top-level entity parameters frozenset({'user_id'})
    #    are not supported in search(). Use filters={'user_id': '...'} instead.`
    #    ⚠️ 它让**二代/三代 Agent 直接 500**（两者都在入口注入长期记忆）。
    #    回归测试:`api/test_agent_repairs.py::test_search_user_memory_matches_mem0_2x_signature`
    results = mem0_client.search(query, filters={"user_id": user_id}, top_k=top_k)
    # 🔴 2026-09-20 第二处（同一依赖漂移的另一半）:**返回形状也变了**。
    #    mem0 2.x 的 search() 返回 **`{"results": [...]}`**（dict），**不是 list**。
    #    此前直接 `for r in results` ⇒ 遍历 dict 拿到的是**键（字符串）**
    #    ⇒ 线上实测 `TypeError: string indices must be integers`。
    #    ⚠️ 这一处是**第一次没修完**才暴露的：我当时只验了"不抛异常 + len()=1"，
    #       而**一个只有 1 个键的 dict，len() 也是 1** ⇒ 验了"没炸"，没验"形状对不对"。
    items = results.get("results", []) if isinstance(results, dict) else (results or [])
    if items:
        return [r["memory"] for r in items if isinstance(r, dict) and "memory" in r]
    return []