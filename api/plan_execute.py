"""
Plan-and-Execute 模块
实现任务规划与逐步执行。
"""
import os
import json
from typing import List, Dict
from langchain_openai import ChatOpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_CHAT
from langchain_core.messages import HumanMessage, SystemMessage

# ==================== 初始化规划专用 LLM ====================
planner_llm = ChatOpenAI(
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0  # 规划需要确定性，不能有随机性
)

# ==================== 任务规划器 ====================
def plan_task(user_goal: str) -> List[Dict]:
    """
    将用户的复杂目标分解为有序的步骤清单。

    返回格式:
    [
        {"step": 1, "action": "搜索上周AI新闻", "tool": "search", "input": "2026年7月第一周 AI 重要新闻"},
        {"step": 2, "action": "筛选与科技公司相关的新闻", "tool": "filter", "input": "科技公司"},
        ...
    ]
    """
    system_prompt = """你是一个专业的任务规划助手。你的职责是将用户的目标分解为可执行的步骤清单。

**工具使用原则：**
- execute_python 只能执行已有的代码，不能生成新代码。
- 如果用户需求是“写一段代码”，你应该先自己生成代码文本，然后调用 execute_python 去执行它。
- 如果某个工具没有列在可用工具清单中，说明它不存在，不要规划使用该工具的步骤。

**可用工具：**
- search：搜索互联网信息
- calculator：计算数学表达式
- execute_python：执行一段已编写好的 Python 代码
- fetch_webpage：获取网页文本内容
- screenshot_webpage：截取网页并保存为图片

**规划规则：**
1. 每个步骤必须是一个具体的、可执行的操作。
2. 步骤之间必须有清晰的逻辑顺序，不能跳跃。
3. 如果某个步骤依赖前面的结果，必须在描述中明确说明。
4. 每个步骤需要指定使用的工具（tool）和输入（input）。
5. 可用的工具包括：search（搜索）、calculator（计算）、filter（筛选）、summarize（总结）、generate（生成文本）。
6. 步骤数量控制在 3-7 个。

**输出格式（严格JSON数组）：**
[
    {"step": 1, "action": "操作描述", "tool": "工具名", "input": "工具输入"},
    {"step": 2, "action": "操作描述", "tool": "工具名", "input": "工具输入"}
]

请严格按照JSON格式输出，不要包含任何其他文本。"""

    response = planner_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"用户目标：{user_goal}\n\n请为此目标制定详细的步骤计划：")
    ])

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
    temperature=0.1
)

# 新增：动态重规划
def execute_plan_with_replan(plan: List[Dict], user_goal: str = "") -> str:
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

    while current_plan and replan_count <= max_replans:
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

        # 1. 动态生成输入
        dynamic_input = generate_dynamic_input(step, context, user_goal)
        
        # 2. 执行步骤（带重试）
        step_result = execute_step_with_quality_check(step, context, user_goal)
        
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

    return "\n".join(results)


# 修改原有的 execute_plan 函数，改为调用带重规划的版本
def execute_plan(plan: List[Dict], user_goal: str = "") -> str:
    """
    执行计划（默认启用动态重规划）。
    """
    return execute_plan_with_replan(plan, user_goal)

def generate_dynamic_input(step: Dict, context: str, user_goal: str) -> str:
    """
    动态输入生成器：根据当前上下文和步骤信息，生成最优的工具输入参数。
    """
    system_prompt = """你是一个执行助手。根据当前任务步骤、上下文和用户目标，生成这一步的具体输入参数。
- 如果需要搜索，请生成最精准的搜索关键词。
- 如果需要计算，请提取出具体的数学表达式。
- 如果需要筛选或总结，请明确筛选条件或总结的重点。

请只输出具体的输入参数，不要包含其他任何文字。"""

    user_prompt = f"""用户目标：{user_goal}
当前执行步骤：{json.dumps(step, ensure_ascii=False)}
历史执行上下文：{context if context else '无'}

请为此步骤生成最优的输入参数："""

    response = executor_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ])
    return response.content

# ==================== 质量评估专用 LLM（轻量、快速） ====================
quality_checker_llm = ChatOpenAI(
    # 用最轻量的模型，节省成本和延迟，
    # 推荐使用一个小型、快速的本地模型（比如Qwen3-1.7B），专门做这种简单的通过/不通过判断。
    # 因为没有本地部署，因为没额定暂时用qwen3.7-plus
    model=LLM_MODEL_CHAT,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    temperature=0  # 评估需要确定性
)

def check_step_quality(step: Dict, step_result: str, user_goal: str, context: str) -> bool:
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

    response = quality_checker_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ])
    
    verdict = response.content.strip().upper()
    return "PASS" in verdict


def execute_step_with_quality_check(step: Dict, context: str, user_goal: str, max_retries: int = 3) -> str:
    """
    执行步骤，并加入质量检查。
    如果结果不达标，会重新生成输入并重试，最多重试 max_retries 次。
    """
    for attempt in range(max_retries + 1):
        # 1. 动态生成输入（每次重试都可能生成不同的输入）
        dynamic_input = generate_dynamic_input(step, context, user_goal)
        
        # 2. 执行步骤
        step_result = execute_step_with_retry(step, dynamic_input, context)
        
        # 3. 如果执行本身失败（工具调用失败），直接返回失败
        if "执行失败" in step_result:
            return step_result
        
        # 4. 质量检查
        if check_step_quality(step, step_result, user_goal, context):
            return step_result
        else:
            print(f"步骤{step['step']} 质量不达标，第{attempt+1}次重试...")
            # 在上下文中加入质量反馈，帮助生成更好的输入
            context += f"\n[上一轮结果质量不达标，请调整策略]"
    
    # 所有重试都不达标，返回最后一次的结果（比什么都不给强）
    return step_result + "\n[注意：此步骤经过多次重试，质量可能不达标]"

def execute_step_with_retry(step: Dict, input_data: str, context: str, max_retries: int = 2) -> str:
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
                input_data = generate_dynamic_input(step, context + f"\n[上一步尝试失败，原因：{str(e)}]", "")
            else:
                return f"执行失败（已重试{max_retries}次）：{str(e)}"


def execute_single_step(step: Dict, input_data: str, context: str) -> str:
    """
    真正的单步执行逻辑。
    根据工具名调用相应函数，或使用LLM模拟未知工具。
    """
    tool_name = step["tool"]
    
    # 对于已有的真实工具，直接调用
    if tool_name == "calculator":
        try:
            return str(eval(input_data))
        except Exception as e:
            return f"计算错误: {e}"
    
    # 对于系统中没有的工具，用LLM来模拟执行
    else:
        prompt = f"""请模拟执行以下操作。
操作：{step['action']}
工具：{tool_name}
工具输入：{input_data}
执行上下文：{context}

请直接输出操作结果。"""
        response = executor_llm.invoke([HumanMessage(content=prompt)])
        return response.content