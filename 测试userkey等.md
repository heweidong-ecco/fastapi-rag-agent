JWT_SECRET_KEY=b53e206ed0367fc462552dbc6da6bb563c5bd09c7f5970ac0b04126b7d2cd16b
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
API_KEY=test-key-123

# 1. 登录获取Token：
在 Swagger 中调用 POST /auth/login：
测试使用的名字和钥匙
json
{
  "user_name": "admin",
  "password": "admin123"
}
保存返回的 access_token 和 refresh_token。

{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInR5cGUiOiJhY2Nlc3MiLCJleHAiOjE3ODI1MjA2NzksImlhdCI6MTc4MjUxOTc3OX0.2frDm6FCeeVDizaTA_jshKpuEBT-ubZiwW3QQvLnAmw",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInR5cGUiOiJyZWZyZXNoIiwiZXhwIjoxNzgzMTI0NTc5LCJpYXQiOjE3ODI1MTk3Nzl9.-HGLnGYHMWjpL3s6Fl96DPZ0QP8tbc4Y1WigQCer1RQ",
  "token_type": "bearer",
  "expires_in": 900
}

配置Grafana
访问 http://localhost:3000，用户名 admin，密码 admin
Configuration → Data Sources → Add data source → Prometheus
URL 填 http://prometheus:9090，点击 Save & test
Create → Dashboard → Add panel

在Metrics输入：
QPS：rate(api_requests_total[1m])
P99延迟：histogram_quantile(0.99, rate(api_request_duration_seconds_bucket[1m]))
错误率：rate(api_requests_total{status=~"5.."}[1m]) / rate(api_requests_total[1m])
保存Dashboard




