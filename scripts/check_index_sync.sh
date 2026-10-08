#!/usr/bin/env bash
#
# check_index_sync.sh —— 钉：**索引列表里【声明覆盖】的每一份，都真的还在**
#
#     bash scripts/check_index_sync.sh              # 报 🔴（有则退出码 1）
#     bash scripts/check_index_sync.sh --self-test  # 自测：造假索引，证明它真会红
#
# ## 为什么要有它
#
# 业务方 2026-10-09 立了 `frontend/索引.md`，并给了一条纪律：
#   「**其他文档更新了，索引列表同时更新**」
#
# 🔴 但「**同步没同步**」这件事**本身测不出来** —— 没有人知道"索引该列什么"。
#    ⇒ **能测的是【结构】**：**索引声明覆盖的那些，必须真的还在**。
#    ⇒ 所以索引里有一块 **`index-manifest`**（机器可读的覆盖清单）⇒ **本脚本钉它**。
#
# ## ⛔ 它【不】重复 `check_doc_links.sh`
#
# 那道门扫的是**全文反引号里的路径**；本脚本扫的是**索引自己声明的覆盖清单**。
# 两者**靶子不同**：那道管"引用对不对"，这道管"**这一份还在不在**"。
#
# ## 三态（照本仓惯例）
#
#     0 = 过 · 1 = 有缺 · **2 = 判不了**（⛔ 不算通过）
#
# ## ⚠️ 防空跑
#
# 「**清单一条都没解析到**」与「**都合规**」在输出上长得一样 ⇒ 本脚本带下限，
# 低于 `MIN_ENTRIES` ⇒ **红**（本仓前科：`pre-commit-gates.py` 空跑 · `test_web_pages.py` 的 glob 空跑）。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

INDEX="frontend/索引.md"
#: 清单低于这个数 ⇒ 当"解析失败"，⛔ 不当"全都没问题"
MIN_ENTRIES=20

MODE="check"
[ "${1:-}" = "--self-test" ] && MODE="self-test"

# ── 自测：造一份【少了一条】的索引，证明这道门真会红 ──────────────────────
if [ "${MODE}" = "self-test" ]; then
  echo "[自测] 造假索引：把清单里的一条删掉 ⇒ 期望 🔴 + 退出码 1"
  TMPD="$(mktemp -d)"; trap 'rm -rf "${TMPD}"' EXIT
  mkdir -p "${TMPD}/frontend"
  # 删掉清单里的第 3 条（`CHANGELOG.md` 那行），其余原样
  awk 'BEGIN{done=0} /^```index-manifest$/{inb=1;print;next}
       /^```$/{if(inb){inb=0};print;next}
       inb && !done && /^CLAUDE\.md$/{done=1; print "CLAUDE.md"; print "这一条根本不存在.md"; next}
       {print}' "${INDEX}" > "${TMPD}/frontend/索引.md"

  set +e
  out="$(INDEX_OVERRIDE="${TMPD}/frontend/索引.md" bash "${BASH_SOURCE[0]}" 2>&1)"; rc=$?
  set -e
  if [ "${rc}" -eq 1 ] && printf '%s' "${out}" | grep -q '这一条根本不存在'; then
    echo "[自测] ✅ 通过（退出码 1，且点名了那条）"
    echo "[自测] 反向：原索引 ⇒ 期望 0"
    bash "${BASH_SOURCE[0]}" >/dev/null 2>&1 && echo "[自测] ✅ 原索引退出码 0" || { echo "[自测] 🔴 原索引也红了 —— 先修它"; exit 1; }
    exit 0
  fi
  echo "[自测] 🔴 没红（退出码 ${rc}）—— 这道门是瞎的"; echo "${out}" | head -5; exit 1
fi

# ── 正身 ────────────────────────────────────────────────────────────────
INDEX="${INDEX_OVERRIDE:-${INDEX}}"

if [ ! -f "${INDEX}" ]; then
  echo "🔴 索引不在：${INDEX}" >&2
  echo "   ⇒ 它是业务方 2026-10-09 要的那份（「找前端的东西看它，⛔ 不用 grep」）" >&2
  exit 1
fi

python3 - "${INDEX}" "${MIN_ENTRIES}" <<'PY'
import os, re, subprocess, sys

index, min_entries = sys.argv[1], int(sys.argv[2])
text = open(index, encoding="utf-8").read()

# 取 ```index-manifest … ``` 之间的行（⛔ 不认别的块）
m = re.search(r"^```index-manifest\s*\n(.*?)^```\s*$", text, re.M | re.S)
if not m:
    print(f"🔴 {index} 里找不到 ```index-manifest 块 ⇒ 判不了，⛔ 不算通过", file=sys.stderr)
    sys.exit(2)

entries = [ln.strip() for ln in m.group(1).splitlines() if ln.strip() and not ln.strip().startswith("#")]

if len(entries) < min_entries:
    print(f"🔴 清单只解析到 {len(entries)} 条（下限 {min_entries}）⇒ 当【解析失败】，⛔ 不当"
          f"「都没问题」（空跑 = 静默假通过）", file=sys.stderr)
    sys.exit(2)

# 「在不在」的口径 = 【会不会随 clone 一起下来】—— 与 check_doc_links.sh 同款，⛔ 不问磁盘
# 🔴 **必须 `-z`** —— `git ls-files` 默认把非 ASCII 路径**转义成 `\ooo`**
#    （本仓前科：`git ls-tree` 的八进制转义让中文 grep 恒 0）。
#    ⚠️ 用 -z（NUL 分隔、不转义）。⇒ 不加这一条，**所有中文路径都会被误报成"没入库"**。
_raw = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
tracked = {p for p in _raw.decode("utf-8").split("\0") if p}
missing_disk = [e for e in entries if not os.path.exists(e)]
missing_git  = [e for e in entries if e not in tracked and os.path.exists(e)]

if missing_disk or missing_git:
    print("🔴 **索引声明覆盖的东西，有不在的** —— 业务方 2026-10-09 的纪律是"
          "「其他文档更新了，索引列表同时更新」：", file=sys.stderr)
    for e in missing_disk:
        print(f"   · {e}   ⇒ 盘上就没有（被删了 / 改了名）", file=sys.stderr)
    for e in missing_git:
        print(f"   · {e}   ⇒ 盘上有、但【没入库】⇒ 克隆者拿不到", file=sys.stderr)
    print("   ⛔ 处理：要么把它加回来，要么**改索引那一行**（两个都要动，⛔ 不许只动一头）",
          file=sys.stderr)
    sys.exit(1)

print(f"✅ 索引覆盖清单 {len(entries)} 条，全部在（且已入库）。")
PY
