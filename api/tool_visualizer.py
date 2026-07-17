"""
工具调用可视化模块
记录和展示 Agent 工具调用的完整过程。
"""
import time
import json
from typing import Dict, List
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class ToolCallRecord:
    """单次工具调用的完整记录"""
    tool_name: str
    arguments: dict
    result: str
    start_time: float
    end_time: float
    status: str = "success"  # success / error
    error_message: str = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result[:500] if self.result else "",
            "duration_ms": round((self.end_time - self.start_time) * 1000, 2),
            "status": self.status,
            "error_message": self.error_message,
        }

@dataclass
class AgentTrace:
    """一次 Agent 任务的完整执行轨迹"""
    thread_id: str
    user_query: str
    start_time: float
    end_time: float = None
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    agent_decisions: List[dict] = field(default_factory=list)
    final_output: str = ""
    total_tokens: int = 0
    total_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "user_query": self.user_query,
            "duration_ms": round(((self.end_time or time.time()) - self.start_time) * 1000, 2),
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "agent_decisions": self.agent_decisions,
            "final_output": self.final_output[:1000] if self.final_output else "",
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 6),
        }

# 全局轨迹存储（按 thread_id）
_traces: Dict[str, AgentTrace] = {}

def start_trace(thread_id: str, user_query: str):
    """开始一次新的 Agent 任务轨迹"""
    _traces[thread_id] = AgentTrace(
        thread_id=thread_id,
        user_query=user_query,
        start_time=time.time()
    )

def record_tool_start(tool_name: str, arguments: dict, thread_id: str):
    """记录工具调用开始（可在工具实际调用前调用）"""
    if thread_id not in _traces:
        return
    record = ToolCallRecord(
        tool_name=tool_name,
        arguments=arguments,
        result="",
        start_time=time.time(),
        end_time=0.0,
        status="running"
    )
    _traces[thread_id].tool_calls.append(record)

def record_tool_end(tool_name: str, result: str, thread_id: str, status: str = "success", error_message: str = None):
    """记录工具调用结束"""
    if thread_id not in _traces:
        return
    # 找到最近一次同名的 running 状态的调用并更新
    trace = _traces[thread_id]
    for tc in reversed(trace.tool_calls):
        if tc.tool_name == tool_name and tc.status == "running":
            tc.result = result
            tc.end_time = time.time()
            tc.status = status
            tc.error_message = error_message
            break

def record_agent_decision(thread_id: str, decision: dict):
    """记录 Agent 的决策过程"""
    if thread_id not in _traces:
        return
    _traces[thread_id].agent_decisions.append(decision)

def finish_trace(thread_id: str, final_output: str = "", total_tokens: int = 0, total_cost: float = 0.0):
    """结束一次 Agent 任务轨迹"""
    if thread_id not in _traces:
        return
    trace = _traces[thread_id]
    trace.end_time = time.time()
    trace.final_output = final_output
    trace.total_tokens = total_tokens
    trace.total_cost = total_cost

def get_trace(thread_id: str) -> dict:
    """获取指定线程的执行轨迹"""
    if thread_id not in _traces:
        return None
    return _traces[thread_id].to_dict()

def get_all_traces() -> List[dict]:
    """获取所有线程的执行轨迹摘要"""
    return [
        {
            "thread_id": tid,
            "user_query": t.user_query[:100],
            "tool_calls_count": len(t.tool_calls),
            "duration_ms": round(((t.end_time or time.time()) - t.start_time) * 1000, 2),
            "total_cost": round(t.total_cost, 6),
        }
        for tid, t in _traces.items()
    ]