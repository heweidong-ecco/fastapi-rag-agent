"""
测试不同约束条件下的任务规划结果
"""
from plan_execute import planner_llm
from langchain_core.messages import HumanMessage, SystemMessage

GOAL = "帮我研究Python和Go在Web开发中的优劣，并给出推荐"


def test_plan(prompt_version: str, extra_constraints: str):
    """用不同约束测试规划"""
    base_prompt = """你是一个专业的任务规划助手。你的职责是将用户的目标分解为可执行的步骤清单。

**规划规则：**
1. 每个步骤必须是一个具体的、可执行的操作。
2. 步骤之间必须有清晰的逻辑顺序，不能跳跃。
3. 如果某个步骤依赖前面的结果，必须在描述中明确说明。
4. 每个步骤需要指定使用的工具（tool）和输入（input）。
5. 可用的工具包括：search（搜索）、calculator（计算）、filter（筛选）、summarize（总结）、generate（生成文本）。

**输出格式（严格JSON数组）：**
[
    {"step": 1, "action": "操作描述", "tool": "工具名", "input": "工具输入"},
    {"step": 2, "action": "操作描述", "tool": "工具名", "input": "工具输入"}
]

请严格按照JSON格式输出，不要包含任何其他文本。"""

    system_prompt = base_prompt + "\n" + extra_constraints
    
    response = planner_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"用户目标：{GOAL}")
    ])
    
    print(f"\n{'='*60}")
    print(f"测试版本：{prompt_version}")
    print(f"约束条件：{extra_constraints}")
    print(f"{'='*60}")
    print(response.content)
    
    return response.content


if __name__ == "__main__":
    # 测试1：无额外约束（基线）
    test_plan("V1-基线（无额外约束）", "")
    
    # 测试2：限制步骤数
    test_plan("V2-限制步骤数", "6. 步骤总数不超过5个。")
    
    # 测试3：优先使用搜索工具
    test_plan("V3-优先搜索", "6. 优先使用 search 工具获取信息，其他工具只在必要时使用。")
    
    # 测试4：组合约束
    test_plan("V4-组合约束", "6. 步骤总数不超过5个。\n7. 优先使用 search 工具获取信息。")
# ==========预期结果 分析和对比：=============
"""运行测试
bash
cd api
python test_plan_constraints.py

预期观察结果
测试版本	           预期变化
V1-基线（无额外约束）	步骤数可能较多（如4-6步），工具选择多样化
V2-限制步骤数	       步骤数被压缩到5步以内，可能会合并某些步骤（如“对比分析”和“给出推荐”合为一步）
V3-优先搜索     	   工具列表中 search 的比例明显增加，其他工具使用减少
V4-组合约束	           步骤数≤5，且主要使用搜索工具；计划可能更精炼但细节可能缺失

观察要点
步骤数变化：V2和V4的步骤数是否真的≤5？比V1少了多少？
工具选择变化：V3和V4中，search 的使用比例是否上升？是否有不合理的过度依赖？
计划质量：约束后，计划是否还能覆盖原任务的全部需求？有没有重要的步骤被遗漏？
把实际运行结果记录下来，这将是你对“Prompt 工程”理解的最好证明。
"""