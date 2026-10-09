#!/usr/bin/env python3
"""发 / 撤 API Key（`DEC-085` 契约 D 的手）。

## 为什么是脚本，⛔ 不是 HTTP 端点

上公网之后，"发 key"这件事不该多开一个公网面，也不该动路由鉴权门
（`scripts/route-auth-baseline.txt`）。脚本跑在**本机**，只有能登这台机器的人用得到。

## 用法

    venv/bin/python scripts/issue_api_key.py alice            # 发一把，30 天
    venv/bin/python scripts/issue_api_key.py alice --days 7   # 发一把，7 天
    venv/bin/python scripts/issue_api_key.py alice --revoke   # 撤销 alice 名下**全部** key

⚠️ **必须用 `venv/bin/python`，⛔ 不是系统 `python3`** —— 本脚本经 `auth.py` 连带
   `import psycopg2`，而系统 python3 **没装**（实测 `ModuleNotFoundError`）。
   本仓 `scripts/ci-local.sh:110` 挑解释器时也是**优先 venv**，同一取向。

⚠️ 明文 key **只打印这一次** —— 库里存的是 sha256，找不回来。

## 🔴 为什么 `--revoke` 写 `0` 而**不是** `NULL`

`app/access/auth.py` 的判据是 `COALESCE(is_active, 1) = 1`（**NULL 当激活**）。
⇒ 撤销时把列写成 NULL = **没撤销**，而屏幕上会打一句"已撤销"。
   这正是本仓记了一路的「闸是装饰」—— ⇒ 这里**只写 0/1**。
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))

# 🔴 2026-10-09 修：模块化重构（`#123`）把这两个挪进了 `app/access/` 与 `app/core/`，
#    而这里的扁平导入没跟着改 ⇒ **本脚本整条跑不起来**（`ModuleNotFoundError: No module named 'auth'`）。
#    ⚠️ **它是【发凭据】的那把工具** —— 坏了就等于"进不去系统"。
#    ⚠️ 913 条 pytest **照不到脚本**；CI 的 `compileall` 也照不到（**导入期错 ≠ 语法错**）。
from access.auth import create_user_api_key, hash_api_key   # noqa: E402,F401
from core.db import get_db                                  # noqa: E402


def issue(user_name: str, days: int, role: str | None = None) -> None:
    api_key = create_user_api_key(user_name, expire_days=days, role=role)
    shown = role if role is not None else "（未指定 ⇒ 库里写 NULL ⇒ 读侧按用户名回退）"
    print(f"✅ 已为用户 {user_name!r} 发一把 key（{days} 天 · role={shown}）：")
    print()
    print(f"    {api_key}")
    print()
    print("⚠️ 上面这串**只显示这一次**（库里存的是哈希）。现在复制走，别等会儿再回来找。")


def revoke(user_name: str) -> int:
    """把该用户名下**所有还活着的** key 置为 `is_active = 0`；返回影响行数。"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # 🔴 只写 `0` —— ⛔ 不许写 `NULL`（见模块 docstring：NULL 在判据里 = **激活**）。
            # ⚠️ 末尾那个 `COALESCE(is_active, 1) = 1` 是为了让 `rowcount` 报"真的撤掉了几把"；
            #    去掉它也能撤（把 0 再写成 0 是幂等的），但那样报数会虚高，看不出"本来就没活着"。
            cur.execute(
                "UPDATE api_keys SET is_active = 0 "
                "WHERE user_name = %s AND COALESCE(is_active, 1) = 1",
                (user_name,),
            )
            n = cur.rowcount
            conn.commit()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="发 / 撤 API Key（DEC-085 契约 D）")
    ap.add_argument("user_name")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--revoke", action="store_true", help="撤销该用户名下全部 key")
    # 🔴 2026-10-09（B1 · `DEC-129`）：角色。
    #    ⚠️ **不给默认值**（`default=None`）—— "不传"与"传了 free"**不是一回事**：
    #    不传 ⇒ 库里写 `NULL` ⇒ 读侧按用户名**回退**；传了 ⇒ 就是裁决。
    ap.add_argument("--role", default=None,
                    help="角色（free / premium / admin）。⛔ 不传 ≠ 传 free —— 不传走回退")
    args = ap.parse_args()

    if args.revoke:
        n = revoke(args.user_name)
        print(f"{'✅ 已撤销' if n else '⚠️ 没有可撤销的 key（都已撤销 / 用户不存在）'}"
              f"：{args.user_name!r} 共 {n} 行")
        return 0

    issue(args.user_name, args.days, role=args.role)
    return 0


if __name__ == "__main__":
    sys.exit(main())
