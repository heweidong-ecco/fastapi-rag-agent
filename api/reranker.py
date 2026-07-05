"""
重排序模块
使用 Cross-Encoder 模型对候选文档进行精细排序。
"""
from sentence_transformers import CrossEncoder

# 全局加载模型（首次调用时自动下载，之后缓存）
# 使用 BGE-Reranker v2-m3，中文效果优秀
_reranker = None

def get_reranker():
    """懒加载重排序模型，只加载一次"""
    global _reranker
    if _reranker is None:
        print("正在加载重排序模型 BGE-Reranker-v2-m3...")
        _reranker = CrossEncoder(
            "BAAI/bge-reranker-v2-m3",
            max_length=512  # 最大输入长度，超过会截断
        )
        print("重排序模型加载完成")
    return _reranker

def rerank(query: str, docs: list[dict], top_k: int = 3) -> list[dict]:
    """
    对候选文档进行重排序。

    参数:
        query: 用户问题
        docs: 候选文档列表，每个包含 "content" 字段
        top_k: 返回的文档数量

    返回:
        重新排序后的文档列表，每个包含 "content", "source", "rerank_score", "from"
    """
    if not docs:
        return docs

    model = get_reranker()

    # 构建模型输入：[(query, doc_content), ...]
    pairs = [[query, doc["content"]] for doc in docs]

    # 批量计算相关性分数
    scores = model.predict(pairs)

    # 为每个文档添加重排序分数
    for i, doc in enumerate(docs):
        doc["rerank_score"] = round(float(scores[i]), 4)

    # 按分数降序排序
    docs.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

    return docs[:top_k]

import asyncio

async def rerank_async(query: str, docs: list[dict], top_k: int = 3) -> list[dict]:
    """异步版本的Cross-Encoder重排序"""
    return await asyncio.to_thread(rerank, query, docs, top_k)