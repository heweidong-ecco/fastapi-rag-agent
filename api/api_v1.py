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
from auth import create_user_api_key, authenticate_user
from jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from permission import get_user_role, get_user_quota, UserRole
from quota_limiter import quota_limiter
from rate_limiter import user_limiter
from cache import redis_client
from embedding_client import client
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


# ==================== 公开接口 ====================
@router.get(
    "/",
    tags=["公开"]
)
async def root():
    return {"status": "ok", "version": "v1"}

# ==================== 认证接口 ====================
@router.post(
    "/auth/login",
    summary="获取短期令牌和长期令牌",
    description="用户登录，返回 access_token短期令牌 和 refresh_token长期令牌",
    tags=["认证"],
    response_description="新创建的短期令牌时效15分钟，长期令牌30天",
    responses={401: {"description": "用户名或密码错误","content": {"example": {"code": "AUTH_INVALID"}}}}
)
async def login(req: LoginRequest):
    """用户登录，返回 access_token 和 refresh_token"""
    if not authenticate_user(req.user_name, req.password):
        raise AppException(ErrorCode.AUTH_INVALID, "用户名或密码错误")
    return {
        "access_token": create_access_token(req.user_name),
        "refresh_token": create_refresh_token(req.user_name),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post(
    "/auth/refresh",
    summary="换取新的短期令牌",
    description="输入refresh_token，用 refresh_token 换取新的 access_token",
    tags=["认证"],
    response_description="新创建的短期令牌时效15分钟",
    responses={
        401: {
            "description": "无效或过期的刷新令牌",
            "content": {
                "application/json": {
                    "examples": {
                        "AUTH_INVALID": {
                            "summary": "无效令牌",
                            "value": {
                                "error": "刷新令牌已无效",
                                "code": "AUTH_INVALID",
                                "status_code": 401
                            }
                        },
                        "AUTH_EXPIRED": {
                            "summary": "过期的刷新令牌",
                            "value": {
                                "error": "刷新令牌已过期",
                                "code": "AUTH_EXPIRED",
                                "status_code": 401
                            }
                        }
                    }
                }
            }
        }
    }
)
async def refresh(req: RefreshRequest):
    """用 refresh_token 换取新的 access_token"""
    user_name = verify_refresh_token(req.refresh_token)
    if user_name is None:
        raise AppException(ErrorCode.AUTH_EXPIRED, "refresh_token 无效或已过期")
    return {
        "access_token": create_access_token(user_name),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ==================== 用户管理 ====================
@router.post(
    "/admin/create_user",
    summary="创建新用户并生成API Key",
    description="""
    **这个系统内还没有加入初始管理员，此文档仅作为标注记录，参考使用，生成的API Key是30天有效期。**
    **管理员专用接口**：输入用户名和有效期，生成一个全新的 API Key。
    
    **安全注意**：
    - API Key **仅在此次响应中返回一次**，系统不会存储明文Key。
    - 请立即复制并妥善保存，关闭页面后将无法找回。
    - 数据库仅存储 Key 的 SHA256 哈希值，即使数据库泄露也无法还原明文。
    
    **认证要求**：当前版本暂未强制校验管理员身份，生产环境中应限制仅管理员可调用。
    """,
    tags=["用户管理"],
    response_description="新创建的用户信息和API Key（仅展示一次）",
    responses={
        200: {"description": "用户创建成功，返回API Key明文"},
        422: {"description": "请求参数格式错误，如用户名包含非法字符","content": {"example": {"code": "PARAM_INVALID"}}},
        500: {"description": "服务器内部错误，如数据库写入失败", "content": {"example": {"code": "INTERNAL_ERROR"}}}
    }
)
async def create_user(
    req: UserCreate,
    user_name: str = Depends(require_admin),
):
    """管理员创建新用户并返回 API Key"""
    api_key = create_user_api_key(req.user_name, req.expire_days)
    return {
        "user_name": req.user_name,
        "api_key": api_key,
        "expire_days": req.expire_days,
        "warning": "请立即保存此Key，它只显示一次！",
    }



@router.get(
    "/users/{user_id}",
    summary="获取用户信息",
    description="根据用户ID查询用户基本资料。可选择是否返回详细信息。",
    tags=["用户管理"],
    response_description="用户信息对象，包含用户ID和详情标志",
    responses={
        200: {"description": "查询成功"},
        422: {"description": "参数格式错误，如 user_id 不是整数","content": {"example": {"code": "PARAM_INVALID"}}}
    }
)
async def get_user(
    user_id: int = Path(
        ...,
        description="用户的唯一数字ID",
        example=123,
        ge=1
    ),
    include_detail: bool = Query(
        False,
        description="是否返回详细信息（如邮箱、注册时间等），默认仅返回基础信息",
        example=True
    )
):
    return {"user_id": user_id, "detail": include_detail}



# ==================== 调试接口 ====================
@router.get(
    "/debug/count",
    summary="调试：查看数据库中文档数量",
    tags=["调试"]
)
async def debug_count():
    """查看文档总数"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            count = cur.fetchone()[0]
    return {"total_documents": count}

@router.get(
    "/debug/quota/{user_name}",
    summary="权限分流的测试接口",
    description="权限分流的测试接口，限流（按角色不同限额）",
    tags=["调试"]
)
async def check_quota(user_name: str):
    """查看用户配额"""
    role = get_user_role(user_name)
    quota = get_user_quota(user_name)
    remaining = quota_limiter.get_remaining(user_name, quota)
    return {
        "user_name": user_name,
        "role": role,
        "daily_limit": quota,
        "remaining": remaining if remaining != -1 else "无限",
    }

#对比测试：缓存命中和无缓存命中 时间差距 ，正常生产级数据库大概是5倍，看数据库大小
@router.post(
    "/rag/benchmark-embedding",
    summary="对比测试：缓存命中和无缓存命中 时间差距 ，正常生产级数据库大概是5倍，看数据库大小",
    tags=["调试"]
)
async def benchmark_embedding(req:QuestionRequest):
    start = time.time()
    vec1 = get_embedding(req.question)
    t1 = time.time() - start

    start = time.time()
    vec2= get_embedding(req.question)
    t2= time.time() - start

    return {
        "question":req.question,
        "first_call_ms": round(t1*1000,2),
        "second_call_ms": round(t2 * 1000, 2),
        "speedup": f"{t1 / t2:.1f}x",
        "same_vector": vec1[:5] == vec2[:5]
    }

#增加一个调试接口，用来查看当前缓存中有多少个 Embedding 键
@router.get(
    "/debug/cache_stats",
    summary="调试接口，用来查看当前缓存中有多少个 Embedding 键",
    tags=["调试"]
)
async def cache_stats():
    count = 0
    sample = []
    for key in redis_client.scan_iter(match="emb:*", count=100):
        count += 1
        if len(sample) < 5:
            sample.append(key)
    return {
        "cached_embeddings_count": count,
        "sample_keys": sample
    }


@router.get(
    "/tool/benchmark",
    summary="调试接口，对比缓存前后的工具调用耗时s",
    tags=["调试"]
)
async def benchmark_tool():
    """对比缓存前后的工具调用耗时"""
    # 第一次调用（无缓存）
    start = time.time()
    result1 = get_weather("Beijing")
    t1 = time.time() - start
    
    # 第二次调用（命中缓存）
    start = time.time()
    result2 = get_weather("Beijing")
    t2 = time.time() - start
    
    return {
        "first_call_ms": round(t1 * 1000, 2),
        "second_call_ms": round(t2 * 1000, 2),
        "speedup": f"{t1 / t2:.1f}x" if t2 > 0 else "∞",
        "results_same": result1 == result2
    }

# 新增命令桶 调试接口：
@router.get(
    "/debug/rate_limit/{user_name}",
    summary="调试接口，查询某用户的剩余令牌数",
    tags=["调试"]
)
async def check_rate_limit(user_name: str):
    """查询某用户的剩余令牌数"""
    remaining = user_limiter.get_remaining(user_name)
    return {
        "user_name": user_name,
        "remaining_tokens": remaining,
        "capacity": user_limiter.capacity,
        "rate": user_limiter.rate
    }



