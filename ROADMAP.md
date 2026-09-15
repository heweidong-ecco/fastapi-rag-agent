# ROADMAP · fastapi-rag-agent 生产级 RAG + Agent API 服务

- 版本:0.1 · 日期:2026-09-15 · 图例:✔ 完成 · ▶ 进行中 · ⬜ 待办 · ⏸ 暂缓
- 依据:`CLAUDE.md`(架构与修复记录) + git log(截至 `f2dad78` / 2026-09-11)
- **本文件是给新会话的接续锚点** —— 换会话、换机器,从这里读起。

## 当前指针(每次 commit 前更新)

- **下一步**:⬜ **项目重构**(范围待补) → 重构定案后再决定 pytest 与 CI 测试接入
- **本仓库是 PUBLIC**:`github.com/heweidong-ecco/fastapi-rag-agent`,敏感文件已确认未被跟踪
- 里程碑完成即改状态 + commit + 更新本文件(和 `CLAUDE.md` 的指针)

## 交接(2026-09-15 会话末 · 新会话从这里接)

**仓库状态**:`main` 干净,与 `origin/main` 同为 `f2dad78`,零差异。本地孤儿分支 `docs/api-doc-final-review`(已并入)已删除。

**本次做了什么**:
1. 确认 GitHub 链路可用(`git ls-remote` 通;`gh` 已登录 `heweidong-ecco`)
2. 删除已合并的残留分支
3. 新增 CI 骨架 `.github/workflows/ci.yml` —— 只跑 `compileall`,**不含 pytest**

**动手前先知道这些**(本次体检发现,均已挂账未处理):
- `CLAUDE.md` 的「模型命名约定」仍写 `qwen-turbo`/`qwen-plus`,但 `.env` 已切 **DeepSeek**(2026-09-09)。下一个会话读 CLAUDE.md 会按 qwen 去改代码 —— **这是目前最容易踩的坑**
- `CLAUDE.md`「已知遗留问题」里"DashScope 免费额度已耗尽"同样已过期
- `硬性指标终极核查清单.md` 28 项**一项未勾**,P99/失败率/并发/Grafana 都还没有实测数据

## 里程碑

| ID | 里程碑 | 产出 | 验收 | 状态 |
|---|---|---|---|---|
| M0 | 主体功能搭建 | FastAPI + pgvector + Redis + LangGraph Agent;检索三模式/混合检索/重排序/SSE/双认证/限流配额 | 接口可跑通 | ✔ |
| M1 | 全面复审 | `CLAUDE.md` 记录的 **24 项修复**(启动崩溃/认证失效/数据丢失等) | 修复入库 | ✔ |
| M2 | 实机验证修复 | 3 个 commit:LLM env 可配、查询改写空返回回退、BM25 缓存失效 | 实机跑通 | ✔ |
| M3 | 搬运至 GitHub + 链路验证 | 仓库创建(2026-08-17)、本地↔远端同步确认 | 零差异 | ✔ |
| M4 | CI 骨架 | `.github/workflows/ci.yml`(compileall,Python 3.10) | Actions 首次跑绿 | ▶ |
| M5 | **项目重构** | 范围待补 | 待定 | ⬜ |
| M6 | 测试与评估接入 | pytest 套件 + RAGAS 评估复跑 | 待重构后定 | ⏸ |

## 已登记、暂不处理

| 项 | 来源 | 说明 |
|---|---|---|
| 6 个闲置 skill | `/doctor` 体检 2026-09-15 | 31 天 0 使用:`agent-system-creator`/`receiving-code-review`/`using-git-worktrees`/`dispatching-parallel-agents`/`writing-skills`/`subagent-driven-development`。业务方选择维持现状 |
| `~/.claude/local` 266MB | `/doctor` 体检 2026-09-15 | 旧版安装残留,**不在本仓库**,未删 |
| `bad_cases.md` 三项 | 2026-06-28 评估 | `answer_relevancy` 仍为 NaN;`context_precision` 仅 0.4369(当时未开 rerank);评估集缺拒答类样本 |
| Agent 各类死代码 | `CLAUDE.md` | `'''...'''` 注释保留的旧实现,不影响运行 |

> **重构前建议先读**:`CLAUDE.md` 的「关键开发模式」与「认证与授权」两节 —— 那里记着几个"看着安全实则有坑"的契约(中间件抛异常不被捕获、`HTTPBearer` 必须 `auto_error=False`、`get_db()` 连接池契约)。
