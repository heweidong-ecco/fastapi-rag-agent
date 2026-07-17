# 🚀 部署指南

本文档介绍如何将 AI Agent 智能助理系统部署到生产环境。

## 1. 环境要求

| 要求               | 说明                                           |
| :----------------- | :--------------------------------------------- |
| **操作系统**       | Linux / macOS / Windows (WSL2)                 |
| **Docker**         | 20.10+                                         |
| **Docker Compose** | v2.0+（已内置在 Docker Desktop 中）            |
| **内存**           | 建议 8GB 以上（运行 5 个容器 + 本地模型推理）  |
| **磁盘**           | 建议 20GB 以上（包含 Docker 镜像和数据库数据） |

## 2. 快速部署（5 分钟上手）

### 第 1 步：克隆项目

bash
git clone https://jihulab.com/你的用户名/agent-assistant.git
cd agent-assistant

### 创建独立环境venv
-bash  cd ~
-bash  python3 -m venv venv
-bash  source venv/bin/activate
-bash  conda deactivate 

### 第 2 步：配置环境变量

bash
cp .env.example .env
编辑 .env 文件，填入以下必填信息：

bash
# 阿里百炼 API Key（必填，用于 LLM + Embedding + 搜索）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# JWT 签名密钥（必填，请使用随机字符串）
JWT_SECRET_KEY=your-super-secret-key

# 数据库密码（必填，请修改为强密码）
POSTGRES_PASSWORD=your-strong-password

# Mem0 配置（可选，用于长期记忆功能）
MEM0_API_KEY=your-mem0-api-key
其他配置项（如端口、Token 过期时间等）已有默认值，可以暂时不改。

### 第 3 步：启动所有服务

bash
docker compose up -d
首次启动会自动下载镜像并构建 API 服务，大约需要 3-5 分钟。你会看到类似输出：

text
[+] Running 6/6
 ✔ Network agent-assistant_default    Created
 ✔ Container postgres-rag             Healthy
 ✔ Container redis-rag                Healthy
 ✔ Container prometheus               Started
 ✔ Container grafana                  Started
 ✔ Container rag-api                  Started
### 第 4 步：验证部署

bash
# 健康检查
curl http://localhost:8000/health
# 应返回 {"status":"healthy","checks":{"database":"ok","redis":"ok"...}}

# API 版本
curl http://localhost:8000/api/v1/
# 应返回 {"status":"ok","version":"v1"}

### 第 5 步：获取管理员 API Key

首次启动时，系统会自动创建管理员账户。查看日志获取初始 Key：

bash
docker compose logs api | grep "管理员 API Key"
复制输出的 Key，妥善保存。这个 Key 只在首次启动时打印一次。

3. 服务访问地址

部署成功后，你可以通过以下地址访问各个服务：

服务	地址	说明
API 文档	http://localhost:8000/docs	Swagger UI 交互式文档
成本面板	http://localhost:8000/dashboard	Gradio 成本可视化
轨迹查看器	http://localhost:8000/static/trace_viewer.html	工具调用时间线
流式问答测试	http://localhost:8000/static/stream_test.html	流式 SSE 输出测试
Grafana 监控	http://localhost:3000	系统性能监控（admin/admin）
Prometheus	http://localhost:9090	指标采集
4. 环境变量说明

变量名	必填	默认值	说明
DASHSCOPE_API_KEY	是	-	阿里百炼 API Key
JWT_SECRET_KEY	是	-	JWT 签名密钥
POSTGRES_PASSWORD	是	-	数据库密码
MEM0_API_KEY	否	-	Mem0 长期记忆 API Key
POSTGRES_DB	否	rag_db	数据库名
REDIS_HOST	否	redis	Redis 主机名
DB_MAX_CONN	否	30	数据库连接池大小
ACCESS_TOKEN_EXPIRE_MINUTES	否	15	JWT Token 过期时间（分钟）
DEFAULT_DAILY_TOKEN_BUDGET	否	100000	默认每日 Token 预算
RERANKER_MODEL_NAME	否	bge-reranker-v2-m3	重排序模型
5. 常用管理命令

bash
# 查看所有服务状态
docker compose ps

# 查看 API 日志
docker compose logs -f api

# 停止所有服务
docker compose down

# 停止并删除所有数据（慎用！）
docker compose down -v

# 重新构建并启动（代码有更新时）
docker compose build api
docker compose up -d

# 进入 PostgreSQL 数据库
docker compose exec postgres psql -U postgres -d rag_db

# 查看 Redis 缓存
docker compose exec redis redis-cli KEYS "*"

### 6. 数据持久化

所有重要数据都会保存在 Docker 卷（volumes）中，即使执行 docker compose down 也不会丢失：

数据	卷名	说明
PostgreSQL 数据	postgres_data	文档向量、API Key、Token 使用记录
Redis 数据	redis_data	缓存数据
Grafana 面板	grafana_data	监控面板配置
Prometheus 数据	prometheus_data	监控历史数据
备份数据库：

bash
docker compose exec postgres pg_dump -U postgres rag_db > backup.sql
恢复数据库：

bash
docker compose exec -T postgres psql -U postgres -d rag_db < backup.sql

### 7. 更新部署

当项目代码有更新时，执行以下步骤：

bash
# 1. 拉取最新代码
git pull

# 2. 重新构建镜像
docker compose build api

# 3. 滚动更新（不中断服务）
docker compose up -d

# 4. 清理旧镜像（可选）
docker image prune -f

### 8. 常见问题排查

Q1：API 容器一直在重启？

排查步骤：

查看日志：docker compose logs api --tail 50
常见原因：

.env 文件未配置或 DASHSCOPE_API_KEY 无效
数据库密码不一致
端口被占用
Q2：数据库连接失败？

排查步骤：

确保 .env 中 POSTGRES_PASSWORD 与 docker-compose.yml 中一致。
检查 PostgreSQL 容器是否健康：docker compose ps postgres
Q3：Docker 构建镜像时卡在 pip install？

原因： 网络访问 PyPI 太慢。

解决方法： 在 Dockerfile 中为 pip 配置国内镜像源：

dockerfile
RUN pip install --user --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
Q4：Embedding 调用失败？

排查步骤：

检查 DASHSCOPE_API_KEY 是否正确。
检查网络是否能访问阿里云：curl https://dashscope.aliyuncs.com

### 9. 安全加固建议

修改默认密码：Grafana、数据库密码必须在 .env 中修改。
防火墙限制：除 8000 和 3000 外，其他端口（5432、6379）不要对外开放。
使用非 root 用户：创建专用用户运行 Docker。
定期更新依赖：关注阿里百炼 API 的版本更新和安全公告。
配置 HTTPS：通过 Nginx 反向代理并配置 SSL 证书。
text

#### 三、将部署文档整合到项目中

1.  将以上内容保存为 `docs/deploy.md`。
2.  在 `README.md` 中添加链接：
    ```markdown
    ## 🚀 快速开始

    详细部署步骤请查看 [部署指南](docs/deploy.md)。
提交并推送：

bash
git add docs/deploy.md README.md
git commit -m "docs: 添加项目二完整部署指南"
git push