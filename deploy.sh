# deploy.sh（一键部署脚本，保存到项目根目录）
# =============================================
#!/bin/bash
# 生产部署脚本
set -e

echo "========== 开始部署 =========="

# 1. 拉取最新代码（如果需要）
# git pull

# 2. 构建 API 镜像
echo "构建 API 镜像..."
docker compose build api

# 3. 启动所有服务
echo "启动所有服务..."
docker compose up -d

# 4. 等待服务就绪
echo "等待服务就绪..."
sleep 10

# 5. 健康检查
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "✅ 部署成功！"
else
    echo "❌ 健康检查失败，请查看日志：docker compose logs api"
    exit 1
fi

echo "========== 部署完成 =========="
# =============================================
# 运行前chmod +x deploy.sh，部署时执行 bash deploy.sh。