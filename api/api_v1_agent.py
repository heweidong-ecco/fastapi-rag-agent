"""
API v1 路由集中定义
所有 /api/v1 前缀的接口在此管理。
"""
import asyncio
# `③` Task 5 补（2026-10-03 · 真服务实测）：`finally` 里关图的流要用 `anyio.CancelScope(shield=True)`
# **护住** —— 否则那一次 `await` 会被反复投递的取消打断（与 `api_v1_rag.py` 同一处病）。
import anyio
import json
import time
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse   # B1：Agent 端 SSE
from loguru import logger                          # `③` Task 5：取消事件要落到日志（判据①）
from metrics import track_stream_cancel            # `③` Task 5：取消事件进 Prometheus（判据③的观测对象）
from exceptions import ErrorCode, AppException
from deps import get_current_user_hybrid, get_current_user_jwt, require_admin

from agent_graph import agent_graph
from pending_approvals import (
    list_pending, register, resolve,
    find_by_raw_thread_id,            # 丙段：按原 thread_id 反查**属主**
)
# 角色（`DEC-046`）—— `/agent/approve` 的「本人或 admin」判据走这里，
# ⛔ 别在本文件另写 `user_name == "admin"`（那就又多一处口径）。
from permission import UserRole, get_user_role
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
# 多分支路由（意图分类）高级 Agent：定义在 agent_graph_advanced_learning.py
from agent_graph_advanced_learning import build_advanced_agent
from plan_execute import plan_task, execute_plan, BudgetExceededError
from agent_checkpointer import checkpointer_agent
from memory_store import add_user_memory, search_user_memory
# ⛔ 2026-09-21 注释（N13 · **# 可扩展能力**）：`browser_tools` 依赖未安装的 chromium
#    ⇒ 两个端点每调必 500。装好 chromium 后连同下面两个端点一起取消注释。
# from browser_tools import fetch_webpage, screenshot_webpage
from code_executor import execute_python
from tool_health import run_health_check, get_tool_health, UNHEALTHY, _tool_health
from mcp_server import TOOLS_DEFINITION
from token_tracker import (
    check_token_budget, get_token_budget_info, check_budget_warning,
    get_user_summary, get_purpose_summary, get_thread_summary, get_recent_usage,
    get_user_history, generate_monthly_report,
    check_budget_before_call, estimate_tool_cost,
    TOOL_ESTIMATED_COST, PURPOSE_ESTIMATED_COST,
    get_intercept_count, record_cost,
    check_session_token_budget,       # B8（①b Task 2）：会话级上限
    get_user_overview,                # B13（①b Task 7）：**读库**的全时总览
    get_global_daily_token_usage,     # B13（①b Task 7）：全站日级用量（B10 的数）
)
# B13（①b Task 7）：全站日级**上限**常量。⚠️ 与 `get_global_daily_token_usage()`
#    **成对使用** —— 只给"已用"不给"上限"，客户端算不出"全站还剩多少"。
#    ⛔ 别把 1_000_000 写死在这里（`DEC-042` 裁过这个值，改它只该改 `token_config.py`）。
from token_config import GLOBAL_DAILY_TOKEN_LIMIT
# B11（①b Task 4）：全站日级熔断。
# ⚠️ 与 B8 **并列**，⛔ 别把两者合并成一个函数 —— 维度不同（B8 按会话 / B11 按全站），
#    合并后一改就会同时动到两层。（`DEC-041` 与 `B11` 各裁各的范围）
from breaker import circuit, global_key
# 会话键（`DEC-056` 丙段）：**把身份拼进 checkpoint / 会话 id**。
# ⚠️ 为什么必须拼：`thread_id` 在**本文件 6 条端点上**默认就是 `"default"`
#    ⇒ 两个用户都用默认值 ⇒ 共用一个 checkpoint 桶，而消息 reducer 是
#    `Annotated[List, operator.add]`（append）⇒ **模型看得到别人的对话**。
#    ⛔ 只在**传进图 / 传进待接管队列**时拼 —— 响应里回显的仍是调用方传进来的**原值**。
from session_key import session_key
# 记录工具 开始追踪 结束追踪
from tool_visualizer import start_trace, finish_trace, get_trace, get_all_traces
# MCP Client 高级 Agent（会话池版）及动态工具列表
from agent_graph_advanced import mcp_agent, get_mcp_tools

import os

router = APIRouter(prefix="/api/v1")


def summarize_agent_result(result: dict) -> dict:
    """把 LangGraph 的返回态整理成对调用方**有意义**的形状。

    🔴 2026-09-20 修（契约缺陷）:
      这张图带 `interrupt_before=["approval"]` —— **停在审批点时，最后一条消息是
      "只带工具调用、没有文字"的 AIMessage**（实测:`AIMessage content=''
      tool_calls=[{'name': 'calculator', …}]`）。
      而端点原先直接取 `result["messages"][-1].content` ⇒ **返回 200 + 空答案**，
      调用方**完全看不出"正在等人工审批"**（明明有配套的 `/agent/approve`）。
      实测复现:POST /agent/langgraph_chat?question=请计算6*7 → `{"answer": ""}`。

    ⚠️ 判据是「**最后一条消息带 `tool_calls`**」—— 只看这一条。
      · **这条判据为什么成立**（🔴 B4 之后**理由变了**，⛔ 别照旧理解）：
        图带 `interrupt_before=["approval"]` ⇒ 停在审批点时，末条消息**必带** tool_calls。
        而**非敏感**的 tool_calls（`calculator` / `date_today`）**不会出现在本函数的输入里** ——
        它们直接跑 `tools → agent → … → END`，**从不停在图中间**。
        ⇒ 「末条带 tool_calls」在这里**仍然等价于**「停在审批点」。
      · ⚠️ **但等价性依赖上面那一句**：若将来有**别的**路径把"跑了一半的图"喂进本函数
        （流式返回 / 调试端点 / 某个非敏感工具提前返回），这条判据就会**误报 `pending_approval`**。
        ⇒ **改图的路由时，回来重看这里。**
      · **不能**再加 `and not content`：真实 LLM 常见"既写文字又调工具"
        （"我来帮你算一下。" + tool_calls），那种形态同样在等审批，
        加了这个条件就会误报 `answered` ⇒ 调用方照样不知道要去 `/agent/approve`
        （**原缺陷原样保留**，2026-09-20 由合并前评审指出并加了用例）。
      · **也**不会把中途态误报：`ToolMessage` **没有 `tool_calls` 属性**，
        所以"工具刚跑完、正要生成最终答案"那一态天然被排除。
    """
    messages = result.get("messages") or []
    if not messages:
        return {"status": "answered", "answer": ""}
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    content = getattr(last, "content", "") or ""
    if tool_calls:
        return {
            "status": "pending_approval",
            # ⚠️ 保留模型已经写出的文字（真实 LLM 常"先说一句再调工具"）——
            #    但 `status` 明确告诉调用方：**这还不是最终答案**，工具尚未执行。
            "answer": content,
            "pending_tool_calls": [
                {"name": tc.get("name"), "args": tc.get("args")} for tc in tool_calls
            ],
        }
    return {"status": "answered", "answer": content}


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

    ⚠️ 本图带人工审批节点。若返回 `status="pending_approval"`，说明**工具还没执行**，
    要用返回的 `pending_tool_calls` 走 `/agent/approve`（带同一个 `thread_id`）继续。
    """
    # B8 · 会话级 token 上限（`DEC-041`）—— 触顶动作 = **直接拒绝**（`B11` 要素② 已裁）
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）。与上一段**并列、都要过**：
    # B8 管"这个会话花了多少"，这段管"全站今天花了多少"。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # 🅾 丙段断言点 #1：**图收到的键**（⛔ 不是 `thread_id`）—— 守卫 `api/test_session_isolation.py`
    sess = session_key(user_name, thread_id)

    result = agent_graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": sess}}
    )
    summary = summarize_agent_result(result)

    # B5 · 待接管队列（`②` Task 2）—— `MemorySaver` 反查不出"谁卡住了"，只能在这里记账。
    # ⚠️ `else` 那支不是可省的：**本轮没卡住 ⇒ 清掉上一次的登记**，
    #    否则同一个 thread 一旦卡过一次，就会永远留在队列里**变成假待办**。
    # ⚠️ 记账也用 `sess`（⛔ 不是裸 `thread_id`）—— 否则两个人用同一个 `thread_id`
    #    会在**队列里也串号**，`/agent/approve` 会拿着别人的 key 去续跑（丙段）。
    if summary.get("status") == "pending_approval":
        register(sess, user_name, summary.get("pending_tool_calls") or [],
                 raw_thread_id=thread_id, graph="agent_graph")
    else:
        resolve(sess)

    return {
        "question": question,
        "thread_id": thread_id,
        "requested_by": user_name,
        **summary,
    }

@router.post("/agent/langgraph_chat/stream")
async def langgraph_chat_stream(
    question: str,
    thread_id: str = "default",
    user_name: str = Depends(get_current_user_hybrid),
):
    """`/agent/langgraph_chat` 的**流式**版本（`B1`）。SSE 逐 token 返回。

    ## 帧格式（与 `/rag/stream_search` 一致，便于前端复用）

    | 帧 | 何时 |
    |---|---|
    | `data: {"content": "…"}` | **每个 token 一帧** |
    | `data: {"thread_id": …, "status": …, "answer": …, "pending_tool_calls": […]}` | 收尾**一帧汇总** |
    | `data: [DONE]` | 结束哨兵 |

    ⚠️ 那一帧**汇总**不是可有可无的：`status="pending_approval"` 是**唯一**告诉调用方
       "工具还没执行、要带同一个 `thread_id` 去 `/agent/approve`"的地方。
       **砍掉它 = 前端只会看到一个戛然而止的半截答案**，而 HTTP 返回 200。

    ## 🔴 判据是「**逐字出现**」，⛔ 不是「有 `text/event-stream`」

    **假流式**（整段一次到、前端再切字符）**照样有 `text/event-stream`、照样有 `data:` 帧**。
    ⇒ 判据钉在**后端出块**：`api/test_agent_sse.py::test_graph_streams_one_chunk_per_token`。
    ⇒ 「时间戳递增」那一条 TestClient 测不出（拿到的是已缓冲的整段），
      用**真服务 + 真 HTTP** 验：
       `curl -N … | while IFS= read -r line; do echo "$(date +%T.%3N)  $line"; done`

    ## ⚠️ 三条接线**必须与 `/agent/langgraph_chat` 保持一致**（⛔ 别只做一半）

    1. **B8 会话级上限 + B11 全站日级熔断** —— 两条都要过（在**进生成器之前**，
       否则触顶会变成"HTTP 200 + 流到一半断掉"，调用方看不出是被限额拒了）；
    2. **B5 待接管队列** —— 停在审批点时要 `register`，否则 `/agent/pending` 里**找不到它**
       （`MemorySaver` 没有"列出全部 thread"的 API，这个登记是**唯一**的入口）；
    3. **`summarize_agent_result`** —— 状态口径只有它一处，⛔ 别在这里另写一套判断。
    """
    # B8 · 会话级 token 上限（`DEC-041`）—— 触顶动作 = 直接拒绝（与 `/agent/langgraph_chat` 同）
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）—— 与上一段**并列、都要过**
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # 🅾 丙段：**checkpoint / 待接管队列**用拼过身份的键；⛔ 响应里回显的仍是原 `thread_id`。
    #    ⚠️ 与 `check_session_token_budget`（上面，用原值）**是两条轴**，别合并。
    sess = session_key(user_name, thread_id)

    ENDPOINT = "agent_langgraph_chat_stream"   # Prometheus 的 label（`③` Task 5）

    async def generate():
        stream = None
        # ⚠️ 默认按「被取消」算 —— 只有跑到收尾才改成 `"done"`（理由同 `/rag/stream_search`：
        #    Starlette 2.3 抛 `CancelledError`、2.4 抛 `GeneratorExit`，两条都要记到）。
        outcome = "cancelled"
        try:
            # ⚠️ 必须**绑成变量**：`finally` 里要 `aclose()` 它。
            #    ⛔ 别退回"在 `async for` 里内联调用" —— 那样拿不到这个流的句柄，关不掉。
            stream = agent_graph.astream(
                {"messages": [HumanMessage(content=question)]},
                config={"configurable": {"thread_id": sess}},
                stream_mode="messages",
            )
            async for chunk, meta in stream:
                # ⚠️ 只转发 `agent` 节点出的块。图里还有 `tools` / `approval` 节点，
                #    不加这道过滤，它们吐的消息会**混进正文**
                #    （实测：`tools` 节点的 `ToolMessage` 内容会作为一块出现）。
                if meta.get("langgraph_node") != "agent":
                    continue

                # ⚠️ 空 content 的块**必须跳过**：`tool_call` 的碎片 content 就是空的
                #    （实测：一次 tool_call 会来 2–3 个空 content 块）。
                #    不过滤 ⇒ 前端收到一串空白帧。
                if chunk.content:
                    yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
            outcome = "done"
        except asyncio.CancelledError:
            # 客户端断开（`③` Task 5 · `B2`）—— ⛔ **不许吞**：吞掉外层会以为这是"正常结束"。
            # ⚠️ 也**不许在这里 yield**：接收方已经走了，发出去只会让帧层面分不清
            #    「已取消」与「正常收尾」（`/rag/stream_search` 那边的实测同款）。
            raise
        except Exception as e:
            outcome = "error"
            # 兜底：⛔ 别让异常**静默**变成"流自然结束" —— 那前端看到的是
            # "答案说了一半就没了"，而**没有任何错误信号**。
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        finally:
            # 🔴🔴 **顺序与关流方式 = 2026-10-03 真服务实测改的**（与 `api_v1_rag.py` 同一处病）：
            #    `await stream.aclose()` 会被**二次投递的取消**打断 ⇒ 抛 `CancelledError`
            #    ⇒ 排在它后面的计数与日志**一件都不跑**（实测：计数 `2.0→2.0`、日志没有）。
            #    ⇒ ① **同步**的收尾提到 `await` 之前 · ② 关流用 shield 护住。
            if outcome == "cancelled":
                track_stream_cancel(ENDPOINT)
                logger.info(f"[cancel] 客户端断开，已停止生成并关闭图的流 endpoint={ENDPOINT}")

            # 🔴🔴 **本任务的核心动作**：客户端断开后**关掉图的流**。
            #    不关 ⇒ 图会**继续跑完**（`DEC-050` §遗留·3 自己点了这条：
            #    "新的流式路由同样没有 cancel 处理"）—— 继续跑 = 继续调模型 = 继续烧钱。
            #    ⚠️ `shield=True` **必须**：取消作用域反复投递取消，不护住 ⇒ 关流半途而废。
            if stream is not None:
                with anyio.CancelScope(shield=True):
                    await stream.aclose()

        # 🔴🔴 **状态必须取自【图的最终状态】，⛔ 不是"把 `agent` 节点的流式块攒起来"。**
        #
        #    这一条是 **2026-10-03 在真服务上跑出来的**（`③` Task 4 Step 4），不是想出来的：
        #    问一句会触发搜索的话，模型因工具报「未找到工具」而**重试了好几轮**。
        #    原先攒块 ⇒ 攒出的消息**带着上一轮的 `tool_calls`** ⇒ `summarize_agent_result`
        #    判成 `pending_approval` ⇒ **接口报"在等人工审批"，而图其实早就跑完了**
        #    （前端会一直等一个**永远不会来**的批准）。
        #    攒块还会让两轮的 name 粘成 `"date_todayduckduckgo_search"` 这种串
        #    （⚠️ 那是**当时的工具名**；`DEC-051` 已把搜索换成 `web_search` ⇒ ⛔ 别拿这串当真名）。
        #
        #    ⚠️ 一轮就能跑完的场景**盖不住**它 ⇒ 守卫用**两轮**的假图：
        #       `api/test_agent_sse.py::test_status_comes_from_final_state_not_from_streamed_chunks`
        #
        #    ✅ 这样与 `/agent/langgraph_chat` 的口径**完全一致**（它也喂 `result` 整份 state），
        #       状态判定只有 `summarize_agent_result` 一处，⛔ 不在这里另写一套。
        state = await agent_graph.aget_state({"configurable": {"thread_id": sess}})
        summary = summarize_agent_result(state.values or {})

        # B5 · 待接管队列（`②` Task 2）—— 与 `/agent/langgraph_chat` 同款：
        # ⚠️ `else` 那支不是可省的：本轮没卡住 ⇒ 清掉上一次的登记，
        #    否则同一个 thread 卡过一次就**永远留在队列里变成假待办**。
        if summary.get("status") == "pending_approval":
            register(sess, user_name, summary.get("pending_tool_calls") or [],
                     raw_thread_id=thread_id, graph="agent_graph")
        else:
            resolve(sess)

        yield f"data: {json.dumps({'thread_id': thread_id, **summary}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    # ⚠️ `X-Accel-Buffering: no` 不能省：有反代（Nginx / Cloudflare）时它会把 SSE **攒着发**，
    #    本地直连一切正常、**上线后变成假流式** —— 而那是本任务唯一要防的东西。
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ==================== 属于AgentGraph 接口下  新增的： AgentGraph 人工审批接口 ====================


@router.post("/agent/approve")
async def approve_agent_action(
    thread_id: str,
    approved: bool,
    edited_answer: str = None,
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    人工审批接口：批准 / 拒绝 / **改写后提交**（`B6`）。

    🔴 **续跑走的是 `agent_graph.invoke(None, config)`** —— `None` = **从 checkpoint 继续**，
       ⛔ **不是**新开一轮。改成喂新消息 = 上下文断裂，**而接口返回看着一模一样**。
       守卫 ⇒ `api/test_approval_resume.py`（假图钉住调用形状）。

    `edited_answer`：**人工把答案改过之后再放行**。
      · 不给 ⇒ 按原样续跑（行为与改动前一致）
      · 给了 ⇒ 先 `update_state` 把改写推成一条 **`AIMessage`**，再从 checkpoint 续跑
        ⚠️ **必须进 state、不能只当返回值吐出去** —— 只放响应里，**后续节点看不到这个改写**。
        ⚠️ 必须是 `AIMessage`，⛔ 不是 `HumanMessage` —— 后者会让模型把"人给的结论"当**新输入**再答一遍。
      · ⚠️ **只有"批准"时才生效**；拒绝时给了也会被忽略（拒绝的语义是"别做了"）。
    """
    # 🔴 丙段（`DEC-056`）：**先按【原 thread_id】查队列定属主，再按属主拼键**。
    #    ⛔ 别按调用方拼 —— admin 会拼出自己那个不存在的桶 ⇒ **永远批不了别人的**（硬门 D 死掉）。
    candidates = find_by_raw_thread_id(thread_id)
    if not candidates:
        # ⚠️ 队列是**唯一**入口（`MemorySaver` 反查不出"谁卡住了"）⇒ 这里没有 = 没有可批的。
        #    已知代价：`AGENT_CHECKPOINT_BACKEND=sqlite` 重启后（图在盘上、队列在内存）
        #    会走到这一支 —— 但那种会话**本来就已经是孤儿**（见 `pending_approvals` 模块 docstring）。
        return {"status": "error", "message": "当前没有等待审批的任务"}

    if len(candidates) > 1:
        # 同一个原 thread_id 被多个人用过 ⇒ **光凭它定不了是哪一条**（这正是隔离问题本身）。
        # ⛔ 别"挑第一条" —— 那等于随机批一个人的会话。
        owners = sorted({c["user_name"] for c in candidates})
        return {
            "status": "error",
            "message": (f"thread_id={thread_id!r} 对应多条待审批会话（属主：{owners}）—— "
                        f"请先看 `/agent/pending` 确认是哪一个"),
        }

    owner = candidates[0]["user_name"]
    # 🔴 归属校验：**本人或 admin**（admin 那条不是可省的 —— 队列本来就跨用户）。
    if user_name != owner and get_user_role(user_name) != UserRole.ADMIN:
        return {"status": "error", "message": f"无权审批：该会话属于 {owner}"}

    # ⚠️ 用**登记时拼好的**那个键（`candidates[0]["thread_id"]`），⛔ **不在这里重拼** ——
    #    重拼 = 又多一处"拼法"口径，两处一旦不一致，`resolve()` 会静默清不掉（幂等、不报错）。
    sess = candidates[0]["thread_id"]
    config = {"configurable": {"thread_id": sess}}

    # 🔴 按**登记的图**路由（业务方 2026-10-03 裁）：`/agent/langgraph_chat` ⇒ `agent_graph`，
    #    `/agent/memory_chat` ⇒ `checkpointer_agent`。
    #    ⛔ 写死 `agent_graph` 的后果：memory_chat 那条会话**永远放行不了**
    #    （门关了却没有钥匙 —— 比不加门还糟）。
    # ⚠️ 字典**在这里现建**（⛔ 不是模块级常量）：模块级常量会把图对象**早绑定**，
    #    测试里 `monkeypatch.setattr(m, "agent_graph", …)` 就换不掉了。
    GRAPHS = {"agent_graph": agent_graph, "checkpointer_agent": checkpointer_agent}
    graph_name = candidates[0].get("graph", "agent_graph")
    target = GRAPHS.get(graph_name)
    if target is None:
        # ⛔ 别「猜一个」 —— 猜错就是往**别的图**上写状态。
        return {
            "status": "error",
            "message": f"登记表里的图名不认识：{graph_name!r}（已知：{sorted(GRAPHS)}）",
        }

    # 获取当前图的状态
    current_state = target.get_state(config)

    if current_state.next != ("approval",):
        # B5：图没停在审批点 ⇒ **注册表里若有这个 thread，那是陈的** ⇒ 顺手清掉。
        # ⚠️ 这一支也要清 —— 否则"/agent/pending 说有，批的时候说没有"，对不上。
        resolve(sess)
        return {"status": "error", "message": "当前没有等待审批的任务"}

    if approved:
        if edited_answer is not None:
            # B6：人工改写 ⇒ 推进 messages，**再从 checkpoint 续跑**。
            # ⚠️ 不能"跳过模型直接把这个答案返回" —— 那样后续节点（`tools`→`agent`）看不到它。
            target.update_state(
                config, values={"messages": [AIMessage(content=edited_answer)]}
            )
        else:
            # 原样放行：`values=None` ⇒ 不改 state，图继续前进到 approval 节点，然后去 tools
            target.update_state(config, values=None)
        result = target.invoke(None, config)
    else:
        # 拒绝：更新 state，添加一条消息，并终止工具调用流程
        target.update_state(
            config,
            values={"messages": [HumanMessage(content="审批拒绝，请忽略工具调用请求，直接告知用户操作已被拒绝。")]}
        )
        result = target.invoke(None, config)
    
    final_message = result["messages"][-1]

    # B5：批完就注销 —— 否则它会**永远留在队列里**（`resolve` 幂等，重复调不抛）。
    resolve(sess)

    return {
        "status": "approved" if approved else "rejected",
        "thread_id": thread_id,
        "answer": final_message.content,
        "requested_by": user_name,
    }


@router.get("/agent/pending")
async def list_pending_approvals(
    user_name: str = Depends(get_current_user_hybrid),
):
    """列出**当前等待人工接管**的会话（硬门 D 的入口）。

    🔴 **为什么要有这个端点**：`MemorySaver` **没有"列出全部 thread"的 API**
    ⇒ 没有它，**接管事件在界面上根本找不到**（硬门 D 判据③ 的反例正是这个）。
    数据来自 `api/pending_approvals.py`（**进程内存** —— ⚠️ 重启即空，见其 spec）。

    ⚠️ **本端点只读**，不改任何状态；批准/拒绝走 `POST /agent/approve`。

    🔴 **2026-10-03（`DEC-056` 丙段）起每行多两个字段**（**加性**，老调用方不受影响）：
      · `raw_thread_id` —— 调用方传的**原值**（`thread_id` 现在是**拼过身份**的键）
      · `graph` —— 这条会话停在**哪张图**上（`agent_graph` / `checkpointer_agent`）
        ⇒ **批量批的时候要看它**：`/agent/approve` 按它选图。
    """
    rows = list_pending()
    return {"count": len(rows), "items": rows, "requested_by": user_name}

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
    # B8 · 会话级 token 上限（`DEC-041`）
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）。与上一段**并列、都要过**：
    # B8 管"这个会话花了多少"，这段管"全站今天花了多少"。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # 🅾 丙段断言点：图收到的键 = 拼过身份的（⛔ 不是裸 `thread_id`）
    sess = session_key(user_name, thread_id)

    result = advanced_agent.invoke(
        {
            "messages": [HumanMessage(content=question)],
            "user_name": user_name,
            "memory_space": memory_space,
        },
        config={"configurable": {"thread_id": sess}}
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
    thread_id: str = "default",       # ⚠️ B8 补：本端点原先**没有** thread_id
    user_name: str = Depends(get_current_user_hybrid),
):
    """完整的 Plan-and-Execute 流程"""
    # B8 · 会话级 token 上限（`DEC-041`）—— 触顶直接拒绝
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）。与上一段**并列、都要过**：
    # B8 管"这个会话花了多少"，这段管"全站今天花了多少"。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # 1. 规划：将用户目标分解为步骤清单
    # ⚠️ 2026-09-20 修：此处原是一个**字符串字面量**（`"""任务规划接口：…"""`）——
    #    函数在上一行**已经有 docstring** ⇒ 它是**空操作**；
    #    且它描述的是「规划」这一**子步骤**，不是整个函数的职责。
    #    ⇒ 改成**普通注释**（保留信息、去掉误导）。
    # 🔴 2026-09-21 改（§十四 · ③-a/③-b），两件事一起：
    #
    #  ① **丢到线程里跑** —— `plan_task` / `execute_plan` 是**同步**的，直接在 async 端点里调
    #     会**阻塞事件循环**（一个慢请求卡住**整个 API**）。
    #     以前执行是「LLM 模拟」所以很快；**N15 真调工具之后会真发网络请求、真跑代码**，
    #     阻塞的代价从"理论问题"变成"现实问题"。
    #     📌 同型先例：`/agent/fetch_webpage` 那两个端点也是因为这个才用 `asyncio.to_thread`。
    #
    #  ② **接住 `BudgetExceededError`** —— `plan_execute` 现在**查预算并记账**（③-b）。
    #     预算耗尽要报 **QUOTA_EXCEEDED**，而不是漏成 500。
    #     ⚠️ 用 `AppException` 是**路由层**抛的，能被全局处理器接住
    #     （中间件里抛的接不住 —— 见 `CLAUDE.md` 的那条警告；这里是路由层，安全）。
    try:
        plan = await asyncio.to_thread(plan_task, goal, user_name)
        execution_result = await asyncio.to_thread(execute_plan, plan, goal, user_name)
    except BudgetExceededError as e:
        raise AppException(
            ErrorCode.QUOTA_EXCEEDED,
            f"今日 Token 预算已用完，无法执行本任务。{e}",
        )

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
    """带持久化记忆的 Agent 对话接口。

    ⚠️ **2026-10-03（`DEC-056` 丙段）起带人工审批**：若返回 `status="pending_approval"`，
       说明**工具还没执行**，要带同一个 `thread_id` 走 `/agent/approve` 继续。
       🔴 改动前本端点**没有审批门** —— 同一个仓里，`/agent/langgraph_chat` 停下等人批、
       而这里**直接执行**（`DEC-051` §遗留·2）。
    """
    # B8 · 会话级 token 上限（`DEC-041`）
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）。与上一段**并列、都要过**：
    # B8 管"这个会话花了多少"，这段管"全站今天花了多少"。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # 🅾 丙段断言点：图收到的键 = 拼过身份的（⛔ 不是裸 `thread_id`）
    # 🔴 本端点就是 `DEC-056` 丙段点名的那个 —— 两个人用默认 `thread_id` 曾共用一个桶。
    sess = session_key(user_name, thread_id)
    config = {"configurable": {"thread_id": sess}}
    result = checkpointer_agent.invoke(
        {"messages": [HumanMessage(content=question)]},
        config=config
    )
    # 🔴 丙段：本端点现在**会停在审批点**（`checkpointer_agent` 的 `interrupt_before=["approval"]`）。
    #    ⇒ 状态判定**复用 `summarize_agent_result`**，⛔ 别再在这里另写一套
    #      （它已经是"停没停在审批点"的**唯一**口径，见其 docstring）。
    summary = summarize_agent_result(result)

    # B5 · 待接管队列 —— 与 `/agent/langgraph_chat` 同款：卡住 ⇒ 登记；没卡住 ⇒ 清掉上一次的。
    # ⚠️ `graph="checkpointer_agent"` **必须写**：`/agent/approve` 靠它决定续跑哪张图
    #    （写上之前，approve 只会去问 `agent_graph` ⇒ 这个会话**永远放行不了**）。
    if summary.get("status") == "pending_approval":
        register(sess, user_name, summary.get("pending_tool_calls") or [],
                 raw_thread_id=thread_id, graph="checkpointer_agent")
    else:
        resolve(sess)

    return {
        "question": question,
        "thread_id": thread_id,
        "requested_by": user_name,
        **summary,
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
#
# ⛔⛔ 2026-09-21 整块注释（N13 · 业务方裁「挂起 + 直接注释掉 + 标『# 可扩展能力』」）
#
#   **# 可扩展能力 —— 装上 chromium 后取消下面的注释即可启用。**
#
#   为什么挂起（两条都实测过，缺一不可）：
#     ① 本仓**任何部署方式都没装 chromium**（`api/Dockerfile` / `docker-compose.yml`
#        都没有 `playwright install`）⇒ 不只是"本机的问题"
#     ② 本机**缓存里的 chromium 是旧 build（1228，556 MB）**，而 playwright 1.62 要 build **1234**
#        ⇒ 版本不匹配，**装了旧的也照样跑不了**
#   实测报错原文：
#     `BrowserType.launch: Executable doesn't exist at .../chromium_headless_shell-1234/...`
#
#   为什么**不是**留一个会 500 的端点：那正是本仓反复在防的
#     「**看起来能用、其实不能用**」。宁可不暴露。
#   ⚠️ 代价：`ROUTES` 由 **14 → 12**（在 PR 里显式声明过）。
#
#   重新启用时**必须一起做**（否则会踩回 2026-09-20 修过的那个坑）：
#     · 取消 `api/mcp_server.py` 里 `TOOLS` 的两行 + `browser_tools` 的 import
#     · 取消 `api/tool_health.py` 里 `TEST_ARGS_MAP` 的两项
#     · 取消 `api/api_v1_agent.py` 顶部的 `from browser_tools import ...`
#     · 把 `api/test_agent_repairs.py` 里那两条 skip 掉的用例恢复
#   保留下来的知识（**别丢**）：这两个端点**必须**用 `asyncio.to_thread` 跑 ——
#     `browser_tools` 是 Playwright **同步** API，直接在 async 端点里调会报
#     `It looks like you are using Playwright Sync API inside the asyncio loop.`（实测）。
#     对应用例现在 skip 着，重新启用时取消 skip。
#
# @router.post("/agent/fetch_webpage")
# async def agent_fetch_webpage(
#     url: str,
#     user_name: str = Depends(get_current_user_hybrid),
# ):
#     """使用Playwright获取网页文本内容
#
#     🔴 2026-09-20 修:必须丢到**线程**里跑 —— `browser_tools` 用的是 Playwright
#        **同步** API，而本端点是 async ⇒ 直接在事件循环所在线程里调会报
#        `playwright._impl._errors.Error: It looks like you are using Playwright
#        Sync API inside the asyncio loop.`（实测）
#        ⛔ 不能把 `browser_tools` 改成 async —— 它同时被 **MCP server 的同步路径**
#           调用（`create_mcp_tool_handler` 里是同步 `tool_func.invoke`）。
#        回归测试:`api/test_agent_repairs.py::test_fetch_webpage_is_not_invoked_on_the_event_loop`
#     """
#     result = await asyncio.to_thread(fetch_webpage.invoke, {"url": url})
#     return {"url": url, "content": result, "requested_by": user_name}
#
# # ==================== 新增“网页截图”工具测试接口 ====================
# # 添加一个“网页截图”工具（使用page.screenshot()），让Agent能把网页保存为图片。
#
# @router.post("/agent/screenshot_webpage")
# async def agent_screenshot_webpage(
#     url: str,
#     user_name: str = Depends(get_current_user_hybrid),
# ):
#     """使用Playwright截取网页并保存为图片
#
#     🔴 2026-09-20 修:同上（`fetch_webpage` 那条的孪生兄弟）——
#        同步 Playwright 必须丢到线程里跑。**两个端点一起修**，防止只改一个。
#        回归测试:`api/test_agent_repairs.py::test_screenshot_webpage_is_not_invoked_on_the_event_loop`
#     """
#     result = await asyncio.to_thread(screenshot_webpage.invoke, {"url": url})
#     return {"url": url, "result": result, "requested_by": user_name}

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
    await run_health_check()
    return {"tools": _tool_health, "requested_by": user_name}


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
    """查看当前用户的 Token 预算信息 + **全站**日级额度。

    ⚠️ 2026-10-03（`①b` Task 7 · `B13`）**加了 `global_*` 三个字段** ——
    在那之前，`B10`/`B11` 的全站日级额度（超了**所有人**吃 429）**没有任何出口**：
    `get_global_daily_token_usage()` 全仓只被 `breaker` 调过。
    ⇒ 看不见它逼近，只能等 429。

    ⚠️ **两套口径，别读混**：
      · `daily_budget` / `used_today` / `remaining` = **本用户**（`R1.3`，`QuotaMiddleware` 用它）
      · `global_*` = **全站合计**（`R1.4`，`B10`/`B11` 用它）
      ⛔ 两者不是同一个上限的两半。
    """
    info = get_token_budget_info(user_name)
    global_used = get_global_daily_token_usage()
    return {
        "user_name": user_name,
        **info,
        "global_daily_limit": GLOBAL_DAILY_TOKEN_LIMIT,
        "global_used_today": round(global_used, 2),
        # ⚠️ `get_global_daily_token_usage()` 查库失败是 fail-open（返回 0.0）
        #    ⇒ 那种情况下这里会显示"全站还剩满额"。与同族取舍一致，⛔ 不加特判。
        "global_remaining": round(max(0, GLOBAL_DAILY_TOKEN_LIMIT - global_used), 2),
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
    """使用 MCP Client 的 Agent 对话接口（请求级隔离）

    ⚠️ 2026-09-20 修：这段 docstring 原先**躺在 `start_trace()` 之后**（函数体第二句），
       是**空操作** —— 函数本身**没有 docstring**。已上移到签名正下方。
    """
    # 记录工具 开始追踪
    start_trace(thread_id, question)

    # B8 · 会话级 token 上限（`DEC-041`）
    # ⚠️ 放在 `start_trace` **之后**：超限被拒时，追踪里仍留得下这次尝试的痕迹。
    #    本端点原有的 `check_budget` 依赖判的是【用户**日**预算】，与会话级是**两个东西**，并存。
    ok, why = check_session_token_budget(user_name, thread_id)
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # B11 · 全站日级熔断（`①b` Task 4）。与上一段**并列、都要过**：
    # B8 管"这个会话花了多少"，这段管"全站今天花了多少"。
    ok, why = circuit(global_key())
    if not ok:
        raise AppException(ErrorCode.QUOTA_EXCEEDED, why)

    # 🅾 丙段断言点：**checkpoint 键**拼身份（⛔ 不是裸 `thread_id`）。
    # ⚠️ 但下面 state 里的 `thread_id` **保持原值** —— 它喂的是【追踪/花费】那条轴
    #    （`agent_graph_advanced.py:246/268` → `record_tool_*`），
    #    那条轴的**读**端点 `/agent/trace/{thread_id}`（`:1133`）用的也是原值。
    #    ⛔ 两条轴别混：混了就得连追踪的读写一起改（那是另一件事，不是丙段）。
    #    🔴 **那条轴本身有跨用户可见的洞** ⇒ 已立账 `docs/待办总表.md` 的 **N4**。
    sess = session_key(user_name, thread_id)

    result = await mcp_agent.ainvoke(
        {
            "messages": [HumanMessage(content=question)],
            "user_name": user_name,
            "memory_space": memory_space,
            "thread_id": thread_id,     # 注入 thread_id（追踪轴，保持原值）
        },
        config={"configurable": {"thread_id": sess}}
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
    tools_result = await get_mcp_tools()
    # 🔴 2026-09-20 修:`get_mcp_tools()` 返回的是 **`ListToolsResult`**（列表在 `.tools`），
    #    **不是列表本身** —— 与本文件另一处（`get_llm_with_mcp_tools`）是**同一个 bug 的
    #    两个入口**，先前只修了那一个 ⇒ 本路由 `for t in tools` 必
    #    `AttributeError: 'tuple' object has no attribute 'name'` ⇒ **100% 500**；
    #    且 `len(tools)` 同样不对。
    #    回归测试:`api/test_agent_repairs.py::test_mcp_tools_dynamic_handles_list_tools_result`
    _tools = tools_result.tools
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema
            }
            for t in _tools
        ],
        "total": len(_tools),
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
    花费总览：展示当前用户的 Token 消耗和费用概况。**读库 · 全时累计**。

    ⚠️ 2026-10-03（`①b` Task 7 · `B13`）**改了口径**，两处都改了：

    | | 改前 | 改后 |
    |---|---|---|
    | 数据源 | `get_user_summary` / `get_purpose_summary` —— **进程内存**，重启归零 | `get_user_overview` —— **读 `token_usage_logs`** |
    | 窗口 | 本进程启动以来 | **全时累计** |
    | `by_purpose` 范围 | 🔴 **全站**（那两个内存函数都不分用户） | **本人**（与 `total_*` 一致） |

    🔴 **为什么必须改**：改前它自称"最直观的『花了多少钱』查询接口"，
    但实测 admin 在库里有 **4216 tokens**、它答 `0` —— **不报错、界面照常出数**。
    📄 实跑记录 ⇒ `docs/specs/token_tracker.md` 的 `①b` Task 7 段。

    ⚠️ **"今天花了多少"不归本接口** —— 那是 `R1.3` 口径，
       去 `/agent/token/budget`（或看板）。本接口答的是"一共"。
    """
    overview = get_user_overview(user_name)

    return {
        "user_name": user_name,
        "total_cost": overview["total_cost"],
        "total_tokens": overview["total_tokens"],
        "total_calls": overview["calls"],
        "by_purpose": overview["by_purpose"],
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