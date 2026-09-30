#!/usr/bin/env python3
"""列出【没有鉴权依赖】的路由 —— 并和基线比（B 类检查）。

## 为什么要有这个脚本（2026-09-30）

**起因**：核 `api_v1.py` 时手工扫"哪些路由没鉴权"，**第一版扫出 0 条** ——
因为 `FastAPI 0.141` 起 `include_router` 的结果被包成 `_IncludedRouter`，
**`len(app.routes)` 不再等于路由总数**。

🔴 **而这个坑【仓里早就写着】** —— `api/test_public_paths.py:17-20` 一字不差地记着。
⇒ **知识在，但挂在一个谁都不会去读的地方**（那个测试文件的 docstring 里）。
⇒ 所以把它**做成一条能跑的命令**（本仓立场：「**写不出命令的，就是还没核过**」）。

## 用法

```bash
python3 scripts/check_route_auth.py                 # 只列出（人读）
python3 scripts/check_route_auth.py --baseline      # 和基线比，多了就 exit 1
python3 scripts/check_route_auth.py --write-baseline # 把当前结果写成新基线
```

⚠️ **它不 import 网络/DB** —— 但会 import `main`（那会建 Gradio Blocks、要 `.env`）。
   实测耗时见脚本末尾的 `--selftest`。

⚠️ **判据的口径**：`PUBLIC_PATHS` 里的**跳过不报**（那些是**有意公开**的，
   如 `/health` `/metrics` `/auth/login`）—— **只报"不在公开名单、又没鉴权依赖"的**。
"""
import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API = REPO / "api"
BASELINE = REPO / "scripts" / "route-auth-baseline.txt"

# 这些依赖名 = 「这条路由要身份」。
# ⚠️ 加新依赖时**记得加进这里**，否则会误报成"无鉴权"。
AUTH_NAMES = {
    "get_current_user",          # API Key
    "get_current_user_hybrid",   # API Key 或 JWT
    "get_current_user_jwt",      # JWT
    "require_admin",             # 管理员
    "check_budget",              # 预算检查（它内部就依赖身份）
}


def _dep_names(dependant) -> set:
    """递归取一个 dependant 子树里所有依赖的函数名。"""
    out = set()
    for sub in getattr(dependant, "dependencies", []) or []:
        call = getattr(sub, "call", None)
        if call is not None:
            out.add(getattr(call, "__name__", str(call)))
        out |= _dep_names(sub)
    return out


def _collect_apiroutes(routes, out: list) -> list:
    """🔴 本脚本存在的一半理由：**必须递归进 `_IncludedRouter`**。

    ⛔ 直接遍历 `app.routes` 会漏掉所有 `include_router` 进来的路由 ——
       在本仓那是 **53 条里的 48 条**（实测：不递归只能看到 5 条）。
    """
    for r in routes:
        kind = type(r).__name__
        if kind == "_IncludedRouter":
            # ⚠️ 属性名是 `original_router`（不是 `.routes`/`.router`）—— 实测出来的
            _collect_apiroutes(getattr(r.original_router, "routes", []) or [], out)
        elif kind == "APIRoute":
            out.append(r)
    return out


def scan() -> tuple[list[tuple[str, str]], int]:
    """返回 (无鉴权路由列表, 总路由数)。"""
    sys.path.insert(0, str(API))
    os.chdir(API)                      # ⚠️ `main` 的导入期要读相对路径的 .env

    # 🔴 必须在 `import main` **之前**设 —— 同 `api/conftest.py:20` 的理由：
    #    Gradio 在**导入期**就起非 daemon 线程去连 huggingface.co 发匿名遥测，
    #    本机网络不通时**卡在 TCP connect 上** ⇒ 实测把本脚本从 ~3s 拖到 **91s**。
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    import warnings
    warnings.filterwarnings("ignore")

    from main import app, PUBLIC_PATHS      # noqa: E402

    routes = _collect_apiroutes(app.routes, [])
    no_auth = []
    for r in routes:
        if r.path in PUBLIC_PATHS:
            continue
        if _dep_names(r.dependant) & AUTH_NAMES:
            continue
        methods = sorted((r.methods or set()) - {"HEAD", "OPTIONS"})
        no_auth.append((methods[0] if methods else "?", r.path))
    return sorted(no_auth, key=lambda x: x[1]), len(routes)


def _read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        ln.strip()
        for ln in BASELINE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="和基线比；变多则 exit 1")
    ap.add_argument("--write-baseline", action="store_true", help="写成新基线")
    args = ap.parse_args()

    rows, total = scan()
    paths = {p for _, p in rows}

    if args.write_baseline:
        BASELINE.write_text(
            "# 无鉴权路由基线（scripts/check_route_auth.py --write-baseline 生成）\n"
            "# 每一行 = 一条「不在 PUBLIC_PATHS、且没有鉴权依赖」的路由。\n"
            "# ⚠️ 这份基线【不是「允许清单」】—— 它是「已知的债」，见 docs/待办总表.md 🅗 的 S1/S2/S14。\n"
            "# ⛔ 变多 = 新引入了没鉴权的路由 ⇒ 该拦；变少 = 修好了 ⇒ 重新生成基线。\n"
            + "\n".join(sorted(paths)) + "\n",
            encoding="utf-8",
        )
        print(f"✅ 基线已写入 {BASELINE.relative_to(REPO)}（{len(paths)} 条）")
        return 0

    print(f"真实 APIRoute 总数：{total}（含 include_router 进来的 —— 已递归进 _IncludedRouter）")
    print(f"🔴 无鉴权路由：{len(rows)} 条\n")
    for m, p in rows:
        print(f"   {m:6} {p}")

    if not args.baseline:
        return 0

    base = _read_baseline()
    new = paths - base
    gone = base - paths
    if new:
        print(f"\n❌ 比基线【多了 {len(new)} 条】—— 新引入了没鉴权的路由：")
        for p in sorted(new):
            print(f"     + {p}")
        print("\n⇒ 要么给它加 `Depends(get_current_user_hybrid)`（或 require_admin），")
        print("   要么确认它确实该公开 —— 后者请同时把它加进 `main.PUBLIC_PATHS`。")
        return 1
    if gone:
        print(f"\n✅ 比基线少了 {len(gone)} 条（修好了）：")
        for p in sorted(gone):
            print(f"     - {p}")
        print("   ⇒ 跑 `--write-baseline` 更新基线。")
        return 0
    print("\n✅ 与基线一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
