# `api/deps.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 部分可用 —— **HTTP 侧完整**；**WebSocket 侧 2026-10-05 才补上**（此前 WS 整条裸奔） |
| **对外提供** | **HTTP 认证**：`get_current_user`（API Key）· `get_current_user_jwt`（JWT）· `get_current_user_hybrid`（两者皆可）· `require_admin`（管理员）· `verify_jwt_token`（纯函数）· `oauth2_scheme`<br>**WebSocket 认证**（🆕 `DEC-075`）：`require_ws_user`（依赖）· `resolve_ws_identity`（**纯函数**）· 常量 `WS_AUTH_TIMEOUT_SECONDS` / `WS_CLOSE_POLICY_VIOLATION`(1008) / `WS_CLOSE_INTERNAL_ERROR`(1011) |
| **谁在用** | `api/api_v1.py` · `api/api_v1_agent.py` · `api/api_v1_rag.py`（含 WS 那两条路由）· `api/main.py` —— ⚠️ 见 `scripts/check_route_auth.py` 的 `AUTH_NAMES`**就是靠本文件的函数名认人的** |

## ✅ 做了什么

- HTTP 三种凭据（API Key / JWT / hybrid）都能解析成 `user_name`；`require_admin` 再叠一层角色。
- **WS 首帧认证**（`DEC-075`）：`require_ws_user` 挂在 WS 路由上 ⇒ 客户端连上后**第一帧**发
  `{"type":"auth","api_key":…}`（或 `{"token":"<JWT>"}`）⇒ 通过才回 `{"type":"ready","user":"…"}`，
  不通过以 `close(1008)` 关闭，**端点体一次都不执行**。
- 认证失败**分清是谁的问题**：凭据不行 = **1008**；认证服务自己不可用（库连不上）= **1011**。

## 🟡 做到哪 / 缺什么

- ✅ `DEC-074`：`scripts/check_route_auth.py` 已**接线进 CI + 提交门**（此前只是"有脚本"）。
- ✅ `DEC-075`：`/api/v1/ws/agent` 挂上 `require_ws_user`；
  ⚰️ `/api/v1/ws/test` **同日已删**（`DEC-075` §十 · 纯回声测试桩 · 消费者 = 0）。
  ⇒ 基线里那条 WS **已消掉**（`scripts/route-auth-baseline.txt` 现只剩 HTTP 的 `/api/v1/`）。
- ⬜ **WS 的会话桶仍是"每连接"** —— `thread_id = f"ws-{uuid4}"`，重连 = 换桶。
  见 `DEC-075` 遗留·2（全局日级熔断 B11 仍罩着，故未失控）。
- ⬜ **`verify_api_key` 的 `get_db()` 没有 try**（`DEC-074` 遗留·4）——
  HTTP 侧库抖动时"带无效 key"会变成 **500 而不是 401**。
  ⚠️ **WS 侧已绕过这个坑**（`resolve_ws_identity` 自己 try ⇒ 1011），但**HTTP 侧没修**。

## ⚠️ 看代码会误判的地方

| 看代码容易以为 | 实际 |
|---|---|
| 🔴 **「WS 路由也能用 `get_current_user_hybrid` 那套」** | ⛔ **送不上来** —— `new WebSocket(url)` **不能自定义请求头**（浏览器 API 限制）⇒ `X-API-Key` / `Authorization` 客户端**根本发不出**。⚠️ 照抄 HTTP 依赖的形态**看着像接了鉴权**，实际是把所有人都挡在门外（或更糟：以为挡了其实没有）。⇒ WS 只能走**首帧 / 查询串 / 子协议**三条路，本轮选**首帧**（`DEC-075`）。 |
| 🔴 **「`require_ws_user` 里怎么还 `accept()` 了一次，端点里那次可以删」** | ✅ **端点里那次【必须】删** —— 星型 1.6.0 的 `WebSocket.accept()` **不幂等**，第二次会 `RuntimeError: Expected ASGI message "websocket.send" …, but got 'websocket.accept'`（实测）。本文件里那次是**唯一**一次。 |
| 🔴 **「失败直接 `close()` 不就行了，何必抛异常」** | ⛔ **会连发两帧 close** ⇒ `RuntimeError: Cannot call "send" once a close message has been sent.`。<br>星型自己会接住 `WebSocketException` 并 `close(code=…, reason=…)`（`ExceptionMiddleware.websocket_exception`，靠 **MRO** 命中 —— `fastapi.WebSocketException` 是 `starlette.exceptions.WebSocketException` 的子类，实测）。<br>⚠️ **只能二选一**：自己 close，**或**抛异常让星型 close。 |
| 🔴 **「先 `close()` 再 `accept()` 也一样，反正都是关」** | ⛔ **两回事**：`accept()` **之前**关 ⇒ 浏览器只看到**握手失败**，**拿不到关闭码**（实测）；`accept()` 之后关 ⇒ 前端 `onclose` 能读到 `code=1008` 与 `reason`。<br>⇒ 顺序是**用户可见行为**的一部分，⛔ 不是实现细节。 |
| 🔴 **「1008 和 1011 都是失败，随便报一个」** | ⛔ **对客户端是相反的处置**：1008 = 你的凭据不行（**换 key**）；1011 = 我这边不行（**重试，别换 key**）。<br>把库抖动报成 1008，等于**告诉用户去换一把没问题的 key** —— 他换了还是连不上，且**永远查不到原因**。 |
| 🔴 **「`deps.py` 里鉴权 fail-closed，那 `token_tracker` 怎么 fail-open，统一一下」** | ⛔ **故意相反，别统一**：这里是**安全边界**（放错了 = 匿名进门）；那边是**成本控制**（挡错了 = 全站停摆）。`token_tracker.get_session_token_usage` 的 docstring 里写着同一条。 |
| 🔴 **「中间件不是已经挡过了吗」** | ⛔ **挡不到 WS** —— `api/main.py` 那两个是 `BaseHTTPMiddleware`，**只看 `scope["type"] == "http"`**。⇒ WS 的鉴权**只能挂在路由自己的依赖上**，这也是它曾经整条裸奔的原因。 |
| 🔴 **「改了个鉴权函数名而已，跑一下测试就行」** | ⛔ **还要改 `scripts/check_route_auth.py` 的 `AUTH_NAMES`** —— 那个门是靠**函数名字符串**认人的，**名单漂了它会静默放过**（实测：把 `require_ws_user` 从名单里拿掉，两条 WS 立刻被判为"无鉴权"）。 |

## 关联

`docs/decisions/DEC-075-WS首帧认证.md`（本模块 WS 侧的设计与备选）·
`docs/decisions/DEC-041-B8会话上限的窗口与接线范围.md` 遗留·1（WS 无鉴权这条债的**出处**）·
`docs/decisions/DEC-074-中间件豁免名单改名与路由鉴权门的接线.md`（`AUTH_NAMES` 那道门）·
`docs/decisions/DEC-065-删除-无鉴权端点与收口鉴权.md`（同一族收口）·
`docs/specs/api_v1_rag.md` · `docs/specs/main.md` · `docs/specs/token_tracker.md`
