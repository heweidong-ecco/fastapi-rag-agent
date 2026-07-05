import sys
import json
from loguru import logger


def setup_logger():
    """配置 Loguru，输出 JSON 到控制台，同时写入文件"""
    
    # 移除默认的 handler
    logger.remove()
    
    # 1. 控制台输出：彩色格式，方便开发调试
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{extra[request_id]}</cyan> | "
               "<level>{message}</level>",
        level="DEBUG",
        colorize=True
    )
    
    # 2. 文件输出：JSON 格式，方便生产环境分析
    logger.add(
        "logs/api_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[request_id]} | {message}",
        level="INFO",
        rotation="00:00",      # 每天凌晨0点创建新文件
        retention="30 days",   # 保留30天
        encoding="utf-8"
    )
    
    # 3. 错误日志单独输出
    logger.add(
        "logs/error_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {extra[request_id]} | {message}",
        level="ERROR",
        rotation="00:00",
        retention="90 days",   # 错误日志保留更久
        encoding="utf-8"
    )
    
    return logger
'''
# 送到远程平台 HTTP 推荐方案一，
一、阿里云日志服务（SLS）—— 最推荐，原生集成

为什么选它？

你已经在用阿里云百炼（DashScope）的 Embedding、Rerank、Qwen 模型。
SLS 是阿里云原生服务，和你的 API Key、网络环境完全打通。
提供实时查询、可视化仪表盘、告警、日志投递（OSS/ MaxCompute）等全套能力。
Python SDK 官方维护，Loguru 和 SLS 有现成的集成方案。
集成步骤

1. 安装 SDK

bash
pip install aliyun-log-python-sdk loguru-aliyun-log
2. 在 logger_config.py 中添加 SLS Handler

python
from loguru import logger
import os

def setup_logger():
    logger.remove()
    
    # ... 保留你之前的控制台、文件、错误日志配置 ...
    
    # 新增：阿里云 SLS 远程日志
    logger.add(
        "logs/api_{time:YYYY-MM-DD}.log",  # 本地保留一份兜底
        # ... 你原来的配置 ...
    )
    
    # ===== SLS 远程日志 =====
    logger.add(
        aliyun_sls_handler(
            endpoint=os.getenv("SLS_ENDPOINT", "cn-hangzhou.log.aliyuncs.com"),
            access_key_id=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID"),
            access_key_secret=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"),
            project=os.getenv("SLS_PROJECT", "rag-agent-logs"),
            logstore=os.getenv("SLS_LOGSTORE", "api-logs"),
        ),
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[request_id]} | {message}",
    )
    
    return logger
如果你不想用第三方封装，可以直接用阿里云原生 SDK 写一个自定义 Sink：

python
from aliyun.log import LogClient, PutLogsRequest, LogItem

class AliyunSLSSink:
    def __init__(self, endpoint, access_key_id, access_key_secret, project, logstore):
        self.client = LogClient(endpoint, access_key_id, access_key_secret)
        self.project = project
        self.logstore = logstore
    
    def write(self, message):
        log_item = LogItem()
        log_item.set_time(int(time.time()))
        log_item.set_contents([("message", message)])
        request = PutLogsRequest(self.project, self.logstore, "", "", [log_item])
        self.client.put_logs(request)

# 在 setup_logger 里添加
logger.add(AliyunSLSSink(...).write, level="INFO")
3. 在阿里云控制台查看日志

打开 SLS 控制台
进入你的 Project → Logstore → 查询分析
可以用 SQL 语法实时查询：
'''