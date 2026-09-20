"""全仓审计的 🔴A / 🔴B 两条修复的回归测试（2026-09-20）

| # | 位置 | 问题 |
|---|---|---|
| **A** | `api/main.py:440` | **`/ready` 在 DB/Redis 挂掉时返回 500 而非 503** —— `health_check()` 不健康时 `return JSONResponse(...)`，而 `/ready` 对它调 `health.get("status")` ⇒ **`JSONResponse` 没有 `.get`** ⇒ `AttributeError` ⇒ 全局处理器返回 500 |
| **B** | `api/api_v1.py:136,144` · `api/schemas.py:86` | **公开 `/docs` 上的安全声明与代码相反** —— 原文三句「还没有加入初始管理员」「当前版本暂未强制校验管理员身份」「管理接口…暂不加权限控制」，而代码里 `api_v1.py:156` = `Depends(require_admin)`、`main.py:466` 启动即 `ensure_admin_exists` |

⚠️ 这两条都是**"声明与事实不符"**型 —— 靠跑一遍端点**发现不了 B**（它只出现在 `/docs` 与 Postman 导入里），
   所以 B 的用例直接查 **OpenAPI 文档对象**，而不是发请求。
"""
import ast
import contextlib
import pathlib

import pytest


# ===========================================================================
# 🔴A · /ready 健康检查不通过时必须是 503，不是 500
# ===========================================================================
def test_ready_returns_503_not_500_when_unhealthy(monkeypatch):
    """/ready 在底层不可用时必须回 **503**（"暂时不可用"），**不能是 500**（"服务内部错误"）。

    🔴 实测根因（2026-09-20）：`health_check()` 有**两种返回类型** ——
       健康时返回 `dict`，不健康时 `return JSONResponse(status_code=503, ...)`。
       而 `/ready` 无条件对它调 `.get("status")`
       ⇒ `JSONResponse` 没有 `.get` ⇒ `AttributeError: 'JSONResponse' object has no attribute 'get'`
        ⇒ 被全局异常处理器兜住 ⇒ **500**。

    ⚠️ 对 **K8s / 负载均衡** 来说这两个码是**不同语义**：
       503 = "别把流量给我，等会儿再试"；500 = "我坏了"。
       把"依赖挂了"报成"我坏了"，正是就绪探针最不该犯的错。

    ⇒ 本用例**真调 `/ready`**，把 DB 与 Redis 两条探针都打挂。
    """
    import main as M
    from fastapi.testclient import TestClient

    # 越过 /ready 的「启动后 10 秒内一律 503」那层门，否则测不到后面的逻辑
    monkeypatch.setattr(M, "APP_START_TIME", 0)

    def _boom(*_a, **_kw):
        raise RuntimeError("模拟依赖不可用")

    @contextlib.contextmanager
    def _dead_db():
        raise RuntimeError("模拟数据库不可用")
        yield  # pragma: no cover

    monkeypatch.setattr(M, "get_db", _dead_db)
    monkeypatch.setattr(M.redis_client, "ping", _boom)

    # ⚠️ `raise_server_exceptions=False` —— **本用例要断言的是真实 HTTP 状态码**，
    #    而不是"抛了个异常"。默认的 True 会让异常直接冒到测试里，
    #    那样就**测不出**"生产上到底是 500 还是 503"（生产环境有全局处理器兜住）。
    client = TestClient(M.app, raise_server_exceptions=False)
    resp = client.get("/ready")

    assert resp.status_code == 503, (
        f"/ready 在依赖不可用时返回了 **{resp.status_code}**（期望 **503**）。"
        "500 的语义是'服务内部错误'，会让 K8s/LB 误判 —— "
        "这两条依赖挂了应当报 503（暂时不可用）。"
        f"实际响应体：{resp.text[:200]}"
    )


# ===========================================================================
# 🔴B · 公开 /docs 上的安全声明不能与代码相反
# ===========================================================================
# 这三句是原文里**与代码相反**的断言（改后的描述不该再出现它们）
_CONTRADICTORY_CLAIMS = (
    "还没有加入初始管理员",
    "暂未强制校验管理员身份",
    "暂不加权限控制",
)


def test_openapi_descriptions_do_not_deny_admin_enforcement():
    """`/docs`（= `app.openapi()`）里不能出现"未加管理员/未鉴权"这类**与代码相反**的声明。

    🔴 实测（2026-09-20）：`/api/v1/admin/create_user` 的 `description` 里有三句
       「这个系统内**还没有加入初始管理员**」「当前版本**暂未强制校验管理员身份**」
       「管理接口（仅供管理员使用，**暂不加权限控制**）」——
       而代码事实是：`api/api_v1.py:156` = `Depends(require_admin)`（非 ADMIN 直接 403）、
       `api/main.py:466` 启动时 `ensure_admin_exists(logger)`（初始管理员是有的）。

    ⚠️ **这些字符串是 OpenAPI `description`，会原样渲染进公开的 `/docs`，并被 Postman 导入**
       ⇒ 面向**外部读者**的**安全声明**，说反了比不说更糟（会让人以为管理接口是敞开的）。
    ⚠️ 它**只出现在文档对象里**，发请求测不出来 ⇒ 所以本用例查 `app.openapi()`。
    """
    import main as M

    spec = M.app.openapi()
    hits = []
    for path, ops in (spec.get("paths") or {}).items():
        for method, op in (ops or {}).items():
            if not isinstance(op, dict):
                continue
            text = " ".join(str(op.get(k, "")) for k in ("summary", "description", "response_description"))
            for claim in _CONTRADICTORY_CLAIMS:
                if claim in text:
                    hits.append(f"{method.upper()} {path} :: 「{claim}」")

    assert not hits, (
        "OpenAPI 描述里仍有**与代码相反**的安全声明（会渲染进公开 /docs）：\n  "
        + "\n  ".join(hits)
        + "\n代码事实：`admin/create_user` 用的是 `Depends(require_admin)`；启动时 `ensure_admin_exists`。"
    )


# ===========================================================================
# §二 · 一个类里不能有【同名方法定义两次】
# ===========================================================================
def test_no_duplicate_method_definitions_in_preprocessor():
    """`document_preprocessor.py` 的类里，**同名方法不能定义两次**。

    🔴 实测（2026-09-20）：`remove_noise_markers` 被定义了**两次** ——
       `:85-86` 是**只有一句 docstring 的空壳**，`:88-103` 才是真实现。
       Python **后者胜出** ⇒ 当前行为是对的，**但改 `:85` 那份不会生效** ——
       下一个人照着上面那份改，改完"没反应"，且**没有任何报错**。

    ⚠️ **为什么不用"跑一下看输出"来测**：两条定义**在行为上恰好相同**
       （一条是空的、一条是真的，但真正生效的始终是后面的）
       ⇒ 无论修没修，跑 `remove_noise_markers()` **都通过**。
       ⇒ 这是**结构缺陷**，只能用**结构判据**守。

    📌 与 `CLAUDE.md` 修复记录 **#7 同型** —— `db.py` 的 `get_db()` 曾被重复定义 ⇒
       **写入不提交**（那次是行为真的错了）。⚠️ 本仓已两次踩同一个坑。
    """
    src = pathlib.Path(__file__).with_name("document_preprocessor.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        seen = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen.setdefault(item.name, []).append(item.lineno)
        for name, linenos in seen.items():
            if len(linenos) > 1:
                problems.append(f"{node.name}.{name} 定义了 {len(linenos)} 次，行号：{linenos}")

    assert not problems, (
        "同一个类里有【同名方法定义多次】—— 先定义的那份**永远不会生效**，"
        "改它不会报错、也不会有任何效果：\n  " + "\n  ".join(problems)
    )
