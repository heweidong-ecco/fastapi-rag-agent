# 决策记录：DEC-044 · `①b · Task 5（L2）` —— **只做构造收口，⛔ 不做自动兜底**

- 日期：2026-10-02（业务方裁定日 · 同日落盘）
- 状态：**已采纳（形态改写过）** —— 本 DEC 定的是 `①b · Task 5` 的**实际形状**，
  ⚠️ **它与 `token_tracker.md` 里那份【原始计划】不同**：原计划要「换下一个模型」，**落地的是"只收口"**
- 关联：`DEC-040`（额度统一到 token 一套 —— 同类"收口"思路的先例）·
  `DEC-043`（断路器 —— 它的 `model:` 那一类**正是本 DEC 推迟掉的东西**）·
  `docs/specs/llm_factory.md`（落点的 spec）· `docs/specs/token_tracker.md`（①b Task 5 的修订块）·
  `fastapi-rag-agent-TODO待办/LLM模型路由与额度策略-待裁-20260930.md`

## 决策事项

`①b · Task 5（L2）` 的原标题是「**某个模型的免费额度耗尽 ⇒ 换下一个**」。
动手前发现它其实是**两件事**，而且**价值差得很远**：

| # | 问题 | 原计划怎么写的 | 核出来的情况 |
|---|---|---|---|
| **一** | 要不要把 **15 个 LLM 构造点**收进一个工厂？ | ⛔ **一个字没提** —— 计划默认「换模型」是在别处加逻辑 | 全仓 **15 处**各自写 `ChatOpenAI(model=…, api_key=…, base_url=…, max_tokens=…)`，**三个值取自同一组配置常量**却在 15 处各抄一遍 |
| **二** | 收口之后，**要不要顺带做"主 provider 用完 ⇒ 自动切备用"**？ | ✅ 这是计划的主体 | 技术上可行（`Runnable.with_fallbacks` 存在），**但有一处静默缺陷**（见下 ⚠️） |

### 为什么现在要定

- **一的价值与"换 provider"无关**：就算永远只用 DeepSeek，**改 `max_tokens` 也要动 15 处**。
  本仓对"同一件事有两个落点"有明确前科（`DEC-029` 两套口径差 35 倍 → `DEC-040` 花一整轮合掉）。
- **二有一个"看起来能做、实际会静默出错"的岔路** —— 见下方实证。
  **如果不先把这条写下来，下一个人会照着原计划直接上 `with_fallbacks`，然后账目悄悄错掉。**

## ⚠️ 关键实证（**2026-10-02 实测 · 这条是整个 DEC 的重心**）

`Runnable.with_fallbacks(fallbacks, exceptions_to_handle=(...))` —— 拿**真的 `ChatOpenAI`** 当备用实测：

```
主.with_fallbacks([真的 ChatOpenAI 备用])
  w.bind_tools(tools)  →  ✅ 能用，且返回的对象仍然带兜底
  w.model_name         →  🔴 永远返回【主】模型名
```

> 🔴 **我在这上面判断错过一次，记下来**：我先查的是**类**（`RunnableWithFallbacks` 上没有
> `bind_tools` / `model_name`）⇒ 断言「**整个服务起不来**」（5 处 `bind_tools` 会 AttributeError）。
> **⛔ 那是错的** —— 实例有 `__getattr__` 委托。后来是一条失败的测试把我逼去查**实例**才发现。
> 📌 **教训**：`hasattr(类, x)` **不等于** `hasattr(实例, x)`。
> 📌 反证测试钉在 `api/test_llm_factory.py::test_wrapping_would_silently_break_cost_attribution`。

⇒ **结论**：`with_fallbacks` **不会炸**，**真正的缺陷是静默的** ——
**备用模型烧掉的 token，会被那 4 处成本记账记到【主】模型头上**（`model_name` 不换）。

## 备选方案

| 方案 | 一句话 | 评价 |
|---|---|---|
| **甲 · 只做构造收口**（**采纳**） | 新建 `api/llm_factory.py` 的 `make_llm(model_role, token_role)`，15 处改走它；**⛔ 不加任何降级/重试逻辑** | ✅ **零行为变化**（角色按改动前的取值**原样固化**，见 `EXPECTED_ROLES`）；✅ **改 `model` / `max_tokens` / 换 provider 只剩一个落点**；✅ 顺带修掉 `evaluate_with_ragas.py` 那个**与 `config.py` 不一致的兜底值**；✅ **门禁能从"每处各自写对"升级成"工厂以外零直连"** |
| 乙 · 收口 **+** 自动兜底 | 甲 + `主.with_fallbacks([备])` | ✅ **收益是真的**：额度耗尽那一刻**不用人工介入**<br>⛔ **代价是静默的**：备用接管时**账记错**（见上实证）⇒ 要**额外**再做一层"谁真的答的"的传递<br>⛔ **收益只在"额度耗尽那一刻"兑现**，而那一刻**本来就有人工动作**（改 `.env` + 重建容器）<br>⚠️ **而且它解不了这个项目的真实问题**：本轮限制是**免费额度一次性用完**（`L3` 已裁「永久，人工解封」）⇒ 兜底只是把"报错"延后到**第二个 key 也耗尽** |
| 丙 · 不改 | 维持 15 处直连 | ⛔ 换 provider / 改上限**必然漏**（本仓栽过：`evaluate_with_ragas.py` 就是"计划里一次没提"的那处）；⛔ 门禁**只能钉"每处写对"**，钉不了"只有一个落点" |

## 裁定

**取「甲」**（业务方 2026-10-02：「**按甲走**」）。核心一句话：

> **先把"在哪写"收到一处；"用完了怎么办"留到有明确负责人时再做 ——
> ⛔ 不要用一个会静默记错账的方案，去换一个只在特定时刻兑现的便利。**

⚠️ **本轮"兜底"的方式仍是【手动】的**：额度耗尽 ⇒ **请求直接报错**，人工改 `.env` 的
`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_*` 并**重建容器**
（⚠️ `docker compose restart` **不重读 `env_file`**，要用 `docker compose up -d api`）。

## 落点

| 件 | 位置 |
|---|---|
| 工厂（**唯一构造点**） | `api/llm_factory.py`（`make_llm()` · 两个轴见下） |
| 15 个调用点 | `grep -rn "make_llm(" api/ --include="*.py" \| grep -v test_` |
| 角色裁定表 | `api/test_max_tokens_wiring.py` 的 `EXPECTED_ROLES`（旧名 `EXPECTED_MAX_TOKENS`） |
| 门禁 | `api/test_max_tokens_wiring.py`（**工厂以外零 `ChatOpenAI(`**）· `api/test_llm_factory.py`（返回值形状 / 两个轴 / 不拉 langchain） |
| 将来做真兜底的落点 | **只需改 `api/llm_factory.py` + 处理那 5 个 `bind_tools` 点**，15 个调用点一行都不用再动 |

### 两个轴（⛔ 别合成一个参数）

| 轴 | 取值 | 决定 |
|---|---|---|
| **模型轴** | `"fast"` / `"chat"` | `LLM_MODEL_FAST` 还是 `LLM_MODEL_CHAT` |
| **长度轴** | `"answer"` / `"agent"` | `MAX_TOKENS_ANSWER`(2000) 还是 `MAX_TOKENS_AGENT`(1024) |

**4 种组合现网都存在** ⇒ 合成一个参数会**悄悄截断某一类**。

## 反悔成本

| 要改哪条 | 代价 | 判据（改完怎么验） |
|---|---|---|
| **甲 → 乙（补自动兜底）** | **中** —— 要改 `llm_factory` + 补一层「谁真的答的」传给 4 处记账点 | 🔴 **先写反证**：`api/test_llm_factory.py::test_wrapping_would_silently_break_cost_attribution` **必须先红**（它现在证明的是"包装会静默记错账"）—— 它**不红就说明还没解决那 4 处** |
| **甲 → 丙（退回直连）** | **低（一行门禁）但后果大** | 删掉 `test_no_raw_chatopenai_outside_the_factory` ⇒ 回头**没有任何东西**阻止再长出第 16 个直连点 |
| **改某个调用点的角色** | **低** | `EXPECTED_ROLES` **必须同步改**，否则 `test_every_make_llm_call_passes_the_agreed_roles` 立刻红（⚠️ 这正是它存在的意义） |
| **让"角色"可以传变量** | **低** | ⛔ **别这么做** —— 门禁靠**字面量**读取角色，传变量会让它**失明**（该测试里已写明这条） |

> 📌 **本 DEC 顺带更正了原计划的一处判断**：`token_tracker.md` 原文写
> 「**本 Task 本来就要动那 17 个构造点**」——
> **①「17」是没数就写下的数**（AST 实测 **15**）；**② 原计划**的落点是 `api/breaker.py`，
> **实际落点是新建的 `api/llm_factory.py`**（`breaker.py` 一行没改）。
