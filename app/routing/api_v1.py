"""
API v1 路由集中定义
所有 /api/v1 前缀的接口在此管理。
"""
import time
from fastapi import APIRouter, Depends

from core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from core.exceptions import ErrorCode, AppException
from routing.schemas import (
    QuestionRequest,
    LoginRequest,
    RefreshRequest,
    UserCreate,
)
from routing.deps import require_admin
from core.db import get_db
from rag.embedding_client import get_embedding
# B11（①b Task 4）：全站日级熔断
from billing.breaker import circuit, global_key
from access.auth import create_user_api_key, authenticate_user
from access.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from access.permission import get_user_role
from billing.token_tracker import get_token_budget_info
from access.rate_limiter import user_limiter
from core.cache import redis_client
# ⚠️ 批 6（`DEC-082`）删掉 `from embedding_client import client` —— 它**全仓只有这一处**，
#    且**从未被使用**；而 `client` 已改成惰性构造，留着这行会让 `api_v1` 直接 ImportError。
# ⚠️ 2026-10-04 删 `get_weather`（`DEC-065`）：它在本文件**只有** `/tool/benchmark` 一处用，
#    那条端点已删。
#
# ⚠️ 2026-10-07：本文件**又删掉 27 个从未被引用的导入**（`T6` 存量 · 判据 `ruff --select F401`）：
#    `json` · `StreamingResponse`/`JSONResponse` · `DocumentInsert`/`BatchDocumentInsert` ·
#    `get_current_user_hybrid`/`get_current_user_jwt` · `insert_document`/`insert_batch_documents` ·
#    `calculator`（`D1` 旧账，本条即它的收口）· `invalidate_bm25_cache` ·
#    `hybrid_search`/`rerank_search`/`hybrid_search_with_rewrite` ·
#    `create_fast_pipeline`/`create_accurate_pipeline`/`create_full_pipeline` ·
#    `File`/`UploadFile` · `tempfile` · `DocumentPreprocessor` · `split_text_with_filter` ·
#    `parse_document` · `get_chat_history`/`append_chat_history` · `agent_graph` · `os`。
#    🔴 **删的只是【本文件里的导入行】，⛔ 没有删任何模块** —— 那些模块本身照旧存在、照旧可 import，
#       将来要接回来就是**补一行**的事。⚠️ `tools_with_cache.py` / `tool_cache.py` 两个**死模块**
#       仍在 `T6` 的「先挂起」里，**本刀没碰**。


router = APIRouter(prefix="/api/v1")


# ==================== 公开接口 ====================
@router.get(
    "/",
    tags=["公开"]
)
async def root():
    return {"status": "ok", "version": "v1"}


@router.get(
    "/info",
    tags=["公开"],
    summary="服务索引（**原 `GET /` 的那段 JSON**，2026-10-09 挪来）",
    description=(
        "⚠️ 这一段**原先挂在 `GET /`** 上，而 `GET /` 在 2026-10-09 改成了"
        "**总览首页**（302 → `/static/web/index.html`）。\n\n"
        "🔴 裁定的原话是「**挪走，⛔ 不是删**」—— 所以它整段**原样**在这里，"
        "⛔ 一个字都没改。**若你是来找那段 JSON 的，就是它。**"
    ),
)
async def service_info():
    """服务索引。⚠️ 内容原样照搬原 `GET /`（见 `app/main.py` 里那段注释的沿革）。"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "services": {
            "public": "/api/v1",
            "rag": "/api/v1/rag",
            "agent": "/api/v1/agent",
        },
    }

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
    **管理员专用接口**：输入用户名和有效期，生成一个全新的 API Key。

    **认证要求**：**必须由管理员调用** —— 本接口以 `Depends(require_admin)` **强制校验**，
    非管理员直接得到 **403**（`仅管理员可执行此操作`）。
    初始管理员由应用**启动时**的 `ensure_admin_exists` 创建。

    **安全注意**：
    - API Key **仅在此次响应中返回一次**，系统不会存储明文Key。
    - 请立即复制并妥善保存，关闭页面后将无法找回。
    - 数据库仅存储 Key 的 SHA256 哈希值，即使数据库泄露也无法还原明文。
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



# ==================== 【已删除】GET /api/v1/users/{user_id} ====================
# 🔴 2026-10-04 **删除**（`DEC-065`）—— 函数 `get_user` 已移除。
# 原先是：
#     async def get_user(user_id: int = Path(...), include_detail: bool = Query(False)):
#         return {"user_id": user_id, "detail": include_detail}
#
# 为什么删（三条）：
#   ① **一行数据都不读** —— 不查库、不看 `user_name`，纯粹回显入参。它是 **Path/Query
#      参数校验的演示**，却挂了 `tags=["用户管理"]` + `summary="获取用户信息"`，
#      **极易被当成真接口**。
#   ② 本仓**自己早就点名要处理它**：`app/routing/specs/api_v1.md` ⚠️④ 与「待办」表第 4 条
#      原文写着「**要么真查库，要么删**」⇒ 本次裁「删」。
#   ③ 消费者 = 0（仓内无前端 · 无测试引用 · 只有 Postman 1 个文件夹，已删）。
#
# ⛔ **别照抄这个形状再把端点加回来** —— `app/tests/test_removed_endpoints.py::test_users_by_id_stays_removed`
#    会红。若真要恢复，**先读 `docs/decisions/DEC-065-*.md`**，且必须**同时**给出真实数据来源
#    与 `Depends(require_admin)`（它读的是**任意** user_id）。
# ================================================================================



# ==================== 调试接口 ====================
# 🔴 2026-10-04（`DEC-065`）：本节的 4 条 + `/rag/benchmark-embedding` 全部补上
#    `Depends(require_admin)`。此前它们**匿名可打** —— 其中 `/debug/quota/{user_name}` 与
#    `/debug/rate_limit/{user_name}` **泄露任意用户的角色/配额/限流桶**（**可枚举用户名**），
#    `/rag/benchmark-embedding` 更是**全仓唯一匿名真烧钱**的端点。
# ⚠️ **参数名用 `_admin`**：`check_quota` / `check_rate_limit` 的**路径参数就叫 `user_name`**
#    （那个是「要查谁」，管理员才有权指定别人）⇒ 依赖的返回值不能重名，取值也不用。
@router.get(
    "/debug/count",
    summary="调试：查看数据库中文档数量",
    tags=["调试"]
)
async def debug_count(_admin: str = Depends(require_admin)):
    """查看文档总数"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            count = cur.fetchone()[0]
    return {"total_documents": count}

@router.get(
    "/debug/quota/{user_name}",
    summary="权限分流的测试接口",
    description="查看用户的日配额（**token 口径** · 按角色不同预算）",
    tags=["调试"]
)
async def check_quota(user_name: str, _admin: str = Depends(require_admin)):
    """查看用户的日配额（**token 口径** · `DEC-046`）。

    🔴 2026-10-03 改：原先返回「每日**请求次数**」（`permission.ROLE_QUOTA` + `quota_limiter`）。
    两者口径实测**差 35 倍**（`DEC-029`）⇒ 业务方裁「统一到 token 一套」（`DEC-040`）。
    ⚠️ 字段名 `daily_limit` / `remaining` **保留**，但**单位已从「次」变成 token**。
    """
    role = get_user_role(user_name)
    info = get_token_budget_info(user_name)
    return {
        "user_name": user_name,
        "role": role,
        "daily_limit": info["daily_budget"],
        "remaining": info["remaining"],
        "used_today": info["used_today"],
    }

#对比测试：缓存命中和无缓存命中 时间差距 ，正常生产级数据库大概是5倍，看数据库大小
@router.post(
    "/rag/benchmark-embedding",
    summary="对比测试：缓存命中和无缓存命中 时间差距 ，正常生产级数据库大概是5倍，看数据库大小",
    tags=["调试"]
)
async def benchmark_embedding(req: QuestionRequest, _admin: str = Depends(require_admin)):
    # B11 · 全站日级熔断（`①b` Task 4）。
    # 🔴 🔴 2026-10-04（`DEC-065`）**补上 `Depends(require_admin)`** ——
    #    此前本端点在全仓**独一份**：**匿名可打、且真花钱**（下面 `get_embedding()` 真调 DashScope）。
    #    ⚠️ **熔断层与鉴权层是两件事，⛔ 别因为有了 B11 就不加鉴权**：
    #      B11 管的是「**全站今天超预算了就别再烧**」，**管不住「谁都能烧」**。
    #    ⚠️ 它仍然接不上 B8（会话级要 `user_name`/`thread_id`，这里只有身份、没有会话）；
    #      B11 是**全站**级、`circuit("global:…")` 不需要用户身份 ⇒ 它仍是唯一能管住这条的那层。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

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
async def cache_stats(_admin: str = Depends(require_admin)):
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


# ==================== 【已删除】GET /api/v1/tool/benchmark ====================
# 🔴 2026-10-04 **删除**（`DEC-065`）—— 函数 `benchmark_tool` 已移除。
# 原先它把 `get_weather("Beijing")` 调两次、比耗时，输出 `speedup`。
#
# 为什么删：
#   🔴 **它 benchmark 的是一个 mock** —— `tools_with_cache.get_weather` 的本体是
#      `time.sleep(2)` + 硬编码 `f"{city}当前温度25°C，晴"`。⇒ 这个端点证明的只是
#      「**缓存装饰器在一个假函数上生效了**」，**证明不了任何生产事实**。
#      ⚠️ 而缓存装饰器本身已有单测覆盖（`app/tests/test_audit_fixes.py`）⇒ **信息量为零**。
#   ⚠️ 它还**匿名可打**（是待办 `S1` 的两条之一）—— 虽然不花钱，但一个只会
#      `sleep(2)` 的端点挂在公网上没有任何理由。
#
# ⛔ **别照抄这个形状再把端点加回来** —— `app/tests/test_removed_endpoints.py::test_tool_benchmark_stays_removed`
#    会红。⚠️ 若将来真要 benchmark 缓存，**必须拿真函数**（如 `/rag/benchmark-embedding`
#    那样真调 DashScope），且**必须带鉴权**。
# ==============================================================================

# 新增命令桶 调试接口：

# 新增命令桶 调试接口：
@router.get(
    "/debug/rate_limit/{user_name}",
    summary="调试接口，查询某用户的剩余令牌数",
    tags=["调试"]
)
async def check_rate_limit(user_name: str, _admin: str = Depends(require_admin)):
    """查询某用户的剩余令牌数"""
    remaining = user_limiter.get_remaining(user_name)
    return {
        "user_name": user_name,
        "remaining_tokens": remaining,
        "capacity": user_limiter.capacity,
        "rate": user_limiter.rate
    }



