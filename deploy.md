Docker本地一键部署指南
部署文档

1. 环境要求

操作系统：Linux / macOS / Windows (推荐使用 WSL2)
Docker：20.10+
Docker Compose：v2.0+ （已内置在 Docker Desktop 中）
内存：建议 8GB 以上（用于运行多个容器和本地重排序模型）
2. 项目结构

确保你的项目目录包含以下关键文件：

text
your-project/
├── api/                     # FastAPI 应用代码
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ...
├── docker-compose.yml       # 全家桶编排文件
├── prometheus.yml           # Prometheus 配置
├── .env.example             # 环境变量模板
└── README.md
3. 快速开始（5分钟上手）

第1步：克隆项目

bash
git clone https://github.com/你的用户名/你的仓库名.git
cd 你的仓库名
第2步：配置环境变量

bash
cp .env.example .env
用你喜欢的编辑器打开 .env 文件，填入以下必填信息：

bash
# 阿里百炼 API Key（用于 Embedding 和 LLM 调用）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# JWT 签名密钥（请生成一个随机字符串）
JWT_SECRET_KEY=your-super-secret-key

# 数据库密码（请修改为强密码）
POSTGRES_PASSWORD=your-strong-password
其他配置项（如端口、Token过期时间等）已有默认值，可以暂时不改。

第3步：启动所有服务

bash
docker compose up -d
首次启动会自动下载镜像并构建API服务，大约需要3-5分钟。你会看到类似输出：

text
[+] Running 6/6
 ✔ Network your-project_default    Created
 ✔ Container postgres-rag          Healthy
 ✔ Container redis-rag             Healthy
 ✔ Container prometheus            Started
 ✔ Container grafana               Started
 ✔ Container rag-api               Started
第4步：验证部署

bash
# 健康检查
curl http://localhost:8000/health
# 应返回 {"status":"healthy","checks":{"database":"ok","redis":"ok"...}}

# API版本
curl http://localhost:8000/api/v1/
# 应返回 {"status":"ok","version":"v1"}
第5步：访问服务

服务	地址	默认账号密码
API 文档	http://localhost:8000/docs	无需登录
Grafana 监控	http://localhost:3000	admin / admin
Prometheus	http://localhost:9090	无需登录
4. 常用管理命令

bash
# 查看所有服务状态
docker compose ps

# 查看API日志
docker compose logs -f api

# 停止所有服务
docker compose down

# 停止并删除所有数据（慎用！）
docker compose down -v

# 重新构建并启动（代码有更新时）
docker compose build api
docker compose up -d
5. 数据持久化

所有重要数据都会保存在 Docker 卷（volumes）中，即使执行 docker compose down 也不会丢失：

PostgreSQL 数据：postgres_data 卷
Redis 数据：redis_data 卷
Grafana 面板：grafana_data 卷
Prometheus 监控数据：prometheus_data 卷
如果希望完全清空数据重头开始，执行 docker compose down -v。

6. 环境变量说明

变量名	必填	默认值	说明
DASHSCOPE_API_KEY	是	-	阿里百炼 API Key
JWT_SECRET_KEY	是	-	JWT 签名密钥（请使用随机字符串）
POSTGRES_PASSWORD	是	-	数据库密码
POSTGRES_DB	否	rag_db	数据库名
REDIS_HOST	否	redis	Redis 主机名（Docker内部）
DB_MAX_CONN	否	30	数据库连接池最大连接数
ACCESS_TOKEN_EXPIRE_MINUTES	否	15	JWT Access Token 过期时间（分钟）
7. 常见问题排查

问题	解决方案
端口被占用	修改 .env 中的端口映射，或停止占用端口的服务
API 启动失败	docker compose logs api 查看错误日志
数据库连接失败	确保 .env 中 POSTGRES_PASSWORD 与 docker-compose.yml 中一致
Embedding 调用失败	检查 DASHSCOPE_API_KEY 是否正确，网络是否能访问阿里云
三、云平台部署指南（以阿里云ECS为例）

当需要把服务暴露到公网或用于生产环境时，推荐使用云服务器。

第1步：准备云服务器

推荐配置：2核CPU、4GB内存、40GB系统盘（阿里云ECS或同等配置）。
操作系统：Ubuntu 22.04 LTS。
网络：确保安全组规则放行了 8000（API）、3000（Grafana）等必要端口。
第2步：连接到服务器并安装Docker

bash
ssh root@你的服务器IP

# 安装 Docker（官方脚本）
curl -fsSL https://get.docker.com | bash

# 启动 Docker 并设置开机自启
systemctl start docker
systemctl enable docker

# 验证安装
docker --version
# Docker version 24.x.x
第3步：上传项目并启动

bash
# 克隆你的项目（或通过 scp 上传）
git clone https://github.com/你的用户名/你的仓库名.git
cd 你的仓库名

# 配置 .env（参考 Docker 部署章节）
cp .env.example .env
nano .env  # 填入你的真实配置

# 启动所有服务
docker compose up -d
第4步：配置域名和HTTPS（可选）

在域名服务商处添加A记录，指向你的服务器IP。
使用 Nginx 或 Caddy 作为反向代理，并配置SSL证书。
Nginx 配置示例（/etc/nginx/sites-available/rag-api）：

nginx
server {
    listen 80;
    server_name api.your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;  # 流式输出需要关闭缓冲
    }
}
第5步：安全加固

修改默认密码：Grafana、数据库密码必须在 .env 中修改。
防火墙限制：除 8000 和 3000 外，其他端口（5432、6379）不要对外开放。
使用非 root 用户：创建专用用户运行 Docker。