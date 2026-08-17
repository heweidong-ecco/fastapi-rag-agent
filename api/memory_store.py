"""
长期记忆模块：基于 Mem0 的记忆存储与检索
"""
import os
from mem0 import Memory

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
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "model": "qwen-turbo",
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
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
    results = mem0_client.search(query, user_id=user_id, limit=top_k)
    if results:
        return [r["memory"] for r in results]
    return []