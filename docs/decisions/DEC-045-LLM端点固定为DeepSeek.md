# 决策记录：DEC-045 · LLM 端点固定为 **DeepSeek** —— 默认值与 key 兜底**一起去百炼**

- 日期：2026-10-02（业务方裁定日 · 同日落盘）
- 状态：**已采纳**
- 关联：`DEC-017`（LLM 换 DeepSeek 的**起点**：`.env` 切过去了）·
  `DEC-044`（Task 5 收口 —— 本 DEC 是**同一个落点**的顺延：那次收的是"在哪写"，这次改的是"默认写什么"）·
  `DEC-031` / `DEC-032`（评估脚本改读 `.env`）·
  `docs/specs/llm_factory.md` · `docs/契约/环境变量.md` §4

## 决策事项

业务方 2026-10-02 原话：

> 「**现在不用百炼的了，决定已经不用了，llm 就用 env 的 deepseek api**」

`.env` **早就是 DeepSeek**（`DEC-017` 切的），所以**运行时一行都不用改**。
要裁的是**代码侧**的两处，它们还停在百炼：

| # | 问题 | 核出来的情况 |
|---|---|---|
| **一** | `api/config.py:53-55` 的**默认值**用什么？ | 仍是 `dashscope` + `qwen-turbo` / `qwen-plus`。**CI 没有 `.env` ⇒ 走的就是它**（`ci.yml` 那个"打印生效配置"步骤实测印 `qwen-turbo`） |
| **二** | `api/config.py:52` 的 `LLM_API_KEY = os.getenv(...) **or DASHSCOPE_API_KEY**` 还留吗？ | 🔴 **现在这条是错的** —— `LLM_API_KEY` 一旦缺失，会拿 **embedding（百炼）的 key** 去请求 **DeepSeek 端点**。两个 provider 不同的端点、不同的 key ⇒ **静默错配** |

### 为什么现在要定

- 一是**口径**问题：产品已经只用 DeepSeek，代码默认值还写着百炼 ⇒ **看代码会误判**（本仓最常见的病）。
- 二是**真隐患**：跨 provider 的 key 兜底**只在"刚好两个 provider 同一家"时才对**。
  切走之后就变成"拿 A 家的钥匙开 B 家的门"，而它**不报配置错**，只在运行时 401 ——
  排查时第一个会怀疑的是 key 写错了，而不是**兜底规则**错了。

## 备选方案

| 方案 | 一句话 | 评价 |
|---|---|---|
| **甲 · 默认值改 DeepSeek + 删掉百炼兜底**（**采纳**） | `config.py:53-55` 默认值改 DeepSeek；`config.py:52` 的 `or DASHSCOPE_API_KEY` **删掉**；`LLM_API_KEY` 并入 `validate_config()` | ✅ 代码口径 = 产品口径，**看代码不再误判**；✅ 消灭跨 provider 错配；✅ 与"敏感配置禁止默认值"的既有取向一致（`config.py:38` 那一段） |
| 乙 · 只改默认值，兜底先留着 | 默认值改 DeepSeek，`or DASHSCOPE_API_KEY` 不动 | ⛔ **错配那条隐患原样保留** —— 而它恰恰是"不报错、只在运行时炸"的那类 |
| 丙 · 都不动 | 靠 `.env` 覆盖 | ⛔ CI 无 `.env` ⇒ **实际跑的是百炼的默认值**，而日志里印的是 `qwen-turbo` ⇒ **代码与运行时说的是两回事** |

## 裁定

**取「甲」**（业务方 2026-10-02 在四选项里勾「默认值改 DeepSeek + 去掉百炼兜底」）。核心一句话：

> **代码里的默认值要等于产品真正在用的那家；跨 provider 的 key 兜底必须删掉 ——
> 它省下的一次填表，换来的是一个不报错的错配。**

## 落点

| 件 | 位置 | 改成什么 |
|---|---|---|
| LLM 默认值 | `api/config.py:53-55` | `LLM_BASE_URL=https://api.deepseek.com` · `LLM_MODEL_FAST`/`LLM_MODEL_CHAT=deepseek-v4-flash` |
| LLM key | `api/config.py:52` | `os.getenv("LLM_API_KEY")`（⛔ **删掉** `or DASHSCOPE_API_KEY`） |
| 启动校验 | `api/config.py:58-79` 的 `validate_config()` | 加一项 `LLM_API_KEY`（fail-closed） |
| 契约 | `docs/契约/环境变量.md` §4 | 默认值列 + `LLM_API_KEY` 改 🔴 必填 |
| 示例 | `.env.example` | 「不填 = 走百炼」那句**作废** |
| 自证脚本 | `scripts/ci-local.sh` | ⚠️ **旁证失效** —— 见下「连带影响 ①」 |

## ⚠️ 连带影响（**本 DEC 真正要留下来的部分**）

### ① `ci-local.sh` 那条「自证 `.env` 不在场」的**旁证失效了**

它原来靠**值不同**来证明：本机 `.env` 写 `deepseek-*`，而**临时副本里印 `qwen-turbo`**
⇒ 说明走的是**代码默认值** ⇒ `.env` 确实被拿掉了。

🔴 **默认值改成 `deepseek-v4-flash` 之后，两边同值 ⇒ 这个对比再也分不出**。
⇒ 判据已改成**直接看 `.env` 在不在**（脚本第 4 步本来就有硬断言 `[ ! -e "${TMP}/.env" ]`）。
📌 **同源教训**：**判据不能依赖"两个东西恰好不同"** —— 那个不同**会被一次无关的修改消掉**，
而消掉之后**判据不会报错，只会静默变成永远通过**。

### ② 🔴 **`L6`（百炼控制台开「用完即停」）【不作废】**

业务方说"不用百炼了"，指的是 **LLM**。**Embedding 仍在百炼**（`text-embedding-v2`，
`api/embedding_client.py:12`）。
⇒ 「**用完即停**」保护的是**那把 embedding key**，它**照样会悄悄转付费**。
⇒ 作废的只是 L6 的后半句（「确认 Key 勾选了要用的 **LLM** 模型」）。

### ③ 默认值与 `.env` 同值**消掉了一类 CI 红**

`docs/说明/测试.md` §5.1 记的那类「本地绿、CI 红」（同一键两种默认值）**在模型名这根轴上不会再发生**。
⚠️ **但那根轴本身没消失** —— `.env` 里还有 DB / Redis / 凭据，CI 依旧不读 `.env`。

### ④ ⚠️ 实际先炸的是 import，不是 `validate_config`

`validate_config()` 只在 **startup** 跑（`api/main.py:537`），而 `make_llm()` 在
**模块导入期**就被调用（15 个调用点，见 `DEC-044`）。
⇒ 真缺 `LLM_API_KEY` 时，**先炸的是 `ChatOpenAI(api_key=None)`**，`validate_config` 那条更友好的
报错**很可能走不到**。加它是因为**政策要写下来 + 改导入顺序后仍有人拦**，⛔ 不是因为它能拦住现在这一次。

## 反悔成本

| 要改哪条 | 代价 | 判据（改完怎么验） |
|---|---|---|
| **甲 → 乙/丙（把兜底加回来）** | 低（一行）但后果是原来那条错配 | ⛔ **别加回来** —— 真要"一把 key 全用"，那是**产品决策**，得先裁；判据是 `grep -n 'or DASHSCOPE_API_KEY' api/config.py` **必须为空** |
| **换回百炼（整个 LLM provider 回退）** | 低 —— 改 `config.py:53-55` + `.env` + 重建容器 | 判据：`bash scripts/ci-local.sh` 仍绿（它读的是 `ci.yml` 的 env，与 provider 无关） |
| **改默认模型名** | 低 | ⚠️ **必须同时登记单价** —— `api/test_token_config.py::test_models_actually_in_use_have_explicit_pricing` 会红 |
| **`LLM_API_KEY` 改回可选** | 低 | 同步删掉 `validate_config` 里那一条 + 改 `docs/契约/环境变量.md` §4 的 🔴 |
