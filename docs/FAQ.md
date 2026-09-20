# 📋 常见问题与故障排查 (FAQ)

> 🔴 **2026-09-20 说明**：本 FAQ 原先**整份都假设 Docker 路径**（Q1–Q3 全是 `docker compose`），
> 而 `docker compose up -d` 会 **build 含 torch 的镜像**，在 8GB 内存的机器上**跑不动**（实测）。
> **已补 Q1.1–Q1.5**，覆盖**轻量路径**（DB/Redis 用 Docker、API 跑本机）与 clone 者真会撞的坑。
> 路径选择见 `README.md` 的「3. 启动」。

## 一、部署相关

### Q1.1：我不想（或不能）构建 Docker 镜像，怎么在本机跑起来？

用**轻量路径** —— 它不构建任何镜像，只跑两个现成的 DB/Redis 容器：

```bash
# ⚠️ 先判断容器在不在 —— 已有就用 start，别用 up（理由见下方告示）
docker ps --format '{{.Names}}' | grep -E 'postgres-rag|redis-rag' \
  && docker start postgres-rag redis-rag \
  || docker compose up -d postgres redis      # 只有这两个是现成镜像

python3.10 -m venv venv
venv/bin/pip install -r api/requirements-test.txt    # ← 注意是 -test 那份（不含 torch）
cp .env.example .env                          # 然后填【四项】：见 Q1.4
cd api && ENABLE_DASHBOARD=false ../venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

> 🔴 **2026-09-20 修：此处原写「直接 `docker compose up -d postgres redis`」—— 在已有同名容器的机器上是错的。**
> 实测本机 `postgres-rag`/`redis-rag` 的 `com.docker.compose.project` 是 **`my-fixed-name`**、
> 配置文件指向**另一个仓库**，而本仓 `docker compose ps` 是空的（不认领）⇒ 直接 `up` 会计划
> **`Container postgres-rag Creating`** ⇒ **撞名硬失败**，或**重建到 `fastapi-rag-agent_app-net`**
> —— 后者会打断依赖旧网络名的 `agent-eval-gate`（见 Q1.3）。

⚠️ **两个 `requirements` 别弄混**：`requirements.txt` **含** `sentence-transformers`/`transformers`/
`camelot-py[cv]`/`opencv-python`（**拖 GB 级 torch**）；`requirements-test.txt` 是它的**剔重版（只做减法）**。
**本仓默认路径不需要 torch**（默认模式 `accurate_norerank`；`api/reranker.py:14` 是真懒加载）。
**代价**：`mode=accurate` / `mode=full` / `/rag/rerank_search` 在本机跑不了 —— 要装 torch + 2.3GB 模型。

### Q1.2：`git clone` 报 `Repository not found`？

2026-09-20 之前 README 里的克隆地址是**占位符**（`https://github.com/你的用户名/rag-agent-api.git`），
照抄必然失败。**真实地址**：

```bash
git clone https://github.com/heweidong-ecco/fastapi-rag-agent.git
```

### Q1.3：起服务时报 `psycopg2.OperationalError: connection to server at "localhost", port 5432 failed: Connection refused`

**Postgres 容器没在跑**（不是代码问题）。先确认：

```bash
docker ps                                  # 有没有 postgres-rag / redis-rag
docker start postgres-rag redis-rag        # 若已存在但停了：重启【现有】容器，不要 up（见下）
```

> ⚠️ **用 `docker start`，不要用 `docker compose up -d`** —— 后者可能**重建**容器并让它落到新网络名，
> 从而打断依赖旧网络名的外部工具（本仓的 `agent-eval-gate` 评测 harness 就是这种）。
> 另外本仓对 `.env` 里的 `POSTGRES_HOST=postgres` 有**本地覆盖**：`config.py` 见 `DOCKER_ENV` 非 true 时
> 自动改指 `localhost`（见 `docker-compose.yml` 的 `DOCKER_ENV=true`）。

### Q1.4：应用起不来，报 `EnvironmentError` / 提示缺配置？

`api/config.py` 的 `validate_config()` 对**四个必填项**是 **fail-closed**（缺失即拒绝启动）：

| 必填 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | Embedding 用（阿里百炼）。**必须是真 key**（见下方三种情况的准确行为） |
| **`POSTGRES_PASSWORD`** | ⚠️ **最容易漏的一项** —— `.env.example` 里给了占位值 `mysecretpassword`，所以"看起来不用管"；但**删掉/留空就会拒绝启动** |
| `JWT_SECRET_KEY` | 随便一串随机值 |
| `LOGIN_PASSWORD` | 管理员登录口令；**缺失 = 拒绝启动**（刻意不留默认口令） |

> ⚠️ **2026-09-20 更正 —— key 的三种情况，行为不同（我直接对 SDK 实测过）**：
> | key 的值 | 结果 |
> |---|---|
> | **缺失**（`None`） | **导入期**就抛 `OpenAIError`（应用起不来） |
> | **空串** `''` | SDK **不抛**；由 `validate_config` 拦下，抛 `EnvironmentError`（干净的报错） |
> | **dummy**（如 `'dummy'`） | **起得来**，直到**真调用时**才 401 |
>
> 本处原文写"空的或 dummy 会在导入期抛"—— **两者都不成立**（CI 正是靠 dummy key 才跑得起来）。

### Q1.5：`pytest` 报 `Storage folder ./.mem0/qdrant is already accessed by another instance of Qdrant client`

**这是已知限制，不是测试坏了** —— `api/memory_store.py:12` 在**模块导入期**就开本地 Qdrant
（`path="./.mem0/qdrant"`），而本地 Qdrant 是**单实例锁**。⇒ **应用跑着的时候 `pytest` 跑不了。**

**逃生口（两个都要，实测只有其一不行）**：① 从**仓库根**跑（避开 `api/.mem0/qdrant`）
② 设 `MEM0_DIR=<临时目录>`（避开 `~/.mem0/migrations_qdrant`）：

```bash
pkill -f "uvicorn main:app"                                  # 或 ①
MEM0_DIR=$(mktemp -d) venv/bin/python -m pytest api/ -m "not integration and not needs_db" -q
```

### Q1：执行 `docker compose up -d` 后，API 容器一直在重启？

**排查步骤：**
1. 查看 API 日志：
   ```bash
   docker compose logs api --tail 50
   ```
2. 常见原因：
   - `.env` 文件未配置：确保复制了 `.env.example` 为 `.env`，并填入了真实的 `DASHSCOPE_API_KEY`、`POSTGRES_PASSWORD`、`JWT_SECRET_KEY`。
   - 数据库密码不一致：`.env` 中的 `POSTGRES_PASSWORD` 必须与 `docker-compose.yml` 中设置的一致。
   - 端口被占用：确保 8000、5432、6379 等端口没有被其他程序占用。

### Q2：启动后 API 返回 500 错误？

**排查步骤：**
1. 查看 API 日志，定位具体报错信息。
2. 检查阿里百炼 API Key 是否正确：
   ```bash
   docker compose exec api env | grep DASHSCOPE
   ```
3. 检查数据库和 Redis 是否正常运行：
   ```bash
   docker compose ps
   ```
   确保 `postgres-rag` 和 `redis-rag` 的状态为 `Up (healthy)`。

### Q3：Docker 构建镜像时卡在 pip install 步骤？

**原因：** 网络访问 PyPI 太慢。

**解决方法：** 在 Dockerfile 中为 pip 配置国内镜像源：

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## 二、认证相关

### Q4：调用 API 时返回 401 或 403？

- **401 (未认证)**：
  - 检查请求头中是否携带了 `X-API-Key` 或 `Authorization: Bearer <token>`。
  - 检查 API Key 是否已过期（默认有效期 30 天）。
- **403 (无权限)**：
  - 确认你的用户角色有对应的权限。只有管理员才能创建新用户和删除文档。

> 注意：`deps.py` 中 `HTTPBearer` 使用 `auto_error=False`，纯 API Key 请求（不带 `Authorization` 头）也可正常通过。

### Q5：忘记管理员 API Key 怎么办？

**解决方法：** 进入 PostgreSQL 容器查看或重置管理员 Key：

```bash
docker compose exec postgres psql -U postgres -d rag_db
```

```sql
-- 查看管理员账户
SELECT user_name, created_at, expires_at FROM api_keys WHERE user_name = 'admin';
-- 如需重置，删除现有管理员记录，重启服务后会自动创建新的管理员 Key
DELETE FROM api_keys WHERE user_name = 'admin';
```

### Q5.1：Swagger UI 的 Authorize 按钮授权无效，接口仍返回 401？

**原因：** 早期版本在接口中手动定义 `authorization: str = Header(None)`，与 Swagger 内置的 Authorize 机制冲突。

**当前状态：** `deps.py` 已改用 FastAPI 原生 `HTTPBearer` 安全方案（`oauth2_scheme = HTTPBearer(auto_error=False)`），配合 `get_current_user_hybrid`，Swagger 的 Authorize 按钮对 JWT 认证可正常工作。这是开发调试工具的兼容性问题，不影响生产环境 API 的实际认证功能。

## 三、检索与生成相关

### Q6：检索结果为空或不相关？

**排查步骤：**
1. 确认文档已成功入库：
   ```bash
   curl http://localhost:8000/api/v1/debug/count
   ```
2. 检查 pgvector 索引是否生效：
   ```sql
   SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'documents';
   ```
3. 尝试切换检索模式，对比效果（`/rag/search?mode=xxx`）：
   - `mode=fast`：向量 + BM25 + RRF 融合，速度最快
   - `mode=accurate`：查询改写 + 向量 + BM25 + 重排序，精度最高
   - `mode=full`：查询扩展 + 改写 + 混合检索 + 重排序 + 答案生成

### Q7：答案包含编造的信息（幻觉）？

**原因：** LLM 没有严格遵守上下文约束。

**解决方法：**
- 在生成答案时开启 `strict_mode=true`，严格限制 LLM 只能使用检索到的文档。
- 开启 `citations=true`，强制答案标注来源，便于溯源核查。
- 开启重排序（`mode=accurate`）过滤低相关文档。

### Q8：检索速度太慢？

**优化方向：**
- 调整检索模式：不需要重排序时使用 `mode=fast`。
- 缩小候选文档数：将 `candidate_multiplier` 从 3 降到 2。
- 开启 Redis 缓存：Embedding 结果会被缓存，重复查询速度提升。
- 检查数据库连接池：确保 `DB_MAX_CONN` 足够大（建议 20-30）。

## 四、性能与监控

### Q9：如何查看系统当前性能指标？

- **Prometheus 指标**：`GET http://localhost:8000/metrics`
- **Grafana 面板**：http://localhost:3000（默认账号 admin/admin）

### Q10：压测时出现大量失败请求？

**排查步骤：**
1. 检查数据库连接池是否耗尽：
   ```bash
   docker compose exec postgres psql -U postgres -d rag_db -c "SELECT count(*) FROM pg_stat_activity;"
   ```
2. 增大连接池大小（`.env` 中的 `DB_MAX_CONN`）。
3. 检查阿里百炼 API 是否被限流（免费额度耗尽会返回 `403 Free quota exhausted`）。
4. 检查用户级限流是否触发（默认 3次/秒，容量 20；高频压测建议提高限流参数）。

## 五、Agent 相关

> 📌 **本节 2026-09-20 从原系统的 `Agent/docs/faq_agent.md` 迁入**（该目录已处置，`git show 351f699 --stat` 可查原文）。
> 原文件共 Q1–Q16，其中 **Q1–Q6 与本 FAQ 逐条重复**、**Q16 与上面 Q10 重复** —— 只迁**不重复的 9 条**。
> ⚠️ **迁入时逐条核过代码**，其中 **A7 原写法是错的**（见该条说明）。

### A1：Agent 调用工具时返回「未找到工具」？

这是 **`mcp_server.py` 的 `TOOLS` 列表与 LLM 工具表不一致** 的典型症状。

```bash
# ① 看 MCP 注册了哪些工具（这是"能不能调"的权威）
curl http://localhost:8000/api/v1/agent/mcp_tools_dynamic -H "Authorization: Bearer <token>"
# ② 看工具健康状态（unhealthy 的会被自动移出可用列表）
curl http://localhost:8000/api/v1/agent/tool_health -H "Authorization: Bearer <token>"
```

- **MCP 注册表**在 `api/mcp_server.py:24` 的 `TOOLS`（**当前 6 项**）。
- **LLM 工具表**在 `api/agent_graph_advanced_learning.py:47-51`（**当前 7 项**）。
- ⚠️ **两张表不一致时，LLM 看得见、却调不到**，且**不报错、不 500**，只回一句「未找到工具」。
  🔴 **本仓当前就有这一处**：`fetch_webpage_html` 在 LLM 表里，**不在** MCP `TOOLS` 里 ⇒ 待修（见 `docs/待办登记-2026-09-20-全仓审计与方向更正.md` §一·C）。
- 不健康的工具（`unhealthy`）会被移出可用列表 —— 这是**设计行为**，不是 bug。

### A2：Agent 的回答不准确或编造信息？

1. 检查是否开了 `strict_mode`（严格模式）。
2. 用轨迹接口看它到底检索到了什么：
   ```bash
   curl http://localhost:8000/api/v1/agent/trace/{thread_id} -H "Authorization: Bearer <token>"
   ```
3. 调系统提示词，明确加「不要编造信息」约束。
4. **先怀疑语料**：本仓知识库里 **35/77 行是测试数据**（见「已知限制 #4」），命中测试垃圾就会答得离谱。

### A3：Agent 反复调用同一个工具、陷入循环？

通常是工具返回的结果不满足 Agent 预期，导致它反复重试。

1. 先用 A1 的两个接口确认工具**本身**是否正常。
2. 看执行轨迹（可视化页面真实存在：`api/static/trace_viewer.html`）：
   ```
   http://localhost:8000/static/trace_viewer.html
   ```
3. 给最大工具调用次数加限制 —— 逻辑在 `api/agent_graph_advanced_learning.py:246` 的 `should_continue`。

### A4：Token 统计的数据重启后丢失？

**部分属正常**。统计同时写内存与数据库，**内存缓存重启即清零，数据库里的历史记录仍在**。

```bash
curl "http://localhost:8000/api/v1/agent/cost/records?days=30" -H "Authorization: Bearer <token>"
```

持久化写入点在 `api/token_tracker.py`（`INSERT INTO token_usage_logs`）。

### A5：预算检查拦截了正常的调用？

```bash
curl http://localhost:8000/api/v1/agent/token/budget -H "Authorization: Bearer <token>"
```

1. 预算用完 ⇒ 管理员可调整用户角色（`free` → `premium`）。
2. 预估成本过高 ⇒ 检查 `api/token_tracker.py:485` 的 `TOOL_ESTIMATED_COST` 是否合理
   （该表通过 `/api/v1/agent/budget/estimates` 暴露）。

> ⚠️ **本仓历史坑**：预算闸门曾因**三处单位错配**而**恒放行**（已修，见 `CHANGELOG`）。
> ⇒ 若你改过 `TOOL_ESTIMATED_COST` 的单位，**必须回归这条**。

### A6：成本面板（Gradio Dashboard）无法访问？

1. 确认服务已起：`docker compose ps`
2. 地址是 **`http://localhost:8000/dashboard`**（**不是**独立端口）。
3. 它由 `api/cost_dashboard.py` 挂载，**默认开启**（`api/main.py:523`：`ENABLE_DASHBOARD` 默认 `"true"`）。
4. ⚠️ **如果你是按 README 的轻量路径起的服务**，命令行里带了 `ENABLE_DASHBOARD=false` ⇒ **面板被刻意跳过**
   （为了不导入 gradio/matplotlib）。**这不是坏了** —— 去掉那个环境变量即可。

### A7：长期记忆（Mem0）不生效？

> 🔴 **2026-09-20 更正 —— 原系统这条写的是「检查 `.env` 中的 `MEM0_API_KEY`」，在本仓是错的。**
> 本仓 Mem0 跑的是**本地模式**，**不连云、也没有 `MEM0_API_KEY` 这个键**
> （`api/memory_store.py:12-39`：向量库 = 本地 `./.mem0/qdrant`；embedder = `DASHSCOPE_API_KEY`；
> Mem0 自己的 LLM = `LLM_API_KEY`/`LLM_BASE_URL`）。
> **按原写法去 `.env` 里找那个键，会白找。**

**正确的排查顺序：**

1. **先看是不是 Qdrant 单实例锁** —— 这是本仓最常见的"记忆不生效"：
   `memory_store.py` 在**模块导入期**就开 `./.mem0/qdrant`，而本地 Qdrant 是单实例锁。
   ⇒ 症状与处置见上面 **Q1.5**（`pytest` 与应用**不能同时跑**）。
2. 确认 `DASHSCOPE_API_KEY` 有效（**embedder 走它**，失效则记忆写不进也搜不出）。
3. 确认 `LLM_*` 四键（若切过 DeepSeek）—— Mem0 内部用 `LLM_MODEL_FAST` 做记忆抽取。
4. 确认写入成功：
   ```bash
   curl "http://localhost:8000/api/v1/agent/memory/search?query=用户偏好" -H "Authorization: Bearer <token>"
   ```
5. 确认对话时带了正确的 `memory_space` 参数。

### A8：如何清空某个用户的长期记忆？

⚠️ **本仓没有提供删除单条记忆的 API**（`api/memory_store.py` 里**没有** `delete` 方法 —— 原系统文档说"可调用 Mem0 的 `delete()`"，**在本仓不成立**）。

可行的办法：**直接清本地存储目录** `./.mem0/qdrant`（或设 `MEM0_DIR` 指到别处），重启服务即可。
⚠️ 这是**整库清空**，不是按用户删。

### A9：Agent 响应速度很慢？

1. **确认 Redis 在跑**（缓存正常是最大的加速项）。
2. **降模型等级**：查询改写等非关键任务改用 `LLM_MODEL_FAST`（默认 `qwen-turbo`）。
3. **减少工具调用次数**：优化 REACT 决策提示词，避免不必要的来回。
4. **检查重排序**：⚠️ 本仓默认模式 `accurate_norerank` **不碰** Cross-Encoder；若你切到 `mode=accurate/full`，
   要等 **2.3GB** 模型加载 —— **本机（8GB 内存）装不下**（见「已知限制 #2」）。
5. **看是不是撞了 A3 的工具循环**（循环会让你觉得"慢"，其实是重复调用）。
