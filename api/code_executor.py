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
    
'''
以下只是最基础的 简单的Docker 容器隔离 代码，不够完整，只是基础的代码。
更详细完整的代码和方案在“第68天：⭐️代码执行器 安全沙箱执行Python代码”“将代码执行器升级为 Docker 容器隔离 执行方案和代码。”

Docker 容器隔离

原理：为每次代码执行启动一个全新的、最小化的 Docker 容器（如 python:3.10-slim），将代码注入容器，执行后立即销毁。容器天然提供进程、文件系统、网络和内存的隔离。
优点：

近乎完美的隔离性，即使代码有恶意也几乎无法影响宿主机。
可自由配置容器环境（预装库、资源限制等）。
生态成熟，工具链丰富。
缺点：

启动延迟高：容器启动需要1-3秒，不适合高频实时调用。
资源消耗较大（每个容器占用内存、CPU）。
需要管理 Docker 环境和镜像。
推荐实现：

python
import docker
import tempfile
import os

client = docker.from_env()

def run_code_in_docker(code: str) -> str:
    # 将代码写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        tmp_path = f.name
    
    try:
        # 启动容器执行代码
        container = client.containers.run(
            image='python:3.10-slim',
            command=f'python /code/{os.path.basename(tmp_path)}',
            volumes={os.path.dirname(tmp_path): {'bind': '/code', 'mode': 'ro'}},
            network_disabled=True,      # 禁用网络
            mem_limit='128m',           # 内存限制
            cpu_period=100000,
            cpu_quota=50000,            # 限制CPU使用
            remove=True,                # 执行后自动删除
            timeout=10,                 # 超时10秒
            stderr=True,
        )
        return container.decode('utf-8')
    finally:
        os.unlink(tmp_path)

'''