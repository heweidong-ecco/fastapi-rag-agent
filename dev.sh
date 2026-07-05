# 快速启动脚本 dev.sh
# dev.sh（本地开发模式，保存到项目根目录）：
# =============================================
#!/bin/bash
# 本地开发模式启动脚本
set -e

echo "启动 PostgreSQL 和 Redis 容器..."
docker compose up -d postgres redis

echo "等待 PostgreSQL 启动..."
until docker compose exec -T postgres pg_isready -U postgres -d rag_db 2>/dev/null; do
    sleep 2
done
echo "PostgreSQL 已就绪。"

echo "启动 FastAPI 服务（本地 venv + 热重载）..."
cd api
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# =============================================
# 运行前执行 chmod +x dev.sh，然后 bash dev.sh。