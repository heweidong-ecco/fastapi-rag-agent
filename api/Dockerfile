# ==================== 第一阶段：构建阶段 ====================
FROM python:3.10-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖（gcc 等，如果有 C 扩展的包需要编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 在第一阶段（builder）里
RUN mkdir -p /root/.pip && echo "[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/" > /root/.pip/pip.conf
# 将依赖安装到 /install 目录，用于后续复制
# --user 安装到用户目录，避免权限问题
RUN pip install --user --no-cache-dir -r requirements.txt


# ==================== 第二阶段：运行阶段 ====================
FROM python:3.10-slim AS runtime

# 设置工作目录
WORKDIR /app

# 只安装运行时必需的库（不需要 gcc 等编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的 Python 包
COPY --from=builder /root/.local /root/.local

# 复制应用代码
COPY . .

# 将 pip 用户安装的包路径加入 PATH
ENV PATH=/root/.local/bin:$PATH

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]