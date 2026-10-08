"""守卫：工具的【定义】只有一处事实源 —— 四个正本模块，⛔ 别再手抄第 N 份。

⚠️ **为什么用 AST 而不是 grep**：注释和 docstring 里也写着这些工具名，
   正则会把**说明文字**当成违规（本仓栽过 —— 见 `api/test_tool_dispatch.py` 的表头）。

## 🔴 2026-10-08：施工单 Step 1 那条判据是**坏的**，这里换了尺子

施工单让写「找 `tools = [...]` 里的**字符串字面量**」。**实测本仓不成立**：

```
$ python -c "<AST 扫 api/*.py 的 tools 赋值>"
  agent_checkpointer.py:60             tools = ... 元素类型=['Name']
  agent_graph.py:55                    tools = ... 元素类型=['Name']
  api_v1_rag.py:973                    tools = ... 元素类型=['Name']
  agent_graph_advanced_learning.py:64  tools = ... 元素类型=['ListComp']   ← 已派生
```

⇒ **四处元素全是 `ast.Name`（对象），一个字符串字面量都没有**
⇒ 施工单那条判据**一开始就是绿的**，什么都没测
⇒ **反证检验**：把结论取反（"还在手抄"）⇒ 那条命令**打出来的还是空**
⇒ **尺子没在量它该量的事**。

⇒ 本文件改成量**真正重复的那个东西**：`@tool` 装饰的**函数定义**。
   判据（可打印）：`grep -rn '@tool' api/*.py` 里每个工具名**只该出现一次**。
"""

import ast
import importlib
from pathlib import Path

import pytest

API = Path(__file__).resolve().parent

#: 交给 LLM 的四个工具名（= `mcp_server.TOOLS` 里那四个）
TOOL_NAMES = {"calculator", "date_today", "web_search", "execute_python"}

#: ✅ **允许**【定义】这些工具的模块 —— 正本，每个工具**只有一处**。
#:    ⚠️ 新增一个工具 ⇒ 在 `mcp_server.TOOLS` 加一行 + 在这里登记它的**定义处**
#:       （⛔ 不是"到处都能定义"）。
DEFINITION_HOMES = {
    "simple_tools.py": {"calculator", "date_today"},
    "search_tools.py": {"web_search"},
    "code_executor.py": {"execute_python"},
}


def _decorator_names(node: ast.AST) -> list:
    """把装饰器写成名字列表 —— `@tool` / `@tool()` / `@mod.tool` 都还原成 `tool`。"""
    out = []
    for d in getattr(node, "decorator_list", []):
        if isinstance(d, ast.Name):
            out.append(d.id)
        elif isinstance(d, ast.Attribute):
            out.append(d.attr)
        elif isinstance(d, ast.Call):
            f = d.func
            out.append(f.id if isinstance(f, ast.Name) else getattr(f, "attr", "?"))
    return out


def _tool_definitions(path: Path):
    """产出 `(行号, 函数名, 装饰器们)` —— 只挑**被装饰的**、且名字是工具名的定义。

    ⚠️ 只认**被装饰的**：`simple_tools_impl.calculator_impl` 那种裸 `def` 是**实现**，
       不是工具对象，⛔ 不算重抄。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in TOOL_NAMES:
            continue
        decs = _decorator_names(node)
        if decs:
            yield node.lineno, node.name, decs


def test_only_home_modules_define_tools():
    """🔴 除正本外，**任何模块**都不该再 `@tool` 定义一个工具。

    反证：往任意模块塞一个 `@tool def calculator` ⇒ 本用例红并点名它。
    """
    offenders = {}
    for p in sorted(API.glob("*.py")):
        if p.name.startswith("test_"):
            continue
        allowed = DEFINITION_HOMES.get(p.name, set())
        hits = [(ln, nm, decs) for ln, nm, decs in _tool_definitions(p) if nm not in allowed]
        if hits:
            offenders[p.name] = hits

    assert offenders == {}, (
        "🔴 这些文件在**手抄工具定义**（正本见 DEFINITION_HOMES 表）：\n"
        + "\n".join(f"  {f}: {h}" for f, h in offenders.items())
    )


#: 运行时那条：`tools` 是**模块级**的这几个（`api_v1_rag` 的在函数体里 ⇒ 单独测不了）
DERIVED_MODULES = ["agent_graph", "agent_checkpointer", "agent_graph_advanced_learning"]


@pytest.mark.parametrize("modname", DERIVED_MODULES)
def test_module_tools_are_derived_from_registry(modname):
    """每个模块交给 LLM 的 `tools` **必须是已注册工具的子集** —— ⛔ 不许夹带私货。

    ⚠️ 这是**行为面**那条：AST 只管"有没有多定义一份"，
       这条管"真正交出去的是不是同一批对象"。
    """
    import mcp_server

    registered = {t["func"].name for t in mcp_server.TOOLS}
    mod = importlib.import_module(modname)
    names = {t.name for t in mod.tools}

    assert names <= registered, f"🔴 {modname}.tools 里有**未注册**的工具：{names - registered}"


def test_execute_python_not_yet_in_unisolated_graphs():
    """🔴 `execute_python` **暂不进那两张无隔离的图**（`Task 6` · 业务方 2026-10-08「待定」）。

    为什么：`agent_graph` / `agent_checkpointer` 里它**不在** `SENSITIVE_TOOLS` 审批名单、
    **又没有容器隔离** ⇒ 放进去等于开一条**无审批 + 无隔离**的任意代码执行。
    ✅ 等批② 容器落地后再放开 —— 那时把这条用例**改写**成要求它**在**表里。

    ⚠️ 反证：把这行的断言取反（改成 `in`）在**当前**实现下会红 ⇒ 这条尺子在量东西。
    """
    import agent_graph
    import agent_checkpointer

    for mod in (agent_graph, agent_checkpointer):
        assert "execute_python" not in {t.name for t in mod.tools}, (
            f"🔴 {mod.__name__}.tools 里有 execute_python —— 它在那张图里无审批、无隔离"
        )


def test_all_graphs_share_the_same_tool_objects():
    """🔴 删掉三份副本之后，**它们拿到的是同一个对象** —— 这是「能力没丢」的判据。

    为什么单开一条：批① Task 4 把 `test_safe_math_wiring.py` 的守护面从 5 处收到 1 处，
    而那条规矩要求「**每删一个站点，就要能说出它原来守的能力现在由谁守**」。
    答案就是这一条 —— 用 `is`（**对象同一**）证明，⛔ **不是**"名字一样"。

    ⚠️ 反证：把任意一张图改回自带一份 `@tool` ⇒ `test_only_home_modules_define_tools` 先红；
       若只把对象换成"另一个同名副本"，**本用例红**。
    """
    import agent_graph
    import agent_checkpointer
    import agent_graph_advanced_learning
    import mcp_server

    #: 唯一事实源 —— `mcp_server.TOOLS` 里那批**对象**
    shared = {t["func"].name: t["func"] for t in mcp_server.TOOLS}

    for mod in (agent_graph, agent_checkpointer, agent_graph_advanced_learning):
        got = {t.name: t for t in mod.tools}
        # ⚠️ 只钉这两个：`web_search` 三处本来就都导入同一个对象，
        #    而这两个原先各有一份**逐字等价但不同对象**的副本。
        for name in ("calculator", "date_today"):
            assert got[name] is shared[name], (
                f"🔴 {mod.__name__}.{name} **不是**共享对象（又抄了一份？）"
                f"\n   got ={got[name]!r}\n   want={shared[name]!r}"
            )


# ===========================================================================
# demo 模式下不注册 execute_python（批② Task 6）
# ===========================================================================
def _registered_tools_in_subprocess(extra_env: dict):
    """在**子进程**里 import `mcp_server`，报回它注册的工具名。

    ⚠️ **必须走子进程**：`TOOLS` 是**模块级**建好的 ⇒ 同进程里改 env
       对已经 import 过的模块**无效**（本仓 `test_tool_dispatch.py` 踩过同一个坑，
       那里也是用子进程解决的）。⛔ 别改成 `monkeypatch.setenv` —— 那会**静默无效**。
    """
    import json
    import os
    import subprocess
    import sys

    env = {**os.environ, **extra_env}
    proc = subprocess.run(
        [sys.executable, "-c",
         "import json, mcp_server; print(json.dumps([t['func'].name for t in mcp_server.TOOLS]))"],
        capture_output=True, text=True, env=env, cwd=str(API),
    )
    assert proc.returncode == 0, f"子进程 import 失败：{proc.stderr[-400:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_execute_python_is_registered_by_default():
    """✅ **正向对照**：不设开关时它**在**。

    ⚠️ **没有这一条，一个"把 TOOLS 清空"的实现也能让下面那条绿** ——
       那正是本仓反复栽的「**尺子量不到它该量的事**」。
    """
    tools = _registered_tools_in_subprocess({"DEMO_MODE": ""})

    assert "execute_python" in tools, f"默认该注册它，实际：{tools}"


def test_execute_python_is_not_registered_in_demo_mode():
    """🔴 **demo 模式下 `execute_python` 不进 `mcp_server.TOOLS`。**

    **为什么**：demo 跑在**魔搭创空间**上，而**一个 Studio = 一个容器**（实测）——
    **没有第二个容器**能跑执行器。⇒ 若不注册它，`execute_python` 会**回落本地子进程**
    （`EXECUTOR_URL` 为空），也就是**又回到宿主同权限的沙箱**里跑。
    业务方原话：「不要暴露在系统中执行，**是安全事故**」。

    ⚠️ 判据是**子进程里重新 import 后的真值**，⛔ 不是"源码里有这个 if"。
    """
    tools = _registered_tools_in_subprocess({"DEMO_MODE": "1"})

    assert "execute_python" not in tools, f"🔴 demo 模式下它还注册着：{tools}"
    # ⚠️ 反向对照：别的工具**不许被顺手删掉**
    assert {"calculator", "date_today", "web_search"} <= set(tools), f"别的工具被误删了：{tools}"
