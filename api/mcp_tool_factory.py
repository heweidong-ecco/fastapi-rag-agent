"""
MCP 工具工厂：将 LangChain @tool 函数自动封装为 MCP 标准接口
"""
from typing import Dict, Any
from mcp.types import Tool

# 新增：version 版本号
def create_mcp_tool_definition(tool_func,version: str = "1.0.0") -> Dict:
    """
    从 @tool 函数自动生成 MCP 工具定义。
    
    参数:
        tool_func: LangChain 的 @tool 装饰的函数
        version: 工具版本号，默认 "1.0.0"

    返回:
        符合 MCP 标准的工具定义字典，包含 name, description, inputSchema, version
    """
    # 从 LangChain 的 BaseTool 中提取元数据
    tool_name = tool_func.name
    tool_description = tool_func.description
    
    # 从函数的类型提示中自动构建 inputSchema
    props = {}
    required = []
    
    if hasattr(tool_func, 'args_schema') and tool_func.args_schema:
        schema = tool_func.args_schema.schema()
        for prop_name, prop_info in schema.get("properties", {}).items():
            props[prop_name] = {
                "type": prop_info.get("type", "string"),
                "description": prop_info.get("description", prop_name)
            }
            required = schema.get("required", [])
    else:
        # 如果没有显式的 args_schema，默认一个空的 input 参数
        props = {
            "input": {"type": "string", "description": "工具输入"}
        }
        required = ["input"]
    
    return {
        "name": tool_name,
        "description": tool_description,
        "version": version,  # 新增：版本号
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": required
        }
    }

def create_mcp_tool_handler(tool_func):
    """
    从 @tool 函数自动生成 MCP 工具调用处理器。
    
    参数:
        tool_func: LangChain 的 @tool 装饰的函数
    
    返回:
        一个可调用的函数，接收 arguments 字典，返回字符串结果。
        如果工具调用失败，返回结构化的错误信息，不会抛出异常。
    """
    def handler(arguments: dict) -> str:
        """工具调用处理器（带错误处理）"""
        try:
            if hasattr(tool_func, 'args_schema') and tool_func.args_schema:
                input_obj = tool_func.args_schema(**arguments)
                result = tool_func.invoke(input_obj)
            else:
                result = tool_func.invoke(arguments)
            return str(result)
        except Exception as e:
            # 捕获所有异常，返回结构化的错误信息，避免 Agent 崩溃
            error_msg = (
                f"工具调用失败\n"
                f"工具名称: {tool_func.name}\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误详情: {str(e)}\n"
                f"请检查输入参数是否正确，或稍后重试。"
            )
            return error_msg
    
    return handler
