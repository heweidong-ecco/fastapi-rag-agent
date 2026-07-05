"""
综合检索管线
（带耗时统计）
将查询改写、混合检索、RRF 融合、重排序整合为统一入口。
每个环节可独立开关，通过配置参数灵活组合。
"""
import time
from query_rewriter import expand_query, rewrite_query
from reranker import rerank_async
from embedding_client import get_embedding
from db import search_similar_async, bm25_search_async
from collections import defaultdict
from langchain_openai import ChatOpenAI
import os

import asyncio

class RAGPipeline:
    """可配置的 RAG 检索管线 （带耗时统计） """

    def __init__(
        self,
        enable_rewrite: bool = False,
        enable_expand: bool = False,
        enable_bm25: bool = True,
        enable_rerank: bool = True,
        rrf_k: int = 60,
        candidate_multiplier: int = 3,
        answer_llm=None
    ):
        """
        参数:
            enable_rewrite: 是否启用查询优化（口语转书面语、指代消解）
            enable_expand: 是否启用查询扩展（生成多个查询变体）
            enable_bm25: 是否启用 BM25 关键词检索
            enable_rerank: 是否启用 Cross-Encoder 重排序
            rrf_k: RRF 平滑常数
            candidate_multiplier: 候选文档倍数（多召回留足重排序空间）
        """
        self.enable_rewrite = enable_rewrite
        self.enable_expand = enable_expand
        self.enable_bm25 = enable_bm25
        self.enable_rerank = enable_rerank
        self.rrf_k = rrf_k
        self.candidate_multiplier = candidate_multiplier
        # 增加一个用于生成答案的 LLM 实例
        self.answer_llm = answer_llm or ChatOpenAI(
            model="qwen-turbo",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0
        )

    from document_preprocessor import DocumentPreprocessor
    preprocessor = DocumentPreprocessor()

    async def search_async(
        self,
        query: str,
        top_k: int = 5,
        conversation_history: list[str] = None,
        generate_answer: bool = False,   # 新增
        strict_mode: bool = False,        # 新增
        citations: bool = False,          # 新增
    ) -> dict:
        timing = {}  # 存储各阶段耗时（毫秒）
        t_total_start = time.time()
        # 查询规范化（与文档入库使用同一套规则）
        from document_preprocessor import DocumentPreprocessor
        preprocessor = DocumentPreprocessor()
        query = preprocessor.clean_whitespace(query)
        query = preprocessor.normalize_text(query)
        """
        执行完整检索流程，返回结果和管线元信息。
        """
        pipeline_info = {
            "original_query": query,
            "rewrite_enabled": self.enable_rewrite,
            "expand_enabled": self.enable_expand,
            "bm25_enabled": self.enable_bm25,
            "rerank_enabled": self.enable_rerank,
        }

        # ===== 第一阶段：查询改写 =====
        t_rewrite_start = time.time()
        search_queries = [query]

        if self.enable_rewrite:
            rewritten = rewrite_query(query, conversation_history)
            search_queries = [rewritten]
            pipeline_info["rewritten_query"] = rewritten

        if self.enable_expand:
            base = search_queries[0]
            expanded = expand_query(base, num_variants=3)
            search_queries = expanded
            pipeline_info["expanded_queries"] = expanded

        timing["rewrite_ms"] = round((time.time() - t_rewrite_start) * 1000, 2)

        # ===== 第二阶段：多路检索 + RRF 融合 =====
        t_search_start = time.time()
        all_docs = []
        seen_contents = set()

        for sq in search_queries:
            # 向量检索
            query_embedding = get_embedding(sq)
            vector_results = await search_similar_async(query_embedding, top_k=top_k * self.candidate_multiplier)

            # BM25 检索
            bm25_results = []
            if self.enable_bm25:
                bm25_results = await bm25_search_async(sq, top_k=top_k * self.candidate_multiplier)

            # RRF 融合当前子查询的两路结果
            fused = self._rrf_fusion(vector_results, bm25_results, top_k * self.candidate_multiplier)
            for doc in fused:
                if doc["content"] not in seen_contents:
                    seen_contents.add(doc["content"])
                    all_docs.append(doc)

        # 对所有子查询的结果再次做 RRF 排序
        all_docs.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
        candidates = all_docs[:top_k * self.candidate_multiplier]
        timing["search_ms"] = round((time.time() - t_search_start) * 1000, 2)

        # ===== 第三阶段：重排序 =====
        t_rerank_start = time.time()
        if self.enable_rerank and candidates:
            candidates = await rerank_async(query, candidates, top_k=top_k)
        timing["rerank_ms"] = round((time.time() - t_rerank_start) * 1000, 2)


        SIMILARITY_THRESHOLD =0.7
        if candidates:
            candidates = [
                doc for doc in candidates
                if doc.get("rrf_score",0) >= SIMILARITY_THRESHOLD
                or doc.get("rerank_score",0) >= 0 # 重排序分数是 logits，正数即可
            ]
        # 如果所有文档都被过滤掉，返回空列表
        if not candidates:
            return{
                "query":query,
                "pipeline":pipeline_info,
                "timing":timing,
                "docs":[],
            }

        # ===== 总计 =====
        timing["total_ms"] = round((time.time() - t_total_start) * 1000, 2)

        # ===== 返回 =====
        result = {
            "query": query,
            "pipeline": pipeline_info,
            "timing": timing,
            "docs": candidates[:top_k],
        }
        
        # ========== 生成答案（可选） ==========
        if generate_answer and candidates:
            if citations:
            # 带引用
                from answer_with_citations import generate_answer_with_citations
                answer, sources = generate_answer_with_citations(
                    candidates[:top_k], query, self.answer_llm
                )
                result["answer"] = answer
                result["sources"] = sources
            else:
                # 普通生成
                context_text = "\n\n".join([doc["content"] for doc in candidates[:top_k]])
                # 根据 strict_mode 选择 Prompt
                if strict_mode:
                    system_prompt = "根据上下文回答。找不到则说'无法回答'。"
                else:
                    system_prompt = "根据上下文回答，可适当补充常识。"
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import StrOutputParser
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt + "\n\n上下文：\n{context}"),
                    ("user", "{question}")
                ])
                chain = prompt | self.answer_llm | StrOutputParser()
                answer = chain.invoke({"context": context_text, "question": query})
                result["answer"] = answer

        # 如果过滤后 candidates 为空，generate_answer 即使为 True 也不生成答案（因为没有上下文）
        elif generate_answer and not candidates:
            result["answer"] = "根据现有资料，无法回答。"

        return result 

    def _rrf_fusion(self, vector_docs, bm25_docs, top_k):
        """内部 RRF 融合函数"""
        rrf_scores = defaultdict(float)
        doc_info = {}

        for rank, (doc_id,content, source, similarity) in enumerate(vector_docs, start=1):
            rrf_scores[content] += 1.0 / (self.rrf_k + rank)
            doc_info[content] = {"id": doc_id,"content": content, "source": source, "from": "vector"}

        for rank, (doc_id, content, source, bm25_score) in enumerate(bm25_docs, start=1):
            rrf_scores[content] += 1.0 / (self.rrf_k + rank)
            if content in doc_info:
                doc_info[content]["from"] = "both"
            else:
                doc_info[content] = {"id": doc_id,"content": content, "source": source, "from": "bm25"}

        sorted_contents = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for content, rrf_score in sorted_contents[:top_k]:
            info = doc_info[content]
            info["rrf_score"] = round(rrf_score, 4)
            results.append(info)

        return results


# 预定义几套常用配置
def create_fast_pipeline() -> RAGPipeline:
    """快速检索：不用查询改写和重排序，速度最快"""
    return RAGPipeline(enable_rewrite=False, enable_expand=False, enable_bm25=True, enable_rerank=False)

def create_accurate_pipeline() -> RAGPipeline:
    """精确检索：启用查询改写和重排序，效果最好"""
    return RAGPipeline(enable_rewrite=True, enable_expand=False, enable_bm25=True, enable_rerank=True)

def create_accurate_norerank_pipeline() -> RAGPipeline:
    """精确检索：启用查询改写和重排序，效果最好"""
    return RAGPipeline(enable_rewrite=True, enable_expand=False, enable_bm25=True, enable_rerank=False)

def create_full_pipeline() -> RAGPipeline:
    """完整管线：启用所有优化，效果最佳但延迟最高"""
    return RAGPipeline(enable_rewrite=True, enable_expand=True, enable_bm25=True, enable_rerank=True)