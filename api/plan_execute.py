"""
Plan-and-Execute 模块
实现任务规划与逐步执行。

> ## ✅ **执行层现在是【真调用工具】**（2026-09-21 重写 · §十四 · N15）
>
> **此前（2026-09-20 核实）**：`execute_single_step()` **只对 `calculator` 真调用**，
> 其余全部走「请 LLM 模拟执行」—— 端点 `/agent/plan_execute` 看起来在跑真工具，
> **实际只有规划是真的**。
>
> **现在**：`execute_single_step()` 从 MCP 注册表取**真 handler** 并**真调用**，
> 入参字段名从工具的 `args_schema` **派生**（不手写映射）。
>
> ⚠️ **真调的代价 —— 这些现在会真的发生**：
>   · **会真的发起网络请求**（`web_search`）
>   · **会真的执行代码**（`execute_python`，沙箱内、5 秒上限）
>   · **耗时与失败率都不再由 LLM"编"决定** —— 会有真超时、真报错
>   · 📌 **浏览器工具已按 N13 从注册表摘掉**（依赖未安装的 chromium）⇒
>     执行层**当前只有 4 个工具可用**：`calculator` / `date_today` / `web_search` / `execute_python`
>
> 📌 登记位置：`docs/待办登记-2026-09-20-全仓审计与方向更正.md` §十四（N15）。
>   裁决记录：业务方 2026-09-20「**从零新做**」，原话「**大改是必要的**」。
"""
import os
import json
import time
from typing import List, Dict
from langchain_openai import ChatOpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_CHAT
from langchain_core.messages import HumanMessage, SystemMessage

# ⚠️ 2026-09-21（§十四 · ③-b）：接上**预算与记账**。
#    实测过：这两个 import **不会拉起任何重包**（psycopg2 / sqlalchemy / numpy / … 都不进）——
#    `token_tracker` 走的是**函数内惰性导入** `db`（2026-09-17 切开点 2）。
from token_tracker import check_budget_before_call, record_usage

# 🔴 2026-09-21 加（③ 的遗留 —— 同一类问题的另一半）：
#    **③ 只补了「工具调用」的超时，没补「LLM 调用」的。**
#
#    实测：三个 `ChatOpenAI(...)` 都是 `timeout=None` ⇒ 吃 **openai SDK 的默认值**：
#      `connect=5s, read=600s（10 分钟）, write=600s`，且 SDK 还会自己 `max_retries=2`
#    ⇒ **一次 LLM 调用最坏可等 600 × (1+2) = 30 分钟。**
#    而 `plan_execute` 最坏跑「3–7 步 × 每步重试 3 次 × 每步 2 次 LLM 调用」
#    ⇒ **理论上能挂几个小时。**
#
#    ⇒ 这里把**超时与重试都显式写死**，让最坏情况**可算**：
#       单次 LLM 调用最坏 = `timeout × (1 + max_retries)`
#    ⚠️ 与 `SEARCH_TIMEOUT_SECONDS`（20s，网络搜索）和 `MAX_EXEC_TIME`（5s，沙箱执行）
#       **是三件不同的事**，别混：一个是模型往返、一个是外部搜索、一个是本地跑代码。
PLANNER_LLM_TIMEOUT = 60      # 规划：prompt 大、输出是一份 JSON 计划
EXECUTOR_LLM_TIMEOUT = 30     # 每步的参数值生成：输入小、输出一句话或一段代码
QUALITY_LLM_TIMEOUT = 20      # 质量检查：只回 PASS / FAIL

# ⚠️ **显式设成 1**（SDK 默认是 2）—— 重试本身就是"再来一遍完整超时"，
#    层数越多，最坏时长越难算。1 次重试已经能盖住大多数瞬时抖动。
LLM_MAX_RETRIES = 1

# `plan_execute` 的**总时长预算（秒）** —— 见 `execute_plan_with_replan` 里的用法。
# ⚠️ 为什么需要它：单次调用有上限 ≠ 整条计划有上限。
#    一个 7 步的计划 × 每步重试，哪怕每步都很"守规矩"，加起来也能很久。
PLAN_TOTAL_BUDGET_SECONDS = 120


# ==================== 初始化规划专用 LLM ====================
planner_llm = ChatOpenAI(
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0,  # 规划需要确定性，不能有随机性
    timeout=PLANNER_LLM_TIMEOUT,
    max_retries=LLM_MAX_RETRIES,
)

# ==================== 任务规划器 ====================

# 🔴 2026-09-20 修（§三·C1，业务方裁「同源」）：**可用工具清单改为从 MCP 注册表派生。**
#
#    此前这里**手写了两份互相矛盾**的工具清单（同一个 prompt 里！）：
#      · 第一份写 `search` —— 而 MCP 注册表里**没有** `search`，真名是 **`web_search`**
#      · 第二份写 `search / calculator / filter / summarize / generate`
#        —— 后三个**全仓不存在**
#    ⇒ **两份都不能照用**，LLM 会被引着规划出根本不存在的工具名。
#
#    ⚠️ 与 🔴C 是**同一个根因**：**手工维护的工具清单必然漂**。
#       ⇒ 改为从 `mcp_server.TOOLS` 派生（单一事实源）—— 以后加工具只需改那一处。
from mcp_server import TOOLS as _MCP_TOOLS, TOOL_HANDLERS as _TOOL_HANDLERS


def _available_tool_lines() -> str:
    """把 MCP 注册表渲染成给 LLM 读的「可用工具」清单（**唯一来源**）。"""
    lines = []
    for t in _MCP_TOOLS:
        fn = t["func"]
        # 用工具描述的第一行（docstring 首行）—— 与 `bind_tools` 发给 LLM 的是同一份
        desc = (fn.description or "").strip().splitlines()[0] if fn.description else ""
        lines.append(f"- {fn.name}：{desc}")
    return "\n".join(lines)


# ==================== 预算与记账（③-b） ====================

class BudgetExceededError(Exception):
    """Token 预算不足 —— 由 `_invoke_llm` 抛出，端点层捕获后转成 QUOTA_EXCEEDED。"""


def _invoke_llm(llm, messages, purpose: str, user_name: str = "unknown") -> object:
    """**统一的 LLM 调用入口**：先查预算 → 调用 → 再记【真实用量】。

    🔴 2026-09-21 新增（§十四 · ③-b）。**此前 `plan_execute` 完全不查预算、不记账** ——
       而它会**真跑 LLM**（规划 1 次 + 每步动态输入 1 次 + 每步质量检查 1 次），
       ⇒ **免费用户的每日配额根本管不到 `/agent/plan_execute` 这条路**。

    📌 **照抄 2 代 `/agent/mcp_chat` 的模式**（`agent_graph_advanced.py:303/315`），**不另起炉灶**：
       同样是 `check_token_budget` → 调用 → 从 `usage_metadata` 取真实 token → `record_usage`。
       这里只是把它包成**一个入口**，免得在四个调用点各抄一遍。
    """
    allowed, reason = check_budget_before_call(user_name, purpose=purpose)
    if not allowed:
        raise BudgetExceededError(reason)

    response = llm.invoke(messages)

    # ⚠️ 有 `usage_metadata` 才记账 —— 没有就**如实不记**，不编一个数字进去
    usage = getattr(response, "usage_metadata", None) or {}
    if usage:
        record_usage(
            model=getattr(llm, "model_name", None) or getattr(llm, "model", "unknown"),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            purpose=purpose,
            user_name=user_name,
            thread_id="plan_execute",
        )
    return response


def _tool_arg_field(tool_name: str):
    """派生某个工具**唯一入参**的字段名（**从 MCP 注册表，不手写**）。

    🔴 **为什么要派生而不是写死**：与 §三·C1（工具清单同源）**同一个道理** ——
       手工维护的映射必然与注册表漂移。加工具 / 改参数名时，这里自动跟上。

    返回：
      · 字段名（`str`）—— 该工具正好有**一个**入参时
      · `None` —— 工具不存在 / 没有入参 / 入参不是单一字段
        ⇒ 调用方据此走**降级**（不猜参数名，宁可报明确错误）
    """
    for t in _MCP_TOOLS:
        fn = t["func"]
        if fn.name != tool_name:
            continue
        schema = getattr(fn, "args_schema", None)
        if schema is None:
            return None
        try:
            fields = list(schema.model_fields.keys())
        except AttributeError:  # 不是 pydantic v2 模型
            return None
        return fields[0] if len(fields) == 1 else None
    return None

def plan_task(user_goal: str, user_name: str = "unknown") -> List[Dict]:
    """
    将用户的复杂目标分解为有序的步骤清单。

    返回格式（⚠️ `tool` 的取值**只能是** `_available_tool_lines()` 里列出的那些）:
    [
        {"step": 1, "action": "搜索上周AI新闻", "tool": "web_search", "input": "2026年7月第一周 AI 重要新闻"},
        {"step": 2, "action": "计算同比增幅", "tool": "calculator", "input": "(120-100)/100"},
        ...
    ]
    """
    system_prompt = """你是一个专业的任务规划助手。你的职责是将用户的目标分解为可执行的步骤清单。

**工具使用原则：**
- execute_python 只能执行已有的代码，不能生成新代码。
- 如果用户需求是“写一段代码”，你应该先自己生成代码文本，然后调用 execute_python 去执行它。
- 如果某个工具没有列在可用工具清单中，说明它不存在，不要规划使用该工具的步骤。

**可用工具（**这就是全部**，不要用清单外的名字）：**
__TOOL_LIST__

**规划规则：**
1. 每个步骤必须是一个具体的、可执行的操作。
2. 步骤之间必须有清晰的逻辑顺序，不能跳跃。
3. 如果某个步骤依赖前面的结果，必须在描述中明确说明。
4. 每个步骤需要指定使用的工具（tool）和输入（input）。
5. **`tool` 的取值只能来自上面的「可用工具」清单** —— 清单里没有的，就是不存在，不要规划它。
6. 步骤数量控制在 3-7 个。

**输出格式（严格JSON数组）：**
[
    {"step": 1, "action": "操作描述", "tool": "工具名", "input": "工具输入"},
    {"step": 2, "action": "操作描述", "tool": "工具名", "input": "工具输入"}
]

请严格按照JSON格式输出，不要包含任何其他文本。""".replace("__TOOL_LIST__", _available_tool_lines())

    response = _invoke_llm(
        planner_llm,
        [SystemMessage(content=system_prompt),
         HumanMessage(content=f"用户目标：{user_goal}\n\n请为此目标制定详细的步骤计划：")],
        purpose="plan_execute.plan",
        user_name=user_name,
    )

    # 解析LLM返回的JSON
    try:
        plan = json.loads(response.content)
        return plan
    except json.JSONDecodeError:
        # 如果LLM返回的不是纯JSON，尝试提取JSON部分
        import re
        json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return [{"step": 1, "action": "无法解析规划", "tool": "chat", "input": user_goal}]


# ==================== 任务执行器 ====================
# 执行器专用模型，温度稍高，以便在动态调整时具备一定灵活性
executor_llm = ChatOpenAI(
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0.1,
    timeout=EXECUTOR_LLM_TIMEOUT,      # 🔴 2026-09-21：见上方共用说明
    max_retries=LLM_MAX_RETRIES,
)

# 新增：动态重规划
def execute_plan_with_replan(plan: List[Dict], user_goal: str = "",
                             user_name: str = "unknown") -> str:
    """
    执行计划，并在某一步彻底失败时自动触发重规划。
    包含循环检测和工具降级策略。
    """
    context = ""
    results = []
    current_plan = plan[:]  # 复制一份计划，避免修改原计划

    # 新增：工具连续失败计数器和失效工具列表
    tool_failure_counts = {}
    failed_tools = set()
    # 新增：最大重规划次数
    max_replans = 5
    replan_count = 0

    # 🔴 2026-09-21 加（③ 的遗留）：**总时长预算**。
    #    **单次调用有上限 ≠ 整条计划有上限** —— 一个 3–7 步的计划，
    #    哪怕每步都"守规矩"，叠起来也能很久（每步最多 2 次 LLM 调用 + 1 次工具，
    #    外面还套着"最多 3 次重试"和"最多 5 次重规划"）。
    #    ⚠️ 与单次超时的关系：单次超时管"这一下别卡死"，总预算管"这件事别没完没了"。
    t0 = time.time()
    timed_out = False

    while current_plan and replan_count <= max_replans:
        if time.time() - t0 > PLAN_TOTAL_BUDGET_SECONDS:
            timed_out = True
            break

        step = current_plan[0]
        step_num = step["step"]
        tool_name = step.get("tool", "unknown")
        
        # 检查工具是否已失效
        if tool_name in failed_tools:
            # 工具已失效，跳过这一步（或用LLM模拟）
            fallback_result = f"工具 {tool_name} 当前不可用，使用备用策略生成结果。"
            # 可选：用LLM模拟该工具的输出
            try:
                fallback_result = execute_single_step(step, step.get("input", ""), context)
            except:
                pass
            result_summary = f"步骤{step_num}（{tool_name}已降级处理）：{fallback_result[:200]}"
            
            results.append(result_summary)
            context += f"\n{result_summary}"
            current_plan.pop(0)
            continue

        # 1. 动态生成输入 —— ⚠️ 2026-09-20 删（§三·B10）：
        #    此处原有一行 `dynamic_input = generate_dynamic_input(step, context, user_goal)`，
        #    但**下面那行根本不用它**（`execute_step_with_quality_check` 的签名里没有这个参数）。
        #    📌 2026-09-21：这句话里的 `user_goal` 后面**曾经被误加过一个 `, user_name`** ——
        #       那是一次**盲替换命中注释**的事故（见 :472 的修复记录），此处已还原。
        #    ⇒ 它是**纯重复**：这个函数**内部自己就调 `generate_dynamic_input`**（见 :264），
        #      而且真的用了（:267）。⇒ 原来那句 = **每走到这个分支白花一次 LLM 调用**。
        #
        # 2. 执行步骤（带重试）
        step_result = execute_step_with_quality_check(step, context, user_goal, user_name)
        
        # 3. 判断是否彻底失败
        if "执行失败（已重试" in step_result:
            # 更新失败计数
            tool_failure_counts[tool_name] = tool_failure_counts.get(tool_name, 0) + 1
            # 如果同一个工具连续失败超过3次，标记为失效
            if tool_failure_counts[tool_name] >= 3:
                failed_tools.add(tool_name)
                print(f"工具 {tool_name} 连续失败3次，已标记为失效，后续将使用降级策略。")

            # 步骤彻底失败，触发重规划
            replan_count += 1
            print(f"步骤{step_num}彻底失败，触发重规划...")
            
            # # 构建重规划上下文，加入失效工具信息
            replan_context = f"""用户原始目标：{user_goal}
已完成步骤：
{chr(10).join(results)}
当前步骤失败：{step_result}
以下工具已失效，请勿使用：{', '.join(failed_tools) if failed_tools else '无'}
请重新规划剩余步骤，排除已失败的策略和失效工具。"""
            
            # 调用规划器重新生成后续计划
            new_plan = plan_task(replan_context)
            
            if new_plan:
                # 用新计划替换剩余步骤
                current_plan = new_plan
                context += f"\n[步骤{step_num}失败，已重新规划]"
                continue
            else:
                # 重规划也失败了，终止执行
                results.append(f"步骤{step_num}失败且重规划失败：{step_result}")
                break
        
        # 4. 成功：重置该工具的失败计数
        if tool_name in tool_failure_counts:
            tool_failure_counts[tool_name] = 0

        # 5. 成功：更新上下文和结果
        result_summary = f"步骤{step_num}完成：{step_result[:200]}"
        results.append(result_summary)
        context += f"\n{result_summary}"
        
        # 6. 移除已执行的步骤，继续下一个
        current_plan.pop(0)
        
    if replan_count > max_replans:
        results.append(f"[系统] 已达到最大重规划次数（{max_replans}次），执行终止。")
    elif timed_out:
        # ⚠️ **如实说明"没跑完"** —— 不能让它看起来像正常结束。
        #    剩余步骤数一起报出来，调用方才知道**结果是不完整的**。
        results.append(
            f"[系统] 已超过总时长预算（{PLAN_TOTAL_BUDGET_SECONDS} 秒），执行【提前终止】——"
            f"**结果不完整**，剩余 {len(current_plan)} 个步骤未执行。"
            f"提示：把目标拆得更小，或减少步骤数后重试。"
        )

    return "\n".join(results)


# 修改原有的 execute_plan 函数，改为调用带重规划的版本
def execute_plan(plan: List[Dict], user_goal: str = "", user_name: str = "unknown") -> str:
    """
    执行计划（默认启用动态重规划）。
    """
    return execute_plan_with_replan(plan, user_goal, user_name)

def _strip_code_fence(text: str) -> str:
    """去掉 LLM 常加的 ``` 围栏。

    🔴 **这条不是洁癖**：`execute_python` 要的是**可直接执行的代码**，
       LLM 很爱回 ```` ```python\\nprint(1)\\n``` ```` ⇒ 那会**直接语法错**。
       实测里这是「代码类工具」最常见的一种"看着对、其实跑不了"。
    """
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    lines = lines[1:]                                    # 去掉 ``` 或 ```python
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]                               # 去掉收尾的 ```
    return "\n".join(lines).strip()


def generate_dynamic_input(step: Dict, context: str, user_goal: str, user_name: str = "unknown") -> str:
    """生成这一步交给工具的**入参值**（该工具那个唯一字段的值）。

    🔴 2026-09-21 改（§十四 · N15）：真调用之后，这里产出的**不再是一句给 LLM 看的描述**，
       而是**要直接塞进 `handler({字段名: 值})` 的那个值**。
       不把这个说清楚，LLM 会按"通用输入"写 —— 例如给 `execute_python` 回一句中文描述、
       而不是代码 ⇒ 真调用时立刻崩。
    """
    tool_name = step.get("tool", "")
    field = _tool_arg_field(tool_name)
    tool_desc = ""
    for t in _MCP_TOOLS:
        if t["func"].name == tool_name:
            tool_desc = (t["func"].description or "").strip()
            break

    system_prompt = f"""你是一个执行助手。你要为一次**工具调用**生成它需要的那个参数值。

**目标工具**：`{tool_name}`
**工具说明**：{tool_desc}
**要生成的参数名**：`{field if field else '（该工具入参不是单一字段）'}`

⚠️ 只输出**参数的值本身**：不要输出参数名、不要 JSON、不要解释、不要引号包裹、不要代码围栏。
⚠️ 值的形态必须符合那个工具的期望 —— 例如 `execute_python` 要**可直接执行的 Python 代码**、
   `calculator` 要**纯数学表达式**、`web_search` 要**搜索关键词**。"""

    user_prompt = f"""用户目标：{user_goal}
当前执行步骤：{json.dumps(step, ensure_ascii=False)}
历史执行上下文：{context if context else '无'}

请输出该参数的值："""

    response = _invoke_llm(
        executor_llm,
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        purpose="plan_execute.dynamic_input",
        user_name=user_name,
    )
    return _strip_code_fence(response.content)

# ==================== 质量评估专用 LLM（轻量、快速） ====================
quality_checker_llm = ChatOpenAI(
    # 用最轻量的模型，节省成本和延迟，
    # 推荐使用一个小型、快速的本地模型（比如Qwen3-1.7B），专门做这种简单的通过/不通过判断。
    # 没有本地部署 ⇒ 用配置里的 chat 模型（`model=` 那一行就是它）
    # ⚠️ 2026-09-20 修：原注释写死「暂时用 qwen3.7-plus」—— 那是**无效模型名**
    #    （`CLAUDE.md` 已明列），且与下面真正生效的 `model=LLM_MODEL_CHAT` 不符。
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0,  # 评估需要确定性
    timeout=QUALITY_LLM_TIMEOUT,      # 🔴 2026-09-21：见上方共用说明
    max_retries=LLM_MAX_RETRIES,
)

def check_step_quality(step: Dict, step_result: str, user_goal: str, context: str,
                       user_name: str = "unknown") -> bool:
    """
    评估单步执行结果的质量。
    返回 True 表示达标，False 表示需要重试。
    """
    system_prompt = """你是一个严格的质量检查员。你的任务是判断一个步骤的执行结果是否达到了该步骤的目标。

**判断标准：**
1. 结果是否与步骤描述的目标一致？
2. 结果是否包含有效信息（不是空话、不是错误信息）？
3. 结果是否与用户的总目标相关？
4. 如果是搜索步骤，结果是否提供了实质内容（而不是“未找到”或无关内容）？

请只回答一个单词：PASS（通过）或 FAIL（不通过）。不要输出任何其他内容。"""

    user_prompt = f"""用户总目标：{user_goal}
当前步骤：{json.dumps(step, ensure_ascii=False)}
历史上下文：{context if context else '无'}
执行结果：{step_result[:500]}

请判断此步骤的执行结果是否达标："""

    response = _invoke_llm(
        quality_checker_llm,
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        purpose="plan_execute.quality_check",
        user_name=user_name,
    )
    
    verdict = response.content.strip().upper()
    return "PASS" in verdict


def execute_step_with_quality_check(step: Dict, context: str, user_goal: str,
                                    user_name: str = "unknown", max_retries: int = 3) -> str:
    """
    执行步骤，并加入质量检查。
    如果结果不达标，会重新生成输入并重试，最多重试 max_retries 次。
    """
    for attempt in range(max_retries + 1):
        # 1. 动态生成输入（每次重试都可能生成不同的输入）
        # 🔴 2026-09-21 修：这里**原本漏传 `user_name`** ——
        #    本次端到端实测（`POST /agent/plan_execute`）才暴露出来：
        #      `token_usage_logs` 里 `plan_execute.dynamic_input` 的 4 条**全记在 `unknown` 头上**，
        #      而 `plan` / `quality_check` 的记在 `admin` 头上。
        #    ⇒ 后果：**这部分的额度算不到发起人头上 ⇒ 配额管不住他**（正是 ③-b 要解决的问题）。
        #    ⚠️ **它是怎么漏的**：那次改动用的是**盲替换** `s.replace(old, new, 1)`，
        #       **命中了 `:283` 注释里的同一串**（注释在前 ⇒ 先被替换），**真正的这行反而没改到**。
        #       📌 本仓复盘反复记的那一类：「**判据选错 / 注释当代码**」—— 这次是我自己犯的。
        #       教训：**改完要按行号核**，别只看"替换成功了几处"。
        #    回归用例：`test_plan_execute_tools.py::test_dynamic_input_records_usage_for_the_real_user`
        dynamic_input = generate_dynamic_input(step, context, user_goal, user_name)
        
        # 2. 执行步骤
        step_result = execute_step_with_retry(step, dynamic_input, context, user_name)
        
        # 3. 如果执行本身失败（工具调用失败），直接返回失败
        if "执行失败" in step_result:
            return step_result
        
        # 4. 质量检查
        if check_step_quality(step, step_result, user_goal, context, user_name):
            return step_result
        else:
            print(f"步骤{step['step']} 质量不达标，第{attempt+1}次重试...")
            # 在上下文中加入质量反馈，帮助生成更好的输入
            context += "\n[上一轮结果质量不达标，请调整策略]"  # ⚠️ 2026-09-20 去掉多余的 f（D1/pyflakes：f-string 无占位符）
    
    # 所有重试都不达标，返回最后一次的结果（比什么都不给强）
    return step_result + "\n[注意：此步骤经过多次重试，质量可能不达标]"

def execute_step_with_retry(step: Dict, input_data: str, context: str,
                            user_name: str = "unknown", max_retries: int = 2) -> str:
    """
    带重试机制的单步执行器。
    """
    for attempt in range(max_retries + 1):
        try:
            result = execute_single_step(step, input_data, context)
            return result
        except Exception as e:
            if attempt < max_retries:
                # 失败时，重新生成输入参数
                input_data = generate_dynamic_input(
                    step, context + f"\n[上一步尝试失败，原因：{str(e)}]", "", user_name
                )
            else:
                return f"执行失败（已重试{max_retries}次）：{str(e)}"


def execute_single_step(step: Dict, input_data: str, context: str) -> str:
    """**真正的单步执行** —— 把这一步交给 MCP 注册表里那个工具【真调用】。

    🔴 2026-09-21 重写（§十四 · N15 · 业务方裁「**从零新做**」）。
       此前这里**只对 `calculator` 真调用**，其余**全部走「请 LLM 模拟执行」** ——
       端点 `/agent/plan_execute` 看起来在跑真工具，**实际只有规划是真的**。

    现在的做法（**与 MCP 服务端同一套机制**，不另起炉灶）：
      ① 从 `TOOL_HANDLERS` 取该工具的**真 handler**（注册表是唯一事实源）
      ② 从 `args_schema` **派生**它唯一入参的字段名（`_tool_arg_field`，不手写映射）
      ③ `handler({字段名: input_data})` —— **真调用，返回真结果**

    ⚠️ **失败一律【抛异常】，不吞成错误字符串** —— 上游两条路都是靠异常工作的：
       · `execute_step_with_retry()` 捕获后**重新生成输入再试一次**
       · `execute_plan_with_replan()` 的「失效工具降级」分支
       ⇒ 改成"返回错误字符串"会让**重试机制静默失效**（看起来在重试、其实没有）。
    """
    tool_name = step["tool"]

    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"未找到工具: {tool_name}")

    field = _tool_arg_field(tool_name)
    if field is None:
        raise ValueError(
            f"工具 {tool_name} 的入参不是【单一字段】— 当前执行层不支持。"
            f"要么把该工具改成单字段，要么在这里为它加一条显式映射（别猜参数名）。"
        )

    return str(handler({field: input_data}))
