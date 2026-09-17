"""
API v1 路由集中定义
所有 /api/v1 前缀的接口在此管理。
"""
import json
import time
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse, JSONResponse

from config import ACCESS_TOKEN_EXPIRE_MINUTES
from exceptions import ErrorCode, AppException
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
from embedding_client import get_embedding

from permission import get_user_role, get_user_quota, UserRole
from tools_with_cache import get_weather, calculator
from db import invalidate_bm25_cache
from hybrid_search import hybrid_search
from hybrid_search import rerank_search
from hybrid_search import hybrid_search_with_rewrite
from rag_pipeline import create_fast_pipeline, create_accurate_pipeline, create_full_pipeline
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
    """上传并解析多格式文档（PDF/Word/Markdown/HTML）"""
    """上传并解析多格式文档，经过预处理后入库"""
    # 检查文件格式
    allowed_extensions = ["pdf", "docx", "md", "html"]
    ext = file.filename.lower().split(".")[-1]
    if ext not in allowed_extensions:
        raise AppException(
            ErrorCode.PARAM_INVALID,
            f"不支持的文件格式: {ext}，支持: {', '.join(allowed_extensions)}"
        )
    
    # 保存临时文件
    import tempfile
    import os
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
    """混合检索：向量 + BM25 关键词"""
    docs = hybrid_search(req.question, req.top_k)
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
    """带重排序的混合检索"""
    docs = rerank_search(req.question, req.top_k)
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
    """带查询改写的混合检索"""
    docs = hybrid_search_with_rewrite(req.question, req.top_k)
    return {
        "question": req.question,
        "method": "query rewrite + hybrid search + RRF",
        "docs": docs,
        "requested_by": user_name,
    }

# 添加综合检索接口 RAGPipeline
from rag_pipeline import create_fast_pipeline, create_accurate_pipeline, create_accurate_norerank_pipeline,create_full_pipeline

@router.post("/rag/search")
async def unified_search(
    req: QuestionRequest,
    mode: str = "accurate_norerank",  # 可选: "fast", "accurate","accurate_norerank" "full"
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    综合检索入口，支持多种模式切换，返回各阶段耗时统计。

    **模式说明：**
    - **fast**：仅 BM25 + 向量检索 + RRF 融合，速度最快。
    - **accurate**：增加查询改写和 Cross-Encoder 重排序，精度最高。
    - **full**：在 accurate 基础上增加查询扩展，覆盖最全。
    """
    # 根据 mode 选择管线
    if mode == "fast":
        pipeline = create_fast_pipeline()
    elif mode == "full":
        pipeline = create_full_pipeline()
    elif mode == "accurate":
        pipeline = create_accurate_pipeline()
    else:
        pipeline = create_accurate_norerank_pipeline()

    # 执行检索
    result = await pipeline.search_async(
        req.question,
        top_k=req.top_k,
        conversation_history=req.conversation_history,  # 传递历史
        generate_answer=req.generate_answer,
        strict_mode=req.strict_mode,
        citations=req.citations,
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
            cur.execute("SELECT content FROM documents LIMIT %s", (req.top_k,))
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
from fastapi.responses import StreamingResponse
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_CHAT
import asyncio
import json

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
        from langchain_openai import ChatOpenAI  # 惰性导入：放在函数内，导入期不拉 langchain
        _llm_stream = ChatOpenAI(
            model=LLM_MODEL_CHAT,
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            temperature=0.3,
            streaming=True  # 关键：开启流式模式
        )
    return _llm_stream

@router.post("/rag/stream_search")
async def stream_search(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_hybrid),
):
    # 1. 若前端未主动传历史，则从 Redis 加载该用户最近5轮对话
    if not req.conversation_history:
        req.conversation_history = get_chat_history(user_name)
    """
    流式RAG问答接口（融合优化版）（支持引用溯源和历史补偿）。
    使用SSE逐字返回生成的答案，提供类似ChatGPT的体验。
    """
    # 1. 检索（与普通接口相同）
    # 1. 向量检索（这部分不是流式的，一次性查完）
    # 构建当前输入的这条的历史对话，真停止按钮的调用（使它支持历史补偿）
    query_embedding = get_embedding(req.question)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, content, source, 1 - (embedding <=> %s::vector) AS similarity
                FROM documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (query_embedding, query_embedding, req.top_k))
            results = cur.fetchall()
    
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
    async def generate():
        collected_parts = []          # 用于拼凑完整回答
        try:
            # 调用流式LLM
            stream = get_llm_stream().stream(messages)
            for chunk in stream:
                if chunk.content:
                    collected_parts.append(chunk.content)
                    # SSE格式：data: 内容\n\n 直接发送纯文本，前端逐字显示
                    yield f"data: {json.dumps({'content': chunk.content})}\n\n"
                    # 关键：让出控制权，不做任何阻塞性等待
                    await asyncio.sleep(0.01)  # 小延迟，让前端能平滑渲染
            
            # 发送结束信号
            yield "data: [DONE]\n\n"
            # ---- 在这里记录对话历史 ----
            # 生成完成后，将本轮问答自动存入 Redis
            full_answer = "".join(collected_parts)
            # 记录用户问题
            append_chat_history(user_name, "user", req.question)
            # 记录助手完整回答
            append_chat_history(user_name, "assistant", full_answer)
            # 如果有引用，在结束后发送来源列表
            if req.citations and sources_list:
                yield f"data: {json.dumps({'sources': sources_list})}\n\n"
        except asyncio.CancelledError: 
            # 精确捕获：客户端主动断开连接
            print("客户端断开连接，停止生成")
            yield "data: [DONE]\n\n"
        except Exception as e:
            # 兜底：其他未知错误
            # 客户端断开连接，优雅退出
            print(f"流式生成出错: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # 6. 返回SSE流式响应（禁用缓冲）
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用Nginx缓冲（如果有）
        }
    )

# ==================== WebSocket 端点 ====================
# 模拟: 客户端发送用户问题，服务端模拟 Agent 的思考-行动-观察循环
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
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
        from langchain_openai import ChatOpenAI
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_community.tools import  DuckDuckGoSearchRun
        from langchain_core.tools import tool

        #一 初始化模型
        llm=ChatOpenAI(
            model=LLM_MODEL_CHAT,
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            temperature=0,
        )
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
    try:
        while True:
            data = await websocket.receive_text()
            request = json.loads(data)
            user_message = request.get("message", "")
            
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
# 原有同步接口（需API Key）
@router.post(
    "/rag/ask",
    summary="原有同步接口（需API Key）",
    tags=["模拟类测试"]
)
async def ask_question(
    req: QuestionRequest,
    user_name: str = Depends(get_current_user_hybrid)
):
    start = time.time()
    # 同步检索（使用数据库）
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM documents WHERE requested_by = %s  LIMIT %s   -- 只检索当前用户的文档",
                (user_name, req.top_k))
            rows = cur.fetchall()
    docs = [r[0] for r in rows]
    duration = time.time() - start
    return {
        "question": req.question,
        "requested_by":user_name,
        "docs": docs,
        "elapsed": f"{duration:.3f}秒",
        "requested_by": user_name  # 记录是谁调用的
    }

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