"""
代码执行器的**纯 stdlib 内核**（无 langchain 依赖）。

从 `code_executor.py` 切出（重构计划 ⑥ 切开点 3）。目的：让**沙箱白名单与执行逻辑**
可在**只有标准库**的环境里被导入和测试 —— 此前它们住在 `code_executor.py` 里，
而那个文件在**模块层** `from langchain_core.tools import tool`，
于是想单测沙箱就必须先把 langchain 装齐。

⚠️ **依赖方向单向**：本模块**只 import 标准库**（`sys` 未用故未列）。
`code_executor.py` 引用本模块；**本模块绝不反向引用** `code_executor.py`。

📌 `code_executor.py` 只是给 `execute_python_impl` 套一层 `@tool` 外壳（供 Agent 调用）。
"""
import io
import contextlib

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


def execute_python_impl(code: str) -> str:
    """
    执行一段已编写好的 Python 代码，并返回执行结果（**纯逻辑，无 langchain 依赖**）。

    行为与切分前完全一致 —— 只搬位置，不改逻辑：
    先做代码意图检测（拒绝"需求描述"而非可执行代码），再在 `create_safe_globals()`
    给出的受限环境里 `exec`，捕获 stdout，超长截断。

    ⚠️ 对外说明的完整版（安全限制 / 适用场景）写在 `code_executor.execute_python`
    的 docstring 里 —— 那是给 **LLM 读的工具描述**，必须留在 `@tool` 那一层。
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
