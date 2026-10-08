# MCP 无状态与传输层 —— 官方原文摘录

> ## 这份文档是什么
>
> **把 MCP（Model Context Protocol）官方文档里关于「无状态」和「传输层」的原始说法摘下来**，
> **逐条附出处**，供以后查阅、引用、核对。
>
> ⛔ **它不是本项目的设计文档。** 本项目自己的 MCP 路线裁定 ⇒
> `docs/decisions/DEC-104-MCP客户端统一路线-解SDK锁与长驻会话.md`。
>
> ⚠️ **它自足**：不依赖本仓任何别的文档 ⇒ **可整份复制到其它仓库**（同 `docs/说明/魔搭创空间-部署与平台约束.md` 的体例）。
>
> ## ⛔ 一条硬约束：**只放官方原文，⛔ 不放"我记得是这样"**
>
> 本文件里**每一句带引号的话都必须能在这个 URL 上再抓一遍**（抓法见 §七）。
> 项目自己的判断**必须标注**为 `⚪ 本项目判断`，**不许混进官方原文里**。
> 📌 **为什么定这条规矩**：写这份文档之前，我曾凭记忆写下
> 「Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers」——
> **那不是我核实过的原文**（真原文见 §五）。**记忆在协议细节上不可靠**，所以这份文件的信用全押在「可再抓一遍」上。

## 可信度标记（沿用本仓 `docs/说明/` 的体例）

| 标记 | 含义 |
|---|---|
| 🟢 官方 | 官方文档原文，**附 URL，可再抓** |
| 🔵 实测 | 本机跑命令测出来的（附命令） |
| ⚪ 本项目判断 | 本项目的推论 / 工程取舍，**⛔ 不是协议要求** |
| ⚠️ 未核实 | 听说 / 有印象，但**没抓到出处** ⇒ 别引用 |

---

## 一 · 一句话

🟢 **MCP 的「无状态」是 `2026-07-28` 这一版修订引入的，指的是「协议层不再有会话（no protocol-level sessions）」** ——
去掉 `initialize` 握手、去掉 `Mcp-Session-Id` 头。

🔴 **它 ⛔ 不等于「每次调用起一个新进程」。** stdio 传输在 `2026-07-28` 里**仍然是**
「a **client-launched subprocess**」的措辞（见 §三·原文 2、§四·误读 ①）。

---

## 二 · 版本时间线（**哪一版有握手**）

🟢 官方版本号 = `YYYY-MM-DD`，**代表「最后一次不向后兼容的修订」的日期**。

| 修订版 | 有无 `initialize` 握手 | 说明 |
|---|---|---|
| **2025-06-18** 及更早 | **有** | 属于官方所称的「handshake-based protocol revisions」 |
| 2025-11-25 | **有** | 官方在 `2026-07-28` 的 changelog 里称它为「**the previous revision**」 |
| **2026-07-28** | **无**（已去掉） | 🔴 **当前版本** · 「Make MCP stateless」（`SEP-2575` / `SEP-2567`） |

🟢 **原文**（Versioning 页）：**「The current protocol version is 2026-07-28.」**
🟢 **原文**（Versioning 页）：**「the previous revision, 2025-11-25.」**
🟢 **原文**（Versioning 页）：**「For interoperability with servers and clients that implement the
handshake-based protocol revisions (`2025-11-25` and earlier), see Backward Compatibility.」**

⇒ 🔴 **「handshake-based」这个标签覆盖 `2025-11-25` 及更早** ——
⚠️ **所以 `2025-06-18` 属于「有握手」那一类**（这条曾被记错，此处以上面这句原文为准）。

---

## 三 · 官方原文（**逐条，可再抓**）

### 原文 1 · `2026-07-28` 为什么要变无状态（去掉握手）

> **Make MCP stateless: remove the `initialize` / `notifications/initialized` handshake.**
> Every request now carries its protocol version and client capabilities in `_meta`
> (`io.modelcontextprotocol/protocolVersion`, `io.modelcontextprotocol/clientCapabilities`).
> Clients SHOULD identify themselves on each request (`io.modelcontextprotocol/clientInfo`),
> and servers SHOULD identify themselves in each result's `_meta`
> (`io.modelcontextprotocol/serverInfo`). Version mismatches return
> `UnsupportedProtocolVersionError` (`SEP-2575`).

📄 `https://modelcontextprotocol.io/specification/2026-07-28/changelog`

### 原文 2 · `2026-07-28` 去掉了协议级会话（`Mcp-Session-Id`）

> **Remove protocol-level sessions and the `Mcp-Session-Id` header from the Streamable HTTP transport.**
> List endpoints (`tools/list`, `resources/list`, `prompts/list`) **no longer vary per-connection**.
> Servers that need cross-call state use **explicit, server-minted handles passed as ordinary tool
> arguments** (`SEP-2567`).

📄 同上（`2026-07-28` changelog）

> ⚪ **本项目判断**：这一条对**本项目没有直接影响** —— 本项目走的是 **stdio**，
> 不是 Streamable HTTP，用的也不是服务端跨调用状态。

### 原文 3 · `2026-07-28`：stdio 仍然是「客户端启动的子进程」

> **`stdio`: newline-delimited messages over the standard streams of a client-launched subprocess.**

📄 `https://modelcontextprotocol.io/specification/2026-07-28/basic/transports`

### 原文 4 · `2026-07-28`：只有「进程生命周期」是 stdio 特有的

> Custom transports that run over a reliable bidirectional byte stream (e.g., Unix domain sockets
> or TCP) SHOULD reuse the **stdio framing** rather than defining a new one: the stdio binding is
> **just newline-delimited JSON-RPC over a byte stream**, and **only its process-lifecycle rules are
> specific to standard streams.**

📄 同上

### 原文 5 · `2026-07-28`：向后兼容段（承认旧版是「连接级会话」）

> **Earlier protocol revisions established a connection-scoped session with an `initialize` handshake**
> and allowed servers to initiate JSON-RPC requests.

📄 同上（`2026-07-28` transports · Backward Compatibility）

### 原文 6 · `2025-06-18`：stdio 的定义（**旧版措辞，对照用**）

> **In the stdio transport:**
> - **The client launches the MCP server as a subprocess.**
> - The server reads JSON-RPC messages from its standard input (`stdin`) and sends messages to its
>   standard output (`stdout`).

📄 `https://modelcontextprotocol.io/specification/2025-06-18/basic/transports`

---

## 四 · 「无状态」**不**意味着什么（**三条常见误读**）

### 误读 ① ⛔ 「无状态 ⇒ 每次调用起一个新进程」

**不成立。** 🟢 `2026-07-28` 的 transports 页**仍然**写
「**a client-launched subprocess**」（原文 3），`2025-06-18` 写
「**The client launches the MCP server as a subprocess.**」（原文 6）。

🔴 **无状态说的是「协议层没有会话」**（没有 `initialize` 握手、没有 `Mcp-Session-Id`）——
**⛔ 它没有规定子进程什么时候起、起几个。**

### 误读 ② ⛔ 「无状态 ⇒ 不能常驻一个长连接 / 长会话」

**官方没有这么说。** 🟢 官方只把 stdio 的**规则**限定为「**process-lifecycle rules**」
（原文 4），**⛔ 没有规定进程生命周期必须多短**。

⚪ **本项目判断**：既然协议不要求，那么「**开一个长驻的 `async with`**」在协议上是允许的 ——
本项目正是这么决定的（`DEC-104`）。**这是工程取舍，⛔ 不是协议要求。**

### 误读 ③ ⚠️ 「无状态 ⇒ 幂等（idempotent）」

⚠️ **未核实**：这是**第三方**的推论，我在官方文档里**没找到这句**。
🔴 **别引用。** 「无状态」（没有会话）与「幂等」（同样输入 ⇒ 同样副作用）**是两件事**。

---

## 五 · 官方【没有】说的事（⚠️ **「查无」也是结论**）

> 📌 **为什么要专门写这一节**：本仓立场 ——
> **「从不命中」与「没人违规」在机器痕迹上完全一样**。
> ⇒ **把"我没找到"写下来**，下一个人就不用再找一遍，**也不会误以为"官方默许"**。

- 🔴 **官方没有**任何关于「子进程启动开销 / 每次起进程太贵」的表述。
  ⇒ 「**每次起子进程太贵**」是 ⚪ **本项目自己的工程判断**。
- 🔴 **官方没有**「一个 agent 配一个 MCP server 子进程」这类规定。
- 🔴 **官方没有**说「无状态 ⇒ 必须无状态地部署」。

---

## 六 · ToolAnnotations 是【提示】，⛔ 不是【权限】

🟢 **原文**（`2025-06-18` · server/tools）：

> **For trust & safety and security, clients MUST consider tool annotations to be untrusted unless
> they come from trusted servers.**

📄 `https://modelcontextprotocol.io/specification/2025-06-18/server/tools`

⇒ **`readOnlyHint` / `destructiveHint` 这类注解**，**在没有"可信来源"的前提下必须当成不可信** ——
🔴 **⛔ 不许拿它当授权依据**（例如"这个工具标了 `readOnlyHint`，所以可以自动执行"）。

⚠️ **本节是这份文档存在的原因之一**：我原先记得的措辞是
「Clients **should never** make tool use decisions based on ToolAnnotations received from untrusted servers」——
**那不是我核实过的原文**；**上面这句才是。**

---

## 七 · 怎么重新抓一遍（**可重跑**）

`WebFetch` 在本机对 `modelcontextprotocol.io` 会被拦（"Unable to verify if domain … is safe to fetch"）⇒
用 `curl`（本仓 `docs/规范/文档体系-外部依据.md` 记过同一个绕法）。本机无 `pandoc` / `lynx` / `w3m` ⇒ 用 `python3` 去标签。

```bash
strip() { python3 -c "
import sys,re,html
t=sys.stdin.read()
t=re.sub(r'(?is)<(script|style|svg|nav|header|footer)\b.*?</\1>',' ',t)
t=re.sub(r'(?is)<br\s*/?>','\n',t)
t=re.sub(r'(?is)</(p|li|h[1-6]|div|tr|pre|code)>','\n',t)
t=re.sub(r'(?s)<[^>]+>',' ',t)
t=html.unescape(t); t=re.sub(r'[ \t]+',' ',t); t=re.sub(r'\n\s*\n+','\n',t)
print(t.strip())"; }

curl -sSL --max-time 20 https://modelcontextprotocol.io/specification/2026-07-28/changelog       | strip | grep -n 'stateless\|Mcp-Session-Id'
curl -sSL --max-time 20 https://modelcontextprotocol.io/specification/versioning                 | strip | grep -n 'current protocol version\|handshake-based'
curl -sSL --max-time 20 https://modelcontextprotocol.io/specification/2026-07-28/basic/transports | strip | grep -n 'client-launched subprocess\|process-lifecycle'
curl -sSL --max-time 20 https://modelcontextprotocol.io/specification/2025-06-18/server/tools    | strip | grep -n 'untrusted'
```

⚠️ `…/specification/versioning` 会 **308 重定向** ⇒ 必须带 `-L`（否则拿到空页）。

**抓到之后怎么核**：把 `grep` 到的**整句**和本文档 §三 / §六 的引文**逐字比** ——
⛔ **别只核"关键词出现过"**（关键词出现 ≠ 那句话还是那个意思）。

---

## 八 · 本项目当前处在哪（🔵 实测 · 随代码变，**用命令核对别抄**）

> 🔴 **2026-10-08（批④-A）更正：下表前两行【已过时】** —— SDK 上界已解到 `mcp>=2.3.0,<3`、
> 实装 **2.3.0**，`api/mcp_server.py` 也已从装饰器迁到 **2.x 的构造器回调**。
> ⚠️ **下表是 2026-10-08 上午的快照，⛔ 不改写**；**现行值一律跑右边那列命令**。
> ⚠️ **"上锁的理由"那一行仍然是【真的】** —— 解包 mcp 2.3.0 实测，
> `Server` **确实没有** `list_tools()`（`grep -n "def list_tools" mcp/server/lowlevel/server.py` ⇒ 0 命中）。
> 📄 迁移的裁定与实测 ⇒ `DEC-110`。

| 项 | 现状 | 判据（可打印） |
|---|---|---|
| SDK 版本要求 | **`mcp>=1.0.0,<2`**（**上了锁**） | `grep -n '^mcp' api/requirements.txt` |
| 上锁的理由 | `mcp` 2.x 的 `Server` 去掉了 `list_tools()`，而 `api/mcp_server.py` 用 `@server.list_tools()` ⇒ `AttributeError` | 同上（:93-94 注释） |
| 实装版本 | 🔵 **mcp 1.30.0** | `./venv/bin/python -c "import importlib.metadata as m; print(m.version('mcp'))"` |
| **服务端**是不是握手形态 | **是** —— 用了 `create_initialization_options()` | `grep -n 'create_initialization_options' api/mcp_server.py` |
| **客户端**在哪 | **只有一条路**走 MCP client：`api/agent_graph_advanced.py` | `grep -rn 'stdio_client\|ClientSession' api/*.py` |
| 会话怎么起的 | **每次调用** `async with stdio_client(...)` → `async with ClientSession(...)`（**短会话**） | `grep -n 'async with stdio_client' api/agent_graph_advanced.py` |

🔴 **⇒ 本项目现在同时处在两个"旧"上**：
① **SDK 版本旧**（`<2` 锁着）· ② **会话模型旧**（每次调用起一次子进程，且服务端还是握手形态）。
**这两条怎么改、什么时候改 ⇒ 见 `DEC-104`。**

---

## 关联

- **本项目自己的 MCP 路线裁定** ⇒ `docs/decisions/DEC-104-MCP客户端统一路线-解SDK锁与长驻会话.md`
- **同类「外部平台/协议」自足文档（体例参考）** ⇒ `docs/说明/魔搭创空间-部署与平台约束.md`
- **本仓文档体系的分层依据（Diátaxis 等）** ⇒ `docs/规范/文档体系-外部依据.md`
