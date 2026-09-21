# 决策记录：DEC-031 · RAGAS 的依赖隔离（独立 venv）与 judge LLM 改走 `.env`

- 日期：2026-09-21
- 状态：**已采纳并执行**
- 关联：`ROADMAP.md` 剩余待办 **#5 RAGAS 实跑验证** · `api/evaluate_with_ragas.py`

## 决策事项（**两件**，同一次做）

1. **RAGAS 的依赖装到哪？** —— 装进产品 venv，还是**另起一个**？
2. **judge LLM 走哪家？** —— 脚本原本**硬编码 DashScope**，而它的 chat 额度**已耗尽（403）**。

## 背景（实测，不是推断）

### 拦路虎一：依赖会砸坏产品 venv

`api/requirements.txt` 钉的是 **`ragas>=0.1.18`**（**没钉死**）。`pip install --dry-run` 实测：

| 装法 | 它会做什么 | 判定 |
|---|---|---|
| **默认**（`ragas>=0.1.18` ⇒ 解析到 **0.4.3**） | `openai` **1.109.1 → 2.54.0**（**主版本跳跃**）· 新装 `scipy` / `scikit-network` / `rich` | ❌ |
| **钉死** `ragas==0.1.21` | `langchain` **0.3.30 → 0.2.17** · `langchain-core` **→ 0.2.43** · `langchain-openai → 0.1.25`（**全是降级**） | ❌ |

**两条路都会动到产品 venv 的核心依赖。** 而本仓在这上面**吃过亏** ——
`ROADMAP.md` 记着：2026-09-20 一次实测发现**三条 Agent 路径曾【全断】**，
而「**七个 bug 没有一个是业务逻辑错 —— 全是【依赖漂移】**」。

⚠️ **额外风险**：venv 现状是 **116 passed / 0 failed**（今天刚跑）。
`openai` 主版本跳跃或 `langchain` 降级，**极可能把这个基线弄红**。

### 拦路虎二：脚本硬编码 DashScope

`api/evaluate_with_ragas.py:35-45` 原本：

```python
eval_llm = ChatOpenAI(model="qwen-plus", api_key=os.getenv("DASHSCOPE_API_KEY"),
                      base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
```

而 **DashScope 的 chat 免费额度已耗尽（403）** ⇒ **装好包也跑不动**。
更别扭的是：它**绕开了项目早就切过去的 DeepSeek**（本仓 `.env` 的 `LLM_*` 三项）。

### ✅ 关键事实：这脚本**可以**隔离

实测 `api/evaluate_with_ragas.py` 的 import **全是第三方**（`json` / `time` / `httpx` / `os` /
`dotenv` / `datasets` / `ragas` / `langchain_openai` / `langchain_core`）——
**不 import 任何本仓模块**，与应用的耦合**只有 HTTP**（`POST /auth/login` + `POST /rag/search`）。
⇒ **它能完全独立运行，不需要产品 venv 里的任何东西。**

## 备选方案

| 方案 | 一句话 | 本次 |
|---|---|---|
| **甲 · 装进产品 venv（默认版本）** | 最省事 | ❌ `openai` 主版本跳跃 |
| **乙 · 装进产品 venv（钉 `ragas==0.1.21`）** | 避开主版本跳跃 | ❌ 改成降级 `langchain`，**同样砸基线** |
| **丙 · 独立 `venv-ragas/`**（**采纳**） | 评估脚本的依赖**与产品运行环境隔离** | ✅ |

**业务方 2026-09-21 裁**：judge LLM「**改成读 `.env` 走 DeepSeek（推荐）**」——
即**脚本要动**。**依赖装到哪**由本 DEC 记录（`--dry-run` 是动手前才跑的）。

## 决策与理由

**丙。** 三条理由：

1. **证据是硬的，不是"保险起见"** —— 两条路**各自**会破坏产品 venv 的核心依赖，**没有第三条"就地装"的路**。
2. **这个脚本本来就不属于产品运行环境** —— 它是**评估工具**，跑在开发机上、通过 HTTP 打应用。
   **评估工具的重依赖没有理由和产品运行时混在一起** —— 这正是本仓"依赖漂移"那条教训的**应用**。
3. **反悔成本极低** —— 它是 `.gitignore` 的一个目录，**删掉即可**；产品 venv **一个包都没动**。

**judge LLM 改走 `.env`**（业务方已裁）—— 顺带修掉一个隐患：
原写法把 `qwen-plus` 和 DashScope 的 base_url **写死在脚本里** ⇒
**项目换模型时这个脚本不会跟着换，而它看起来"还在正常工作"**。

## 执行内容

### 1. 独立 venv

```bash
python3.10 -m venv venv-ragas
./venv-ragas/bin/pip install "ragas==0.1.21" "datasets==2.21.0" httpx python-dotenv
```

⚠️ **`ragas==0.1.21` 是【必须钉】的** —— 脚本写的是 **0.1.x 的 API**
（`from ragas.metrics import faithfulness…` + `evaluate(ds, metrics=[…], llm=…, embeddings=…)`）。
**0.4.x 的 API 完全变了**，装默认版**跑不起来**。

`.gitignore` 新增 `venv-ragas/`（并写明**为什么隔离**）。

### 2. judge LLM 改走 `.env`

```python
eval_llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL_CHAT", "deepseek-chat"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    temperature=0,
)
# ⚠️ embedding 保持 DashScope —— chat 额度耗尽了，embedding 那边仍可用
eval_embeddings = OpenAIEmbeddings(
    model="text-embedding-v2",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
```

### 3. 前置条件（已核）

| 项 | 状态 |
|---|---|
| Postgres / Redis | ✅ healthy（`postgres-rag` / `redis-rag`） |
| API 在跑 | ✅ `GET /health` → 200（database ok · redis ok） |
| 库里有文档 | ✅ `rag_db.documents = 77`，正文就是 **Python / FastAPI / Docker** |
| 评估集主题对得上 | ✅ 37 问全在 Python/FastAPI 上 —— **检索有东西可命中** |
| `.env` 八个键 | ✅ 全有值 |
| 写入风险 | ✅ 脚本只走 `POST /rag/search`（**只读**）⇒ **不污染 `agent-eval-gate` 的评测基线** |

## ⬜ 遗留 / 已知不确定

1. 🔴 **`ragas==0.1.21` 与脚本的兼容性还没验** —— 装完**先跑一次 import + 一条最小
   `evaluate()`**，确认 API 对得上，**再跑全量 37 条**。跑不通就回来改钉的版本。
2. ⚠️ **`api/requirements.txt` 里 `ragas>=0.1.18` 这个不钉死的写法没改** ——
   它会把**用 `requirements.txt` 建环境的人**引向 0.4.3。**本次没动它**（改它会影响 CI 装包），
   **登记在案**。
3. ⚠️ **RAGAS 指标本身的有效性**未评估 —— 本次只回答「**能不能跑通**」。

## 反悔成本

**极低** —— 删掉 `venv-ragas/` 即完全回退；**产品 venv 一个包都没动**
（`/tmp/venv-freeze-before-ragas.txt` 存了 160 包的存底，可逐包比对）。

## 变更记录

- 2026-09-21 建立（业务方裁 judge 走 DeepSeek；依赖隔离由本次 `--dry-run` 实测决定）。
