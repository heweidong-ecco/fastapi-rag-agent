"""
代码执行器：安全沙箱（**面向 LLM 的工具外壳**）。
让 Agent 能编写并执行 Python 代码，处理精确计算和自动化任务。
更多高级沙箱方案：本代码最下方，只备注了 Docker 容器隔离 的方法。
更多的方案：RestrictedPython nsjail / Firejail 云函数服务 Pyodide
等等方案有局限 和安全性，详细对比在"#第68天：代码执行器——安全沙箱执行Python代码"
详细查看，且有"代码执行器"更多具体用法拓展，高级沙箱的混合布置方案和思路。

⚠️ 2026-09-17 重构 ⑥ 切开点 3：**沙箱白名单与执行逻辑已搬到 `code_executor_impl.py`**
（纯 stdlib，可脱离 langchain 单测）。本文件只剩一层 `@tool` 外壳。
为避免老调用方失效，下列常量**在此处重新导出**（`ALLOWED_BUILTINS` / `ALLOWED_MODULES` /
`MAX_EXEC_TIME` / `MAX_OUTPUT_LENGTH` / `create_safe_globals`）——
⚠️ 但 `import code_executor` 仍会拉 **langchain**；**只想用沙箱逻辑就 import `code_executor_impl`**。
"""
from langchain_core.tools import tool

from code_executor_impl import (
    ALLOWED_BUILTINS,
    ALLOWED_MODULES,
    MAX_EXEC_TIME,
    MAX_OUTPUT_LENGTH,
    create_safe_globals,
    execute_python_impl,
)

__all__ = [
    "execute_python",
    "create_safe_globals",
    "ALLOWED_BUILTINS",
    "ALLOWED_MODULES",
    "MAX_EXEC_TIME",
    "MAX_OUTPUT_LENGTH",
]


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
    # ⚠️ 上面这段 docstring 是**给 LLM 读的工具描述**，故留在本层；
    #    真正的逻辑在 code_executor_impl.execute_python_impl（纯 stdlib）。
    return execute_python_impl(code)
