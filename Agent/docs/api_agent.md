# 🤖 Agent API 文档

## 基础信息

| 项目             | 说明                            |
| :--------------- | :------------------------------ |
| **Base URL**     | `http://localhost:8000/api/v1`  |
| **API 版本**     | v1                              |
| **认证方式**     | Bearer Token (JWT) 或 X-API-Key |
| **Content-Type** | `application/json`              |

**认证说明：**
- 使用 `/auth/login` 接口获取 JWT Token。
- 在请求头中携带 `Authorization: Bearer <token>`。
- 或使用管理员 API Key：`X-API-Key: <your-api-key>`。

---

## 1. Agent 对话接口

### 1.1 基础对话

**请求：**
```http
POST /api/v1/agent/advanced_chat?question=今天天气怎么样？&thread_id=default
Authorization: Bearer <token>
```

**参数：**

| 参数           | 类型   | 必填 | 说明                       |
| :------------- | :----- | :--- | :------------------------- |
| `question`     | string | 是   | 用户问题                   |
| `thread_id`    | string | 否   | 会话线程ID，默认 `default` |
| `memory_space` | string | 否   | 记忆空间，默认 `default`   |

**响应：**
```json
{
  "question": "今天天气怎么样？",
  "answer": "今天北京晴，温度25°C，北风3级。",
  "intent": "SEARCH",
  "thread_id": "default",
  "requested_by": "admin"
}
```

### 1.2 MCP 对话

**请求：**
```http
POST /api/v1/agent/mcp_chat?question=计算123*456&thread_id=mcp-demo
Authorization: Bearer <token>
```

**响应：**
```json
{
  "question": "计算123*456",
  "answer": "123乘以456的结果是56088。",
  "thread_id": "mcp-demo",
  "trace": { ... },
  "requested_by": "admin"
}
```

### 1.3 Plan-and-Execute 任务

**请求：**
```http
POST /api/v1/agent/plan_execute?goal=帮我研究量子计算最新进展，生成报告
Authorization: Bearer <token>
```

**响应：**
```json
{
  "goal": "帮我研究量子计算最新进展，生成报告",
  "plan": [
    {"step": 1, "action": "搜索量子计算最新新闻", "tool": "search", "input": "2026 量子计算 突破"},
    {"step": 2, "action": "筛选重要突破", "tool": "filter", "input": "技术突破"},
    {"step": 3, "action": "生成报告", "tool": "summarize", "input": "生成300字报告"}
  ],
  "execution_result": "量子计算在2026年取得了多项重要突破...",
  "requested_by": "admin"
}
```

---

## 2. 记忆管理接口

### 2.1 添加长期记忆

**请求：**
```http
POST /api/v1/agent/memory/add?content=用户喜欢表格形式的数据展示&memory_space=work
Authorization: Bearer <token>
```

**响应：**
```json
{
  "status": "added",
  "content": "用户喜欢表格形式的数据展示",
  "memory_space": "work"
}
```

### 2.2 搜索长期记忆

**请求：**
```http
GET /api/v1/agent/memory/search?query=用户偏好&memory_space=work
Authorization: Bearer <token>
```

**响应：**
```json
{
  "query": "用户偏好",
  "memories": ["用户喜欢表格形式的数据展示", "用户正在学习AI应用开发"],
  "memory_space": "work"
}
```

---

## 3. 成本统计接口

### 3.1 花费总览

**请求：**
```http
GET /api/v1/agent/cost/overview
Authorization: Bearer <token>
```

**响应：**
```json
{
  "user_name": "admin",
  "total_cost": 0.0234,
  "total_tokens": 4500,
  "total_calls": 12,
  "by_purpose": {
    "agent_decision": {"tokens": 2000, "cost": 0.008, "calls": 8},
    "answer_generation": {"tokens": 1500, "cost": 0.009, "calls": 4}
  },
  "requested_by": "admin"
}
```

### 3.2 月度花费报告

**请求：**
```http
GET /api/v1/agent/cost/monthly_report?year=2026&month=7
Authorization: Bearer <token>
```

**响应：**
```json
{
  "report_period": "2026年7月",
  "summary": {
    "total_cost": 1.2345,
    "total_tokens": 250000,
    "total_calls": 180,
    "daily_average_cost": 0.0726,
    "cost_per_call": 0.0069
  },
  "by_purpose": [ ... ],
  "by_model": [ ... ]
}
```

### 3.3 预算查询

**请求：**
```http
GET /api/v1/agent/token/budget
Authorization: Bearer <token>
```

**响应：**
```json
{
  "user_name": "admin",
  "daily_budget": "无限",
  "used_today": 0,
  "remaining": "无限"
}
```

### 3.4 花费明细

**请求：**
```http
GET /api/v1/agent/cost/records?days=7&limit=50
Authorization: Bearer <token>
```

**响应：**
```json
{
  "records": [
    {
      "user_name": "admin",
      "thread_id": "default",
      "model": "qwen-turbo",
      "purpose": "agent_decision",
      "prompt_tokens": 500,
      "completion_tokens": 200,
      "total_tokens": 700,
      "total_cost": 0.0027,
      "tool_name": "web_search",
      "created_at": "2026-07-17 10:30:00"
    }
  ],
  "count": 1
}
```

---

## 4. 工具管理接口

### 4.1 工具列表（MCP）

**请求：**
```http
GET /api/v1/agent/mcp_tools_dynamic
Authorization: Bearer <token>
```

**响应：**
```json
{
  "tools": [
    {"name": "web_search", "description": "搜索互联网信息", "inputSchema": {...}},
    {"name": "calculator", "description": "计算数学表达式", "inputSchema": {...}}
  ],
  "total": 6,
  "requested_by": "admin"
}
```

### 4.2 可用工具（含健康过滤）

**请求：**
```http
GET /api/v1/agent/available_tools
Authorization: Bearer <token>
```

**响应：**
```json
{
  "healthy_tools": ["web_search", "calculator", "date_today", "execute_python"],
  "unhealthy_tools": ["fetch_webpage"],
  "total": 5
}
```

### 4.3 工具健康检查

**请求：**
```http
GET /api/v1/agent/tool_health
Authorization: Bearer <token>
```

**响应：**
```json
{
  "tools": {
    "web_search": {"status": "healthy", "last_checked": 1750000000.0},
    "fetch_webpage": {"status": "unhealthy", "last_checked": 1750000000.0}
  }
}
```

### 4.4 工具版本查询

**请求：**
```http
GET /api/v1/agent/tool_versions
Authorization: Bearer <token>
```

**响应：**
```json
{
  "tool_versions": {
    "web_search": "2.0.0",
    "calculator": "1.0.0",
    "execute_python": "1.5.0"
  }
}
```

---

## 5. 执行轨迹接口

### 5.1 轨迹列表

**请求：**
```http
GET /api/v1/agent/traces
Authorization: Bearer <token>
```

**响应：**
```json
{
  "traces": [
    {
      "thread_id": "default",
      "user_query": "今天天气怎么样？",
      "tool_calls_count": 1,
      "duration_ms": 1250,
      "total_cost": 0.0054
    }
  ]
}
```

### 5.2 轨迹详情

**请求：**
```http
GET /api/v1/agent/trace/{thread_id}
Authorization: Bearer <token>
```

**响应：**
```json
{
  "trace": {
    "thread_id": "default",
    "user_query": "今天天气怎么样？",
    "duration_ms": 1250,
    "tool_calls": [
      {
        "tool_name": "web_search",
        "arguments": {"query": "今天天气"},
        "result": "今天北京晴，温度25°C...",
        "duration_ms": 450,
        "status": "success"
      }
    ],
    "agent_decisions": [...],
    "final_output": "今天北京晴，温度25°C。",
    "total_tokens": 700,
    "total_cost": 0.0054
  }
}
```

---

## 6. 通用错误码

| 状态码  | 错误码               | 说明           |
| :------ | :------------------- | :------------- |
| **401** | `AUTH_MISSING`       | 缺少认证凭证   |
| **401** | `AUTH_EXPIRED`       | Token 已过期   |
| **403** | `FORBIDDEN`          | 无权限访问     |
| **404** | `RESOURCE_NOT_FOUND` | 资源不存在     |
| **422** | `PARAM_INVALID`      | 参数格式错误   |
| **429** | `QUOTA_EXCEEDED`     | 配额已用完     |
| **429** | `RATE_LIMITED`       | 请求过于频繁   |
| **500** | `INTERNAL_ERROR`     | 服务器内部错误 |
```

#### 三、将 API 文档整合到项目中

1.  将以上内容保存为 `docs/api_agent.md`。
2.  在 `README.md` 中添加链接：
    ```markdown
    ## 📖 API 文档

    完整的 API 文档请查看：
    -   **在线文档**：启动服务后访问 `http://localhost:8000/docs`（Swagger UI）
    -   **离线文档**：[Agent API 接口说明](docs/api_agent.md)
    ```
3.  提交并推送：
    ```bash
    git add docs/api_agent.md README.md
    git commit -m "docs: 添加项目二Agent API完整文档"
    git push
    ```
