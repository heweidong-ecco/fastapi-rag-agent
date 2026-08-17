# 📋 常见问题与故障排查 (FAQ)

## 一、部署相关

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
