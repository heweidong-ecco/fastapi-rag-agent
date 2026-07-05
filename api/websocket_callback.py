# websocket_callback.py
import json
from typing import Any, Dict, List
from langchain_core.callbacks import BaseCallbackHandler
from fastapi import WebSocket

class WebSocketAgentCallback(BaseCallbackHandler):
    """将 Agent 的中间过程实时推送到 WebSocket"""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        """LLM 开始思考时触发"""
        pass  # 可以选择发送一个“思考中”的状态

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """工具开始执行时触发"""
        tool_name = serialized.get("name", "unknown")
        await self.websocket.send_text(json.dumps({
            "type": "action",
            "tool": tool_name,
            "content": f"调用工具：{tool_name}"
        }))

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """工具执行完成时触发"""
        await self.websocket.send_text(json.dumps({
            "type": "observation",
            "content": str(output)[:300]
        }))

    async def on_llm_end(self, response, **kwargs: Any) -> None:
        """LLM 生成完成时触发（可能包含最终答案）"""
        pass  # 最终答案由 on_agent_finish 或直接解析

    async def on_agent_action(self, action, **kwargs: Any) -> None:
        """Agent 决定采取行动时触发"""
        await self.websocket.send_text(json.dumps({
            "type": "action",
            "tool": action.tool,
            "input": str(action.tool_input)[:200],
            "content": f"决定调用：{action.tool}"
        }))

    async def on_agent_finish(self, finish, **kwargs: Any) -> None:
        """Agent 得出最终答案时触发"""
        await self.websocket.send_text(json.dumps({
            "type": "final",
            "content": finish.return_values.get("output", str(finish))
        }))
        await self.websocket.send_text(json.dumps({"type": "done"}))