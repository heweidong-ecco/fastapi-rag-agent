# 决策记录:DEC-013 · M6 的测试分层,以及 CI 到底接哪一层

- 日期:2026-09-17
- 状态:已采纳
- 关联:`api/test_rag_search.py` · `api/pytest.ini` · `.github/workflows/ci.yml` · `ROADMAP.md`「⑦ M6」· `docs/复盘/2026-09-17-给用户的选项里写了没验证的前提.md`

## 决策事项

M6 = 「单模块测试闭环」。要定四件事:

1. **选哪个模块** —— 这是闭环的靶子
2. **测试怎么分层** —— 全都要真 postgres + 外网?那 CI 就接不进来
3. **CI 接哪一层** —— `ci.yml:4` 白纸黑字写着「等本项目重构定案后再接入 —— 见 ROADMAP.md 的 M6」,**本决策就是来兑现这句话的**
4. **顺路挖到的 `mode` 静默兜底**,要不要写进测试

## 背景与约束

**靶子其实没得选。** `CODE_INVENTORY.md:159` 建议二选一:**「最终留下的那套 Agent」** 或 **`/rag/search`**。
前者被**两条**同时挡死:

- **M5 组 1 的 C 档裁决还没做** —— 哪一代是产品版本**未定**(`ROADMAP.md:18` 明说 Agent 不代判)
- **它要 chat LLM** —— `CLAUDE.md` 已登记 qwen-turbo/plus **免费额度耗尽**。**跑不通 = 没有闭环**,M6 的全部意义就没了

而 `/rag/search` **实测跑通**:`mode=fast` → 200,825ms,`docs[0].from == "both"`(BM25 与向量两路都命中、RRF 真的融合了)。
这条路径**不碰 torch**(`create_fast_pipeline` 的 `enable_rerank=False`)、**不调 chat LLM**(`generate_answer` 默认 `False`)。

🔴 **而它今天测试覆盖是 0**:`test_search.py` 测的是 `/rag/pg_search`、`test_locust_payload.py` 只做 OpenAPI 结构断言。
**RRF 恰恰是 2026-08-17 复审里出过 bug 的地方**(§0-4:按 3 元组解包而 `db.search_similar` 返 4 列,必抛 `ValueError`)。

**运行时约束(实测,不是猜的)**:

| 组件 | `/rag/search` 的 L1/L2 需不需要 |
|---|---|
| **Redis** | 🔴 **必需** —— `RateLimitMiddleware` 对每个非公开路径都打 Redis,且 `rate_limiter.py` **没有 `except RedisError`** ⇒ **Redis 不通 = 全站 500**(实测) |
| **Postgres** | ❌ 不需要 —— 断言要么在中间件层、要么在 handler 之前被挡下,要么把库调用 patch 掉了 |
| **外网 embedding** | ❌ 不需要(L2 用 patch) |
| **torch** | ❌ 不需要 |

## 备选方案

**方案一 · 测试怎么分层**

| 方案 | 思路 | 缺点 |
|---|---|---|
| **甲** | **按"需要什么"分四层**(L0 纯逻辑 / L1 契约 / L2 行为 / L3 集成) | 分层的概念成本 —— 但一次讲清后每层各自独立 |
| 乙 | 全部走 HTTP,一套跑到底 | **CI 必然接不进来**(要 postgres + 外网 + torch) |
| 丙 | 只测 `_rrf_fusion` 纯函数 | 零成本,但**锁不住"mode 挑了哪个管线"** —— 而那正是 `/rag/search` 的主职责 |

**方案二 · CI 接哪一层**

| 方案 | 思路 | 缺点 |
|---|---|---|
| **甲** | **加 `services: redis`**,接 L0+L1+L2 | 多一个 service(但 redis **零迁移、零数据、零种子**) |
| 乙 | **零 service**,只接 L0 | 便宜,但 **HTTP 层 CI 看不见** —— mode 分派写错它拦不住 |
| 丙 | 连 postgres 一起接,跑全套 60 条 | 要建表/迁移,工作量与 flaky 面都大 |

**方案三 · `mode` 静默兜底要不要入测**

`api_v1_rag.py:480` 是个裸 `else`,`mode=garbage` **实测 → 200**,静默落进 `accurate_norerank`
(多跑一次查询改写 = 多花钱、多延迟)。拼错一个字母,语义被悄悄换掉,**不报错**。

| 方案 | 缺点 |
|---|---|
| 甲 · **只记录,不写进测试** | 少一层保护 |
| 乙 · 写一条断言把兜底锁住 | 🔴 **测试把缺陷固化成"预期行为"** —— 将来谁真去修,测试反而变红 |
| 丙 · M6 里直接修 | 把"加测试"与"改行为"混进一个 diff,**违反本仓「一 PR 一逻辑变更」** |

## 评估标准

能否在 CI 里真跑起来 / 拦截能力(改坏了会不会红) / 是否把缺陷固化成契约 / 是否守住一 PR 一逻辑变更。

## 方案对比

- **方案一**:丙 被否的关键 —— 它测的是**函数**,不是**端点**。`/rag/search` 的主职责恰恰是"按 mode 挑管线",
  而那行 `if/elif/else` **不在 `_rrf_fusion` 里**,丙 看不见它。
- **方案二**:乙 被否的关键 —— M6 要交的是**闭环**,不是**半条**。只接 L0 等于 CI 仍然看不见端点层。
  丙 被否 —— **postgres 不像 redis 那样零成本**(要建表),而实测已证明 L1/L2 **根本不需要它**。
- **方案三**:乙 被否是因为它**方向反了** —— 门的作用是拦住坏改动,不是把坏现状**焊死**。

## 最终决策 + 理由

**✅ 三个都取甲。**

1. **靶子 = `/rag/search`**(不是选出来的,是另一条路被证据堵死了)
2. **分四层**;CI 接 **L0+L1+L2**,L3 挂 `@pytest.mark.integration` 留本机
3. **CI 加 `services: redis:7`**;`import main` 需要非空 key,故 CI 给 **dummy 环境变量**(离线用例永不真调用)
4. **`mode` 兜底只记录,不写进测试**

## 影响与后续行动

- 新建 `api/test_rag_search.py`(21 条离线 + 1 条集成)· `api/pytest.ini`(注册 `integration` marker ——
  **本仓此前没有任何 pytest 配置**,自定义 marker 会报 `PytestUnknownMarkWarning`)
- `ci.yml` 从 1 个 job 变 2 个;`ci.yml:4` 那句「待 M6」**兑现**
- 🔴 **同批修掉一个会挂死 CI 的缺陷**:`cost_dashboard.py:218` 在**导入期**建 Gradio Blocks,
  Gradio 随即起**非 daemon** 线程去连 `huggingface.co` 发遥测;**网络不通时它们卡在 TCP connect 上永不返回**,
  主线程永远停在 `threading._shutdown` ⇒ **22 条用例全 PASSED,进程退不出去**。
  修法 = `api/conftest.py` 在 `import main` **之前**设 `GRADIO_ANALYTICS_ENABLED=False`。
  ⚠️ 它**随机复现**(取决于当次 DNS/TCP 是快速失败还是挂住)—— 卡住的 CI job 会一直耗到超时上限。
  详见 `docs/复盘/2026-09-17-看到汇总行就以为跑完了.md`
- **未接进 CI 的已登记**(不是忘了):L3 集成层 · 既有测试里**另有 27 条也是离线的**
  (死 postgres 下实测 48 passed,其中 21 条来自新文件)

## 反悔成本

**低。** 删掉新文件与 `pytest.ini`、把 `ci.yml` 退回单 job,即完全回到改动前。

⚠️ 但有**一处不可逆的收益**不该退:关掉 Gradio 遥测那条。退回就等于**把随机挂死放回 CI**。
