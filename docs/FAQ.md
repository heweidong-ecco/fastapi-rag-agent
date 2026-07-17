# 📋 常见问题与故障排查 (FAQ)

将 FAQ 整合到项目中

1.  将以上内容保存为 `docs/FAQ.md`。
2.  在 `README.md` 中添加链接：
    ```markdown
    ## ❓ 常见问题

    遇到问题请先查阅 [FAQ 与故障排查](docs/FAQ.md)。


-----------------------
提交并推送：
bash
git add docs/FAQ.md README.md
git commit -m "docs: 添加FAQ与故障排查文档"
git push

## 一、部署相关

### Q1：执行 `docker compose up -d` 后，API 容器一直在重启？

**排查步骤：**
1. 查看 API 日志：
   ```bash
   docker compose logs api --tail 50
常见原因：

.env 文件未配置：确保你复制了 .env.example 为 .env，并填入了真实的 DASHSCOPE_API_KEY。
数据库密码不一致：.env 中的 POSTGRES_PASSWORD 必须与 docker-compose.yml 中设置的一致。
端口被占用：确保 8000、5432、6379 等端口没有被其他程序占用。
Q2：启动后 API 返回 500 错误？

排查步骤：

查看 API 日志，定位具体报错信息。
检查阿里百炼 API Key 是否正确：

bash
docker compose exec api env | grep DASHSCOPE
检查数据库和 Redis 是否正常运行：

bash
docker compose ps
确保 postgres-rag 和 redis-rag 的状态为 Up (healthy)。
Q3：Docker 构建镜像时卡在 pip install 步骤？

原因： 网络访问 PyPI 太慢。

解决方法： 在 Dockerfile 中为 pip 配置国内镜像源：

dockerfile
RUN pip install --user --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
二、认证相关

Q4：调用 API 时返回 401 或 403？

401 (未认证)：

检查请求头中是否携带了 X-API-Key 或 Authorization: Bearer <token>。
检查 API Key 是否已过期（默认有效期 30 天）。
403 (无权限)：

确认你的用户角色有对应的权限。只有管理员才能创建新用户和删除文档。
Q5：忘记管理员 API Key 怎么办？

解决方法：

进入 PostgreSQL 容器查看或重置管理员 Key：

bash
docker compose exec postgres psql -U postgres -d rag_db
查看管理员账户：

sql
SELECT user_name, created_at, expires_at FROM api_keys WHERE user_name = 'admin';
如果需要重置，删除现有管理员记录，重启服务后会自动创建新的管理员 Key。
三、检索与生成相关

Q6：检索结果为空或不相关？

排查步骤：

确认文档已成功入库：

bash
curl http://localhost:8000/api/v1/debug/count
检查 pgvector 索引是否生效：

sql
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'documents';
尝试切换检索模式，对比效果：

mode=fast：纯向量检索
mode=accurate：向量 + BM25 + 重排序
Q7：答案包含编造的信息（幻觉）？

原因： LLM 没有严格遵守上下文约束。

解决方法：

在生成答案的 Prompt 中增加强约束：

text
如果上下文中没有足够信息，请直接说"根据现有资料，无法回答此问题"。
开启 strict_mode=true，严格限制 LLM 只能使用检索到的文档。
提高相似度阈值，过滤低相关文档：

python
SIMILARITY_THRESHOLD = 0.7  # 在 rag_pipeline.py 中调整
Q8：检索速度太慢？

优化方向：

调整检索模式：不需要重排序时使用 mode=fast。
缩小候选文档数：将 candidate_multiplier 从 3 降到 2。
开启 Redis 缓存：Embedding 结果会被缓存，重复查询速度提升 5 倍以上。
检查数据库连接池：确保 DB_MAX_CONN 足够大（建议 20-30）。
四、性能与监控

Q9：如何查看系统当前性能指标？

访问 Grafana 面板：http://localhost:3000（默认账号 admin/admin）。

Q10：压测时出现大量失败请求？

排查步骤：

检查数据库连接池是否耗尽：

bash
docker compose exec postgres psql -U postgres -d rag_db -c "SELECT count(*) FROM pg_stat_activity;"
增大连接池大小（.env 中的 DB_MAX_CONN）。
检查阿里百炼 API 是否被限流。
text

### Q2 ：Swagger UI 的 Authorize 按钮授权无效，接口仍返回 401？

**现象：**
- 用 curl 或 Python 脚本调用接口，JWT 认证正常。
- 但在 Swagger UI 中，点击顶部 **Authorize** 按钮填入 Token 后，接口仍返回 `AUTH_MISSING`。

**原因：**
接口中手动定义了 `authorization: str = Header(None)` 参数，导致 Swagger 生成的 UI 与内置的 Authorize 机制冲突。Swagger 无法正确地将 Authorize 按钮设置的 Token 映射到手动定义的 Header 参数上。

**解决方法：**
使用 FastAPI 原生的 `HTTPBearer` 安全方案替代手动 Header 解析。

1.  在 `deps.py` 中，使用 `HTTPBearer` 定义认证方案：
    ```python
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    oauth2_scheme = HTTPBearer()

    async def get_current_user_hybrid(
        x_api_key: str = Header(None),
        credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
    ) -> str:
        if x_api_key:
            return await get_current_user(x_api_key)
        if credentials:
            token = credentials.credentials
            return verify_jwt_token(token)
        raise AppException(ErrorCode.AUTH_MISSING, "请提供 API Key 或 Bearer Token")

2. 在接口定义中，删除手动定义的 authorization 参数，仅依赖 Depends(get_current_user_hybrid) 进行认证。
3. 重启服务后，Swagger 的 Authorize 按钮即可正常工作。
注意： 这是一个开发调试工具的兼容性问题，不影响生产环境中 API 的实际认证功能。用 curl、Postman 或其他代码调用 API 不受任何影响。





