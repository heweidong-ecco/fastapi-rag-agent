"""
集中配置管理
所有环境变量在此读取，其他模块从本文件导入。
敏感信息禁止设默认值，启动时强制校验缺失。
"""
import os
import sys
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件（注意路径关系）
# 如果 config.py 放在 api/ 下，需加载上一级的 .env
load_dotenv(
    os.path.join(os.path.dirname(__file__), '..', '.env')
)

# 判断是否在 Docker 环境中运行
# 本地开发时覆盖为 localhost
IS_DOCKER = os.getenv("DOCKER_ENV", "false").lower() == "true"

# ==================== 非敏感配置（有合理默认值） ====================
# 数据库
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "rag_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# JWT 有效期
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# API Key 认证（非敏感，可有一个开发用默认值）
API_KEY = os.getenv("API_KEY", "test-key-123")

# ==================== 敏感配置（禁止默认值，缺失则拒绝启动） ====================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# ==================== 生成/对话 LLM 可配置(默认阿里云百炼;切任意 OpenAI 兼容端点请填 LLM_* 三键) ====================
# embedding 固定走 DASHSCOPE(text-embedding-v2);本段只管 生成/对话 模型。
# 切 DeepSeek 官方示例 → LLM_BASE_URL=https://api.deepseek.com · LLM_API_KEY=<sk-…> · LLM_MODEL_FAST/LLM_MODEL_CHAT=<其模型名>
LLM_API_KEY    = os.getenv("LLM_API_KEY") or DASHSCOPE_API_KEY
LLM_BASE_URL   = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", "qwen-turbo")
LLM_MODEL_CHAT = os.getenv("LLM_MODEL_CHAT", "qwen-plus")


def validate_config():
    """启动时调用，检查敏感配置是否存在"""
    missing = []
    if not DASHSCOPE_API_KEY:
        missing.append("DASHSCOPE_API_KEY")
    if not POSTGRES_PASSWORD:
        missing.append("POSTGRES_PASSWORD")
    if not JWT_SECRET_KEY:
        missing.append("JWT_SECRET_KEY")

    if missing:
        raise EnvironmentError(
            f"以下必需的环境变量未设置，请检查 .env 文件或系统环境变量:\n"
            f"{', '.join(missing)}"
        )

# config.py 末尾添加
DB_MIN_CONN = int(os.getenv("DB_MIN_CONN", "2"))
DB_MAX_CONN = int(os.getenv("DB_MAX_CONN", "30"))

# ==================== 本地开发覆盖 ====================
if not IS_DOCKER:
    POSTGRES_HOST = "localhost"
    REDIS_HOST = "localhost"