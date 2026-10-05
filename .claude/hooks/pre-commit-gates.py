#!/usr/bin/env python3
"""
PreToolUse hook —— **`git commit` 之前，自动跑本仓的五道门**。

## 为什么要它（这不是"再提醒一次"，是补一个结构性缺口）

本仓的规矩一直写着「提交前跑这几道门」，**但它们全靠人记得**。
而本仓有前科：**8 个 PR 一次都没跑过 `/留痕-checks`** ——
结论「**门挂在别处，就等于没有门**」（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）。

📌 **Anthropic 官方说法一致**：「**CLAUDE.md is context, not enforcement.**
必须每次发生的事，该用 hook。」（`docs/规范/文档体系-外部依据.md` §1.5）

📌 **2026-09-29 扩到三道**，依据是**当天实际犯的错**：
* 改完文档**没跑链接检查**（一路靠"我记得"）
* 新建文档**没登记 `docs/文档地图.md`**（脚本有了，但没人跑它）

## 五道门

| # | 门 | 脚本 | 拦住什么 |
|---|---|---|---|
| ① | **凭据门** | `scripts/check_secrets.sh` | PUBLIC 仓里混进明文凭据（**进了历史就改不掉**） |
| ② | **链接检查** | `scripts/check_doc_links.sh` | 文档里指向不存在的路径（**当天已犯 4 次**） |
| ③ | **孤儿检查** | `scripts/check_doc_orphans.sh` | 建了文档**但没人指向它**（索引挂空） |
| ④ | **模块 spec 门**（内联） | — | 新增 `api/*.py` 模块却没有 `docs/specs/<模块>.md` |
| ⑤ | **路由鉴权门** | `scripts/check_route_auth.py --baseline` | 新引入了**没有鉴权依赖**的路由（含 WebSocket）|

⚠️ **五道都会【跳过本次提交】吗** —— 不是，见下面「克制」。

## 行为

```
命中 git commit
  → 依次跑 ①②③（任一不通过 ⇒ 【阻止提交】exit 2，把输出带出来）
  → 全通过 ⇒ 放行（exit 0），stderr 打一行汇总
其它命令 ⇒ 直接放行（不做任何事）
```

## ⚠️ 四条克制（别把它改成"什么都要拦"）

1. **只管 `git commit`** —— 不拦 `add` / `push` / `status`
2. **门跑不起来时【不阻止】** —— 脚本不存在或执行异常 ⇒ **只警告、放行**
   （否则 hook 坏了会把人**锁死**；"门本身坏了"是另一个问题，不该由这里表现出来）
3. **不打印凭据值** —— 它只**转述** `check_secrets.sh` 的输出，那个脚本本身已有脱敏逻辑
4. **⛔ 不用 `jq`** —— 本机**没装**（用它读 stdin 会**静默读空**，见 `DEC` 里那份工作树文档 §四）
"""
import json
import os
import re
import subprocess
import sys

GIT_COMMIT = re.compile(r"\bgit\s+commit\b")

# (显示名, 脚本相对路径)
GATES = [
    ("凭据门", "scripts/check_secrets.sh"),
    ("链接检查", "scripts/check_doc_links.sh"),
    ("孤儿检查", "scripts/check_doc_orphans.sh"),
]

# ── 第 ④ 道门（**内联，不是外部脚本**）：新增模块必须有 spec ──
# 判据：`docs/specs/<模块名>.md` 是否存在（模块名 = `api/xxx.py` 去掉 `.py`）
#
# ⚠️ **只管【新增】的模块**（`--diff-filter=A`），**不管改已有的** ——
#    "改了代码要不要更新 spec"是**判断**，机械判不了（那交给 `spec-remind.py` 提醒）。
SPECS_DIR = ("docs", "specs")
NOT_A_MODULE = ("conftest.py",)


def new_modules_without_spec(repo: str):
    """返回：**本次新增、但没有 spec** 的模块文件列表。"""
    try:
        r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
                           cwd=repo, capture_output=True, text=True, timeout=30)
    except Exception:
        return None                      # git 跑不起来 ⇒ 交给调用方按"跳过"处理
    if r.returncode != 0:
        return None
    bad = []
    for f in r.stdout.splitlines():
        f = f.strip()
        if not (f.startswith("api/") and f.endswith(".py")):
            continue
        base = os.path.basename(f)
        if base.startswith("test_") or base in NOT_A_MODULE:
            continue                     # 测试不算产品模块
        spec = os.path.join(repo, *SPECS_DIR, base[:-3] + ".md")
        if not os.path.exists(spec):
            bad.append((f, os.path.join(*SPECS_DIR, base[:-3] + ".md")))
    return bad


def staged_files(repo: str):
    """本次 staged 的文件列表；**git 跑不起来时返回 `None`**（与"空列表"是两回事）。"""
    try:
        r = subprocess.run(["git", "diff", "--cached", "--name-only"],
                           cwd=repo, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def is_doc_only(repo: str) -> bool:
    """本次 staged 是否【只有文档/脚本】改动（那就不必要求 spec）。"""
    files = staged_files(repo)
    if not files:
        return False
    return not any(f.endswith(".py") for f in files)


# ── 第 ⑤ 道门：路由鉴权（`DEC-074`，2026-10-05 加）──
# 判据脚本 `scripts/check_route_auth.py --baseline`（含 WS，见该脚本 docstring）。
#
# 🔴 它 2026-09-30 就存在、也挂了提醒 hook，**但从没进过 CI，也没进过这道提交门**
#    ⇒ 只在"改路由文件"时提醒一句。本仓原话：**门挂在别处，就等于没有门**。
#
# ⚠️ **触发条件取"任何 api/ 下的产品 .py"**，⛔ 不取具体文件名清单 ——
#    提醒 hook 那边写的是 `{"main.py","api_v1.py","api_v1_rag.py","api_v1_agent.py"}`，
#    **新建一个 `api_v2.py` 就整个漏掉**（`DEC-066`「守卫的形状盲区」）。
#    这里用**范围**而不是**名字**，正是为了不留那个形状。
#    ⚠️ 代价：本仓多数提交都会动 api/*.py ⇒ 每次提交多 ~10s（实测 9.95s）。
#       这是**有意**拿时间换"不会被忘"；CI 那边无条件跑，是真正的兜底。
def api_product_files_staged(repo: str):
    """staged 里 `api/**.py` 的**产品**文件（排除测试与 conftest）。`None` = git 失败。"""
    files = staged_files(repo)
    if files is None:
        return None
    out = []
    for f in files:
        if not (f.startswith("api/") and f.endswith(".py")):
            continue
        base = os.path.basename(f)
        if base.startswith("test_") or base in NOT_A_MODULE:
            continue
        out.append(f)
    return out


def _python_for(repo: str) -> str:
    """优先用仓里的 venv 解释器（能 import 得起 `main`），否则退回 `python3`。"""
    for rel in (("venv", "bin", "python"), ("venv", "Scripts", "python.exe")):
        p = os.path.join(repo, *rel)
        if os.path.exists(p):
            return p
    return "python3"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # 输入不是 JSON ⇒ 不是我们该管的

    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not GIT_COMMIT.search(cmd):
        return 0  # 不是 commit ⇒ 放行

    # 定位仓根：优先 hook 给的 cwd；否则从本文件往上两级（.claude/hooks/x.py → 仓根）
    repo = data.get("cwd") or os.getcwd()
    if not os.path.exists(os.path.join(repo, "scripts", "check_secrets.sh")):
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(os.path.dirname(here))

    passed, failed, skipped = [], [], []

    for name, rel in GATES:
        path = os.path.join(repo, rel)
        if not os.path.exists(path):
            skipped.append(name)
            continue
        try:
            r = subprocess.run(["bash", path], cwd=repo, capture_output=True,
                               text=True, timeout=120)
        except Exception as e:
            skipped.append(f"{name}（跑不起来：{e}）")
            continue
        if r.returncode == 0:
            passed.append(name)
        else:
            failed.append((name, r))

    # ── 第 ④ 道门：新增模块必须有 spec（**硬拦**，业务方 2026-09-29 裁定）──
    # ⚠️ 三种状态**必须分清**。2026-10-01 修：原先写法把「本次没有 .py 改动」
    #    说成了「git 读不到 staged」（**假提示** —— 原样是：
    #      spec_bad = None
    #      if not is_doc_only(repo): spec_bad = new_modules_without_spec(repo)
    #    `is_doc_only` 为真 ⇒ `spec_bad` 保持 None ⇒ 落进下面「读不到 staged」那条；
    #    而真正想说「⏭ 本次无 .py 改动」的那句**永远走不到**（死代码）——
    #    因为 `spec_bad` 非空时必然 `not is_doc_only` ⇒ `is_doc_only(repo)` 恒 False）。
    #    ⇒ 后果：下一个人看到「git 读不到 staged」会去查 git / 查 staged，**白花时间**。
    #    ⇒ 这是「拿动作成功当结果正确」的**镜像版**：**把正常说成故障**。
    # 判据（可复现）：单独 `git add` 一个 .md 后跑本钩子，原先打
    #   `模块spec门 ⚠️ 跳过（git 读不到 staged）`，而 `git diff --cached --name-only`
    #   明明列出了那个文件 ⇒ **git 没坏**。
    # 现在三种状态各归各：
    #   doc_only      ⇒ 这道门**不适用**（本次没碰 .py）      → ⏭
    #   list（含空）  ⇒ git 读到了，结果就是它                → ✅ / 🔴 拦
    #   None          ⇒ git **真失败**（异常 / rc≠0）         → ⚠️ 跳过
    doc_only = is_doc_only(repo)
    spec_bad = None if doc_only else new_modules_without_spec(repo)

    # ── 第 ⑤ 道门：路由鉴权（`DEC-074`）──
    # 三种状态必须分清（同第 ④ 道门的教训：**别把正常说成故障**）：
    #   []        ⇒ 本次没动 api/ 产品代码            → ⏭
    #   [文件…]   ⇒ 跑检查：exit 0 过 / 非 0 拦       → ✅ / 🔴
    #   None      ⇒ git **真失败**                    → ⚠️ 跳过
    route_files = api_product_files_staged(repo)
    route_bad = None          # None = 没跑；否则为 CompletedProcess（非 0 即拦）
    if route_files:
        script = os.path.join(repo, "scripts", "check_route_auth.py")
        if not os.path.exists(script):
            route_files = None
        else:
            try:
                r = subprocess.run(
                    [_python_for(repo), script, "--baseline"],
                    cwd=repo, capture_output=True, text=True, timeout=180)
            except Exception:
                route_files = None          # 跑不起来 ⇒ 只跳过，⛔ 不阻止（同「四条克制」②）
            else:
                if r.returncode != 0:
                    route_bad = r

    # ── 有门没过 ⇒ 阻止 ──
    if failed or spec_bad or route_bad:
        print("", file=sys.stderr)
        print("⛔ 提交前的门【未通过】—— 已阻止本次 commit。", file=sys.stderr)
        if spec_bad:
            print("", file=sys.stderr)
            print("──── 模块 spec 门（新增模块必须有 spec）────", file=sys.stderr)
            for src, spec in spec_bad:
                print(f"   🔴 新增了 {src}，但 {spec} 不存在", file=sys.stderr)
            print("", file=sys.stderr)
            print("   ⇒ 为什么硬拦：**没有 spec 的模块，别人不知道它存在、也不知道做到哪。**",
                  file=sys.stderr)
            print("   ⇒ 建 spec 的模板见 docs/specs/README.md（**⭐ 关键节是「看代码会误判的地方」**）",
                  file=sys.stderr)
        if route_bad is not None:
            print("", file=sys.stderr)
            print("──── 路由鉴权门（新端点必须带鉴权依赖）────", file=sys.stderr)
            for line in (route_bad.stdout or "").splitlines()[-25:]:
                print("   " + line, file=sys.stderr)
            for line in (route_bad.stderr or "").splitlines()[-10:]:
                print("   " + line, file=sys.stderr)
            print("", file=sys.stderr)
            print("   ⇒ 判据全文见 scripts/check_route_auth.py 的 docstring；",
                  file=sys.stderr)
            print("     基线 = scripts/route-auth-baseline.txt（⛔ 它不是「允许清单」）。",
                  file=sys.stderr)
        for name, r in failed:
            print("", file=sys.stderr)
            print(f"──── {name} ────", file=sys.stderr)
            for line in (r.stdout or "").splitlines()[-25:]:
                print("   " + line, file=sys.stderr)
            for line in (r.stderr or "").splitlines()[-10:]:
                print("   " + line, file=sys.stderr)
        print("", file=sys.stderr)
        print("   ⇒ 先处理上面的命中项，再重新 commit。", file=sys.stderr)
        print("   （门的判据见 docs/规范/开发规范.md §2.4 · 处置见 docs/凭据轮换手册.md）",
              file=sys.stderr)
        return 2

    # ── 全过（或跳过）⇒ 放行 ──
    # ⚠️ 顺序要紧：**先判 `doc_only`** —— 否则「本次无 .py 改动」永远被
    #    「读不到 staged」抢先（原 bug）。`None` 那条**只留给 git 真失败**。
    parts = [f"{n} ✅" for n in passed]
    if doc_only:
        parts.append("模块spec门 ⏭ 本次无 .py 改动")
    elif spec_bad == []:
        parts.append("模块spec门 ✅")
    elif spec_bad is None:
        parts.append("模块spec门 ⚠️ 跳过（git 读不到 staged）")
    if route_files:
        parts.append("路由鉴权门 ✅")
    elif route_files == []:
        parts.append("路由鉴权门 ⏭ 本次没动 api/ 产品代码")
    else:
        parts.append("路由鉴权门 ⚠️ 跳过（脚本不在 / 跑不起来 / git 读不到 staged）")
    if skipped:
        parts.append("⚠️ 跳过：" + " · ".join(skipped))
    print(f"🔒 提交前五道门：{' ｜ '.join(parts) or '（无门可跑）'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
