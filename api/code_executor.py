"""
代码执行器：安全沙箱
让 Agent 能编写并执行 Python 代码，处理精确计算和自动化任务。
更多高级沙箱方案：本代码最下方，只备注了 Docker 容器隔离 的方法。
更多的方案：RestrictedPython nsjail / Firejail 云函数服务 Pyodide
等等方案有局限 和安全性，详细对比在"#第68天：代码执行器——安全沙箱执行Python代码"
详细查看，且有"代码执行器"更多具体用法拓展，高级沙箱的混合布置方案和思路。
"""
import sys
import io
import contextlib
from langchain_core.tools import tool

# 安全沙箱配置
ALLOWED_BUILTINS = [
    # 基础内置函数
    "abs", "all", "any", "bool", "bytes", "chr", "dict", "dir",
    "divmod", "enumerate", "filter", "float", "format", "frozenset",
    "hash", "hex", "int", "isinstance", "issubclass", "iter", "len",
    "list", "map", "max", "min", "next", "object", "oct", "ord",
    "pow", "print", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "type", "zip",
    # 常用数学模块
    "math",
]

ALLOWED_MODULES = [
    "math",
    "json",         # JSON 数据处理
    "datetime",     # 日期时间
    "collections",  # 数据结构
    "itertools",    # 迭代工具
    "functools",    # 函数工具
    "re",           # 正则表达式
    "statistics",   # 统计
    "random",       # 随机
]

# 最大执行时间和输出长度限制
MAX_EXEC_TIME = 5  # 最长执行5秒
MAX_OUTPUT_LENGTH = 2000  # 最大输出字符数


def create_safe_globals() -> dict:
    """创建一个安全沙箱的执行环境"""
    safe_globals = {"__builtins__": {}}
    
    # 只注入允许的内置函数
    import builtins
    for func_name in ALLOWED_BUILTINS:
        if hasattr(builtins, func_name):
            safe_globals["__builtins__"][func_name] = getattr(builtins, func_name)
    
    # 注入允许的模块
    for module_name in ALLOWED_MODULES:
        try:
            module = __import__(module_name)
            safe_globals[module_name] = module
        except ImportError:
            pass
    
    return safe_globals


@tool
def execute_python(code: str) -> str:
    """
    执行一段已编写好的 Python 代码，并返回执行结果。

    **重要：此工具只能执行代码，不能生成或编写代码。**

    **安全限制：**
    - 允许的模块：math, json, datetime, collections, itertools, functools, re, statistics, random
    - 禁止文件操作、网络访问、系统命令
    - 最长执行时间：5秒
    - 最大输出长度：2000字符

    **适用场景：**
    - 执行简单的数学计算
    - 处理 JSON 数据
    - 日期时间格式化
    - 正则表达式匹配和替换
    - 简单的列表/字典操作

    **不适用场景（会失败）：**
    - 需要导入大型库（如 numpy, pandas）
    - 需要网络请求
    - 需要读写文件
    - 生成新的代码

    输入必须是一段完整的、可立即执行的 Python 代码字符串。
    """
    # 新增：代码意图检测
    # 如果代码看起来像是一个需求描述而非可执行代码，直接拒绝
    non_code_patterns = [
        "帮我", "请写", "生成", "写一段", "写一个", "创建",
        "help me", "generate", "write", "create",
    ]
    first_line = code.strip().split('\n')[0].lower()
    for pattern in non_code_patterns:
        if pattern in first_line:
            return (
                f"错误：传入的不是可执行的 Python 代码。\n"
                f"看起来你传入的是一个需求描述（包含'{pattern}'）。\n"
                f"execute_python 只能执行已编写好的代码，不能生成代码。\n"
                f"请先生成代码文本，再将代码作为参数传入。"
            )

    try:
        safe_env = create_safe_globals()
        output_buffer = io.StringIO()
        
        with contextlib.redirect_stdout(output_buffer):
            exec(code, safe_env)
        
        result = output_buffer.getvalue()
        
        if len(result) > MAX_OUTPUT_LENGTH:
            result = result[:MAX_OUTPUT_LENGTH] + "\n... (输出过长，已截断)"
        
        if not result.strip():
            return "代码执行成功，但无输出内容。"
        
        return result
        
    except Exception as e:
        return f"代码执行出错: {type(e).__name__}: {str(e)}"
    