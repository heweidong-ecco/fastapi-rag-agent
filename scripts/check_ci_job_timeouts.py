#!/usr/bin/env python3
"""每个 CI job 必须带 `timeout-minutes` —— 缺了就报。

## 为什么（`§七·2` · 出处 `DEC-081` §四）

`ci.yml` 现两个 job **都配了**（`syntax` 5 · `offline-tests` 15），但**靠人记得**：
新建第 3 个 job 时忘了配 ⇒ **静默没有上限**。

🔴 **为什么值得一道门**：卡住的 job **不消耗失败次数、只消耗时间**；
而**「卡住」与「跑得很慢」在机器痕迹上完全一样**
（`docs/复盘/2026-09-17-看到汇总行就以为跑完了.md` §一·附）
⇒ **没有上限时，「卡住」不是一个【显式状态】**。

## 为什么是纯文本解析（⛔ 不 `import yaml`）

`PyYAML` 在本机 `venv` 里有（实测 6.0.3），但**不在 `app/requirements.txt`** ⇒ CI 里没有。
⛔ **不为一道门给 demo 镜像加依赖** —— 同「`ruff` 不进 requirements」那条理由
（那份清单会进 demo 镜像）。本脚本**只用标准库**。

## 口径（GitHub Actions 的缩进形状）

* **job 头** = `jobs:` 之后、**恰好 2 空格**缩进、以 `:` 结尾的行。
* **该 job 自己的块** = 从它的头到**下一个 job 头**（或文件末）。
* 块内必须有**恰好 4 空格**缩进的 `timeout-minutes:`，且值为**正整数**。

⚠️ **为什么不用"扫全文有没有 `timeout-minutes`"**：那数不出**是哪个 job 缺**，
而本门的价值恰恰是**点名**。也 ✅ **不数条数** —— 条数会随 job 增减而变，不是判据。

## 用法

    python3 scripts/check_ci_job_timeouts.py [workflow路径]    # 默认 .github/workflows/ci.yml

## 退出码（⛔ 三种必须分开）

    0  全带（并打印每个 job 的分钟数 —— 让人看得见"尺子有读数"）
    1  有 job 缺 / 值非法 —— **点名**
    2  没能判定（文件不在 / 一个 job 都解析不出来）—— **⛔ 不许当作通过**

🔴 `2` 与 `0` 必须分开：本仓立场「**'没能判定'压成'没有孤儿'** = 静默假通过」
（同 `scripts/check_doc_orphans.sh` 的 T4）。

## ⚠️ 一条已知边界（⛔ 不假装它不存在）

本门**跑在 `ci.yml` 里**，而它检查的**就是 `ci.yml`** ⇒ 若哪天有人**把整个
`offline-tests` job 删掉**，本门**连同它一起消失** ⇒ **静默不再检查**。
退出码 `2` 覆盖的是"**解析不出 job**"，**⛔ 不覆盖**"这个 job 被整个删了"。
"""
import re
import sys
from pathlib import Path

DEFAULT = ".github/workflows/ci.yml"

# ⚠️ 两个锚都要**顶到头**（`^`），否则会匹配到嵌套更深的键（比如 `steps:` 里的东西）。
_JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
_TIMEOUT = re.compile(r"^    timeout-minutes:\s*(\S+)\s*$")


def jobs_with_timeout(text):
    """⇒ `[(job 名, timeout 的原始字符串 或 None)]`。

    `jobs:` 之前的内容**完全不参与** —— 否则 `on:` 下面那些键会被当成 job。
    """
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.rstrip() == "jobs:")
    except StopIteration:
        return []

    starts = [
        (i, m.group(1))
        for i, l in enumerate(lines[start + 1:], start + 1)
        if (m := _JOB.match(l))
    ]

    out = []
    for n, (idx, name) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        found = None
        for l in lines[idx + 1:end]:
            m = _TIMEOUT.match(l)
            if m:
                found = m.group(1)
                break
        out.append((name, found))
    return out


def main(argv):
    path = Path(argv[1] if len(argv) > 1 else DEFAULT)
    if not path.is_file():
        print(f"🔴 读不到 workflow：{path} —— ⛔ 这【不是】通过", file=sys.stderr)
        return 2

    found = jobs_with_timeout(path.read_text(encoding="utf-8"))
    if not found:
        print(
            f"🔴 在 {path} 里一个 job 都没解析出来 —— 形状变了？⛔ 这【不是】通过",
            file=sys.stderr,
        )
        return 2

    bad = []
    for name, val in found:
        if val is None:
            bad.append((name, "缺 `timeout-minutes`"))
        elif not val.isdigit() or int(val) <= 0:
            bad.append((name, f"值非法：{val!r}（要正整数）"))

    if bad:
        print(f"🔴 {path}：以下 job 没有可用的超时上限 ——", file=sys.stderr)
        for name, why in bad:
            print(f"   · {name} —— {why}", file=sys.stderr)
        print(
            "\n📌 卡住的 job 只烧时间、不烧失败次数 ⇒ 没有上限时「卡住」不是显式状态。",
            file=sys.stderr,
        )
        print("📄 出处：`docs/待办总表.md` §七·2 · `DEC-081` §四", file=sys.stderr)
        return 1

    print(
        f"✅ {path}：{len(found)} 个 job 全带超时上限 —— "
        + " · ".join(f"{n}={v}" for n, v in found)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
