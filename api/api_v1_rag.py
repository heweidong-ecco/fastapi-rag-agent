"""
API v1 路由集中定义
所有 /api/v1 前缀的接口在此管理。
"""
import json
import time
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from config import ACCESS_TOKEN_EXPIRE_MINUTES
# ①b Task 5：LLM 的唯一构造落点（`model` / `api_key` / `base_url` / `max_tokens` 都收在那一处）。
# ⚠️ `llm_factory` 模块级只 import `os`（langchain 是在 `make_llm()` **函数内**才 import）
# ⇒ 放文件头**不破坏**本文件「导入期不拉 langchain」的既有做法（原 `MAX_TOKENS_ANSWER` 同理）。
from llm_factory import make_llm
from exceptions import ErrorCode, AppException
# B8 接线（①b Task 2）：会话级 token 上限。
# ⚠️ `token_tracker` 模块级只 import `os/json/threading` 等标准库 + `token_config`
#    （`db` / `langchain` 都是**函数内**惰性导入）⇒ 放文件头**不破坏**本文件
#    「导入期不拉 langchain」的既有做法（与上面 `MAX_TOKENS_ANSWER` 同一条理由）。
from token_tracker import check_session_token_budget
# B11（①b Task 4）：全站日级熔断。与 B8 并列，⛔ 别合并（B8 按会话 / B11 按全站）。
# ⚠️ breaker 只在**函数内**惰性导入 token_tracker ⇒ 放文件头不破坏本文件
#    「导入期不拉重依赖」的既有做法（同上面 `token_tracker` 那条注释的道理）。
from breaker import circuit, global_key
from schemas import (
    QuestionRequest,
    DocumentInsert,
    BatchDocumentInsert,
    LoginRequest,
    RefreshRequest,
    UserCreate,
)
from deps import get_current_user_hybrid, get_current_user_jwt, require_admin
from db import get_db, insert_document,insert_batch_documents
from db import search_similar  # 🔴 2026-10-03 乙段（DEC-056）：stream_search 改走共享层
from embedding_client import get_embedding

from permission import get_user_role, UserRole  # ⚠️ 2026-10-03 删 `get_user_quota`（本文件从未使用；该函数已随 DEC-046 一起删）
from tools_with_cache import get_weather  # ⚠️ 2026-09-20 删 `calculator`（D1）：它在被下方那个**函数内的局部 calculator** 覆盖前从未使用
from db import invalidate_bm25_cache
from hybrid_search import hybrid_search
from hybrid_search import rerank_search
from hybrid_search import hybrid_search_with_rewrite
# ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：这一行与下方（`SearchMode` 那段附近）
#    的导入**重复**，且下方那份还多带 `create_accurate_norerank_pipeline`。
#    实测：本行那份在下方覆盖之前**从未被使用** ⇒ 删本行、保留下方更全的那份。
from fastapi import File, UploadFile
import tempfile

from document_preprocessor import DocumentPreprocessor
from chunker import split_text_with_filter
from document_parser import parse_document

from cache import get_chat_history, append_chat_history

from agent_graph import agent_graph

import os

router = APIRouter(prefix="/api/v1")


# ==================== 文档管理 ====================
# 新增功能，自动绑定当前用户
@router.post(
    "/rag/insert",
    summary="插入单条文档",
    description="""
    接收一段文本，自动调用阿里百炼 text-embedding-v2 模型将其转换为 1536 维向量，
    然后存入 PostgreSQL(pgvector) 数据库。
    
    文档入库后即可被 `/rag/pg_search` 接口检索。
    
    **认证要求**：需要在请求头中携带 `X-API-Key` 或 `Authorization: Bearer <JWT>`。
    """,
    tags=["文档管理"],
    response_description="文档插入成功的确认信息，包含入库内容的摘要",
    responses={
        200: {"description": "文档插入成功"},
        401: {
            "description": "缺少或无效的 API Key / JWT",
            "content": {
                "application/json": {
                    "examples": {
                        "AUTH_MISSING": {
                            "summary": "缺少API Key",
                            "value": {
                                "error": "缺少API Key",
                                "code": "AUTH_MISSING",
                                "status_code": 401
                            }
                        },
                        "AUTH_EXPIRED": {
                            "summary": "凭证已过期",
                            "value": {
                                "error": "API Key无效或已过期",
                                "code": "AUTH_EXPIRED",
                                "status_code": 401
                            }
                        }
                    }
                }
            }
        },
        403: {
            "description": "无权限访问",
            "content": {
                "application/json": {
                    "examples": {
                        "error": "无权限访问",
                        "code": "FORBIDDEN",
                        "status_code": 403
                    }
                }
            }
        },
        429: {
            "description": "请求过于频繁或配额已用完",
            "content": {
                "application/json": {
                    "examples": {
                        "RATE_LIMITED": {
                            "summary": "触发限流",
                            "value": {
                                "error": "请求过于频繁，请稍后再试",
                                "code": "RATE_LIMITED",
                                "status_code": 429
                            }
                        },
                        "QUOTA_EXCEEDED": {
                            "summary": "配额已用完",
                            "value": {
                                "error": "今日调用次数已用完",
                                "code": "QUOTA_EXCEEDED",
                                "status_code": 429
                            }
                        }
                    }
                }
            }
        },
        500: {"description": "服务器内部错误（如 Embedding API 调用失败）","content": {"example": {"code": "INTERNAL_ERROR"}}}
    }
)
async def insert_single_doc(
    doc: DocumentInsert,
    user_name: str = Depends(get_current_user_hybrid),
):
    """插入单条文档，自动生成Embedding并入库"""
    embedding = get_embedding(doc.content)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (content, source, embedding, requested_by) VALUES (%s, %s, %s::vector, %s)RETURNING id",
                (doc.content, doc.source, embedding, user_name)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    # 文档已变更 → 必须**在函数内**失效 BM25 进程内缓存。
    # (原先写在模块级 = 只在 import 时执行一次 ⇒ 插入后缓存不失效,新文档在 BM25 通路里
    #  "不存在",必须重启进程才能检索到。2026-09-11 实测:重启前新文档不在 top10,重启后第 2 名)
    invalidate_bm25_cache()
    return {"status": "inserted","id": new_id, "content": doc.content[:100], "source": doc.source,"requested_by":user_name}

@router.post(
    "/rag/insert_batch",    
    summary="批量插入文档",
    description="""
    批量插入文档，自动调用阿里百炼 text-embedding-v2 模型将其转换为 1536 维向量，
    然后存入 PostgreSQL(pgvector) 数据库。
    
    文档入库后即可被 `/rag/pg_search` 接口检索。
    
    **认证要求**：需要在请求头中携带 `X-API-Key` 或 `Authorization: Bearer <JWT>`。
    """,
    tags=["文档管理"],
    response_description="文档插入成功的确认信息，包含入库内容的摘要",
    responses={
        200: {"description": "文档插入成功"},
        401: {
            "description": "缺少或无效的 API Key / JWT",
            "content": {
                "application/json": {
                    "examples": {
                        "AUTH_MISSING": {
                            "summary": "缺少API Key",
                            "value": {
                                "error": "缺少API Key",
                                "code": "AUTH_MISSING",
                                "status_code": 401
                            }
                        },
                        "AUTH_EXPIRED": {
                            "summary": "凭证已过期",
                            "value": {
                                "error": "API Key无效或已过期",
                                "code": "AUTH_EXPIRED",
                                "status_code": 401
                            }
                        }
                    }
                }
            }
        },
        403: {
            "description": "无权限访问",
            "content": {
                "application/json": {
                    "examples": {
                        "error": "无权限访问",
                        "code": "FORBIDDEN",
                        "status_code": 403
                    }
                }
            }
        },
        429: {
            "description": "请求过于频繁或配额已用完",
            "content": {
                "application/json": {
                    "examples": {
                        "RATE_LIMITED": {
                            "summary": "触发限流",
                            "value": {
                                "error": "请求过于频繁，请稍后再试",
                                "code": "RATE_LIMITED",
                                "status_code": 429
                            }
                        },
                        "QUOTA_EXCEEDED": {
                            "summary": "配额已用完",
                            "value": {
                                "error": "今日调用次数已用完",
                                "code": "QUOTA_EXCEEDED",
                                "status_code": 429
                            }
                        }
                    }
                }
            }
        },
        500: {"description": "服务器内部错误（如 Embedding API 调用失败）","content": {"example": {"code": "INTERNAL_ERROR"}}}
    }
)
async def insert_batch(
    batch: BatchDocumentInsert,
    user_name: str = Depends(get_current_user_hybrid)  # 注入当前用户名
):
    """批量插入文档"""
    count = 0
    for doc in batch.documents:
        embedding = get_embedding(doc.content)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO documents (content, source, embedding, requested_by) VALUES (%s, %s, %s::vector, %s)",
                    (doc.content, doc.source, embedding, user_name)
                )
                conn.commit()
        count += 1
    # 同上：批量插入后也须失效，否则本批新文档检索不到
    invalidate_bm25_cache()
    return {"status": "inserted", "count": count, "requested_by":user_name}

# 上传并解析复杂 PDF 文件
# 文档上传接口，在解析后、入库前进行预处理：
preprocessor = DocumentPreprocessor()

@router.post("/rag/upload_document")
async def upload_document(
    file: UploadFile = File(...),
    domain: str = "default",  # 新增：用户可指定领域，默认为 "default"，法律"legal",医疗"medical"
    user_name: str = Depends(get_current_user_hybrid),
):
    """上传并解析多格式文档（PDF/Word/Markdown/HTML），经过预处理后入库。

    ⚠️ 2026-09-20 修：此处原有**两行紧挨着的 docstring** ——
       第二行（那句「上传并解析多格式文档，经过预处理后入库」，用三引号包着）是**空操作**
       （函数已有一行 docstring）。已把它的信息并入第一行、删掉第二行。
    """
    # 检查文件格式
    allowed_extensions = ["pdf", "docx", "md", "html"]
    ext = file.filename.lower().split(".")[-1]
    if ext not in allowed_extensions:
        raise AppException(
            ErrorCode.PARAM_INVALID,
            f"不支持的文件格式: {ext}，支持: {', '.join(allowed_extensions)}"
        )
    
    # 保存临时文件
    # ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：这里原先又 `import tempfile` / `import os`，
    #    而两者**模块级早就导入过**（见文件头部）⇒ 这两行只是把同名对象再绑一次，纯冗余。
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    # 解析文档
    text = parse_document(tmp_path)
    # 根据领域预处理
    preprocessor = DocumentPreprocessor(domain=domain)
    # 预处理：清洗、去重、标准化
    cleaned_text = preprocessor.process(text)  # 在文件中，不会在中间件NLP全局中传导被读取← 这里要显式调用

    # 分块
    # 可选：对块进行语义去重
    # chunks = preprocessor.deduplicate_chunks(chunks)
    # 分块（根据文件格式选择分块策略）
    # PDF 和 Word 通常为技术文档，Markdown 也按技术文档处理
    doc_type = "legal" if ext == "pdf" else "technical"
    chunks = split_text_with_filter(cleaned_text, doc_type=doc_type, min_length=20)

    # 入库
    for chunk in chunks:
        embedding = get_embedding(chunk)
        insert_document(chunk, file.filename, embedding, user_name)  # user_name 作为 requested_by

    # 清理临时文件
    os.unlink(tmp_path)
    
    return {
        "filename": file.filename,
        "format": ext,
        "domain": domain,
        "chunks_inserted": len(chunks),
        "text_length": len(cleaned_text),
        "preview": cleaned_text[:500],
        "requested_by": user_name,
    }

@router.delete("/rag/documents/{doc_id}", tags=["文档管理"])
async def delete_document(
    doc_id: int = Path(..., ge=1, description="要删除的文档ID"),
    user_name: str = Depends(get_current_user_hybrid),
):
    """删除指定文档（只能删除自己上传的，管理员可删除所有）"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. 先查询文档的归属
            cur.execute("SELECT requested_by FROM documents WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            if row is None:
                raise AppException(ErrorCode.RESOURCE_NOT_FOUND, f"文档 {doc_id} 不存在")
            
            owner = row[0]
            
            # 2. 权限判断：管理员 或 文档上传者本人
            role = get_user_role(user_name)
            if role != UserRole.ADMIN and owner != user_name:
                raise AppException(ErrorCode.FORBIDDEN, "只能删除自己上传的文档")
            
            # 3. 执行删除
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
    
    # 同上：删除后也须失效，否则已删文档仍会出现在 BM25 召回里
    invalidate_bm25_cache()
    return {"status": "deleted", "id": doc_id, "requested_by": user_name}

# ==================== 检索接口 ====================
# 新增 ：只检索 和 返回当前用户的文档
@router.post(
    "/rag/pg_search",
    summary="向量语义检索",
    description="使用阿里百炼 text-embedding-v2 将问题转为向量，在 pgvector 中检索最相关的文档块，返回按相似度降序排列的结果。",
    tags=["检索"],
    response_description="检索结果列表，包含文档内容、来源和相似度分数",
        responses={
        200: {"description": "检索成功"},
        401: {"description": "缺少或无效的 API Key", "content": {"example": {"code": "AUTH_MISSING"}}},
        403: {"description": "API Key 已过期", "content": {"example": {"code": "FORBIDDEN"}}},
        429: {
            "description": "请求过于频繁或配额已用完",
            "content": {
                "application/json": {
                    "examples": {
                        "RATE_LIMITED": {
                            "summary": "触发限流",
                            "value": {
                                "error": "请求过于频繁，请稍后再试",
                                "code": "RATE_LIMITED",
                                "status_code": 429
                            }
                        },
                        "QUOTA_EXCEEDED": {
                            "summary": "配额已用完",
                            "value": {
                                "error": "今日调用次数已用完",
                                "code": "QUOTA_EXCEEDED",
                                "status_code": 429
                            }
                        }
                    }
                }
            }
        },
        500: {"description": "服务器内部错误", "content": {"example": {"code": "INTERNAL_ERROR"}}}
    }
)
async def pg_search(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_hybrid)
):
    query_embedding = get_embedding(req.question)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT content, source, 1 - (embedding <=> %s::vector) AS similarity
                FROM documents
                WHERE requested_by = %s          -- 只检索当前用户的文档
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """, 
                (query_embedding, user_name, query_embedding, req.top_k))
            results = cur.fetchall()
    docs = [
        {
            "content": r[0],
            "source": r[1],
            "similarity": round(r[2], 4)
        }
        for r in results
    ]
    return {
        "question": req.question,
        "requested_by": user_name,
        "docs": docs,
        "embedding_dim": len(query_embedding)
    }


# 混合检索接口,加入BM25稀疏检索
@router.post("/rag/hybrid_search")
async def hybrid_search_api(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_hybrid),
):
    """混合检索：向量 + BM25 关键词（**只在该用户自己的文档内**）"""
    docs = hybrid_search(req.question, req.top_k, user_id=user_name)
    return {
        "question": req.question,
        "method": "hybrid (vector + bm25)",
        "docs": docs,
        "requested_by": user_name,
    }

# 添加重排序检索接口
@router.post("/rag/rerank_search")
async def rerank_search_api(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_hybrid),
):
    """带重排序的混合检索（**只在该用户自己的文档内**）"""
    docs = rerank_search(req.question, req.top_k, user_id=user_name)
    return {
        "question": req.question,
        "method": "hybrid + RRF + Cross-Encoder Rerank",
        "docs": docs,
        "requested_by": user_name,
    }

# 新增带 用户查询问题改写 的检索函数。检索器：只使用了hybrid_search(bm25+vertor+RRF)
@router.post("/rag/rewrite_search")
async def rewrite_search_api(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_hybrid),
):
    """带查询改写的混合检索（**只在该用户自己的文档内**）"""
    docs = hybrid_search_with_rewrite(req.question, req.top_k, user_id=user_name)
    return {
        "question": req.question,
        "method": "query rewrite + hybrid search + RRF",
        "docs": docs,
        "requested_by": user_name,
    }

# 添加综合检索接口 RAGPipeline
from rag_pipeline import create_fast_pipeline, create_accurate_pipeline, create_accurate_norerank_pipeline,create_full_pipeline

# 🔴 `mode` 必须是**受限枚举**，不能是裸 `str` —— 2026-09-17 修，起因见 `unified_search` 的注释。
SearchMode = Literal["fast", "accurate", "accurate_norerank", "full"]

# mode → 管线工厂。**用查表代替 if/elif/else**：漏一个 mode 会 KeyError（当场炸），
# 而不是静默落进某个兜底分支。
PIPELINE_FACTORIES = {
    "fast": create_fast_pipeline,
    "accurate": create_accurate_pipeline,
    "accurate_norerank": create_accurate_norerank_pipeline,
    "full": create_full_pipeline,
}


@router.post("/rag/search")
async def unified_search(
    req: QuestionRequest,
    mode: SearchMode = "accurate_norerank",
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    综合检索入口，支持多种模式切换，返回各阶段耗时统计。

    **模式说明：**
    - **fast**：仅 BM25 + 向量检索 + RRF 融合，速度最快。
    - **accurate**：增加查询改写和 Cross-Encoder 重排序，精度最高。
    - **accurate_norerank**：增加查询改写，但**不做** Cross-Encoder 重排序（**默认值**，不依赖 torch）。
    - **full**：在 accurate 基础上增加查询扩展，覆盖最全。

    ⚠️ `mode` 是**受限枚举**，取值只有上面四个；传别的值会得到 **422**，而不是被静默兜底。
    """
    # 🔴 2026-09-17 修：此处原先是一个**裸 `else`** —— 任何拼错的 mode（如 `fst`）
    # 都不报错，而是**静默换成 `accurate_norerank`**（多跑一次查询改写 = 多花钱、多延迟）。
    # 现在：`mode` 声明为 `SearchMode`（`Literal`），非法值由 FastAPI 在进入函数体之前挡成 422；
    # 且下方改用**查表**，结构上不存在"兜底分支"。决策见 `docs/decisions/DEC-013`。
    pipeline = PIPELINE_FACTORIES[mode]()

    # 执行检索
    result = await pipeline.search_async(
        req.question,
        top_k=req.top_k,
        conversation_history=req.conversation_history,  # 传递历史
        generate_answer=req.generate_answer,
        strict_mode=req.strict_mode,
        citations=req.citations,
        user_id=user_name,   # 🔴 2026-10-03 加（DEC-056）—— 检索只在该用户自己的文档内
    )

    # 添加用户信息
    result["requested_by"] = user_name
    result["mode"] = mode

    return result


@router.post(
    "/rag/jwt_ask",
    summary="JWT认证的问答接口",
    description="输入JWT_SECRET_KEY，获得回答结果",
    tags=["检索"],
    response_description="返回搜索结果：创建JWT_SECRET_KEY，用户名，下的数据结果"
)
async def jwt_ask_question(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_jwt)  # JWT 认证
):
    start = time.time()
    with get_db() as conn:
        with conn.cursor() as cur:
            # 🔴 2026-10-03 乙段（`DEC-056` §1.2 第 7 条）：补上 `WHERE requested_by`。
            #    原先 **零 `WHERE`** ⇒ 查全库。实测：isolation_b 打自己的 JWT
            #    却拿回了 20 篇 admin 的文档（`api/test_isolation.py`）。
            #    ⚠️ **只加过滤，⛔ 不改检索语义** —— 它「拿到 question 却不拿它做检索」
            #       （无 embedding、无 `ORDER BY`）是**另一条账**，不在隔离收口内。
            cur.execute(
                "SELECT content FROM documents WHERE requested_by = %s LIMIT %s",
                (user_name, req.top_k),
            )
            rows = cur.fetchall()
    docs = [r[0] for r in rows]
    duration = time.time() - start
    return {
        "question": req.question,
        "docs": docs,
        "elapsed": f"{duration:.3f}秒",
        "requested_by": user_name
    }

# ==================== 流式输出（SSE） ====================
# ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：此处的 `StreamingResponse` 与 `json`
#    在文件头早已导入过 ⇒ 删这两行。⚠️ 同段的 `import asyncio` **不是重复**（文件头没有），**必须留**。
# ⚠️ 2026-10-02 删（Task 5）：同段的 `from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_CHAT`
#    已**不再被引用** —— 两个构造点都改走 `make_llm()`，那三个值由工厂统一读。
import asyncio
# ⚠️ 2026-10-04 删（`B1` 剩余 4 条链 · 批 3）：`anyio` / `track_stream_cancel` / `logger` /
#    `StreamingResponse` 四个 import **已从本文件移除** —— 它们此前**只被** `stream_search`
#    那段内联生成器用到，而那段整块搬进了 `api/sse.py`（`shield=True` 关流 · 计数 · 日志
#    · `StreamingResponse` 三件都在那边，**只是一份**）。留着就是没人用的 import。
# 🔴 本仓所有流式端点共用 `api/sse.py` 的那副骨架（含 5 条实测约束的顺序）。
from sse import DONE_FRAME, llm_chunk_text, sse_frame, sse_response, sse_stream

# ⚠️ 2026-09-17 重构 ⑥ 切开点 5：惰性单例。
#    原先此处是【模块层】直接 `llm_stream = ChatOpenAI(...)` ⇒
#    `import api_v1_rag`（进而 `import main`）**在导入期就构造 LLM 对象**，
#    哪怕这个进程根本不走流式接口。
#    现改为**首次使用时才建**；此后复用同一实例（与原先的"单例"语义一致）。
_llm_stream = None

def get_llm_stream():
    """惰性构造流式 LLM（首次调用时才建，之后复用）。"""
    global _llm_stream
    if _llm_stream is None:
        # ⚠️ 角色 = 「模型轴 chat」+「长度轴 answer(2000)」—— 见 `api/llm_factory.py` 的模块 docstring。
        #    ⚠️ 惰性仍在：`make_llm()` 自己把 `langchain_openai` 的 import 关在函数内。
        _llm_stream = make_llm(
            "chat", "answer",
            temperature=0.3,
            streaming=True,  # 关键：开启流式模式
        )
    return _llm_stream


# 🔴 `③` Task 6（`B3`）：中断后存进历史的那半截答案**必须带这个尾巴**。
#    理由：历史会被**原样拼进下一轮的 prompt**（`:669-670`）——
#    不带标记 ⇒ 模型会把一段**被截断的回答**当成"上一轮我说完了"，行为跟着变。
INTERRUPTED_SUFFIX = "…（本次回答被中断，以上为已生成部分）"


def _persist_interrupted_turn(user_name: str, question: str, collected_parts: list):
    """客户端中断后，把**已经生成的那半截**补存进对话历史（`③` Task 6 · `B3`）。

    ⚠️ 为什么不是"直接丢"：丢的话**用户那句提问也一起丢**（它和答案写在同一个
       收尾段里）⇒ 用户下一轮问"接着上面说"，历史里**没有任何痕迹**。
       代码原作者的意图写在本文件 `:691` 的注释里（"使它支持历史补偿"）。

    ⚠️ **一块都没生成就不写** —— 写一条空的助手消息只会污染下一轮 prompt。
    """
    answer = "".join(collected_parts).strip()
    if not answer:
        return
    # 成对写：只写答案不写提问 ⇒ 历史里出现一条**没有来由**的助手消息
    append_chat_history(user_name, "user", question)
    append_chat_history(user_name, "assistant", answer + INTERRUPTED_SUFFIX)


@router.post("/rag/stream_search")
async def stream_search(
    req: QuestionRequest,
    thread_id: str = "default",       # ⚠️ B8 补：本端点原先**没有** thread_id
    user_name: str = Depends(get_current_user_hybrid),
):
    """流式RAG问答接口（融合优化版）（支持引用溯源和历史补偿）。
    使用SSE逐字返回生成的答案，提供类似ChatGPT的体验。

    ⚠️ 2026-09-20 修：这段 docstring 原先**躺在两句代码之后**（函数体第三句），
       是**空操作** —— 函数本身**没有 docstring**。已上移到签名正下方。
    """
    # 0. 若前端未主动传历史，则从 Redis 加载该用户最近5轮对话
    if not req.conversation_history:
        req.conversation_history = get_chat_history(user_name)

    # B8 · 会话级 token 上限（`DEC-041`）—— 触顶直接拒绝。
    # ⚠️ 放在**取历史之后、检索之前**：这是本端点**第一处真花钱**的位置之前。
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）—— 与上一段并列、都要过。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)
    # 1. 检索（与普通接口相同）
    # 1. 向量检索（这部分不是流式的，一次性查完）
    # 构建当前输入的这条的历史对话，真停止按钮的调用（使它支持历史补偿）
    query_embedding = get_embedding(req.question)
    # 🔴 2026-10-03 乙段（`DEC-056` §1.2 第 8 条）：改用**共享层**，⛔ 不再自己写 SQL。
    #    原先这段 SQL **零 `WHERE`** ⇒ 查全库。实测（`api/test_isolation.py`）：
    #    isolation_b 的检索上下文里**逐字**出现了 isolation_a 的文档。
    #    `search_similar` 已带 `WHERE requested_by = %s`，且**返回同样的 4 列**
    #    （id, content, source, similarity）⇒ 下面 `r[0..3]` 的映射不用改。
    #    ⚠️ 身份是端点传下去的 —— 这就是「共享层承重」（`DEC-056` 决策 5）。
    results = search_similar(query_embedding, req.top_k, user_id=user_name)

    # 2. 构建上下文列表（用于可能的引用模式）
    contexts = []
    for r in results:
        contexts.append({
            "id": r[0],
            "content": r[1],
            "source": r[2],
            "similarity": r[3]
        })

    if req.citations:
        # 引用模式：构建带编号的上下文和引用规则 Prompt
        context_parts = []
        sources_list = []
        for i, doc in enumerate(contexts, start=1):
            context_parts.append(f"[文档{i}来源：{doc.get('source', '未知')}]\n{doc['content']}")
            sources_list.append({
                "id": doc.get("id"),
                "source": doc.get("source", "未知"),
                "content_preview": doc["content"][:100]
            })
        context_text = "\n\n".join(context_parts)

        system_prompt = f"""你是一个严谨的问答助手。请严格根据以下上下文回答用户的问题。

**引用规则（必须遵守）：**
1. 当你使用上下文中的某条信息时，必须在句末标注来源编号，格式为 `[来源:X]`，其中 X 是文档编号。
2. 如果一句话使用了多个来源，标注为 `[来源:X, Y]`。
3. 不要编造任何上下文以外的信息。如果上下文不足以回答问题，请直接说“根据现有资料，无法回答”。

**上下文文档：**
{context_text}"""
    else:
        # 普通模式
        context_text = "\n\n".join([doc["content"] for doc in contexts])
        system_prompt = f"""你是一个专业的问答助手。请严格根据以下上下文回答用户的问题。
上下文：
{context_text}"""
        sources_list = []

    # 3. 构建当前消息列表（如果有停止当前消息先放历史，如果没有即为空，再放当前提示词）真停止按钮的调用（使它支持历史补偿）
    messages = []
    if req.conversation_history:
        messages.extend(req.conversation_history)

    messages.extend([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.question}
    ])
    
    # 4. 流式生成器
    ENDPOINT = "rag_stream_search"    # Prometheus 的 label（`③` Task 5），⛔ 别与函数名混用

    # 🔴 2026-10-04（`B1` 剩余 4 条链 · 批 3）：**内联生成器整个换成 `sse.sse_stream` 骨架**。
    #    这段原来有 ~80 行 `try / except / except / finally`，与 `/agent/langgraph_chat/stream`
    #    **逐字重复**（那 5 条实测约束因此被抄了两遍）。现在只有 `api/sse.py` 一份。
    #    ⚠️ **等价不是"看起来一样"** —— 下面两处**很反直觉的旧契约**是本端点特有的，
    #    ⛔ **别在"抽公共层"时顺手修正**（前端的适配是照着它们写的）：
    #      ① `[DONE]` 在 `sources` **之前**（见 `_complete`）；
    #      ② 错误路径**没有** `[DONE]`（见 `_on_error`）。
    #    判据：`api/test_cancel_propagation.py` **全绿，且一行断言都没改**。
    async def _complete(collected):
        """收尾尾巴（正常跑完才进）—— ⚠️ **帧序是有讲究的，⛔ 别整理成"先 sources 再 `[DONE]`"**。

        ⚠️ `[DONE]` 排在 `sources` **之前**不是笔误，是本端点一直以来的线上契约（前端已按此适配）。
           抽公共层**不是**顺手改行为的理由 —— 所以骨架**不替我们补 `[DONE]`**，
           整条尾巴交给本函数自己产（见 `api/sse.py` 的「②」）。
        """
        # 发送结束信号
        yield DONE_FRAME
        # ---- 在这里记录对话历史 ----
        # 生成完成后，将本轮问答自动存入 Redis
        full_answer = "".join(collected)
        append_chat_history(user_name, "user", req.question)       # 记录用户问题
        append_chat_history(user_name, "assistant", full_answer)   # 记录助手完整回答
        # 如果有引用，在结束后发送来源列表
        if req.citations and sources_list:
            yield sse_frame({"sources": sources_list}, ensure_ascii=True)

    async def _on_error(exc, collected):
        """🔴 **错误路径的旧行为：只有 error 帧、没有 `[DONE]`** —— 显式覆盖骨架的默认尾巴。

        ⚠️ 骨架的默认是"error 帧 + `[DONE]`"（= `/agent/*` 四条链的现状）。本端点**故意不要**它：
           **`[DONE]` 会被读成"正常收尾"**，而本端点今天靠"**没有** `[DONE]`"分辨出错
           ⇒ 加上它会把"出错"变得**像正常结束**。
        """
        # 兜底：其他未知错误
        print(f"流式生成出错: {exc}")
        yield sse_frame({"error": str(exc)}, ensure_ascii=True)

    return sse_response(sse_stream(
        # 🔴 上游必须是**异步**的（`③` Task 5 · `B2`）：
        #    同步 `for chunk in stream` 会**阻塞事件循环**，取消得等"下一块到达"才送得进来
        #    ⇒ 上游卡住时，最坏要等一整个 chunk 的时间才停得下来。
        lambda: get_llm_stream().astream(messages),
        endpoint=ENDPOINT,
        # ⚠️ 这是**裸 LLM**（不是图）⇒ 用 `llm_chunk_text`。空 `content` 由它一并挡掉
        #    （不过滤 ⇒ 前端收到一串空白帧）。
        extract=llm_chunk_text,
        on_complete=_complete,
        # 🔴 `③` Task 6（`B3`）：取消时把**已经生成的那半截**补存进历史（⛔ 不是直接丢）。
        #    ⚠️ 它**必须是同步的**（`append_chat_history` 是同步函数，`api/cache.py:39`）——
        #       骨架会在 `await aclose()` **之前**调它，这正是"晚切也存得下"的原因（`DEC-054`）。
        #    ⚠️ 骨架的 `logger.info` 与这里的 `print` 不冲突：前者进日志文件，后者仍在 stdout。
        on_cancel=lambda collected: _persist_interrupted_turn(user_name, req.question, collected),
        on_error=_on_error,
        # 🔴 **`ensure_ascii=True` 不是可有可无的**：本端点三帧一直用**默认的 `True`**
        #    （中文变 `\uXXXX`），而骨架的默认是 `False`（中文原样）⇒ 不显式传，**线上字节就变了**。
        #    ⚠️ 两种编码 **JSON 解码后值相同**（前端走 `JSON.parse`，功能无感）——
        #    但它会让"逐帧等价"从"字面为真"变成"差不多"⇒ 本轮保持原字节，统一与否另案裁。
        ensure_ascii=True,
        # ⚠️ 旧实现在每次 `yield` 后有 `await asyncio.sleep(0.01)` **限速** —— 本轮**不改节奏**，
        #    照旧传下去。⛔ 别因为"抽公共"就悄悄删掉它。
        chunk_delay=0.01,
    ))

# ==================== WebSocket 端点 ====================
# 模拟: 客户端发送用户问题，服务端模拟 Agent 的思考-行动-观察循环
from fastapi import WebSocket, WebSocketDisconnect
# ⚠️ 2026-09-20 删（D1/pyflakes 报 redefinition）：此处的 `import json` / `import asyncio`
#    在本文件**已被导入过两次**（文件头 + SSE 段）⇒ 删这两行。
from websocket_callback import WebSocketAgentCallback

from datetime import datetime

# ⚠️ 2026-09-17 重构 ⑥ 切开点 5：惰性单例。
#    原先下面这一整段（初始化 LLM / 定义三个工具 / 建 prompt / create_tool_calling_agent /
#    AgentExecutor）**全在模块层** ⇒ `import api_v1_rag`（进而 `import main`）
#    **在导入期就构造 LLM 与 Agent 对象**，哪怕这个进程从不打开 `/ws/agent`。
#    现整段搬进 get_agent_executor()，**首次使用时才建**，之后复用（与原先单例语义一致）。
#    ⚠️ 工具 docstring 与 prompt 文本**逐字未改** —— 那是给 LLM 看的接口。
_agent_executor = None

def get_agent_executor():
    """惰性构造 WebSocket Agent（首次调用时才建，之后复用）。"""
    global _agent_executor
    if _agent_executor is None:
        # ⚠️ 全部放在函数内：导入期不拉 langchain
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_community.tools import  DuckDuckGoSearchRun
        from langchain_core.tools import tool

        #一 初始化模型
        # ⚠️ 角色 = 「模型轴 chat」+「长度轴 answer(2000)」—— 见 `api/llm_factory.py` 的模块 docstring。
        llm = make_llm("chat", "answer")
        #二 定义工具
        @tool
        async def search(query: str) -> str:
            """搜索互联网获取实时信息。输入搜索关键词。"""
            search_tool = DuckDuckGoSearchRun()
            result = await asyncio.to_thread(search_tool.invoke, query)
            return result

        @tool
        async def calculator(expression:str) -> str:
            """计算一个数学表达式。例如3*4-5/6。输入的必须是纯数学表达式"""
            result = await asyncio.to_thread(eval, expression)
            return str(result)

        @tool
        async def date_today(query: str = "") -> str:
            """查询今天的日期、星期几。忽略查询参数。"""
            now = datetime.now()
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            weekday_str = weekdays[now.weekday()]
            # 直接在协程中返回字符串即可，这个操作不阻塞
            return f"今天是{now.year}年{now.month}月{now.day}日，星期{weekday_str}"

        tools = [calculator, date_today, search]

        # ========== 6. 创建Agent ==========
        # 这是一个专为工具调用设计的标准模板
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful assistant. Use the provided tools to answer the user's question. "
                "If a tool is needed, call it with the appropriate arguments. "
                "After receiving the tool's result, continue reasoning or give the final answer."
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])
        agent = create_tool_calling_agent(llm, tools, prompt)
        _agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    return _agent_executor

@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()

    # B8 · 会话级 token 上限（`DEC-041`）—— 本条的 key 是**每个连接**：
    # ⚠️ 本条 WS **整条没有鉴权**（`DEC-041` 遗留·1），没有用户身份 ⇒ `user_name` 只能是 `"unknown"`。
    #    ⇒ 会话 key 在这里**退化成"每连接"**：一个连接 = 一个会话，
    #      与服务端「连接即会话」的直觉一致（客户端断了重连就是新会话）。
    #    ⚠️ 正因为如此，本链的额度**是按连接算的，不是按人** —— 换连接 = 换桶。
    #       ⛔ 这不是"漏洞"，是**没有身份就谈不上按人计**；根因（WS 无鉴权）记在 DEC-041 遗留里。
    ws_session_id = f"ws-{uuid.uuid4().hex}"
    ws_user_name = "unknown"

    try:
        while True:
            data = await websocket.receive_text()
            request = json.loads(data)
            user_message = request.get("message", "")

            # B8：触顶直接拒绝 —— 用与本文件 `except` 分支**同一套帧格式**（`type` + `content`），
            # 因为 WS 没有 HTTP 状态码可抛（HTTP 端点那边才是 `AppException`）。
            ok, why = check_session_token_budget(ws_user_name, ws_session_id)
            if not ok:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": why
                }))
                await websocket.send_text(json.dumps({"type": "done"}))
                continue

            # B11 · 全站日级熔断（`①b` Task 4）—— 与上一段并列、都要过；
            # ⚠️ WS 没有 HTTP 状态码可抛，用**同一套帧格式**（同上面 B8 那里）。
            ok, why = circuit(global_key())
            if not ok:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": why
                }))
                await websocket.send_text(json.dumps({"type": "done"}))
                continue

            # 通知前端开始处理
            await websocket.send_text(json.dumps({
                "type": "thinking",
                "content": f"收到问题：{user_message}，开始分析..."
            }))
            
            # 创建回调实例
            callback = WebSocketAgentCallback(websocket)
            
            try:
                # 使用回调的 ainvoke（create_tool_calling_agent 的输入键是 "input"，输出键是 "output"）
                # 惰性取单例：首次打开 WS 时才构造 Agent
                executor = get_agent_executor()
                result = await executor.ainvoke(
                    {"input": user_message},
                    config={"callbacks": [callback]}
                )

                # 如果 on_agent_finish 没有被触发，手动发送最终结果
                final_message = result.get("output", "")
                await websocket.send_text(json.dumps({
                    "type": "final",
                    "content": final_message
                }))
                await websocket.send_text(json.dumps({"type": "done"}))
                
            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": f"Agent 执行出错：{str(e)}"
                }))
                await websocket.send_text(json.dumps({"type": "done"}))
    except WebSocketDisconnect:
        print("客户端断开连接")

# 测试 WebSocket 基础通信正常端点
@router.websocket("/ws/test")
async def test_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"收到你的消息：{data}")
    except WebSocketDisconnect:
        print("测试客户端断开")

# ==================== 测试 接口 ===================
# ==================== 模拟类 ====================
# ⚠️ 2026-10-03 **删**（`DEC-057`）：此处原有 `POST /rag/ask` —— 同步函数名 `ask_question`。
#    删的理由（三条，都可打印地核过）：
#      ① 它是 `tags=["模拟类测试"]` 的**桩**，却**读真库**（`SELECT content FROM documents …`）；
#      ② 它的 `LIMIT` **没有配套的 `ORDER BY`** ⇒ **结果不可复现**（同一问题两次可能不同）——
#         这正是本仓反复记的那种「看着像检索、其实不是」的形态；
#      ③ 能力被 `/rag/pg_search` **覆盖**（**同鉴权** `get_current_user_hybrid` · **同入参**
#         `QuestionRequest`，且多了 embedding / `ORDER BY` / 更丰富的输出），而全仓**无消费者**。
#    ⛔ **别照抄这个形状再加回来** —— `api/test_removed_endpoints.py` 会红。
#    📌 顺带消灭了它响应体里那个 **重复的 `"requested_by"` 键**（本仓一处已登记的 dead code）。
#    📄 全文（含消费者清点 · 7 处改动 · 2 处活口径同步 · 反悔成本）⇒ `docs/decisions/DEC-057-删除-rag-ask.md`

# ==================== 模拟RAG异步函数 ====================
async def async_search(query: str) -> list:
    """模拟异步检索，实际可替换为真实RAG"""
    await asyncio.sleep(2)
    return [f"异步文档A({query})", f"异步文档B({query})", f"异步文档C({query})"]

async def parallel_search(queries: list[str]) -> list:
    tasks = [async_search(q) for q in queries]
    return await asyncio.gather(*tasks)

# 异步检索（模拟，无需API Key）
@router.post(
    "/rag/async_ask",
    summary="异步检索（模拟，无需API Key）",
    tags=["模拟类测试"]
)
async def async_ask_question(req: QuestionRequest):
    start = time.time()
    docs = await async_search(req.question)
    duration = time.time() - start
    return {
        "question": req.question,
        "docs": docs,
        "elapsed": f"{duration:.3f}秒",
        "mode": "异步"
    }

# 并行检索（模拟）
@router.post(
    "/rag/parallel_ask",
    summary="并行检索（模拟）",
    tags=["模拟类测试"]
)
async def parallel_ask_question(req: QuestionRequest):
    start = time.time()
    results = await parallel_search([req.question, f"相关：{req.question}"])
    duration = time.time() - start
    return {
        "question": req.question,
        "results": results,
        "elapsed": f"{duration:.3f}秒",
        "mode": "并行异步"
    }