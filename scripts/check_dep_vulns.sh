#!/usr/bin/env bash
#
# check_dep_vulns.sh —— 依赖漏洞扫描（**本地工具，⛔ 不依赖 GitHub 功能**）
#
# ## 为什么有它
#
# 业务方 2026-10-09 裁：「**只开 alert 或者我们自己下载本地依赖扫描工具，本地自测，
# 不依赖 GitHub**」。
#
# ⛔ **不用 Dependabot** —— 它会**自动开 PR**，与本仓「**PR 别频繁开**」正面冲突。
# ✅ **改用 `pip-audit`**（开源 CLI，**在本机跑**，结果自己看）。
#
# ## 用法
#
#     bash scripts/check_dep_vulns.sh                  # 扫 app/requirements.txt
#     bash scripts/check_dep_vulns.sh --self-test      # 自测：证明它【三态都分得开】
#     bash scripts/check_dep_vulns.sh --decide <json>  # 拿一份 pip-audit 的 JSON 走一遍判定
#
# ## 三态（照本仓惯例）
#
#     0 = 没有已知漏洞 · 1 = **有** · **2 = 判不了**（⛔ 不算通过）
#
# ## 🔴🔴 为什么**不能只看 `pip-audit` 的退出码**（2026-10-09 实测栽过）
#
# **实测事故**：网络抖动（`pypi.org` 读超时）⇒ `pip-audit` 抛
# `requests.exceptions.ConnectionError` ⇒ **Python 未捕获异常，退出码 1**。
# 而**「找到漏洞」的退出码也是 1**。
# ⇒ 旧版本（只看 `rc`）**把「网络崩了」报成了「🔴 有已知漏洞」**，
#    还顺手给了"优先升级到修好的版本"的建议 —— 让人去找**根本不存在的漏洞**。
#
# ⚠️ **这正是本仓记过多次的那一族**：**两个不同的状况共用一个信号**
#    （`docs/复盘/2026-10-05-拿代理量当判据.md`）。**「判不了」和「有」必须分开。**
#
# ⇒ **现在的判据换成「输出是不是合法 JSON」**（`--format json`）：
#    拿得到可解析的 JSON ⇒ 才谈得上有/没有；拿不到 ⇒ **判不了（2）**。
#    ⛔ 退出码不再参与判定（它只用于**打印给人看**）。
#
# ## ⚠️ 两条克制（与 `check_lint_baseline.sh` 同款，理由一样）
#
# 1. **找不到 `pip-audit` ⇒ exit 2（"没跑"），⛔ 不是 0** ——
#    「没跑」与「跑了且干净」在机器痕迹上**一模一样**，那正是本仓反复栽的那个坑。
# 2. ⛔ **不进 `pre-commit-gates.py`** —— 它要**联网**、跑一次几十秒，
#    挂在每次提交上会把人烦死。它是**手动/定期**跑的，不是提交门。
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ="${REPO}/app/requirements.txt"
PY="${REPO}/venv/bin/python"
[ -x "${PY}" ] || PY="$(command -v python3)"

# ── 判定：读 `pip-audit --format json` 的输出文件 ⇒ 三态 ────────────────
#
# 返回：0 = 干净 · 1 = 有漏洞（stdout 列出） · 2 = **判不了**（解析不出来）
decide() {  # $1 = json 文件路径
  "${PY}" - "$1" <<'PY'
import json, sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
    deps = data["dependencies"]
except Exception as exc:                       # 网络崩了 / 吐了非 JSON / 结构不对
    print(f"（判不了：{type(exc).__name__}: {exc}）", file=sys.stderr)
    raise SystemExit(2)

bad = []
for d in deps:
    vulns = d.get("vulns") or []
    if vulns:
        ids = [v.get("id", "?") for v in vulns]
        fixes = sorted({f for v in vulns for f in (v.get("fix_versions") or [])})
        bad.append((d.get("name", "?"), d.get("version", "?"), ids, fixes))

if not bad:
    print(f"（扫了 {len(deps)} 个包，0 条）")
    raise SystemExit(0)

print(f"{len(bad)} 个包有已知漏洞：")
for name, ver, ids, fixes in sorted(bad):
    tail = f"   修好于 {', '.join(fixes)}" if fixes else ""
    print(f"  🔴 {name} {ver}   {' '.join(ids)}{tail}")
raise SystemExit(1)
PY
}

# ── 人工/自测用：拿一份现成的 JSON 走判定（与主流程【同一条】代码路径）──
if [ "${1:-}" = "--decide" ]; then
  [ -f "${2:-}" ] || { echo "用法: bash scripts/check_dep_vulns.sh --decide <pip-audit 的 json 文件>" >&2; exit 2; }
  decide "$2"
  exit $?
fi

# ── 自测：证明这【三态都分得开】 ──────────────────────────────────────
#
# 🔴 相 2 是 2026-10-09 那次事故的正例 —— 「网络崩了」必须落 2，⛔ 不许落 1。
if [ "${1:-}" = "--self-test" ]; then
  fails=0
  TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT

  echo "[自测 1/3] 真跑一个【已知含 CVE】的包 ⇒ 期望 exit 1"
  printf 'urllib3==1.26.4\n' > "${TMP}/req.txt"
  "${PY}" -m pip_audit -r "${TMP}/req.txt" --format json > "${TMP}/out.json" 2>"${TMP}/err.txt"
  audit_rc=$?
  decide "${TMP}/out.json" >/dev/null 2>&1
  d_rc=$?
  if [ "${audit_rc}" -eq 0 ]; then
    echo "  🔴 失败：一个已知有 CVE 的版本居然扫不出东西 ⇒ 这道门是假的"
    fails=$((fails + 1))
  elif [ "${d_rc}" -eq 1 ]; then
    echo "  ✅ 它真的会红（⛔ 不是'永远绿'）"
  else
    echo "  🔴 失败：期望判定为 1，实得 ${d_rc}"
    fails=$((fails + 1))
  fi

  echo "[自测 2/3] 喂一份【不是 JSON】的东西（= 网络崩了/Python 抛异常）⇒ 期望 exit 2"
  printf 'Traceback (most recent call last):\nrequests.exceptions.ConnectionError: Read timed out\n' > "${TMP}/garbage.txt"
  decide "${TMP}/garbage.txt" >/dev/null 2>&1
  if [ $? -eq 2 ]; then
    echo "  ✅ 「判不了」没被报成「有漏洞」（🔴 这正是 2026-10-09 栽的那次）"
  else
    echo "  🔴 失败：这份垃圾被报了非 2 ⇒ 网络故障又会被说成'有已知漏洞'"
    fails=$((fails + 1))
  fi

  echo "[自测 3/3] 喂一份【合法且干净】的 JSON ⇒ 期望 exit 0"
  printf '{"dependencies":[{"name":"demo","version":"1.0","vulns":[]}]}\n' > "${TMP}/clean.json"
  decide "${TMP}/clean.json" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "  ✅ 干净就是干净（⛔ 不会因为'解析得通'就乱红）"
  else
    echo "  🔴 失败：一份确定干净的 JSON 被判成了非 0"
    fails=$((fails + 1))
  fi

  if [ "${fails}" -eq 0 ]; then
    echo ""; echo "✅ 自测通过 —— 三态都能分开。"; exit 0
  fi
  echo ""; echo "🔴 自测失败 ${fails} 项。"; exit 1
fi

# ── 主流程 ──
if ! "${PY}" -m pip_audit --version >/dev/null 2>&1; then
  echo "⚠️ 依赖漏洞门【未跑】（按「未跑」计，⛔ 不是通过）—— 找不到 pip-audit。" >&2
  echo "   装法：${PY} -m pip install pip-audit" >&2
  echo "   ⛔ **别写进 app/requirements.txt** —— 那份清单会进 demo 镜像（同 ruff 那条理由）。" >&2
  exit 2
fi

[ -f "${REQ}" ] || { echo "⚠️ 依赖漏洞门【未跑】—— 找不到 ${REQ}" >&2; exit 2; }

# 🔴 **必须用【过滤后】的那份** —— 与 `ci.yml` / `app/Dockerfile` **同一套正则**。
#
# ⚠️ **为什么不能直接扫 `app/requirements.txt`**（实测 2026-10-09）：
#    全量清单在**全新解析**下**装不起来** —— `pip-audit` 会先建临时 venv 真装一遍，
#    而 `transformers(>=4.41,<5)` 与 `gradio==6.27.0` 的依赖**互相冲突** ⇒ 工具直接报
#    `ResolutionImpossible`（⛔ 那不是"依赖有漏洞"，是"这份清单从来没被一起装过"）。
#    ⇒ 本仓 venv 里**也从没同时装过这两个**（`transformers` 是构建期被裁的那 5 个之一）。
#    ⇒ 扫**这份清单实际会装的东西**才对 —— 与 CI 同源。
#
#    📌 顺带：**这条也是「判不了」的一种**（工具自己解析不动）——
#    换成 JSON 判定之后，它会老老实实落 2，⛔ 不会再被误报成"有漏洞"。
FILTER='^(sentence-transformers|transformers|locust|ragas|datasets)'
LIGHT="$(mktemp)"; OUT="$(mktemp)"; ERR="$(mktemp)"
trap 'rm -f "${LIGHT}" "${OUT}" "${ERR}"' EXIT
grep -vE "${FILTER}" "${REQ}" > "${LIGHT}"

echo "[依赖漏洞] 扫 app/requirements.txt（**过滤后** —— 与 ci.yml / Dockerfile 同一套正则）…"
"${PY}" -m pip_audit -r "${LIGHT}" --progress-spinner off --format json > "${OUT}" 2> "${ERR}"
rc=$?          # ⚠️ 只用于**打印给人看**，⛔ 不参与判定 —— 见文件头那段

decide "${OUT}"
verdict=$?

case "${verdict}" in
  0)
    echo "✅ 依赖漏洞门通过 —— 没有已知漏洞。"
    exit 0
    ;;
  1)
    echo ""
    echo "🔴 **有已知漏洞** —— 处置："
    echo "   ① 优先**升级到修好的版本**（改 app/requirements.txt）"
    echo "   ② 若升不动：在 SECURITY.md §3.4 里**写明为什么接受**（⛔ 不许静默放过）"
    exit 1
    ;;
  *)
    echo "⚠️ 依赖漏洞门【未跑】—— pip-audit 没吐出可判定的 JSON（它自己的退出码 ${rc}）。" >&2
    echo "   ⛔ **这不等于「有漏洞」，也不等于「干净」** —— 按「没跑」计。" >&2
    echo "   ---- pip-audit 的 stderr 尾部 ----" >&2
    tail -n 5 "${ERR}" >&2
    exit 2
    ;;
esac
