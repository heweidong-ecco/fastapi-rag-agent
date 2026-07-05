"""
Locust 性能基准测试脚本
测试目标：RAG Agent API 的核心接口
"""
from locust import HttpUser, task, between
import random


class RAGAPIUser(HttpUser):
    """
    模拟真实用户行为：
    - 80% 的时间在做检索
    - 15% 的时间在插入文档
    - 5% 的时间在做健康检查
    """
    wait_time = between(1, 3)  # 每个请求之间等待1-3秒，模拟真实用户思考时间

    def on_start(self):
        """用户初始化：登录获取 Token"""
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

    @task(70)  # 权重80，占总请求的80%
    def search(self):
        """向量检索"""
        questions = [
            "Python编程",
            "人工智能",
            "FastAPI是什么",
            "机器学习",
            "数据分析",
        ]
        self.client.post(
            "/api/v1/rag/pg_search",
            headers=self.headers,
            json={
                "question": random.choice(questions),
                "top_k": 3
            }
        )

    @task(15)  # 权重15
    def insert(self):
        """插入文档"""
        contents = [
            "这是一条性能测试文档，用于评估系统吞吐量。",
            "Python 是一门强大的编程语言。",
            "Docker 容器化技术简化了部署流程。",
        ]
        self.client.post(
            "/api/v1/rag/insert",
            headers=self.headers,
            json={
                "content": random.choice(contents),
                "source": "benchmark"
            }
        )

    @task(10)  # 权重5
    def health(self):
        """健康检查"""
        self.client.get("/health")

    @task(20)  # 权重 20，表示占总请求量的 20%
    def stream_search(self):
        """流式检索接口测试"""
        with self.client.post(
            "/api/v1/rag/stream_search",
            headers=self.headers,
            json={"question": "Python编程", "top_k": 3},
            stream=True,
            catch_response=True  # 允许手动标记成功/失败
        ) as response:
            if response.status_code == 200:
                # 逐行读取 SSE 流，模拟客户端接收过程
                for _ in response.iter_lines():
                    pass
                response.success()
            else:
                response.failure(f"流式请求失败，状态码: {response.status_code}")