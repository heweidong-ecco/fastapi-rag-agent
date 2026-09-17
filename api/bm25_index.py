"""
BM25 关键词检索（jieba 中文分词 + rank_bm25）。

从 `db.py` 切出（重构计划 ⑥ 切开点 1）。目的：让 `import db` 不再被迫拉起
`numpy` / `jieba` / `rank_bm25` 三个重包。

⚠️ **依赖方向只允许单向**：本模块 `from db import get_db`；
`db.py` 一律用**函数内惰性导入**反向引用本模块。
**不要**在 `db.py` 模块层 `import bm25_index` —— 那会形成循环导入，
且只在"先 import db"时才碰巧能跑（"先 import bm25_index"就会炸），是最难查的一类问题。
"""
import numpy as np
import jieba
from rank_bm25 import BM25Okapi

from db import get_db

# 全局缓存：避免每次搜索都重建索引
_bm25_cache = {
    "bm25": None,
    "docs": []
}

def get_all_documents():
    """获取数据库中所有文档的内容、来源和ID，用于构建BM25索引"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, content, source FROM documents")
            return cur.fetchall()

def get_bm25_index():
    """获取缓存的BM25索引，如果不存在则重建"""
    if _bm25_cache["bm25"] is None:
        docs = get_all_documents()
        if docs:
            # 使用 jieba 进行中文分词
            tokenized_docs = [list(jieba.cut(doc[1])) for doc in docs]
            _bm25_cache["bm25"] = BM25Okapi(tokenized_docs)
            _bm25_cache["docs"] = docs
    return _bm25_cache["bm25"], _bm25_cache["docs"]

def invalidate_bm25_cache():
    """在文档插入/删除后调用，清空缓存以触发重建"""
    _bm25_cache["bm25"] = None
    _bm25_cache["docs"] = []

def bm25_search(query: str, top_k: int = 10):
    """
    用 BM25 关键词检索文档。
    返回 [(id, content, source, bm25_score), ...]
    """
    bm25, docs = get_bm25_index()
    if bm25 is None or not docs:
        return []

    tokenized_query = list(jieba.cut(query))
    scores = bm25.get_scores(tokenized_query)

    top_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            doc = docs[idx]
            results.append((doc[0], doc[1], doc[2], float(scores[idx])))

    return results
