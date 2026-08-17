import uuid
import time
from contextvars import ContextVar
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from config import validate_config
from logger_config import logger,setup_logger
from exceptions import AppException, ErrorCode
from api_v1 import router as public_router
from api_v1_rag import router as rag_router
from api_v1_agent import router as agent_router
from db import create_table, init_pool, close_pool
from auth import ensure_admin_exists

from cache import redis_client
# 新增 令牌桶 在 main.py 中集成限流中间件：
# 新增 实现“全局 + 用户”两层令牌桶防护 全局限流器 用户级限流器，rate_limiter 已设置
from starlette.middleware.base import BaseHTTPMiddleware
from rate_limiter import global_limiter, user_limiter
# 新增  嵌入了 Prometheus 指标采集
from metrics import track_request,REQUEST_IN_PROGRESS

from metrics import  get_metrics
from db import get_db

from cache import warmup_cache  # ← 新增这一行

load_dotenv()
# ==================== 应用初始化 ====================
app = FastAPI(
    title="RAG Agent API",
    version="1.0.0",
    description="""
    ## 生产级 RAG + Agent API 服务
    
    ### 核心功能：
    - **文档管理**：上传、向量化、批量导入文档
    - **智能检索**：基于pgvector的语义搜索
    - **认证系统**：支持 API Key 和 JWT 双认证
    - **配额控制**：免费/付费/管理员三级权限
    
    ### 技术栈：
    FastAPI · PostgreSQL+pgvector · Redis · Docker · Prometheus+Grafana
    """,
    contact={
        "name": "hwd",
        "url": "https://github.com/你的用户名",
    },
    license_info={
        "name": "MIT",
    },
)


# ==================== 初始化日志====================
# 加入 三通道”（控制台 + 普通文件 + 错误文件）的日志器。setup_logger
logger = setup_logger()
# 全局变量 ：使用 ContextVar 存储每个请求的 request_id，线程安全
request_id_var: ContextVar[str] = ContextVar("request_id", default="no-id")


# ==================== 请求日志中间件 ====================
# 更新中间件，注入 request_id
# 更新日志中间件，同时记录指标 metrics
@app.middleware("http")
async def log_and_track_request(request: Request, call_next):
    # 生成唯一请求ID
    request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)
    
    # 活跃请求数+1
    REQUEST_IN_PROGRESS.inc()
    
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    # 活跃请求数-1
    REQUEST_IN_PROGRESS.dec()
    
    # 记录指标
    track_request(
        endpoint=request.url.path,
        method=request.method,
        status=response.status_code,
        duration=duration
    )
    
    logger.bind(request_id=request_id).info(
        f"{request.method} {request.url.path} - {response.status_code} ({duration:.3f}s)"
    )
    response.headers["X-Request-ID"] = request_id
    return response

# 新增 令牌桶 在 main.py 中集成限流中间件：
# 新增  在调用 is_allowed 之前获取限流信息，并在请求成功或失败时都设置对应的响应头。
class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件：对所有受保护接口生效"""
    async def dispatch(self, request: Request, call_next):
        # 跳过公开接口（与 QuotaMiddleware 的 public_paths 保持一致，避免登录被 anonymous 桶限死）
        # 健康检查/就绪/指标必须豁免，否则被限流会导致 K8s/Docker 健康探针误判为不健康
        if request.url.path in [
            "/", "/docs", "/openapi.json", "/health", "/ready", "/metrics",
            "/auth/login", "/auth/refresh", "/admin/create_user",
        ]:
            return await call_next(request)
        # ----- 第一层：全局限流（所有请求共享） -----
        if not global_limiter.is_allowed("global"):
            # 全局过载，直接拒绝，不暴露内部用户信息
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "Internal server error",
                    "code": ErrorCode.RATE_LIMITED.value,
                    "status_code": 429
                }
            )
            # 可选：加上全局的限流头，但一般不需要暴露细节
            return response
        
        # ----- 第二层：用户级限流 -----
        # 从请求头获取用户标识：优先 X-API-Key，其次 Bearer JWT（避免所有 JWT 用户共用 anonymous 桶）
        x_api_key = request.headers.get("X-API-Key")
        user_name = None
        if x_api_key:
            user_name = f"user:{x_api_key[:8]}"
        else:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                from jwt_handler import verify_access_token
                jwt_user = verify_access_token(auth_header[7:])
                if jwt_user:
                    user_name = f"user:{jwt_user}"
        if not user_name:
            user_name = "anonymous"

        # 获取用户限流信息（用于响应头）
        # 获取当前限流信息（无论是否被拒绝，都需要构造头部）
        info = user_limiter.get_limit_info(user_name)
        
        # 检查是否允许
        # 用户级限流
        if not user_limiter.is_allowed(user_name):
            # ===== 这里：触发限流时记录警告日志 =====
            request_id = request_id_var.get()
            logger.bind(request_id=request_id).warning(
                f"用户 {user_name} 触发限流"
            )
            # =====================================
            # 注意：中间件中抛出的异常不会被 @app.exception_handler(AppException) 捕获
            # （会落到 ServerErrorMiddleware 的通用 Exception 处理器，返回 500），
            # 因此这里必须直接返回 429 响应。
            return JSONResponse(
                status_code=429,
                content={
                    "error": "请求过于频繁",
                    "code": ErrorCode.RATE_LIMITED.value,
                    "status_code": 429,
                },
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info["reset"]),
                },
            )
        
        # 两层都通过，放行
        response = await call_next(request)
        # 添加用户级限流头（成功时也可返回，让客户端了解配额）
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])
        return response

# 将中间件添加到应用
app.add_middleware(RateLimitMiddleware)

# ==================== 权限分级中间件 ====================
from permission import get_user_role, get_user_quota
from quota_limiter import quota_limiter

class QuotaMiddleware(BaseHTTPMiddleware):
    """检查用户配额，超出限制返回429"""
    
    async def dispatch(self, request: Request, call_next):
        # 跳过公开接口（健康检查/就绪/指标不计配额）
        public_paths = ["/", "/docs", "/openapi.json", "/health", "/ready", "/metrics",
                        "/auth/login", "/auth/refresh", "/admin/create_user"]
        if request.url.path in public_paths:
            return await call_next(request)
        
        # 获取用户身份（支持API Key和JWT两种方式）
        user_name = None
        
        # 方式一：从X-API-Key获取
        x_api_key = request.headers.get("X-API-Key")
        if x_api_key:
            from auth import verify_api_key
            user_name = verify_api_key(x_api_key)
        
        # 方式二：从Authorization头获取JWT
        if not user_name:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
                from jwt_handler import verify_access_token
                user_name = verify_access_token(token)
        
        if user_name:
            # 获取配额
            quota = get_user_quota(user_name)
            info = quota_limiter.get_quota_info(user_name, quota)
            if not quota_limiter.increment_and_check(user_name, quota):
                # 配额已用完，返回429，使用标准化错误格式
                remaining = quota_limiter.get_remaining(user_name, quota)
                role = get_user_role(user_name)
                response = JSONResponse(
                    status_code=429,
                    content={
                        "error": f"今日调用次数已用完，您的角色为 {get_user_role(user_name).value}，每日限额 {quota} 次。",
                        "code": ErrorCode.QUOTA_EXCEEDED.value,
                        "status_code": 429,
                        # 额外信息仍可保留，方便调用方调试
                        "extra": {
                            "role": get_user_role(user_name).value,
                            "daily_limit": quota,
                            "remaining": 0
                        }
                    }
                )
                # 添加标准配额头
                response.headers["X-Quota-Limit"] = str(info["limit"])
                response.headers["X-Quota-Remaining"] = str(info["remaining"])
                response.headers["X-Quota-Reset"] = str(info["reset"])
                return response
            # 配额未满，放行
            response = await call_next(request)
            # 请求成功时也添加配额头，方便客户端了解当前用量
            response.headers["X-Quota-Limit"] = str(info["limit"])
            response.headers["X-Quota-Remaining"] = str(info["remaining"])
            response.headers["X-Quota-Reset"] = str(info["reset"])
            return response
        
        return await call_next(request)

# 将中间件添加到应用（放在限流中间件之后）
app.add_middleware(QuotaMiddleware)

# ==================== 自动规范化请求体中的文本字段中间件 ====================
from document_preprocessor import DocumentPreprocessor
import json
preprocessor = DocumentPreprocessor()

class TextNormalizationMiddleware(BaseHTTPMiddleware):
    """全局文本规范化中间件：自动对请求体中的文本字段进行半角规范化"""

    async def dispatch(self, request: Request, call_next):
        # 只处理 POST/PUT/PATCH 等有请求体的方法
        if request.method in ("POST", "PUT", "PATCH"):
            # 读取请求体
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                    # 递归规范化所有文本字段
                    normalized_data = self._normalize_dict(data)
                    # 将规范化后的数据重新封装为请求体
                    request._body = json.dumps(normalized_data).encode()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # 非JSON请求体，跳过

        response = await call_next(request)
        return response

    def _normalize_dict(self, obj):
        """递归遍历字典/列表，规范化所有字符串值"""
        if isinstance(obj, dict):
            return {k: self._normalize_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._normalize_dict(item) for item in obj]
        elif isinstance(obj, str):
            # 只对可能是自然语言的字段做规范化
            # 跳过明显的非文本字段（如token、url、email）
            if self._is_text_field(obj):
                return preprocessor.normalize_text(obj)
            return obj
        else:
            return obj

    def _is_text_field(self, value: str) -> bool:
        """判断字段值是否为需要规范化的自然语言文本"""
        # 跳过太短的字符串（如ID、状态码）
        if len(value) < 3:
            return False
        # 跳过URL
        if value.startswith("http://") or value.startswith("https://"):
            return False
        # 跳过明显的Token
        if value.startswith("sk-") or value.startswith("eyJ"):
            return False
        return True

# 在 app 创建后添加
app.add_middleware(TextNormalizationMiddleware)

# ==================== 全局异常处理器 ====================
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.error_code.value,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = request_id_var.get()
    logger.opt(exception=True).bind(request_id=request_id).error("未捕获异常: {}", str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": ErrorCode.INTERNAL_ERROR.value,
            "status_code": 500
        }
    )


# ==================== 挂载路由/路由定义 ====================
app.include_router(public_router)
app.include_router(rag_router)
app.include_router(agent_router)

@app.get("/")
async def root():
    return {
        "status": "ok",
        "version": "2.0.0",
        "services": {
            "public":"/api/v1",
            "rag": "/api/v1/rag",
            "agent": "/api/v1/agent",
        },
    }

# 新增  嵌入了 Prometheus 指标采集
# 指标暴露接口
@app.get("/metrics")
async def metrics():
    return get_metrics()

@app.get(
    "/openapi.json", 
    tags=["公开"],
    include_in_schema=False)
async def get_openapi():
    """返回 OpenAPI JSON，可直接导入 Postman"""
    return app.openapi()

# 新增  health 健康检查接口
@app.get("/health",tags=["公开"])
async def health_check():
    """
    健康检查接口。
    检查数据库、Redis、Embedding API 是否正常。
    返回 200 和各项状态，任一不可用则返回 503。
    """
    health_status = {"status": "healthy","checks": {}}
    is_healthy = True

    # 检查数据库
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        is_healthy = False

    # 检查 Redis
    try:
        redis_client.ping()
        health_status["checks"]["redis"] = "ok"
    except Exception as e:
        health_status["checks"]["redis"] = f"error: {str(e)}"
        is_healthy = False

    # Embedding API 不在健康检查中，避免开销和级联故障
    health_status["checks"]["embedding_api"] = "deferred to external monitoring"

    if not is_healthy:
        health_status["status"] = "unhealthy"
        return JSONResponse(
            status_code=503,
            content={
            "error": "Internal server error",
            "code": ErrorCode.SERVICE_UNAVAILABLE.value,
            "status_code": 503}
        )
    return health_status

#添加就绪探针 用于区分“已启动”和“可接受流量”（可选，用于 Kubernetes）
# 应用启动时间（用于就绪判断）
APP_START_TIME = time.time()

@app.get("/ready",tags=["公开"])
async def readiness_check():
    """
    就绪探针接口。
    只有在应用启动足够时间后（如10秒）且健康检查通过时才返回就绪。
    """
    # 等待应用完全初始化（如数据库表创建、管理员账户检查等）
    if time.time() - APP_START_TIME < 10:
        return JSONResponse(
            status_code=503,
            content={
            "error": "Internal server error",
            "code": ErrorCode.SERVICE_UNAVAILABLE.value,
            "status_code": 503}
        )

    # 也可以调用健康检查的逻辑
    health = await health_check()
    if health.get("status") == "unhealthy":
        return JSONResponse(
            status_code=503,
            content={
            "error": "Internal server error",
            "code": ErrorCode.SERVICE_UNAVAILABLE.value,
            "status_code": 503}
        )
    return {"status": "ready"}


# ==================== 应用启动时建表 ====================
import asyncio
from tool_health import run_health_check
async def scheduled_health_check():
    """定时健康检查后台任务"""
    while True:
        await asyncio.sleep(120)  # 每 2 分钟检查一次
        await run_health_check()

@app.on_event("startup")
async def startup_event():
    validate_config()
    init_pool()  # 启动连接池
    create_table()
    ensure_admin_exists(logger)
    warmup_cache()  # ← 新增这一行
    logger.info("应用启动完成")
    # 新增 Agent 工具 健康检查 启动时
    await run_health_check()
    # 新增 Agent 工具 启动后台定时健康检查
    asyncio.create_task(scheduled_health_check())


@app.on_event("shutdown")
async def graceful_shutdown():
    close_pool()  # 关闭连接池
    """应用关闭时执行清理操作"""
    logger.info("收到关闭信号，开始优雅关闭...")

    # 1. 停止接收新请求（FastAPI 自动处理）
    # 2. 等待现有请求处理完成（FastAPI 自动处理）
    # 3. 清理资源
    # 关闭数据库连接池
    try:
        # 如果你的 db.py 使用了连接池，在这里关闭
        logger.info("数据库连接已关闭")
    except Exception as e:
        logger.error(f"关闭数据库连接时出错: {e}")

    # 关闭 Redis 连接
    try:
        redis_client.close()
        logger.info("Redis 连接已关闭")
    except Exception as e:
        logger.error(f"关闭 Redis 连接时出错: {e}")

    # 4. 其他自定义清理工作
    logger.info("优雅关闭完成，服务即将退出")

# ==================== 挂载静态文件 ====================
from fastapi.staticfiles import StaticFiles
import os
# 挂载静态文件目录
# 获取 main.py 所在的目录（即 api/ 目录）
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
# 访问路径：http://localhost:8000/static/stream_test.html

# ==================== 挂载Gradio成本统计可视化面板 ====================
from cost_dashboard import create_dashboard
import gradio as gr
# 访问面板 启动服务后，浏览器打开 http://localhost:8000/dashboard。
dashboard = create_dashboard()
app = gr.mount_gradio_app(app, dashboard, path="/dashboard")

