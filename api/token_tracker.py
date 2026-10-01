"""
Token 统计与成本追踪模块（支持数据库持久化）
"""
import time
import asyncio
from typing import Optional, Dict
from dataclasses import dataclass, field
from collections import defaultdict
# 从 db.py 导入数据库连接（注意路径）
# ⚠️ 2026-09-17 重构 ⑥ 切开点 2：此处**原先在模块层**导入 `db.get_db`，且**重复了两行**
#    （L10 与 L13）。后果：`import token_tracker` 会连带拉起 **psycopg2**，
#    哪怕调用方只想用本模块的纯计算函数（PRICING / 预估 / 汇总）。
#    现改为**函数内惰性导入** —— 见下方各函数体首行的 `from db import get_db`，
#    与本文件既有的 `from permission import ...`（L291）、`import calendar`（L377）同一写法。
#    ⚠️ 位置放在函数体最前、`try` 之前 —— 放 `try` 里会被本函数自己的 `except` 吞掉，掩盖 ImportError。
import threading
import os
import json

# ==================== 数据模型 ====================
@dataclass
class TokenUsage:
    """单次 LLM 调用的 Token 用量"""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    purpose: str           # 调用目的：answer_generation, query_rewrite, tool_execution, etc.
    user_name: str         # 哪个用户
    thread_id: str         # 哪个会话
    cost: float
    timestamp: float = field(default_factory=time.time)

# ==================== 全局统计存储（线程安全，用于快速汇总查询） ====================
_usage_records: list[TokenUsage] = []
_lock = threading.Lock()

# 按用户汇总的统计
_user_summary: Dict[str, Dict] = defaultdict(lambda: {"total_tokens": 0, "total_cost": 0.0, "calls": 0})

# 按用途汇总的统计
_purpose_summary: Dict[str, Dict] = defaultdict(lambda: {"total_tokens": 0, "total_cost": 0.0, "calls": 0})

# 新增：按 thread_id 汇总的统计
_thread_summary: Dict[str, Dict] = defaultdict(lambda: {"total_tokens": 0, "total_cost": 0.0, "calls": 0})

# ==================== 模型计费单价（元/1000 tokens） ====================
# ⚠️ 2026-10-01 搬家（B7）：**常量已移到 `api/token_config.py`**（额度类常量的唯一落点）。
#    这里保留 `PRICING` / `_DEFAULT_PRICING` 两个**同名别名** ⇒ 现有调用方与测试无需改动。
#    ⛔ 行为不变：值逐字相同。
#    📄 为什么搬：额度常量原先散在 4 个文件 6 处，单位还混着 —— 见 `token_config.py` 顶部。
#
#    2026-09-16 的既有约定（**随常量一起搬到 token_config**）：
#    兜底单价与 `record_cost` **共用一份**，别再各写一份 —— 否则对未登记模型，
#    `token_usage_logs.cost` 与 `cost_records.total_cost` 会算出**两个不同金额**，两张表对不上账。
from token_config import (                                    # noqa: E402
    MODEL_PRICING as PRICING,
    DEFAULT_MODEL_PRICING as _DEFAULT_PRICING,
    ROLE_DAILY_TOKEN as ROLE_TOKEN_BUDGET,
    DEFAULT_DAILY_TOKEN_BUDGET,
)

# ==================== 预算控制相关常量 ====================
# ⚠️ 2026-09-20 删（§三·C2）：此处原有 `DEFAULT_DAILY_TOKEN_BUDGET` 与 `ROLE_TOKEN_BUDGET`
#    的**一份重复定义**，与文件下方（`get_user_token_budget` 之前）那份**逐字同值**，
#    而 Python **后者胜出** ⇒ **这一份是被完全遮蔽的死定义**（改它不生效、也不报错）。
#    下方那份**还带注释**（"免费用户：每天1万token"），是更好的那份 ⇒ 保留下方、删此处。
#    📌 与 §二（`remove_noise_markers` 重复定义）**同型**。


def record_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    purpose: str,
    user_name: str = "unknown",
    thread_id: str = "unknown",
    tool_name: str = None,
    tool_args: dict = None,
):
    """记录一次 LLM 调用的 Token 消耗，同时写入内存缓存和数据库。"""
    from db import get_db
    total = prompt_tokens + completion_tokens
    # 计算成本（必须先于 TokenUsage 构造，否则引用未定义变量）
    pricing = PRICING.get(model, _DEFAULT_PRICING)
    cost = (prompt_tokens / 1000) * pricing["prompt"] + (completion_tokens / 1000) * pricing["completion"]
    usage = TokenUsage(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total,
        purpose=purpose,
        user_name=user_name,
        thread_id=thread_id,
        cost=cost,
    )
    
    # 1. 写入内存缓存
    with _lock:
        _usage_records.append(usage)
        # 只保留最近 1000 条记录，防止内存溢出
        if len(_usage_records) > 1000:
            _usage_records.pop(0)
        
        # 更新用户汇总
        _user_summary[user_name]["total_tokens"] += total
        _user_summary[user_name]["total_cost"] += cost
        _user_summary[user_name]["calls"] += 1
        
        # 更新用途汇总
        _purpose_summary[purpose]["total_tokens"] += total
        _purpose_summary[purpose]["total_cost"] += cost
        _purpose_summary[purpose]["calls"] += 1

        # 新增：更新 thread 维度汇总
        _thread_summary[thread_id]["total_tokens"] += total
        _thread_summary[thread_id]["total_cost"] += cost
        _thread_summary[thread_id]["calls"] += 1

    # 2. 持久化到数据库（异步写入，不影响主流程）
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO token_usage_logs 
                       (user_name, thread_id, model, purpose, prompt_tokens, completion_tokens, total_tokens, cost)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_name, thread_id, model, purpose, prompt_tokens, completion_tokens, total, cost)
                )
                conn.commit()
    except Exception as e:
        print(f"[Token] 持久化Token记录失败: {e}")
    # 新增：持久化写入数据库
    record_cost(
        user_name=user_name,
        thread_id=thread_id,
        model=model,
        purpose=purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        tool_name=tool_name,
        tool_args=tool_args,
    )
    print(f"[Token] {purpose} | {model} | {total} tokens | ¥{cost:.4f} | 用户: {user_name}")
    
    # 当单次调用或单日花费超过预设阈值时，自动发送告警
    DAILY_COST_ALERT_THRESHOLD = 10.0  # 每日花费超过10元时告警
    if get_user_summary(user_name).get("total_cost", 0) > DAILY_COST_ALERT_THRESHOLD:
        print(f"⚠️ 用户 {user_name} 今日花费已超过 {DAILY_COST_ALERT_THRESHOLD} 元！")

#
def record_cost(
    user_name: str,
    thread_id: str,
    model: str,
    purpose: str,
    prompt_tokens: int,
    completion_tokens: int,
    tool_name: str = None,
    tool_args: dict = None,
):
    """
    将单次调用的花费明细写入数据库。
    这是花费数据持久化的核心函数。
    """
    from db import get_db
    # 计算费用
    pricing = PRICING.get(model, _DEFAULT_PRICING)
    input_cost = (prompt_tokens / 1000) * pricing["prompt"]
    output_cost = (completion_tokens / 1000) * pricing["completion"]
    total_cost = input_cost + output_cost
    
    # 序列化工具参数
    tool_args_json = json.dumps(tool_args, ensure_ascii=False) if tool_args else None
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO cost_records 
                       (user_name, thread_id, model, purpose, prompt_tokens, completion_tokens, 
                        total_tokens, input_cost, output_cost, total_cost, tool_name, tool_args)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_name, thread_id, model, purpose, prompt_tokens, completion_tokens,
                     prompt_tokens + completion_tokens, input_cost, output_cost, total_cost,
                     tool_name, tool_args_json)
                )
                conn.commit()
    except Exception as e:
        print(f"[Cost] 持久化花费记录失败: {e}")
# ==================== 从数据库查询当日 Token 使用量（用于预算控制） ====================

def get_daily_token_usage(user_name: str) -> float:
    """
    从数据库查询用户今日已消耗的 Token 总数。
    这是预算控制的权威数据源，不依赖内存缓存。
    """
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(total_tokens), 0) 
                       FROM token_usage_logs 
                       WHERE user_name = %s 
                         AND created_at >= CURRENT_DATE""",
                    (user_name,)
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"[Token] 查询当日用量失败: {e}")
        # 降级：返回内存缓存中的值
        with _lock:
            return _user_summary.get(user_name, {}).get("total_tokens", 0)

# ==================== 从数据库查询历史统计（用于趋势分析） ====================
def get_user_history(user_name: str, days: int = 30) -> list:
    """获取用户最近N天的每日Token消耗历史"""
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT DATE(created_at) as date, 
                              SUM(total_tokens) as tokens, 
                              SUM(cost) as cost,
                              COUNT(*) as calls
                       FROM token_usage_logs 
                       WHERE user_name = %s 
                         AND created_at >= CURRENT_DATE - %s
                       GROUP BY DATE(created_at)
                       ORDER BY date DESC""",
                    (user_name, days)
                )
                rows = cur.fetchall()
                return [{"date": str(r[0]), "tokens": r[1], "cost": round(r[2], 4), "calls": r[3]} for r in rows]
    except Exception as e:
        print(f"[Token] 查询历史数据失败: {e}")
        return []

# ==================== 原有的查询函数（保留内存缓存快速查询） ====================
def get_user_summary(user_name: str = None):
    """获取用户维度的汇总统计"""
    with _lock:
        if user_name:
            return dict(_user_summary.get(user_name, {}))
        return dict(_user_summary)

def get_purpose_summary():
    """获取用途维度的汇总统计"""
    with _lock:
        return dict(_purpose_summary)

def get_thread_summary(thread_id: str = None):
    """获取线程维度的汇总统计"""
    with _lock:
        if thread_id:
            return dict(_thread_summary.get(thread_id, {}))
        return dict(_thread_summary)
    
def get_recent_usage(limit: int = 20):
    with _lock:
        return [
            {
                "model": u.model,
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.total_tokens,
                "purpose": u.purpose,
                "user_name": u.user_name,
                "thread_id": u.thread_id,
                "cost": round(u.cost, 4),
                "timestamp": u.timestamp,
            }
            for u in _usage_records[-limit:]
        ]

# ==================== 预算控制 ====================
# ==================== 预算控制函数（已改用数据库查询） ====================
# 1. 成本计算与预算控制
# 在 Token 统计的基础上，你可以实现预算控制：为每个用户设置每日 Token 上限，
# 达到上限后自动拒绝调用或切换为本地小模型。这与第12天的配额检查机制类似，
# 只是维度从“请求次数”变成了“Token 消耗”。
# 默认每日Token预算（可通过环境变量覆盖）
# ⚠️ 2026-10-01 搬家（B7）：本行与下面的 `ROLE_TOKEN_BUDGET` 都已移到 `api/token_config.py`，
#    在文件顶部 import 进来。两个名字保持不变 ⇒ 调用方无需改动。
#
#    顺带按 `DEC-040`（决策一）去掉了 `"admin": float("inf")` ——
#    业务方裁「admin 也要同样上限」⇒ 现在是**有限值**（= premium = 100000/天）。
#    ⚠️ 但"全局日级"是**另一个东西**（B10，在 ①b）—— per-user 检查永远看不到
#    「大家加起来超了」，别拿这条替代它。

def get_user_token_budget(user_name: str) -> float:
    """
    获取用户的每日Token预算。
    根据用户角色返回对应的预算上限。
    """
    from permission import get_user_role, UserRole
    role = get_user_role(user_name)
    return ROLE_TOKEN_BUDGET.get(role, DEFAULT_DAILY_TOKEN_BUDGET)

def check_token_budget_detail(user_name: str, estimated_tokens: int = 0) -> tuple[bool, str]:
    """每日 Token 预算检查 —— **唯一实现**，带原因说明。

    ⚠️ 2026-09-16 抽出本函数：此前 `check_token_budget` / `check_budget_before_call` /
    `check_multilevel_budget`(第三级) **各写一份**同样的判定，且后两份把单位写成「元」
    去和 **Token 预算**相减 ⇒ **恒放行**（见 `docs/decisions/DEC-002`）。
    本函数是**量纲正确**的那一份（Token vs Token），其余一律委托到这里。

    **不含** `record_intercept` —— 拦截记录由调用方负责（各调用方要带上自己的 tool_name）。
    """
    budget = get_user_token_budget(user_name)
    if budget == float("inf"):
        return True, "管理员无限预算"
    used = get_daily_token_usage(user_name)          # Token（权威数据源，不依赖内存缓存）
    remaining = budget - used
    if remaining <= 0:
        return False, f"今日预算已用完（已使用 {used:.0f} tokens，预算 {budget:.0f} tokens）"
    if estimated_tokens > 0 and estimated_tokens > remaining:
        return False, (f"预估消耗 {estimated_tokens:.0f} tokens 超过剩余预算 "
                       f"{remaining:.0f} tokens")
    return True, f"预算充足（剩余 {remaining:.0f} tokens，预估 {estimated_tokens:.0f} tokens）"


def check_token_budget(user_name: str, estimated_tokens: int = 0) -> bool:
    """
    检查用户是否还有Token预算。

    参数:
        user_name: 用户名
        estimated_tokens: 本次调用预估消耗的Token数（可选）

    返回:
        True: 预算充足，可以调用
        False: 预算已用完
    """
    return check_token_budget_detail(user_name, estimated_tokens)[0]

def get_token_budget_info(user_name: str) -> dict:
    """
    获取用户的Token预算信息（用于返回给客户端）。
    """
    budget = get_user_token_budget(user_name)
    used = get_daily_token_usage(user_name)
    remaining = max(0, budget - used) if budget != float("inf") else -1
    
    return {
        "daily_budget": budget if budget != float("inf") else "无限",
        "used_today": round(used, 2),
        "remaining": round(remaining, 2) if remaining != -1 else "无限",
    }


# ====================  新增月度报告生成函数 ====================
def generate_monthly_report(user_name: str, year: int = None, month: int = None) -> dict:
    """
    生成用户指定月份的花费报告。
    
    参数:
        user_name: 用户名
        year: 年份（默认当前年）
        month: 月份（默认当前月，1-12）
    
    返回:
        包含总花费、日均花费、用途分布等信息的报告字典
    """
    from datetime import datetime
    from db import get_db

    # 默认当前月份
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month
    
    # 计算月份范围
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    # 计算该月天数
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    elapsed_days = min(now.day, days_in_month) if year == now.year and month == now.month else days_in_month
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. 总览统计
                cur.execute(
                    """SELECT 
                          COALESCE(SUM(total_tokens), 0) as total_tokens,
                          COALESCE(SUM(cost), 0) as total_cost,
                          COUNT(*) as total_calls
                       FROM token_usage_logs 
                       WHERE user_name = %s 
                         AND created_at >= %s 
                         AND created_at < %s""",
                    (user_name, start_date, end_date)
                )
                row = cur.fetchone()
                total_tokens = row[0]
                total_cost = round(row[1], 4)
                total_calls = row[2]
                
                # 2. 按用途分布统计
                cur.execute(
                    """SELECT purpose,
                              SUM(total_tokens) as tokens,
                              SUM(cost) as cost,
                              COUNT(*) as calls
                       FROM token_usage_logs 
                       WHERE user_name = %s 
                         AND created_at >= %s 
                         AND created_at < %s
                       GROUP BY purpose
                       ORDER BY cost DESC""",
                    (user_name, start_date, end_date)
                )
                purpose_rows = cur.fetchall()
                
                # 3. 按模型分布统计
                cur.execute(
                    """SELECT model,
                              SUM(total_tokens) as tokens,
                              SUM(cost) as cost,
                              COUNT(*) as calls
                       FROM token_usage_logs 
                       WHERE user_name = %s 
                         AND created_at >= %s 
                         AND created_at < %s
                       GROUP BY model
                       ORDER BY cost DESC""",
                    (user_name, start_date, end_date)
                )
                model_rows = cur.fetchall()
                
    except Exception as e:
        print(f"[Token] 生成月度报告失败: {e}")
        return {"error": str(e)}
    
    # 构建报告
    return {
        "report_period": f"{year}年{month}月",
        "days_in_month": days_in_month,
        "elapsed_days": elapsed_days,
        "summary": {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "daily_average_cost": round(total_cost / elapsed_days, 4) if elapsed_days > 0 else 0,
            "daily_average_tokens": round(total_tokens / elapsed_days, 0) if elapsed_days > 0 else 0,
            "cost_per_call": round(total_cost / total_calls, 4) if total_calls > 0 else 0,
        },
        "by_purpose": [
            {
                "purpose": r[0],
                "tokens": r[1],
                "cost": round(r[2], 4),
                "calls": r[3],
                "percentage": round(r[2] / total_cost * 100, 1) if total_cost > 0 else 0
            }
            for r in purpose_rows
        ],
        "by_model": [
            {
                "model": r[0],
                "tokens": r[1],
                "cost": round(r[2], 4),
                "calls": r[3],
                "percentage": round(r[2] / total_cost * 100, 1) if total_cost > 0 else 0
            }
            for r in model_rows
        ],
    }


# ==================== 工具调用预估成本 ====================

# 不同工具的单次调用预估成本（元）
TOOL_ESTIMATED_COST = {
    "web_search": 0.005,         # 搜索工具：通常需要一次 LLM 辅助总结
    "calculator": 0.0,           # 计算器：本地执行，无 API 调用
    "date_today": 0.0,           # 日期查询：本地执行
    "fetch_webpage": 0.003,      # 网页抓取：可能触发 LLM 总结
    "screenshot_webpage": 0.003, # 截图：类似网页抓取
    "execute_python": 0.0,       # 代码执行：本地执行，无 API 调用
}

# 不同用途的单次调用预估成本（元）
PURPOSE_ESTIMATED_COST = {
    "agent_decision": 0.01,      # Agent 决策节点
    "answer_generation": 0.02,   # 生成最终答案
    "query_rewrite": 0.005,      # 查询改写
    "embedding": 0.0005,         # Embedding 调用
    # ⚠️ 2026-09-21 加（§十四 · ③-b）：与上面 `PURPOSE_ESTIMATED_TOKENS` 的三个键**必须一一对应**
    #    （两套表并存不可互相替代 —— 见下面那段说明）。
    "plan_execute.plan": 0.01,
    "plan_execute.dynamic_input": 0.005,
    "plan_execute.quality_check": 0.003,
}

def estimate_tool_cost(tool_name: str) -> float:
    """预估单次工具调用的花费（**元** —— 仅供展示，预算判定请用 estimate_tool_tokens）"""
    return TOOL_ESTIMATED_COST.get(tool_name, 0.01)

def estimate_purpose_cost(purpose: str) -> float:
    """预估单次 LLM 调用的花费（**元** —— 仅供展示，预算判定请用 estimate_purpose_tokens）"""
    return PURPOSE_ESTIMATED_COST.get(purpose, 0.01)

# ⚠️ 两套预估表**必须并存、不可互相替代**（2026-09-16）：
#    · *_COST   → 单位「元」，供 `/agent/budget/estimates` 等**对外展示**用（api_v1_agent.py 暴露了它）
#    · *_TOKENS → 单位「Token」，供**预算判定**用
#    预算的权威单位是 **Token**（ROLE_TOKEN_BUDGET / get_daily_token_usage 都是 Token）。
#    历史上判定逻辑误用了「元」表去和 Token 预算相减 ⇒ 三处闸门恒放行（见 DEC-002）。
TOOL_ESTIMATED_TOKENS = {
    "web_search": 800,           # 搜索工具：通常需要一次 LLM 辅助总结
    "calculator": 0,             # 计算器：本地执行，无 API 调用
    "date_today": 0,             # 日期查询：本地执行
    "fetch_webpage": 600,        # 网页抓取：可能触发 LLM 总结
    "screenshot_webpage": 600,   # 截图：类似网页抓取
    "execute_python": 0,         # 代码执行：本地执行，无 API 调用
}

# 不同用途的单次调用预估 Token 消耗
PURPOSE_ESTIMATED_TOKENS = {
    "agent_decision": 500,       # 对齐 agent_graph_advanced.py:302/340 已在用的经验值
    "answer_generation": 800,
    "query_rewrite": 300,
    "embedding": 100,
    # ⚠️ 2026-09-21 加（§十四 · ③-b）：`plan_execute` 这条路的三种 LLM 调用。
    #    此前 `plan_execute` **完全不查预算、不记账** —— 它会真跑 LLM，而账上一行不记
    #    ⇒ **免费用户的每日配额管不到它**（`/agent/plan_execute`）。见 DEC-027。
    "plan_execute.plan": 500,           # 把目标分解成步骤清单
    "plan_execute.dynamic_input": 300,  # 每步：生成该工具那个字段的值
    "plan_execute.quality_check": 200,  # 每步：判定结果是否达标
}

# 未知工具/用途时的保守兜底（Token）
DEFAULT_ESTIMATED_TOKENS = 500

def estimate_tool_tokens(tool_name: str) -> int:
    """预估单次工具调用的 **Token** 消耗（预算判定的单位）"""
    return TOOL_ESTIMATED_TOKENS.get(tool_name, DEFAULT_ESTIMATED_TOKENS)

def estimate_purpose_tokens(purpose: str) -> int:
    """预估单次 LLM 调用的 **Token** 消耗（预算判定的单位）"""
    return PURPOSE_ESTIMATED_TOKENS.get(purpose, DEFAULT_ESTIMATED_TOKENS)

def check_budget_before_call(
    user_name: str,
    tool_name: str = None,
    purpose: str = None,
    estimated_tokens: int = None
) -> tuple[bool, str]:
    """
    在调用前检查预算是否充足。
    返回: (是否允许, 原因说明)

    ⚠️ 参数单位是 **Token**（自 2026-09-16 起；旧名 `estimated_cost` 单位是「元」）。
    那个旧参数正是本函数此前**恒放行**的原因之一 —— 它把「元」和 **Token 预算**相减。
    见 `docs/decisions/DEC-002-预算闸门失效修法.md`。
    """
    # 1. 计算预估 Token（不再是「元」）
    if estimated_tokens is not None:
        est = estimated_tokens
    elif tool_name:
        est = estimate_tool_tokens(tool_name)
    elif purpose:
        est = estimate_purpose_tokens(purpose)
    else:
        est = DEFAULT_ESTIMATED_TOKENS

    # 2. 每日预算检查 —— 委托给**统一实现**（原先这里自己写了一份错的）
    allowed, reason = check_token_budget_detail(user_name, est)
    if not allowed:
        record_intercept(user_name, tool_name or purpose or "unknown", reason)
    return allowed, reason


def get_daily_usage_cost(user_name: str) -> float:
    """从数据库查询用户今日已消耗的总花费"""
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(cost), 0) 
                       FROM token_usage_logs 
                       WHERE user_name = %s 
                         AND created_at >= CURRENT_DATE""",
                    (user_name,)
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"[Token] 查询当日花费失败: {e}")
        return 0.0
    
# ==================== 拦截统计 ====================

# 拦截计数器（按用户）
_intercept_count: Dict[str, int] = defaultdict(int)
_intercept_lock = threading.Lock()

def record_intercept(user_name: str, tool_name: str, reason: str):
    """记录一次预算拦截"""
    from db import get_db
    with _intercept_lock:
        _intercept_count[user_name] += 1
    # 可选：写入数据库
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS budget_intercepts (
                        id SERIAL PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        tool_name TEXT,
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )"""
                )
                cur.execute(
                    "INSERT INTO budget_intercepts (user_name, tool_name, reason) VALUES (%s, %s, %s)",
                    (user_name, tool_name, reason)
                )
                conn.commit()
    except Exception as e:
        print(f"[Budget] 记录拦截失败: {e}")

def get_intercept_count(user_name: str = None) -> dict:
    """获取拦截统计"""
    with _intercept_lock:
        if user_name:
            return {"user_name": user_name, "total_intercepts": _intercept_count.get(user_name, 0)}
        return {
            "total_intercepts": sum(_intercept_count.values()),
            "by_user": dict(_intercept_count)
        }
    
# ==================== 多级预算配置 ====================

# 单次调用最大花费（元）· 单线程最大花费（元）
# ⚠️ 2026-10-01 搬家（B7）：两个常量已移到 `api/token_config.py`，此处从那里取（文件顶部已 import）。
#    ⛔ 行为不变（默认仍 0.5 / 5.0）。
from token_config import MAX_SINGLE_CALL_COST, MAX_THREAD_COST       # noqa: E402,F811

def check_multilevel_budget(
    user_name: str,
    thread_id: str = "unknown",
    tool_name: str = None,
    purpose: str = None,
    estimated_cost: float = None
) -> tuple[bool, str]:
    """
    多级预算检查：
    1. 单次调用上限（单位：**元**）
    2. 单线程上限（单位：**元**）
    3. 每日预算上限（单位：**Token**）

    ⚠️ 本函数**刻意有两个单位**，别"统一"掉：
      · 第一、二级是**单次/单线程的花费上限**，配 `MAX_SINGLE_CALL_COST` / `MAX_THREAD_COST`（元）——
        它们量纲本来就是对的（元 vs 元），2026-09-16 的修复**没动它们**。
      · 第三级是**每日预算**，权威单位是 **Token**（`ROLE_TOKEN_BUDGET` / `get_daily_token_usage`），
        原先误用「元」去相减 ⇒ 恒放行（DEC-002）。现已委托给 `check_token_budget_detail`。
    """
    # 第一、二级用「元」
    if estimated_cost is not None:
        cost = estimated_cost
    elif tool_name:
        cost = estimate_tool_cost(tool_name)
    elif purpose:
        cost = estimate_purpose_cost(purpose)
    else:
        cost = 0.01

    # 第三级用「Token」—— 两个单位分开算，不混
    est_tokens = (estimate_tool_tokens(tool_name) if tool_name
                  else estimate_purpose_tokens(purpose) if purpose
                  else DEFAULT_ESTIMATED_TOKENS)
    
    # 第一级：单次调用上限
    if cost > MAX_SINGLE_CALL_COST:
        record_intercept(user_name, tool_name or "unknown", f"单次预估花费 ¥{cost:.4f} 超过上限 ¥{MAX_SINGLE_CALL_COST:.4f}")
        return False, f"单次调用预估花费 ¥{cost:.4f} 超过上限 ¥{MAX_SINGLE_CALL_COST:.4f}"
    
    # 第二级：单线程上限
    thread_cost = get_thread_cost(thread_id)
    if thread_cost + cost > MAX_THREAD_COST:
        record_intercept(user_name, tool_name or "unknown", f"线程累计花费 ¥{thread_cost:.4f} + 预估 ¥{cost:.4f} 超过线程上限 ¥{MAX_THREAD_COST:.4f}")
        return False, f"当前线程已花费 ¥{thread_cost:.4f}，预估 ¥{cost:.4f}，超过线程上限 ¥{MAX_THREAD_COST:.4f}"
    
    # 第三级：每日 Token 预算 —— 委托给**统一实现**（原先这里自己写了一份、且单位是错的）
    allowed, reason = check_token_budget_detail(user_name, est_tokens)
    if not allowed:
        record_intercept(user_name, tool_name or purpose or "unknown", reason)
    return allowed, reason

def get_thread_cost(thread_id: str) -> float:
    """查询指定线程的累计花费"""
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(cost), 0) 
                       FROM token_usage_logs 
                       WHERE thread_id = %s""",
                    (thread_id,)
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"[Budget] 查询线程花费失败: {e}")
        return 0.0


# ==================== B8 · 会话级 token 上限（①b Task 2） ====================
# 口径与接线范围见 `docs/decisions/DEC-041-B8会话上限的窗口与接线范围.md`。
#
# ⚠️ **本维度已经有一个上限了** —— 上面的 `MAX_THREAD_COST`（元/线程）。
#    两者的**窗口不同**：那个**不带日期**（全程），本节的**按日**（DEC-041 裁定）——
#    「同一 `thread_id`、两种窗口」是**已知且有意**的，别"顺手统一"掉；
#    归并由 `DEC-040` 的 ①b·Task 6 处理。

def get_session_token_usage(user_name: str, thread_id: str) -> float:
    """某用户某会话【今日】累计 token —— **查表**，⛔ 不读内存。

    ⚠️ **为什么不复用 `_thread_summary`**：那是**进程内存**（`record_usage` 里累加），
       **重启即清零** ⇒ 拿它当上限等于「**重启一下就能绕开限额**」。
       权威数据源只能是 `token_usage_logs`（`get_daily_token_usage` 也是这么做的）。

    ⚠️ **窗口 = 会话 × 今日**（`DEC-041` 决策一）——
       与仓里其余所有 token 预算（用户**日**预算）**同一口径**。
       ⛔ 删掉 `CURRENT_DATE` 就是**换方案**（备选一·乙「纯会话累计」），那条会让会话桶
       **被永久封死**且用户**无自救手段** ⇒ 要改先改 DEC。

    ⚠️ **key = `user_name` + `thread_id`**（`DEC-041` 决策二）——⛔ **`user_name` 不给默认值**。
       现有 4 个 Agent 端点的 `thread_id` **默认值是 `"default"`**；只按 `thread_id` 分桶的话，
       所有没显式传它的调用者会**共用同一个桶** ⇒ 谁先烧完 50000，**其他默认用户一起撞 429**。
       ⇒ 漏传 `user_name` 的调用点应当**立刻报错**（`TypeError`），⛔ 不是静默落进 `unknown`。

    ⚠️ **空 key 归一到 `"unknown"`** —— 与 `record_usage` 的默认值一致。
       ⇒ 记账桶与判定桶**始终一致**；若不归一，记账进 `unknown`、判定查 `''`
       ⇒ **判定永远看不到用量**（静默放行）。
    """
    user_name = user_name or "unknown"
    thread_id = thread_id or "unknown"
    from db import get_db
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(total_tokens), 0)
                       FROM token_usage_logs
                       WHERE user_name = %s
                         AND thread_id = %s
                         AND created_at >= CURRENT_DATE""",
                    (user_name, thread_id)
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"[Token] 查询会话用量失败: {e}")
        # ⚠️ **fail-open**（返回 0 = 没超）—— 与 `get_daily_token_usage` 的取向一致。
        #    理由：配额是**成本控制**，不是**安全边界**；DB 抖动时把服务全停掉代价更大。
        #    📌 与 `api/deps.py` 的鉴权**故意相反**（那里 fail-closed，因为**那是**安全边界）——
        #       ⛔ 别"统一"掉。
        return 0.0


def check_session_token_budget(user_name: str, thread_id: str,
                               estimated_tokens: int = 0) -> tuple[bool, str]:
    """会话级预算判定。返回 `(是否放行, 原因)`。

    **不含** `record_intercept` —— 拦截记录由调用方负责（各调用方要带上自己的 tool_name），
    与 `check_token_budget_detail` 同一条约定。

    触顶动作 = **直接拒绝**（`B11` 要素②，业务方已裁）⇒ 调用方抛
    `AppException(ErrorCode.QUOTA_EXCEEDED, why)`。
    """
    from token_config import SESSION_TOKEN_LIMIT
    used = get_session_token_usage(user_name, thread_id)
    remaining = SESSION_TOKEN_LIMIT - used
    if remaining <= 0:
        return False, (f"本会话预算已用完（已使用 {used:.0f} tokens，"
                       f"会话上限 {SESSION_TOKEN_LIMIT:.0f} tokens）")
    if estimated_tokens > 0 and estimated_tokens > remaining:
        return False, (f"预估消耗 {estimated_tokens:.0f} tokens 超过本会话剩余 "
                       f"{remaining:.0f} tokens")
    return True, f"会话预算充足（剩余 {remaining:.0f} tokens）"


# ==================== 预算通知 ====================

BUDGET_WARNING_THRESHOLD = 0.8  # 80% 阈值

def check_budget_warning(user_name: str) -> dict:
    """
    检查用户是否达到预算警告阈值（80%）。
    如果达到，返回提醒信息；否则返回 None。
    """
    budget = get_user_token_budget(user_name)
    if budget == float("inf"):
        return {"warning": False, "message": None}
    
    used = get_daily_token_usage(user_name)      # Token（原先误用 get_daily_usage_cost 的「元」）
    ratio = used / budget if budget > 0 else 0

    if ratio >= BUDGET_WARNING_THRESHOLD:
        return {
            "warning": True,
            "message": f"⚠️ 您今日已使用预算的 {ratio*100:.0f}%（{used:.0f} / {budget:.0f} tokens），请合理控制调用频率。",
            "ratio": round(ratio, 2),
            "used_tokens": round(used, 0),
            "budget": budget,
        }

    return {"warning": False, "message": None, "ratio": round(ratio, 2)}