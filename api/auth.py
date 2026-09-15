import uuid
import hashlib
from datetime import datetime, timedelta
from db import get_db
from config import LOGIN_USER_NAME, LOGIN_PASSWORD, TEST_USER_PASSWORD

def generate_api_key() -> str:
    """生成一个API Key，格式：sk- + 随机字符串"""
    return "sk-" + uuid.uuid4().hex

def hash_api_key(api_key: str) -> str:
    """对API Key进行哈希，数据库中只存储哈希值"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def create_user_api_key(user_name: str, expire_days: int = 30) -> str:
    """
    为新用户生成API Key并存入数据库。
    返回明文Key（只在生成时显示一次，之后无法找回）。
    """
    api_key = generate_api_key()
    hashed = hash_api_key(api_key)
    expires_at = datetime.now() + timedelta(days=expire_days)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (user_name, key_hash, expires_at) VALUES (%s, %s, %s)",
                (user_name, hashed, expires_at)
            )
            conn.commit()
    
    return api_key
# 创建管理员身份的代码
def ensure_admin_exists(logger=None):
    """
    应用启动时检查管理员账户是否存在。
    如果不存在，则自动创建一个有效期10年的管理员账户，
    并通过日志打印初始 API Key（仅此一次机会获取）。
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM api_keys WHERE user_name = 'admin'")
            count = cur.fetchone()[0]
    
    if count > 0:
        if logger:
            logger.info("管理员账户已存在，跳过自动创建")
        return None
    
    # 创建管理员，有效期10年
    api_key = create_user_api_key("admin", expire_days=3650)
    
    if logger:
        logger.warning("=" * 60)
        logger.warning("首次启动：已自动创建管理员账户")
        logger.warning(f"管理员用户名: admin")
        logger.warning(f"管理员 API Key: {api_key}")
        logger.warning("请立即复制并安全保存此 Key，它仅显示这一次！")
        logger.warning("=" * 60)
    
    return api_key

def verify_api_key(api_key: str):
    """
    验证API Key是否有效。
    返回该Key对应的user_name，如果无效则返回None。
    """
    hashed = hash_api_key(api_key)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_name, expires_at FROM api_keys WHERE key_hash = %s",
                (hashed,)
            )
            row = cur.fetchone()
    
    if row is None:
        return None
    
    user_name, expires_at = row
    if expires_at < datetime.now():
        return None
    
    return user_name


# 登录凭据来自环境变量 —— 2026-09-15 从本文件的硬编码字面量迁出
# （那曾是**公开仓库上的活凭据**；决策见 docs/decisions/DEC-001-认证口令处理路线.md）
#
# ⚠️ 每次调用都重新读环境变量（刻意不缓存到模块级）：这样测试可以 monkeypatch 干预。
def _get_users_db() -> dict:
    """从环境变量构造登录凭据表。

    - `LOGIN_USER_NAME` / `LOGIN_PASSWORD`：主账号。`LOGIN_PASSWORD` 缺失时应用根本起不来
      —— `config.validate_config()` 会在 startup 阶段抛 EnvironmentError。
    - `TEST_USER_PASSWORD`：**可选**。未设则该账号不存在 —— fail-closed，不留任何默认口令。
    """
    db = {}
    if LOGIN_PASSWORD:
        db[LOGIN_USER_NAME] = LOGIN_PASSWORD
    if TEST_USER_PASSWORD:
        db["test_user"] = TEST_USER_PASSWORD
    return db


def authenticate_user(user_name: str, password: str) -> bool:
    """验证用户名和密码"""
    return _get_users_db().get(user_name) == password