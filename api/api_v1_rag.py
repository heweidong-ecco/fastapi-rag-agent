"""
API v1 路由集中定义
所有 /api/v1 前缀的接口在此管理。
"""
import json
# ⚠️ 2026-10-04 删 `import time`（`DEC-065`）：本文件**只有** `/rag/async_ask` 与
#    `/rag/parallel_ask` 用 `time.time()`，两条端点已删（全仓已核，见 `grep -n '\btime\b'`）。
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Path, Query

# ①b Task 5：LLM 的唯一构造落点（`model` / `api_key` / `base_url` / `max_tokens` 都收在那一处）。
# ⚠️ `llm_factory` 模块级只 import `os`（langchain 是在 `make_llm()` **函数内**才 import）
# ⇒ 放文件头**不破坏**本文件「导入期不拉 langchain」的既有做法（原 `MAX_TOKENS_ANSWER` 同理）。
from llm_factory import make_llm
from exceptions import ErrorCode, AppException
# B8 接线（①b Task 2）：会话级 token 上限。
# ⚠️ `token_tracker` 模块级只 import `os/json/threading` 等标准库 + `token_config`
#    （`db` / `langchain` 都是**函数内**惰性导入）⇒ 放文件头**不破坏**本文件
#    「导入期不拉 langchain」的既有做法（与上面 `MAX_TOKENS_ANSWER` 同一条理由）。
from token_tracker import check_session_token_budget, record_from_response, usage_summary
# B11（①b Task 4）：全站日级熔断。与 B8 并列，⛔ 别合并（B8 按会话 / B11 按全站）。
# ⚠️ breaker 只在**函数内**惰性导入 token_tracker ⇒ 放文件头不破坏本文件
#    「导入期不拉重依赖」的既有做法（同上面 `token_tracker` 那条注释的道理）。
from breaker import circuit, global_key
from schemas import (
    QuestionRequest,
    DocumentInsert,
    BatchDocumentInsert,
)
# ⚠️ 2026-10-04 删 `get_current_user_jwt`（`DEC-064`）：它在本文件**只有** `jwt_ask_question` 一处用，
#    随该端点一起删 ⇒ 留着就是没人用的 import。
# ⚠️ `require_admin` 原先挂在这里、**本文件从未用过**（`T6` 的「先挂起」那批）。
#    2026-10-07 清存量时**已删** —— 同批删掉的还有：`JSONResponse` · `ACCESS_TOKEN_EXPIRE_MINUTES` ·
#    `LoginRequest`/`RefreshRequest`/`UserCreate` · `insert_batch_documents` · `get_weather` ·
#    `append_chat_history`/`INTERRUPTED_SUFFIX` · `agent_graph`。⛔ **没删任何模块**，只删导入行。
from deps import get_current_user_hybrid
# `DEC-075`：WebSocket 的首帧认证依赖 —— ⛔ 它与上面那两个**不能互换**（浏览器 WS
# 不能自定义请求头，`X-API-Key` / `Authorization` 送不上来）。
from deps import require_ws_user
from db import get_db, insert_document
from db import search_similar  # 🔴 2026-10-03 乙段（DEC-056）：stream_search 改走共享层
from embedding_client import get_embedding

from permission import get_user_role, UserRole  # ⚠️ 2026-10-03 删 `get_user_quota`（本文件从未使用；该函数已随 DEC-046 一起删）
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

# 🔴 `INTERRUPTED_SUFFIX` 看着"没用"，但**必须留** —— 它是不是死导入，`ruff` 判不了：
#    `api/test_cancel_propagation.py` **6 处**写作 `rag_mod.INTERRUPTED_SUFFIX`（**属性访问**，
#    ⛔ 不是 `from ... import`）。2026-10-07 清存量时**删过一次**，那 6 条用例当场全红
#    （`AttributeError: module 'api_v1_rag' has no attribute 'INTERRUPTED_SUFFIX'`）⇒ 已还原。
#    ⛔ **这就是"F401 不等于死导入"的实例**：ruff 只看本文件的名字，看不见**别人按属性取**。
#    📌 下面 import 行行尾那条 `noqa` 指令（`F401`）是**收尾动作**（2026-10-07，与本批清存量
#       同一刀，⚠️ 注释里⛔不写那个井号，写了 ruff 会把它当成一条坏 noqa 指令打警告）：存量清零后
#       基线空了，本来可以把它留成基线的一条；**⛔ 没有那样做** —— 基线的键是 `(文件, 规则)`，
#       挂一条 = 把 `api/api_v1_rag.py` **所有** F401 一律放行（将来真加了死导入也不报）。
#       行尾 `noqa` 只放行**这一行**，且理由写在行边上。同理见 `api/agent_checkpointer.py:31`。
from cache import get_chat_history, persist_turn, INTERRUPTED_SUFFIX  # noqa: F401


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
    # 🔴 `DEC-085` 裁定 #12：空串挡在**进端点之前**（422）—— ⛔ 否则它会一路走到
    #    `session_key()` 的 `ValueError`，而那时**流已经开了一半**，只能变成 500。
    thread_id: str = Query("default", min_length=1),   # 🔴 2026-10-05 加（B8 需要会话维度）
    user_name: str = Depends(get_current_user_hybrid),
):
    """带查询改写的混合检索（**只在该用户自己的文档内**）"""
    # 🔴🔴 2026-10-05（`DEC-073`）：本端点**此前零闸** —— 而它**无条件**真调 LLM
    #     （`hybrid_search_with_rewrite` 里改写 + 扩展各一次）⇒
    #     ① 单条请求**无上限** ② B8 会话上限 / B11 全站熔断读的计数器它从不写 ⇒ 对它等于不存在。
    #     ⚠️ **两道都要**，与 `/rag/stream_search` 的现状并列（B8 按会话 / B11 按全站，⛔ 别合并）。
    ok, why = check_session_token_budget(user_name, thread_id)   # B8
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    ok, why = circuit(global_key())                              # B11
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

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
    # 🔴 `DEC-085` 裁定 #12：空串挡在**进端点之前**（422）—— ⛔ 否则它会一路走到
    #    `session_key()` 的 `ValueError`，而那时**流已经开了一半**，只能变成 500。
    thread_id: str = Query("default", min_length=1),   # 🔴 2026-10-05 加（B8 需要会话维度）
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
    # 🔴🔴 2026-10-05（`DEC-073`）：本端点**此前零闸** —— 而默认 mode `accurate_norerank`
    #     **本身就开着改写**（真调 LLM）⇒ 单条请求无上限、账本也收不到数据。
    #     ⚠️ 位置在 `PIPELINE_FACTORIES[mode]()` **之前** —— 那是本端点第一处真花钱的地方之前。
    #     ⚠️ **两道都要**（B8 按会话 / B11 按全站），同 `/rag/stream_search` 的现状。
    ok, why = check_session_token_budget(user_name, thread_id)   # B8
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    ok, why = circuit(global_key())                              # B11
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

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


# ==================== 【已删除】POST /rag/jwt_ask ====================
# 🔴 2026-10-04 **删除**（`DEC-064`）—— 端点 `jwt_ask_question` 已移除。三条理由（都可打印地核过）：
#
#   ① **拿到 `question` 却不拿它做检索** —— 无 embedding、无 `ORDER BY`，只是
#      `SELECT content … LIMIT n`。**`LIMIT` 配不上 `ORDER BY`** ⇒ 取哪几行由物理顺序决定
#      ⇒ **同一问题两次可能拿到不同的行**（"看着像检索、其实不是"—— 本仓反复记的那个形态）。
#   ② **能力被 `/rag/pg_search` 覆盖，而且是更严的覆盖** —— 它用 `get_current_user_jwt`，
#      **只收 JWT、不收 API Key**；而 `pg_search` 用 `get_current_user_hybrid`，
#      **JWT 与 API Key 都收** ⇒ 是它的**超集**。
#      ⚠️ **最容易读反的一点**：「只收 JWT」看着像独有能力，其实是**限制** ——
#      ⇒ **删掉它，JWT 用户一个能力都没少**。
#   ③ **全仓无消费者**（清点，⛔ 不是"试了没反应"）—— 无前端 · 测试里只有「**钉它不该被接上限**」
#      的反向守卫（不是"在用"）· Postman 集合里 1 个文件夹。
#
# ⚠️ **它【不欠】隔离账** —— 2026-10-03 乙段已补 `WHERE requested_by`（`DEC-056` §1.2 第 7 条）。
#    ⇒ 删它的理由**全部与隔离无关**，⛔ 别把本段读成隔离收口的一部分（同 `DEC-057` §二）。
#
# ⛔ **别照抄这个形状再把端点加回来** —— `api/test_removed_endpoints.py::test_rag_jwt_ask_stays_removed`
#    会红（判据是 **404**，⛔ 不是"不是 200"：它删之前带鉴权，回的就是 **401**）。
# 📄 全文（消费者清点 · 改动清单 · 反悔成本）⇒ `docs/decisions/DEC-064-删除-rag-jwt-ask.md`

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


class _StreamUsageTap:
    """把「发帧」与「记账」分开：`extract` 逐块累积，`record` 在收尾时落一笔账。

    ## 🔴 为什么必须是它，⛔ 不能靠骨架

    `sse.sse_stream` 只把**通过 `text` 过滤的块**攒进 `collected` ——
    而本仓 provider 把 `usage_metadata` 挂在**最后一帧、且那帧 `content=''`** 上
    （实测 ⇒ `fastapi-rag-agent-TODO待办/探针-流式与记账.py` §结论 1/2）
    ⇒ 它**必然**被 `llm_chunk_text`（`return chunk.content or None`）滤掉。
    ⇒ 累积必须发生在**过滤之前**。骨架里唯一看到**每一块**的钩子就是 `extract`
      （`sse.py`：`text = extract(item) if extract is not None else item` 排在
      `if not text: continue` **之前**）。

    ⚠️ **所以这里的 `extract` 有副作用**（既发帧、又攒账）。这是**有意的**：
       两个动作的输入是**同一串块**；分两处遍历 = 要么重复读流，要么漏掉空 content 那帧。

    ⚠️ ⛔ **别把 `content` 过滤搬进来** —— 那一帧正是 usage 的载体。
       守卫 ⇒ `api/test_rag_billing_wiring.py::test_stream_search_bills_the_usage_frame_that_has_no_text`
    """

    __slots__ = ("_agg",)

    def __init__(self):
        self._agg = None          # 聚合块（`AIMessageChunk.__add__`）

    def extract(self, chunk):
        """喂给 `sse_stream` 的 `extract`：**累积所有块**，返回该发的文本（沿用旧口径）。"""
        # ⚠️ 对【所有】块做 `+`，⛔ 不跳空 content（`plan_execute.py:202-205` 同款写法）
        self._agg = chunk if self._agg is None else self._agg + chunk
        return llm_chunk_text(chunk)

    def record(self, llm, *, user_name, thread_id):
        """收尾（**只在这条出口**）时调用：先记账，**成了才返回帧载荷**。

        🔴 `DEC-085` 契约 B：返回的是 `usage` 帧的载荷（`dict`），⛔ 不再是 `bool`。
           判据只有一条 —— **记账了才出帧、没记账就不出帧**（两者同源）。
           载荷由 `token_tracker.usage_summary` 拼，⛔ **不在这里重算一遍模型名与钱**
           （那会造出第二份取数口径，`DEC-072` 的代价就是从那儿来的）。

        ⚠️ 它**只在正常跑完**那条路被调 —— 取消 / 异常时带 usage 的那一帧根本没到
           ⇒ 如实不记、也不出帧，⛔ **不编一个数进账本**（`DEC-053` §遗留·2）。
        """
        if self._agg is None:
            return None
        if not record_from_response(
            llm, self._agg, "answer_generation",
            user_name=user_name, thread_id=thread_id,
        ):
            return None
        return usage_summary(llm, self._agg)


# 🔴 2026-10-04（`DEC-055`）：`INTERRUPTED_SUFFIX` 与 `_persist_interrupted_turn` **搬去
#    `api/cache.py`** —— 6 条流式端点现在共用同一段留痕（`persist_turn`），
#    本文件只**再导出**这个名字（`api/test_cancel_propagation.py` 按 `rag_mod.INTERRUPTED_SUFFIX` 取它）。
#    ⚠️ 搬家的理由不是"整理"：只有一份实现，`DEC-055` 那三条规则（成对写 / 空答案不写 / 非 done 带尾巴）
#       才不会在 6 处各写一遍、各漏一条。


# 🔴 `F4` ①（`DEC-091`）：无据拒答的那句话**只说一次**，下面**两处共用** ——
#    ① `citations` 分支的 system prompt（「请**直接说**…」）；
#    ② 收尾时判定「这一轮算不算拒答」。
#    ⚠️ 非抽常量不可的理由：这两处**必须一致**，而它们分家的表现是**静默的** ——
#       prompt 里换了措辞 ⇒ 判据认不出来 ⇒ `no_answer` 帧永远不发 ⇒
#       页面上只是一句普通回答，**没有任何报错**（本仓「两处各写一遍 ⇒ 静默漂移」那一族）。
# ⚠️ 判据是「**以它开头**」，⛔ 不是"含"：2026-10-06 spike 实测 **8/8** 模型都把它放在**开头**
#    （与 prompt 里那句「请**直接说**」相符）。**误判比漏判有害**（把答得好的那轮画成"资料里没有"）
#    ⇒ 宁可严。代价写实：换过措辞的拒答（如「文档未提及净利润，因此无法回答该问题。」）会被漏掉，
#    那只是**退化成今天的样子**，⛔ 不会更糟。取舍全文 ⇒ `docs/decisions/DEC-091`。
REFUSAL_SENTENCE = "根据现有资料，无法回答"


@router.post("/rag/stream_search")
async def stream_search(
    req: QuestionRequest,
    # 🔴 `DEC-085` 裁定 #12：空串挡在**进端点之前**（422）—— ⛔ 否则它会一路走到
    #    `session_key()` 的 `ValueError`，而那时**流已经开了一半**，只能变成 500。
    thread_id: str = Query("default", min_length=1),   # ⚠️ B8 补：本端点原先**没有** thread_id
    user_name: str = Depends(get_current_user_hybrid),
):
    """流式RAG问答接口（融合优化版）（支持引用溯源和历史补偿）。
    使用SSE逐字返回生成的答案，提供类似ChatGPT的体验。

    ⚠️ 2026-09-20 修：这段 docstring 原先**躺在两句代码之后**（函数体第三句），
       是**空操作** —— 函数本身**没有 docstring**。已上移到签名正下方。
    """
    # 0. 若前端未主动传历史，则从 Redis 加载该用户最近5轮对话
    if not req.conversation_history:
        req.conversation_history = get_chat_history(user_name, thread_id=thread_id)

    # B8 · 会话级 token 上限（`DEC-041`）—— 触顶直接拒绝。
    # ⚠️ 放在**取历史之后、检索之前**：这是本端点**第一处真花钱**的位置之前。
    # 🔴 `scope="session"`（`DEC-090` · `R3.2`）：两种熔断 `code` 相同 ⇒ 必须显式标出
    #    是哪种，否则前端写不出「何时恢复」（会话级**开个新会话立刻能继续**）。
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why, scope="session")

    # B11 · 全站日级熔断（`①b` Task 4）—— 与上一段并列、都要过。
    # 🔴 `scope="global"`：全站共享 ⇒ 用户**做什么都救不回来**，只能等跨天。
    #    ⛔ 与上面那句**不是一回事**，别合并。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why, scope="global")
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
                # 🔴 `DEC-085` 契约 A：`index` 与上一行的 `[文档{i}]` **必须来自同一个 `i`**。
                #    ⛔ 别在别处再算一次编号 —— 两处各写一遍 ⇒ 静默错位
                #    （点开的是对的文档、内容是错的那篇），而没有任何报错。
                "index": i,
                "id": doc.get("id"),
                "source": doc.get("source", "未知"),
                # 🔴 `DEC-085` 契约 A：`content` 是**全文**，给"点开引用"看。
                #    `content_preview` 仍在（老前端用它）—— ⛔ 不是替换，是追加。
                "content": doc["content"],
                "content_preview": doc["content"][:100],
                # 🔴 `DEC-089`：硬门 B 的证真那句要求「点开能看到 **chunk id + 相似度分**」。
                #    这个数**本来就在手上**（上面 `contexts` 里的 `r[3]`）—— 只是没人往帧里放。
                # ⚠️ **两个出口**（本处 + `answer_with_citations.py`）必须保持同形，
                #    有 `test_both_sources_exits_have_the_same_key_set` 钉着。
                "similarity": doc.get("similarity"),
            })
        context_text = "\n\n".join(context_parts)

        system_prompt = f"""你是一个严谨的问答助手。请严格根据以下上下文回答用户的问题。

**引用规则（必须遵守）：**
1. 当你使用上下文中的某条信息时，必须在句末标注来源编号，格式为 `[来源:X]`，其中 X 是文档编号。
2. 如果一句话使用了多个来源，标注为 `[来源:X, Y]`。
3. 不要编造任何上下文以外的信息。如果上下文不足以回答问题，请直接说“{REFUSAL_SENTENCE}”。

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
    tap = _StreamUsageTap()           # 🔴 `DEC-084`：流式答案的记账（见类 docstring）

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
        # 🔴 2026-10-06（`DEC-084`）：记账排在【任何 `yield` 之前】（`sse.py` 约束① 同源）——
        #    `yield` 是 await 点，被"二次投递的取消"打断 ⇒ 排在它后面的收尾**一件都不跑**，
        #    可钱**已经花了**。⚠️ `persist_turn` 仍留在原位（那是 `DEC-055` 定的，⛔ 本轮不动它）。
        # 🔴 `DEC-085` 契约 B：`record` 现在**返回载荷**（`None` = 没记成）。
        payload = tap.record(get_llm_stream(), user_name=user_name, thread_id=thread_id)
        # 发送结束信号
        yield DONE_FRAME
        # 🔴 `F4` ①（`DEC-091`）：**这一轮算不算"无据拒答"** —— 让"拒答了"成为一个
        #    **机器可读的字段**，⛔ 不是让前端去读正文猜。判据与 prompt 那句**共用同一个常量**
        #    （`REFUSAL_SENTENCE`，理由见它的注释）。
        # ⚠️ 位置：`[DONE]` 之后、`sources` **之前** —— 它描述的是**刚结束的那段答案**，
        #    而 `sources` 那一趟前端会重画；标志先到，那一趟才能**一次画对**。
        #    ⛔ 别挪到 `usage` 后面（前端得多收一帧才敢下判断，白多一次重画）。
        # ⚠️ 它**只说"这轮拒答了"**，⛔ 不把提示文案塞进帧里 —— 文案属于呈现层，
        #    塞进帧就变成又一份要两边同步的契约（`api/static/js/sse.js` 的 `refusalNotice`）。
        if "".join(collected).lstrip().startswith(REFUSAL_SENTENCE):
            yield sse_frame({"no_answer": True}, ensure_ascii=True)
        # ---- 在这里记录对话历史 ----
        # 生成完成后，将本轮问答自动存入 Redis
        # 🔴 `DEC-055`：三条出口（`done` / `cancelled` / `error`）**共用 `persist_turn`**
        #    ⇒ `status` 这个区分只有一份实现，⛔ 不是在这里手写一遍 `append_chat_history`。
        #    ⚠️ `done` 的字节与改前**逐字相同**（答案原样，⛔ 不 strip、⛔ 不带标记）。
        #    ⚠️ **唯一的行为变化**：空答案 ⇒ **连提问也不写**（旧代码会写下孤零零的提问）。
        persist_turn(user_name, req.question, "".join(collected), thread_id=thread_id, status="done")
        # 如果有引用，在结束后发送来源列表
        if req.citations and sources_list:
            yield sse_frame({"sources": sources_list}, ensure_ascii=True)
        # 🔴 `DEC-085` 契约 B：本轮的 token / 费用 —— **纯追加的最后一帧**。
        #    ⛔ 不许挪到 `[DONE]` 之前（那是线上契约，前端按"见 [DONE] 后才收 sources/usage"适配）。
        #    ⚠️ 取消 / 出错时**没有**这一帧 —— 前端按"缺这一帧"处理，⛔ 别补一个 0。
        if payload is not None:
            yield sse_frame({"usage": payload}, ensure_ascii=True)

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
        # ⚠️ 这是**裸 LLM**（不是图）⇒ 旧口径用 `llm_chunk_text`。空 `content` 由它一并挡掉
        #    （不过滤 ⇒ 前端收到一串空白帧）。
        # 🔴 `DEC-084`：现在传 `tap.extract` —— 它**返回的仍是 `llm_chunk_text(chunk)`**（发帧口径不变），
        #    只是**顺手把每一块 `+` 进聚合**（usage 挂在最后一帧、而那帧 `content=''` ⇒ 见类的 docstring）。
        extract=tap.extract,
        on_complete=_complete,
        # 🔴 `DEC-055`：**取消与异常两条出口**都把**已经生成的那半截**补存进历史（⛔ 不是直接丢）。
        #    ⚠️ 它**必须是同步的**（`persist_turn` 走同步的 `append_chat_history`）——
        #       骨架会在 `await aclose()` **之前**调它，这正是"晚切也存得下"的原因（`DEC-054`）。
        #    ⚠️ 骨架的 `logger.info` 与 `_on_error` 里的 `print` 不冲突：前者进日志文件，后者仍在 stdout。
        on_incomplete=lambda collected, status: persist_turn(
            user_name, req.question, "".join(collected), thread_id=thread_id, status=status,
        ),
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

# 🔴 2026-10-08（批① Task 4）：`from datetime import datetime` **删了** ——
#    它**只**服务于 `get_agent_executor()` 里那个自带的 `date_today`（已删，改为共享工具）。

# ⚠️ 2026-09-17 重构 ⑥ 切开点 5：惰性单例。
#    原先下面这一整段（初始化 LLM / 定义三个工具 / 建 prompt / create_tool_calling_agent /
#    AgentExecutor）**全在模块层** ⇒ `import api_v1_rag`（进而 `import main`）
#    **在导入期就构造 LLM 与 Agent 对象**，哪怕这个进程从不打开 `/ws/agent`。
#    现整段搬进 get_agent_executor()，**首次使用时才建**，之后复用（与原先单例语义一致）。
#    ⚠️ 工具 docstring 与 prompt 文本**逐字未改** —— 那是给 LLM 看的接口。
_agent_executor = None
# `DEC-075`：与 `_agent_executor` **同一个单例里**的 LLM —— 记账要用它的 `model_name`。
# ⛔ 别让记账去猜模型名（`DEC-072`：本仓因写死 `"qwen-turbo"` 按错的单价记过账）。
_agent_llm = None

def get_agent_executor():
    """惰性构造 WebSocket Agent（首次调用时才建，之后复用）。"""
    global _agent_executor, _agent_llm
    if _agent_executor is None:
        # ⚠️ 全部放在函数内：导入期不拉 langchain
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_core.prompts import ChatPromptTemplate
        # 🔴 2026-10-08 收口（批① Task 4）：**实现**改为调**共享工具**，**外壳保持 async**。
        #
        #    🔴 **为什么不能直接把这三个换成 `mcp_server` 那份**：原文是 `async def`，且
        #       `return await asyncio.to_thread(...)` —— **有意把阻塞丢出事件循环**。
        #       `mcp_server` 那份是**同步**的 ⇒ 直接替换会**在事件循环里同步跑 20 秒的网络调用**。
        #       ⇒ 保留 async 外壳，只把**实现**与**工具描述**指向共享工具（那才是本 task 的目的）。
        #    ⚠️ **【工具 schema 变更】**：工具名由 `search` 改为 `web_search`
        #       （= 注册表里的真名，与 `SENSITIVE_TOOLS` 默认值一致）；`calculator` /
        #       `date_today` 的 **docstring 也换成共享那份**（更详细）。
        #
        #一 初始化模型
        # ⚠️ 角色 = 「模型轴 chat」+「长度轴 answer(2000)」—— 见 `api/llm_factory.py` 的模块 docstring。
        llm = make_llm("chat", "answer")
        _agent_llm = llm
        #二 定义工具
        from langchain_core.tools import StructuredTool
        from mcp_server import TOOLS as _MCP_TOOLS

        _src = {t["func"].name: t["func"] for t in _MCP_TOOLS}

        def _async_shell(src):
            """把**同步**工具包成 async 壳：`to_thread` 把它丢出事件循环。

            ⚠️ `name` / `description` / `args_schema` **全部取自共享工具** ——
               这样"给 LLM 的工具描述"也只有一处事实源（本 task 的目的）。
            """
            async def _call(**kwargs):
                return await asyncio.to_thread(src.invoke, kwargs)

            return StructuredTool.from_function(
                coroutine=_call,
                name=src.name,
                description=src.description,
                args_schema=src.args_schema,
            )

        # 🔴 `eval` 那条没丢（`DEC-049` / `DEC-066`）：`calculator` 的实现仍在
        #    `api/safe_math.py`，三道闸与守卫在 `api/test_safe_math_wiring.py`。
        #    📌 这里**曾经是本仓第 6 份 `calculator` 拷贝**，且写的是
        #       `asyncio.to_thread(eval, expression)`（`eval` 是**实参**）⇒ 旧判据
        #       （只认「`ast.Call` 的 func 是裸名 `eval`」）**两道守卫都看不见它**，
        #       而**命令真的跑了**（实测返回值 `'0'`）。⇒ `DEC-066` 已修那两条判据。
        search = _async_shell(_src["web_search"])
        calculator = _async_shell(_src["calculator"])
        date_today = _async_shell(_src["date_today"])

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


def get_agent_llm():
    """取与 `get_agent_executor()` **同一个单例**里的 LLM（记账要用它的 `model_name`）。"""
    get_agent_executor()
    return _agent_llm


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket, ws_user_name: str = Depends(require_ws_user)):
    # ⛔ **不要在这里 `await websocket.accept()`** —— `require_ws_user` 已经 accept 过了，
    #    而星型 1.6.0 的 `accept()` **不幂等**（第二次会 RuntimeError，实测）。
    #
    # 🔴 **身份来自上面那个依赖**（`DEC-075`）—— 本条 WS 此前**整条没有鉴权**
    #    （`DEC-041` 遗留·1）：真花钱（LangChain Agent + chat LLM + `web_search`）
    #    却匿名可达。端点体要**认证通过之后**才会被执行 —— 判据见
    #    `api/test_ws_auth.py::test_ws_agent_body_never_runs_before_auth`。
    #
    # B8 · 会话级 token 上限（`DEC-041`）—— key = `(user_name, thread_id)`。
    # ⚠️ `thread_id` 这里**仍是每连接一个**（`ws-<uuid>`）：WS 没有客户端传上来的会话 id
    #    ⇒ 重连接 = 新桶。**这是已知的、有意留下的口子**，见 `DEC-075` 遗留·2
    #    （全局日级熔断 B11 仍然罩着，故不因它而失控）。
    ws_session_id = f"ws-{uuid.uuid4().hex}"

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
            
            try:
                # 使用回调的 ainvoke（create_tool_calling_agent 的输入键是 "input"，输出键是 "output"）
                # 惰性取单例：首次打开 WS 时才构造 Agent
                executor = get_agent_executor()
                # 🔴 创建回调实例 —— **必须带身份**（`DEC-075`）：
                #    它现在**同时负责记账**（`on_llm_end`），而账要记到**认证出来的那个人**头上。
                #    ⛔ 三个都是必填 keyword：漏传 = `TypeError`（响亮），⛔ 不是静默记成 `"unknown"`。
                callback = WebSocketAgentCallback(
                    websocket,
                    user_name=ws_user_name,
                    thread_id=ws_session_id,
                    llm=get_agent_llm(),
                )
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

# ⚰️ 2026-10-05 **删**（`DEC-075` §十）：此处原有 **WS `/ws/test`** ——
#    一个纯回声的「WebSocket 基础通信」桩，`ecb146b`（首次提交）起就在。
#    ⚠️ **本墓碑刻意不写那串装饰器字面量**（写成 `WS /ws/test`）——
#       本文件下面 `DEC-057` 那条墓碑也是这么写的。理由：本仓判据 `grep -c '@router\.' api/api_v1_rag.py`
#       是**数路由**用的，注释里留同款字面串会让它**多数一条**（`DEC-065` 实测过：带 ⇒ 14，去掉 ⇒ 12）。
#    删的理由（三条，与 `DEC-065` 删那 4 条**同一套标准**，⛔ 不是另立一套）：
#      ① **消费者 = 0** —— 本仓没有任何东西连它（`api/static/websocket_test.html` 连的是
#         `/api/v1/ws/agent`）；`git log -S 'ws/test' -- 'api/test_*.py'` 在 `DEC-074` 之前
#         **零命中**；仓外（`agent-eval-gate` 等 5 个项目）也全 0。
#      ② **它本来就是「测试桩」** —— `DEC-055` 的流式出口普查表里就是这么记的。
#      ③ **连「探活」这个唯一可能的用途也没了** —— `DEC-075` 给它补上首帧认证之后，
#         它自己也要凭据 ⇒ 留着的唯一理由（免鉴权的 WS 探活口子）已经不成立。
#    ⚠️ 这是**删除**，⛔ 不是「先隐起来」：`DEC-065` 那批也是直接删。
#    ⛔ **别改回来** —— `api/test_removed_endpoints.py::test_ws_test_stays_removed` 会红。

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

# ============ 【已删除】POST /rag/async_ask · POST /rag/parallel_ask ============
# 🔴 2026-10-04 **删除**（`DEC-065`）—— 连同它们**专用的**两个 helper
#    `async_search()` / `parallel_search()` 一并移除（全仓**只有这两条端点**在调它们）。
#
# 原先它们是：
#     async def async_search(query):  await asyncio.sleep(2); return ["异步文档A(…)", …]
#     async def parallel_search(qs):  return await asyncio.gather(*[async_search(q) for q in qs])
#     router.post("/rag/async_ask",    tags=["模拟类测试"])  →  async def async_ask_question(req)
#     router.post("/rag/parallel_ask", tags=["模拟类测试"])  →  async def parallel_ask_question(req)
#     ⚠️ 上面两行**故意去掉 `@`** —— 本仓数路由的判据是 `grep -c '@router\.'`，
#        留着 `@` 会让【墓碑注释】也被数进去（判据纪律 #2：注释里也有同样的串）。
#        实测：带 `@` ⇒ 14（错，多算 2）；不带 ⇒ **12**（对）。
#
# 为什么删：
#   🔴 **纯 mock** —— 库里没有、embedding 没有、LLM 没有，只是 `asyncio.sleep(2)` 之后
#      返回硬编码字符串 `["异步文档A({query})", …]`。**消费者 = 0**（仓内无前端 ·
#      无测试引用 · 只有 Postman 2 个文件夹，已删）。
#   ⇒ ⚠️ 这两条一删，`tags=["模拟类测试"]` **整组归零**：
#      `/rag/ask` 2026-10-03 删（`DEC-057`）· `/rag/jwt_ask` 2026-10-04 删（`DEC-064`）。
#      **那组四条走完，模式完全一样：先没人用，再删。**
#
# ⚠️ **顺带收掉 `import time`**（文件头第 6 行）：本文件**只有**这两条端点用 `time.time()`
#    （全仓已核：`grep -n '\btime\b' api/api_v1_rag.py` 只命中 `import` 与这两处）。
#    ⛔ `import asyncio` **留着** —— `:794` `:800` 的 `asyncio.to_thread` 还在用。
#
# ⛔ **别照抄这个形状再把端点加回来** ——
#    `api/test_removed_endpoints.py::test_rag_async_ask_stays_removed` /
#    `::test_rag_parallel_ask_stays_removed` 会红。
# 🔴 **若真要再加一条「不花钱、不查库」的端点**，必须**同时**做一件事：
#    **重建一份反向接线守卫**（原先是 `test_breaker_wiring.py` 与
#    `test_session_budget_wiring.py` 里那两张豁免清单）—— ⚠️ 那两张清单**随本次删除已空，
#    空清单 = `for` 体一次都不跑 = 恒绿假通过 ⇒ 两段守卫**已删**。详见 `DEC-065`。
# ==============================================================================
