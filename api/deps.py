"""
依赖注入函数集中定义
所有 FastAPI 的 Depends() 依赖在此管理。
"""
from typing import Optional
from fastapi import Header, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from exceptions import AppException, ErrorCode
from auth import verify_api_key as verify_key
from jwt_handler import verify_access_token

# 全局 Bearer 认证方案实例（替换原来的 security）
# auto_error=False：允许请求只带 X-API-Key 而不带 Authorization 头时也能通过依赖解析，
# 否则 HTTPBearer 会在缺少 Authorization 头时直接抛 403，导致纯 API Key 认证全部失效。
oauth2_scheme = HTTPBearer(auto_error=False)

# ------------------ 纯 Token 验证函数（供内部调用） ------------------
def verify_jwt_token(token: str) -> str:
    """验证 JWT token 字符串，返回用户名，失败抛出异常"""
    user_name = verify_access_token(token)
    if user_name is None:
        raise AppException(ErrorCode.AUTH_EXPIRED, "access token 无效或已过期")
    return user_name

# ==================== 依赖注入： API Key 认证 ====================
async def get_current_user(x_api_key: str = Header(None)) -> str:
    """
    从请求头 X-API-Key 中提取并验证 API Key。
    返回 user_name，无效则抛出异常。
    """
    if not x_api_key:
        raise AppException(ErrorCode.AUTH_MISSING, "缺少 API Key")
    
    user_name = verify_key(x_api_key)
    if user_name is None:
        raise AppException(ErrorCode.AUTH_EXPIRED, "API Key 无效或已过期")
    
    return user_name

# ==================== 依赖注入： JWT 认证 （与API Key共存）====================
async def get_current_user_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme)
) -> str:
    if credentials is None:
        raise AppException(ErrorCode.AUTH_MISSING, "缺少 Bearer Token")
    token = credentials.credentials
    user_name = verify_access_token(token)
    if user_name is None:
        raise AppException(ErrorCode.AUTH_EXPIRED, "access token 无效或已过期")
    return user_name

# ------------------ 新：Hybrid 认证（自动识别 API Key / JWT） ------------------
# 新的 Hybrid 认证依赖
async def get_current_user_hybrid(
    x_api_key: str = Header(None),
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
) -> str:
    """支持 X-API-Key 或 Bearer Token 两种认证方式"""
    if x_api_key:
        return await get_current_user(x_api_key)
    if credentials:
        token = credentials.credentials
        return verify_jwt_token(token)
    raise AppException(ErrorCode.AUTH_MISSING, "请提供 API Key 或 Bearer Token")

# ------------------ 管理员权限校验（Hybrid 版本） ------------------
async def require_admin(
    user_name: str = Depends(get_current_user_hybrid)
) -> str:
    """校验当前用户是否为管理员，支持 API Key / JWT"""
    from permission import get_user_role, UserRole
    role = get_user_role(user_name)
    if role != UserRole.ADMIN:
        raise AppException(ErrorCode.FORBIDDEN, "仅管理员可执行此操作")
    return user_name


