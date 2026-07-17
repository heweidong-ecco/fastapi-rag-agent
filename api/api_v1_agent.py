"""
API v1 路由集中定义
所有 /api/v1 前缀的接口在此管理。
"""
import json
import time
from fastapi import APIRouter, Depends, Path, Query
from exceptions import ErrorCode, AppException
from deps import get_current_user_hybrid, get_current_user_jwt, require_admin

from agent_graph import agent_graph
from langchain_core.messages import HumanMessage
from langchain_core.messages import HumanMessage, ToolMessage
from agent_graph_advanced import build_advanced_agent
from agent_graph import agent_graph
from plan_execute import plan_task, execute_plan
from agent_checkpointer import checkpointer_agent
from memory_store import add_user_memory, search_user_memory
from browser_tools import fetch_webpage
from browser_tools import screenshot_webpage
from code_executor import execute_python
from tool_health import run_health_check, _tool_health
from mcp_server import TOOLS_DEFINITION
from tool_health import get_tool_health, UNHEALTHY
from token_tracker import check_token_budget, get_token_budget_info
from exceptions import AppException, ErrorCode
from agent_graph_advanced import mcp_agent, get_mcp_tools
# 记录工具 开始追踪 结束追踪
from tool_visualizer import  start_trace, finish_trace
# token 预算通知（80% 阈值提醒）
from token_tracker import check_budget_warning
from token_tracker import get_user_summary, get_purpose_summary, get_recent_usage,get_thread_summary
from token_tracker import get_user_summary, get_purpose_summary, get_thread_summary, get_recent_usage
from token_tracker import get_user_history
from token_tracker import generate_monthly_report
from token_tracker import check_budget_before_call, estimate_tool_cost, TOOL_ESTIMATED_COST, PURPOSE_ESTIMATED_COST
from token_tracker import get_intercept_count
from token_tracker import record_cost
from tool_visualizer import get_trace, get_all_traces

import os

router = APIRouter(prefix="/api/v1")

# ==================== 以下是 Agent 接口 ====================
# ==================== AgentGraph 接口 ====================
@router.post("/agent/langgraph_chat")
async def langgraph_chat(
    question: str,                    # 这是一个查询参数
    thread_id: str = "default",       # 这也是一个查询参数
    user_name: str = Depends(get_current_user_hybrid), # 这是依赖注入
):
    """
    使用 LangGraph Agent 进行对话。
    thread_id 用于区分不同的对话会话。
    """
    result = agent_graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": thread_id}}
    )
    # 提取最后一条消息的文本内容
    final_message = result["messages"][-1]
    return {
        "question": question,
        "answer": final_message.content,
        "thread_id": thread_id,
        "requested_by": user_name,
    }

# ==================== 属于AgentGraph 接口下  新增的： AgentGraph 人工审批接口 ====================


@router.post("/agent/approve")
async def approve_agent_action(
    thread_id: str,
    approved: bool,
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    人工审批接口：批准或拒绝 Agent 的工具调用请求。
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    # 获取当前图的状态
    current_state = agent_graph.get_state(config)
    
    if current_state.next != ("approval",):
        return {"status": "error", "message": "当前没有等待审批的任务"}
    
    if approved:
        # 批准：直接执行 None，图会继续前进到 approval 节点，然后去 tools
        agent_graph.update_state(config, values=None)
        result = agent_graph.invoke(None, config)
    else:
        # 拒绝：更新 state，添加一条消息，并终止工具调用流程
        agent_graph.update_state(
            config,
            values={"messages": [HumanMessage(content="审批拒绝，请忽略工具调用请求，直接告知用户操作已被拒绝。")]}
        )
        result = agent_graph.invoke(None, config)
    
    final_message = result["messages"][-1]
    return {
        "status": "approved" if approved else "rejected",
        "thread_id": thread_id,
        "answer": final_message.content,
        "requested_by": user_name,
    }

# ==================== 高级图LangGraph进阶 接口：包含---条件边、循环、子图  ====================


advanced_agent = build_advanced_agent()

@router.post("/agent/advanced_chat")
# 新增Mem0 灵活 独立隔离的记忆空间，memory_space，默认：default
async def advanced_agent_chat(
    question: str,
    thread_id: str = "default",
    memory_space: str = "default",
    user_name: str = Depends(get_current_user_hybrid),
):
    """使用多分支路由的高级 Agent 进行对话"""
    result = advanced_agent.invoke(
        {
            "messages": [HumanMessage(content=question)],
            "user_name": user_name,
            "memory_space": memory_space,
        },
        config={"configurable": {"thread_id": thread_id}}
    )
    return {
        "question": question,
        "answer": result.get("final_output", "处理完成"),
        "intent": result.get("intent", "unknown"),
        "thread_id": thread_id,
        "memory_space": memory_space,
        "requested_by": user_name,
    }

# ==================== Plan-and-Execute:AgentGraph 接口 ====================


@router.post("/agent/plan_execute")
async def agent_plan_execute(
    goal: str,
    user_name: str = Depends(get_current_user_hybrid),
):
    """完整的 Plan-and-Execute 流程"""
    # 1. 规划
    """任务规划接口：将用户目标分解为步骤清单"""
    plan = plan_task(goal)

    # 2. 执行
    execution_result = execute_plan(plan, goal)

    return {
        "goal": goal,
        "plan": plan,
        "execution_result": execution_result,
        "requested_by": user_name,
    }


# ==================== 测试类 ====================
# ==================== checkpointer 测试 ====================


@router.post("/agent/memory_chat")
async def memory_chat(
    question: str,
    thread_id: str = "default",
    user_name: str = Depends(get_current_user_hybrid),
):
    """带持久化记忆的 Agent 对话接口"""
    config = {"configurable": {"thread_id": thread_id}}
    result = checkpointer_agent.invoke(
        {"messages": [HumanMessage(content=question)]},
        config=config
    )
    final_message = result["messages"][-1]
    return {
        "question": question,
        "answer": final_message.content,
        "thread_id": thread_id,
        "requested_by": user_name,
    }
# ==================== Men0 添加记忆管理接口 测试 ====================

# 搜索 新增改动，灵活使用user_id进行用户不同功能的记忆空间隔离。
@router.post("/agent/memory/add")
async def add_memory(
    content: str,
    memory_space: str = "default",  # 新增：记忆空间名称
    user_name: str = Depends(get_current_user_hybrid),
):
    # 组合出唯一的 user_id
    user_id = f"{user_name}:{memory_space}"
    add_user_memory(user_id, content)
    return {
        "status": "added",
        "content": content,
        "memory_space": memory_space,
    }
# 搜索 新增改动，灵活使用user_id进行用户不同功能的记忆空间隔离。
@router.get("/agent/memory/search")
async def search_memory(
    query: str,
    memory_space: str = "default",  # 新增：记忆空间名称
    user_name: str = Depends(get_current_user_hybrid),
):
    """搜索用户长期记忆"""
    # 组合出唯一的 user_id
    user_id = f"{user_name}:{memory_space}"
    memories = search_user_memory(user_id, query)
    return {
        "query": query,
        "memories": memories,
        "memory_space": memory_space,
    }


# ==================== 单独的浏览器工具测试接口 ====================


@router.post("/agent/fetch_webpage")
async def agent_fetch_webpage(
    url: str,
    user_name: str = Depends(get_current_user_hybrid),
):
    """使用Playwright获取网页文本内容"""
    result = fetch_webpage.invoke({"url": url})
    return {"url": url, "content": result, "requested_by": user_name}

# ==================== 新增“网页截图”工具测试接口 ====================
# 添加一个“网页截图”工具（使用page.screenshot()），让Agent能把网页保存为图片。


@router.post("/agent/screenshot_webpage")
async def agent_screenshot_webpage(
    url: str,
    user_name: str = Depends(get_current_user_hybrid),
):
    """使用Playwright截取网页并保存为图片"""
    result = screenshot_webpage.invoke({"url": url})
    return {"url": url, "result": result, "requested_by": user_name}

# ==================== 新增 代码执行器 工具 测试接口 ====================


@router.post("/agent/execute_code")
async def agent_execute_code(
    code: str,
    user_name: str = Depends(get_current_user_hybrid),
):
    """在安全沙箱中执行Python代码"""
    result = execute_python.invoke({"code": code})
    return {"code": code, "result": result, "requested_by": user_name}

# ==================== Agent 工具 健康检查 测试接口 ====================


@router.get("/agent/tool_health")
async def agent_tool_health(
    user_name: str = Depends(get_current_user_hybrid),
):
    """查看所有工具的健康状态"""
    return {"tools": _tool_health, "requested_by": user_name}

@router.post("/agent/tool_health/refresh")
async def agent_tool_health_refresh(
    user_name: str = Depends(get_current_user_hybrid),
):
    """手动刷新工具健康检查"""
    run_health_check()
    return {"tools": _tool_health, "requested_by": user_name}

'''
# ==================== Agent mcp_tools 工具  测试接口 ====================
from mcp_server import TOOLS_DEFINITION

@router.get("/agent/mcp_tools")
async def agent_mcp_tools(
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取所有 MCP 注册的工具列表"""
    return {"tools": TOOLS_DEFINITION, "requested_by": user_name}
'''

# ==================== Agent 工具 版本查询 接口 ====================
# 查看所有工具及其版本号

@router.get("/agent/tool_versions")
async def agent_tool_versions(
    user_name: str = Depends(get_current_user_hybrid),
):
    """查看所有工具及其版本号"""
    versions = {
        name: defn["version"]
        for name, defn in TOOLS_DEFINITION.items()
    }
    return {"tool_versions": versions, "requested_by": user_name}

# ==================== Agent 工具 健康检查与工具列表的联动查询 接口 ====================

@router.get("/agent/available_tools")
async def agent_available_tools(
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取当前健康且可用的工具列表（已自动过滤不健康工具）"""
    healthy_tools = []
    unhealthy_tools = []
    
    for tool_def in TOOLS_DEFINITION.values():
        tool_name = tool_def["name"]
        health = get_tool_health(tool_name)
        
        if health == UNHEALTHY:
            unhealthy_tools.append(tool_name)
        else:
            healthy_tools.append({
                "name": tool_name,
                "description": tool_def["description"],
                "version": tool_def.get("version", "unknown"),
            })
    
    return {
        "healthy_tools": healthy_tools,
        "unhealthy_tools": unhealthy_tools,
        "total": len(healthy_tools) + len(unhealthy_tools),
        "requested_by": user_name,
    }

# ==== 升级版 Agent MCP Client 新增 Token预算检查依赖和查询 接口 ====================


# 预算检查依赖（注入到需要控制成本的接口中）
async def check_budget(
    user_name: str = Depends(get_current_user_hybrid),
):
    """检查当前用户的Token预算是否充足"""
    if not check_token_budget(user_name):
        info = get_token_budget_info(user_name)
        raise AppException(
            ErrorCode.QUOTA_EXCEEDED,
            f"今日Token预算已用完。已使用 {info['used_today']} / {info['daily_budget']} tokens。"
        )
    return user_name

# 新增：Token预算查询接口
@router.get("/agent/token/budget")
async def agent_token_budget(
    user_name: str = Depends(get_current_user_hybrid),
):
    """查看当前用户的Token预算信息"""
    info = get_token_budget_info(user_name)
    return {
        "user_name": user_name,
        **info,
        "requested_by": user_name,
    }

# ==================== 升级版 Agent MCP Client 工具 测试接口 ====================

@router.post("/agent/mcp_chat")
async def mcp_agent_chat(
    question: str,
    thread_id: str = "default",
    memory_space: str = "default",
    # 在需要控制成本的接口中使用
    # 新增 Token预算检查依赖和查询
    # user_name: str = Depends(get_current_user_hybrid),
    user_name: str = Depends(check_budget),  # 改为使用预算检查
):
    # 记录工具 开始追踪
    start_trace(thread_id, question)

    """使用 MCP Client 的 Agent 对话接口（请求级隔离）"""
    result = await mcp_agent.ainvoke(
        {
            "messages": [HumanMessage(content=question)],
            "user_name": user_name,
            "memory_space": memory_space,
            "thread_id": thread_id,     # 注入 thread_id
        },
        config={"configurable": {"thread_id": thread_id}}
    )
    final_message = result["messages"][-1]

    # 记录工具 结束追踪
    finish_trace(thread_id, final_message.content)

    # 预算提醒
    warning_info = check_budget_warning(user_name)

    return {
        "question": question,
        "answer": final_message.content,
        "thread_id": thread_id,
        "requested_by": user_name,
         "budget_warning": warning_info["message"] if warning_info["warning"] else None,
    }

# ==================== 升级版 Agent MCP Client  动态获取当前可用的工具列表 接口 ====================
@router.get("/agent/mcp_tools_dynamic")
async def agent_mcp_tools_dynamic(
    user_name: str = Depends(get_current_user_hybrid),
):
    """通过 MCP Client 动态获取当前可用的工具列表"""
    tools = await get_mcp_tools()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema
            }
            for t in tools
        ],
        "total": len(tools),
        "requested_by": user_name,
    }

# ==== 升级版 Agent MCP Client 添加 Token统计 查询  接口 ====================


@router.get("/agent/token/usage")
async def agent_token_usage(
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取当前用户的 Token 使用统计"""
    summary = get_user_summary(user_name)
    return {
        "user_name": user_name,
        "summary": summary,
        "requested_by": user_name,
    }

@router.get("/agent/token/purpose")
async def agent_token_purpose(
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取按用途分类的 Token 使用统计"""
    return {
        "purpose_summary": get_purpose_summary(),
        "requested_by": user_name,
    }

@router.get("/agent/token/recent")
async def agent_token_recent(
    limit: int = 20,
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取最近的 Token 使用记录"""
    return {
        "recent_usage": get_recent_usage(limit),
        "requested_by": user_name,
    }

@router.get("/agent/token/thread")
async def agent_token_thread(
    thread_id: str = None,
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取按线程维度的 Token 使用统计（不传 thread_id 则返回所有线程）"""
    summary = get_thread_summary(thread_id)
    return {
        "thread_id": thread_id if thread_id else "all",
        "summary": summary,
        "requested_by": user_name,
    }

# ====  Token统计 全部代码 Token花费可视化接口  接口 ====================


@router.get("/agent/cost/overview")
async def agent_cost_overview(
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    花费总览：展示当前用户的 Token 消耗和费用概况。
    这是最直观的“花了多少钱”查询接口。
    """
    user_summary = get_user_summary(user_name)
    purpose_summary = get_purpose_summary()

    return {
        "user_name": user_name,
        "total_cost": round(user_summary.get("total_cost", 0), 4),
        "total_tokens": user_summary.get("total_tokens", 0),
        "total_calls": user_summary.get("calls", 0),
        "by_purpose": {
            purpose: {
                "tokens": info["total_tokens"],
                "cost": round(info["total_cost"], 4),
                "calls": info["calls"]
            }
            for purpose, info in purpose_summary.items()
        },
        "requested_by": user_name,
    }
# ====  Token统计 历史查询 接口 ====================


@router.get("/agent/token/history")
async def agent_token_history(
    days: int = 30,
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取用户最近的 Token 消耗历史趋势"""
    history = get_user_history(user_name, days)
    return {
        "user_name": user_name,
        "days": days,
        "history": history,
    }

# ====  Token统计 月度报告  接口 ====================


@router.get("/agent/cost/monthly_report")
async def agent_monthly_report(
    year: int = None,
    month: int = None,
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    生成用户指定月份的 Token 花费报告。
    
    参数:
        year: 年份（可选，默认当前年）
        month: 月份（可选，默认当前月，1-12）
    """
    report = generate_monthly_report(user_name, year, month)
    report["requested_by"] = user_name
    return report

# ====  Token统计 预算检查查询接口  接口 ====================

@router.get("/agent/budget/check")
async def agent_budget_check(
    tool_name: str = None,
    purpose: str = None,
    user_name: str = Depends(get_current_user_hybrid),
):
    """检查当前用户是否有足够预算执行指定操作"""
    allowed, reason = check_budget_before_call(
        user_name=user_name,
        tool_name=tool_name,
        purpose=purpose
    )
    info = get_token_budget_info(user_name)
    return {
        "allowed": allowed,
        "reason": reason,
        "budget_info": info,
        "estimated_cost": estimate_tool_cost(tool_name) if tool_name else None,
        "requested_by": user_name,
    }

@router.get("/agent/budget/estimates")
async def agent_budget_estimates(
    user_name: str = Depends(get_current_user_hybrid),
):
    """查看所有工具的单次调用预估成本"""
    return {
        "tool_estimates": TOOL_ESTIMATED_COST,
        "purpose_estimates": PURPOSE_ESTIMATED_COST,
        "requested_by": user_name,
    }

# ====  Token统计 拦截统计查询：按用户 接口 ====================


@router.get("/agent/budget/intercepts")
async def agent_budget_intercepts(
    user_name: str = Depends(get_current_user_hybrid),
):
    """查看预算拦截统计"""
    return {
        **get_intercept_count(user_name),
        "requested_by": user_name,
    }

# ====  Token统计 花费明细查询 接口 ====================


@router.get("/agent/cost/records")
async def agent_cost_records(
    days: int = 7,
    limit: int = 100,
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取最近N天的花费明细记录"""
    try:
        from db import get_db
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT user_name, thread_id, model, purpose, prompt_tokens, completion_tokens,
                              total_tokens, total_cost, tool_name, created_at
                       FROM cost_records 
                       WHERE user_name = %s 
                         AND created_at >= CURRENT_DATE - %s
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (user_name, days, limit)
                )
                rows = cur.fetchall()
                records = [
                    {
                        "user_name": r[0],
                        "thread_id": r[1],
                        "model": r[2],
                        "purpose": r[3],
                        "prompt_tokens": r[4],
                        "completion_tokens": r[5],
                        "total_tokens": r[6],
                        "total_cost": round(r[7], 4),
                        "tool_name": r[8],
                        "created_at": str(r[9])
                    }
                    for r in rows
                ]
        return {"records": records, "count": len(records), "requested_by": user_name}
    except Exception as e:
        return {"error": str(e)}
    
# ====  添加轨迹追踪查询 接口 ====================


@router.get("/agent/trace/{thread_id}")
async def agent_trace_detail(
    thread_id: str,
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取指定线程的执行轨迹详情"""
    trace = get_trace(thread_id)
    if trace is None:
        return {"error": f"未找到线程 {thread_id} 的执行轨迹"}
    return {"trace": trace, "requested_by": user_name}

@router.get("/agent/traces")
async def agent_trace_list(
    user_name: str = Depends(get_current_user_hybrid),
):
    """获取所有线程的执行轨迹摘要列表"""
    return {"traces": get_all_traces(), "requested_by": user_name}