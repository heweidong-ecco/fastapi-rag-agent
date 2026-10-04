"""探针 · 把 `.invoke()` 换成 `.stream()` 之后，**`usage_metadata` 还在不在**？（2026-10-04）

    ./venv/bin/python "fastapi-rag-agent-TODO待办/探针-流式与记账.py"

🔴 **本探针【真打 API】（4 次调用 · 每次约 40 token）—— 与 `探针-真流式与子图.py` 不同，那个不联网。**
   跑之前先想清楚为什么要跑：**假模型答不了这个问题** ——
   假模型不吐 `usage`，真服务端**吐不吐**、**挂在哪一块上**，只有真调用能测。
   ⛔ 别把它塞进 `pytest`（会变成 CI 里花钱 + 需要 key 的用例）。

📌 **它存在的理由**：链 B / C / D 都靠 `response.usage_metadata` 记账（`record_usage`）。
   把节点从 `.invoke()` 改成 `.stream()` 是本次 B1 的核心改动 ——
   若流式拿不到 `usage_metadata`，**记账会【静默停掉】**：
   接口一切正常、单测全绿，只是免费用户的配额再也管不住这条路。
   仓规：「**写不出命令的，就是还没核过。**」⇒ 这条**不许靠读码下结论**。

---

## 实测结果（2026-10-04 · 本机 · `deepseek-v4-flash`）

| 场景 | 块数 | 聚合块的 `usage_metadata` | 聚合块的 `.usage` |
|---|---|---|---|
| `.invoke()`（基线，链 B/C/D 现状） | — | ✅ `{input_tokens: 35, output_tokens: 53, …}` | ❌ **无此属性** |
| `.stream()` 聚合，`stream_usage=False`（**默认**） | **90** | ✅ `{input_tokens: 36, output_tokens: 89, …}` | ❌ 无此属性 |
| `.stream()` 聚合，`stream_usage=True`（构造时） | — | ✅ 同左 | ❌ 无此属性 |
| `chat` 模型轴（= `planner_llm` / `advanced_chat`） | **89** | ✅ `{input_tokens: 36, output_tokens: 88, …}` | ❌ 无此属性 |
| `chat` + `answer` 长度轴 | **115** | ✅ `{input_tokens: 36, output_tokens: 114, …}` | ❌ 无此属性 |

### 三条结论

1. ✅ **记账【不会】因换流式而停** —— 本仓的 provider 在**最后一块**
   （`content` 为空的那块）上带 `usage_metadata`，而 `AIMessageChunk.__add__` 会把它**合并进来**。
   ⇒ **不需要** `stream_usage=True`（`False` 也拿得到）。
2. ⚠️ **但聚合必须是「对【所有】块做 `+`」**，⛔ **不许在聚合循环里跳过空 `content` 的块** ——
   **usage 恰好就挂在那一块上**（实测：最后一块 `content=''`）。跳过它 ⇒ 账又没了。
   （发帧那一侧按 `if chunk.content:` 过滤**没问题**，那时聚合已经做完了。）
3. ✅ **`.stream()` 是真流式**：90 / 89 / 115 块，时间戳递增（首块 0.151s，之后密集）——
   ⛔ 不是「1 块整段」的假流式。

---

## 🔴 附带撞出来的一个**既有** bug（⛔ 与本次改动无关，但就在要改的那个函数里）

`api/agent_checkpointer.py:61` 的守卫写的是：

```python
if hasattr(response, "usage"):        # ← 真响应上【恒为 False】
    record_usage(..., prompt_tokens=response.usage.prompt_tokens, ...)
```

**实测**（本探针 §③）：

| 对象 | `hasattr(obj, "usage")` | `hasattr(obj, "usage_metadata")` |
|---|---|---|
| 真 `AIMessage`（`.invoke()`） | ❌ **False** | ✅ True |
| 聚合块 `AIMessageChunk`（`.stream()`） | ❌ **False** | ✅ True |

⇒ **`agent_checkpointer.py` 的 `record_usage` 在真实服务上【一次都没执行过】**
（`AIMessage` 只有 `usage_metadata`；token 另在 `response_metadata["token_usage"]` 里）。
**`/agent/memory_chat` 的 token 从来没进过账** ⇒ 免费用户那条配额形同虚设。

⚠️ **旁证这有多静默**：2026-10-01 的 🅗 S4 那次扫查**改过这个块里面**的 `model=` 实参
（`qwen-turbo` → 从对象取），却**没发现整个块不可达** ——
**给一个永不执行的 `if` 分支做参数修正**，改完一切照旧，也没有任何测试报红
（`grep '\.usage\b' api/test_*.py` 零命中：**没有一条用例造过带 `.usage` 的假对象**）。
📌 同族：`DEC-051`（工具名两处来源 · 静默落 `else`）。

⚠️ **本探针只负责【报告】它，⛔ 不修** —— 修它会让一批**本来不记账**的调用开始记账，
进而**开始拦人**（`check_budget_before_call`），那是**行为变更，要单独裁**。

---

## ⚠️ 本探针**没有**证明的

* 换成流式之后**端到端**还记账 —— 那要真跑 `/agent/plan_execute` 看 `token_usage_logs` 落没落行
  （本探针只测「`usage_metadata` 到不到手」这一层）。
* 链 C 的 `llm_with_tools`（`.bind_tools()` 之后的对象）行为一致 —— 未单独测；
  但绑定只加 kwargs，**不换 `_stream` 实现**。
* 别的模型 / 别的 provider 也这样 —— 本仓现网就是这一个（`LLM_BASE_URL`）。
"""
import sys
import time

sys.path.insert(0, "api")

import config  # noqa: F401  ← import 副作用就是 load_dotenv（⛔ 别删，删了没 key）
from langchain_core.messages import HumanMessage
from llm_factory import make_llm

MSGS = [HumanMessage(content="用一句话解释什么是向量检索")]


def drive(llm, label: str):
    t0, n, agg, stamps = time.time(), 0, None, []
    for c in llm.stream(MSGS):
        # ⚠️ 对【所有】块做 `+`，⛔ 不跳过 content 为空的块（usage 挂在最后那块上，见文件头结论 2）
        agg = c if agg is None else agg + c
        n += 1
        stamps.append(round(time.time() - t0, 3))
    print(f"\n=== {label} ===")
    print(f"   model        = {getattr(llm, 'model_name', '?')}")
    print(f"   stream_usage = {getattr(llm, 'stream_usage', '<无此属性>')}")
    print(f"   块数         = {n}   （1 = 假流式；>1 且时间戳递增 = 真流式）")
    print(f"   时间戳       = {stamps[:4]}")
    print(f"   聚合 usage_metadata = {getattr(agg, 'usage_metadata', None)}")
    print(f"   聚合 .usage         = {getattr(agg, 'usage', '<无此属性>')}")
    return agg


def main():
    llm = make_llm("fast", "agent")

    print("=== ② 基线：.invoke() 的属性名（链 C/D 用 usage_metadata，链 B 用 .usage）===")
    r = llm.invoke(MSGS)
    print(f"   hasattr(.usage)          = {hasattr(r, 'usage')}")
    print(f"   hasattr(.usage_metadata) = {hasattr(r, 'usage_metadata')}")
    print(f"   response_metadata[token_usage] = "
          f"{getattr(r, 'response_metadata', {}).get('token_usage')}")

    drive(llm, "① fast/agent · 默认 stream_usage=False")
    drive(make_llm("fast", "agent", stream_usage=True), "①-b fast/agent · stream_usage=True")
    drive(make_llm("chat", "agent", temperature=0.0), "③ chat/agent（= planner_llm）")
    drive(make_llm("chat", "answer"), "④ chat/answer")


if __name__ == "__main__":
    main()
