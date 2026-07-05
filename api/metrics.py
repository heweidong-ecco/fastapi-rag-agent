from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# 请求总数（按接口和状态码分类）
REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"]
)

# 请求延迟分布
REQUEST_LATENCY = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["endpoint", "method"]
)

# 当前活跃请求数
REQUEST_IN_PROGRESS = Gauge(
    "api_requests_in_progress",
    "Number of requests currently in progress"
)


def track_request(endpoint: str, method: str, status: int, duration: float):
    """记录一次请求的指标"""
    REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=str(status)).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(duration)


def get_metrics():
    """返回Prometheus格式的指标数据"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )