"""🔴 真起 MCP 子进程、真走 stdio 协议 —— 本仓**唯一**一条 MCP 端到端守卫。

## 为什么必须有这一条（批④ 立）

`api/test_agent_repairs.py` 里那几条 MCP 用例**全都 monkeypatch 掉**了
`stdio_client` / `ClientSession` ⇒ 它们验的是**我们和假对象的契约**，⛔ 不是「真协议跑不跑得通」。

⇒ **服务端 API 接错了（批④ 唯一的风险面），现有测试一条都不会红。**
这条守的就是那个面：**真子进程 × 真协议 × 真调用**。

⚠️ **成本**（实测 2026-10-08）：单次调用 **1.8s** · `list_tools` **1.4s** ⇒ 本文件约 **3s**。
   不标 `integration` / `needs_db` —— 它**不碰网、不碰库**（⛔ 别为了省 3 秒把它摘出 CI，
   那等于把**唯一**能抓 API 迁移错误的东西摘掉）。

📌 它的价值证明：**迁移前它就绿**（Task 1 跑过）⇒ 迁移后若变红，**一定是迁移搞坏的**。
"""
import asyncio

#: 真调用的探针工具 —— 用 `calculator`：**纯本地、无网、无副作用**，且结果是确定的
PROBE_TOOL = "calculator"
PROBE_ARGS = {"expression": "6*7"}
PROBE_EXPECT = "42"


def test_served_tools_match_the_registry():
    """🔴 **服务端真的吐出来的工具**，必须与 `mcp_server.TOOLS` **逐名一致**。

    为什么这条能抓迁移错误：`list_tools` 处理器若是**没接上**（或还留着 1.x 的装饰器形态），
    客户端会拿到**空清单或直接报错** —— 而「注册了 7 个」与「服务真出 7 个」是**两件事**。

    ⚠️ 反证（施工单 Task 3 会做）：把 `on_list_tools=` 从 `Server(...)` 里拿掉 ⇒ **本用例红**。
    """
    import mcp_server

    from agent_graph_advanced import get_mcp_tools

    served = sorted(t.name for t in asyncio.run(get_mcp_tools()).tools)
    registered = sorted(t["func"].name for t in mcp_server.TOOLS)

    assert served == registered, (
        f"🔴 服务端吐出来的工具与注册表对不上\n  服务端={served}\n  注册表={registered}"
    )
    # ⚠️ 反向对照：别让一条"两边都是空集"把本用例洗成绿
    assert registered, "注册表是空的 —— 本用例会退化成空集合比对"


def test_real_call_round_trips_through_stdio():
    """真调一个工具，结果**原样回来** —— 端到端把 `call_tool` 那条线走通。"""
    from agent_graph_advanced import call_mcp_tool

    out = asyncio.run(call_mcp_tool(PROBE_TOOL, PROBE_ARGS))

    assert out == PROBE_EXPECT, f"期望 {PROBE_EXPECT!r}，实际 {out!r}"
