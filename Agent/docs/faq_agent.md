
# 📋 Agent 系统 FAQ 与故障排查

## 一、部署相关

### Q1：执行 `docker compose up -d` 后，API 容器一直在重启？

**排查步骤：**
1. 查看 API 日志：
   ```bash
   docker compose logs api --tail 50
   ```
2. 常见原因：
   - **`.env` 文件未配置**：确保你复制了 `.env.example` 为 `.env`，并填入了真实的 `DASHSCOPE_API_KEY`。
   - **数据库密码不一致**：`.env` 中的 `POSTGRES_PASSWORD` 必须与 `docker-compose.yml` 中设置的一致。
   - **端口被占用**：确保 8000、5432、6379 等端口没有被其他程序占用。

### Q2：Docker 构建镜像时卡在 `pip install` 步骤？

**原因：** 网络访问 PyPI 太慢。

**解决方法：** 在 `Dockerfile` 中为 pip 配置国内镜像源：
```dockerfile
RUN pip install --user --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### Q3：Embedding 或 LLM 调用失败？

**排查步骤：**
1. 检查 `DASHSCOPE_API_KEY` 是否正确。
2. 检查网络是否能访问阿里云：
   ```bash
   curl https://dashscope.aliyuncs.com
   ```
3. 检查阿里百炼控制台的额度是否用完。

---

## 二、认证相关

### Q4：调用 API 时返回 401 或 403？

**401 (未认证)：**
-   检查请求头中是否携带了 `Authorization: Bearer <token>`。
-   检查 Token 是否已过期（默认有效期 15 分钟）。

**403 (无权限)：**
-   确认你的用户角色有对应的权限。只有管理员才能创建新用户和删除文档。

### Q5：忘记管理员 API Key 怎么办？

**解决方法：**
1. 查看应用启动日志：
   ```bash
   docker compose logs api | grep "管理员 API Key"
   ```
2. 如果没有找到，进入 PostgreSQL 容器查看：
   ```bash
   docker compose exec postgres psql -U postgres -d rag_db -c "SELECT user_name, key_hash, created_at FROM api_keys WHERE user_name='admin';"
   ```
3. 如果需要重置，删除现有管理员记录后重启服务，会自动创建新的管理员 Key。

### Q6：Swagger UI 的 Authorize 按钮授权无效，接口仍返回 401？

**原因：** 接口中手动定义了 `authorization: str = Header(None)` 参数，与 Swagger 内置的 Authorize 机制冲突。

**解决方法：** 在 Swagger 中测试时，使用 curl 或 Postman，在请求头中手动添加 `Authorization: Bearer <token>`。

---

## 三、Agent 工具调用相关

### Q7：Agent 调用工具时返回“未找到工具”？

**排查步骤：**
1. 检查 MCP Server 是否正确注册了该工具：
   ```bash
   curl http://localhost:8000/api/v1/agent/mcp_tools_dynamic \
     -H "Authorization: Bearer <token>"
   ```
2. 检查 `mcp_server.py` 中的 `TOOLS` 列表是否包含该工具。
3. 检查工具的健康状态：
   ```bash
   curl http://localhost:8000/api/v1/agent/tool_health \
     -H "Authorization: Bearer <token>"
   ```
   如果工具状态为 `unhealthy`，Agent 会自动跳过该工具。

### Q8：Agent 的回答不准确或编造信息？

**排查步骤：**
1. 检查是否开启了 `strict_mode`（严格模式）。
2. 检查检索到的文档是否相关——可通过轨迹接口查看：
   ```bash
   curl http://localhost:8000/api/v1/agent/trace/{thread_id} \
     -H "Authorization: Bearer <token>"
   ```
3. 调整系统提示词（System Prompt），增加“不要编造信息”的约束。

### Q9：Agent 反复调用同一个工具，陷入循环？

**原因：** 工具返回的结果不满足 Agent 的预期，导致它反复重试。

**解决方法：**
1. 检查工具的健康状态，确认工具是否正常工作。
2. 查看执行轨迹，观察工具返回的具体内容：
   ```bash
   curl http://localhost:8000/static/trace_viewer.html
   ```
3. 在 Agent 的 `should_continue` 函数中增加最大工具调用次数限制。

---

## 四、成本统计相关

### Q10：Token 统计的数据重启后丢失？

**原因：** Token 统计数据同时存储在内存和数据库中，但内存缓存重启后会清零。

**说明：** 重启后，内存缓存中的数据会丢失，但数据库中的历史记录仍然存在。你可以通过以下接口查看持久化的数据：
```bash
curl http://localhost:8000/api/v1/agent/cost/records?days=30 \
  -H "Authorization: Bearer <token>"
```

### Q11：预算检查拦截了正常的调用？

**排查步骤：**
1. 检查当前预算状态：
   ```bash
   curl http://localhost:8000/api/v1/agent/token/budget \
     -H "Authorization: Bearer <token>"
   ```
2. 如果预算已用完，管理员可以调整用户的角色（如从 `free` 升级为 `premium`）。
3. 如果预估成本过高，检查 `TOOL_ESTIMATED_COST` 配置是否合理。

### Q12：成本面板（Gradio Dashboard）无法访问？

**排查步骤：**
1. 确认服务已启动：`docker compose ps`
2. 访问地址应为 `http://localhost:8000/dashboard`（注意不是独立端口）。
3. 检查 `cost_dashboard.py` 是否正确加载。

---

## 五、长期记忆相关

### Q13：长期记忆（Mem0）不生效？

**排查步骤：**
1. 检查 Mem0 配置是否正确（`.env` 中的 `MEM0_API_KEY`）。
2. 确认记忆已成功添加：
   ```bash
   curl http://localhost:8000/api/v1/agent/memory/search?query=用户偏好 \
     -H "Authorization: Bearer <token>"
   ```
3. 检查 Agent 对话时是否携带了正确的 `memory_space` 参数。

### Q14：如何清空某个用户的长期记忆？

**解决方法：**
目前没有直接删除单条记忆的 API，但可以通过 Mem0 官方控制台管理记忆数据。或者通过代码调用 Mem0 的 `delete()` 方法。

---

## 六、性能相关

### Q15：Agent 响应速度很慢？

**优化方向：**
1. **开启缓存**：确保 Redis 缓存正常工作。
2. **降低模型等级**：将查询改写等非关键任务改用 `qwen-turbo`。
3. **减少工具调用次数**：优化 Agent 的决策 Prompt，避免不必要的工具调用。
4. **检查重排序模型**：如果使用了 BGE-Reranker，确保模型已加载且推理速度正常。

### Q16：压测时出现大量失败请求？

**排查步骤：**
1. 检查数据库连接池是否耗尽：
   ```bash
   docker compose exec postgres psql -U postgres -d rag_db -c "SELECT count(*) FROM pg_stat_activity;"
   ```
2. 增大连接池大小（`.env` 中的 `DB_MAX_CONN`）。
3. 检查阿里百炼 API 是否被限流。
4. 检查 Docker 容器的资源使用情况：
   ```bash
   docker stats
   ```
```

---

### 将 FAQ 整合到项目中

1.  将以上内容保存为 `docs/faq_agent.md`。
2.  在 `README.md` 中添加链接：
    ```markdown
    ## ❓ 常见问题

    遇到问题请先查阅 [FAQ 与故障排查](docs/faq_agent.md)。
    ```
3.  提交并推送：
    ```bash
    git add docs/faq_agent.md README.md
    git commit -m "docs: 添加项目二FAQ与故障排查文档"
    git push
    ```

---

