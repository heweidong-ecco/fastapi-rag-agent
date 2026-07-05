"""
批量插入初始测试文档
用法：python seed_documents.py
"""
import requests

# ===== 配置 =====
BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"

# ===== 要插入的文档数据 =====
TEST_DOCUMENTS = [
    {"content": "Python 是一门解释型、面向对象的高级编程语言，广泛应用于数据科学、人工智能和 Web 开发。", "source": "tech"},
    {"content": "FastAPI 是一个现代、高性能的 Python Web 框架，用于构建 API，基于 Starlette 和 Pydantic。", "source": "tech"},
    {"content": "Docker 是一个容器化平台，可以将应用及其依赖打包成镜像，实现快速部署和环境隔离。", "source": "tech"},
    {"content": "机器学习是人工智能的一个分支，通过从数据中学习模式来做出预测或决策。", "source": "tech"},
    {"content": "PostgreSQL 是一个功能强大的开源关系型数据库，支持 JSON、全文搜索和扩展插件。", "source": "tech"},
    {"content": "Redis 是一个内存中的数据结构存储系统，常用作数据库、缓存和消息代理。", "source": "tech"},
    {"content": "LangChain 是一个用于构建大语言模型应用的框架，提供了链、代理和检索等抽象。", "source": "tech"},
    {"content": "向量数据库是一种专门存储和检索高维向量的数据库，常用于相似性搜索和推荐系统。", "source": "tech"},
    {"content": "苹果公司是美国的一家高科技公司，以 iPhone、Mac 等产品闻名于世。", "source": "business"},
    {"content": "2025 年全球人工智能市场规模达到数千亿美元，预计未来几年仍将保持高速增长。", "source": "business"},
]

# ===== 主流程 =====
def main():
    session = requests.Session()
    
    # 1. 登录获取 Token
    print("🔑 登录中...")
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "user_name": USERNAME,
        "password": PASSWORD
    })
    if resp.status_code != 200:
        print(f"❌ 登录失败：{resp.status_code} {resp.text}")
        return
    token = resp.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("✅ 登录成功")
    
    # 2. 批量插入文档
    print(f"📄 准备插入 {len(TEST_DOCUMENTS)} 条文档...")
    resp = session.post(f"{BASE_URL}/rag/insert_batch", json={
        "documents": TEST_DOCUMENTS
    })
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 批量插入成功，共插入 {data['count']} 条文档")
    else:
        print(f"❌ 插入失败：{resp.status_code} {resp.text}")

if __name__ == "__main__":
    main()