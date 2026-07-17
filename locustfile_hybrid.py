"""
混合负载压测脚本：模拟用户同时使用 RAG 检索和 Agent 对话
"""
from locust import HttpUser, task, between
import random

# ==================== RAG 测试数据 ====================
RAG_QUESTIONS = [
    "Python 编程的特点是什么？",
    "Docker 能解决什么问题？",
    "机器学习和人工智能的关系",
    "PostgreSQL 有哪些特性？",
    "向量数据库在 RAG 中的作用",
    "FastAPI 的性能优势",
]

# ==================== Agent 测试数据 ====================
AGENT_QUESTIONS = [
    "今天天气怎么样？",
    "计算 123*456",
    "今天是几号？",
    "帮我搜索最新的人工智能新闻",
    "翻译'你好，世界'成英文",
]

AGENT_FOLLOW_UPS = [
    "它的性能怎么样？",
    "那和别的技术比呢？",
    "能举个具体的例子吗？",
]

# ==================== 用户行为类 ====================
class HybridUser(HttpUser):
    """模拟真实用户：80% 做 RAG 检索，20% 使用 Agent"""
    wait_time = between(1, 3)

    def on_start(self):
        """登录获取 Token"""
        response = self.client.post("/api/v1/auth/login", json={
            "user_name": "admin",
            "password": "admin123"
        })
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}

    @task(60)  # 权重 60：RAG 检索
    def rag_search(self):
        """RAG 检索（模拟项目一的使用）"""
        self.client.post(
            "/api/v1/rag/search",
            headers=self.headers,
            json={
                "question": random.choice(RAG_QUESTIONS),
                "top_k": 3,
                "mode": "accurate",
            },
            name="/rag/search (RAG检索)"
        )

    @task(10)  # 权重 10：RAG 检索 + 生成答案
    def rag_search_with_answer(self):
        """RAG 检索 + 生成答案"""
        self.client.post(
            "/api/v1/rag/search",
            headers=self.headers,
            json={
                "question": random.choice(RAG_QUESTIONS),
                "top_k": 3,
                "mode": "accurate",
                "generate_answer": True,
            },
            name="/rag/search (RAG生成答案)"
        )

    @task(15)  # 权重 15：Agent 基础对话
    def agent_chat(self):
        """Agent 基础对话"""
        self.client.post(
            "/api/v1/agent/mcp_chat",
            headers=self.headers,
            json={
                "question": random.choice(AGENT_QUESTIONS),
                "thread_id": f"perf-{random.randint(1, 100)}",
            },
            name="/agent/mcp_chat (Agent对话)"
        )

    @task(10)  # 权重 10：Agent 多轮对话
    def agent_multi_turn(self):
        """Agent 多轮对话（先提问，再追问）"""
        question = random.choice(AGENT_QUESTIONS)
        follow_up = random.choice(AGENT_FOLLOW_UPS)
        thread_id = f"perf-multi-{random.randint(1, 50)}"

        # 第一轮
        self.client.post(
            "/api/v1/agent/mcp_chat",
            headers=self.headers,
            json={"question": question, "thread_id": thread_id},
            name="/agent/mcp_chat (多轮-第一轮)"
        )

        # 短暂思考
        import time
        time.sleep(0.5)

        # 追问
        self.client.post(
            "/api/v1/agent/mcp_chat",
            headers=self.headers,
            json={
                "question": follow_up,
                "thread_id": thread_id,
                "conversation_history": [f"用户: {question}"],
            },
            name="/agent/mcp_chat (多轮-追问)"
        )

    @task(5)  # 权重 5：健康检查
    def health_check(self):
        """健康检查"""
        self.client.get("/health", name="/health (健康检查)")