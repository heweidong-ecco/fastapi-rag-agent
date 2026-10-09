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
#     bash scripts/check_dep_vulns.sh              # 扫 app/requirements.txt
#     bash scripts/check_dep_vulns.sh --self-test  # 自测：证明它真能扫出东西
#
# ## 三态（照本仓惯例）
#
#     0 = 没有已知漏洞 · 1 = **有** · **2 = 判不了**（⛔ 不算通过）
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

# ── 自测：造一个【已知有漏洞】的依赖清单，证明这道门真会红 ──────────────
if [ "${1:-}" = "--self-test" ]; then
  echo "[自测] 拿一个【已知含漏洞】的包跑 ⇒ 期望 exit 1"
  TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
  # `urllib3==1.26.4` 有多个已知 CVE（本仓⛔ 没用它，只是拿来当夹具）
  printf 'urllib3==1.26.4\n' > "${TMP}/req.txt"
  if "${PY}" -m pip_audit -r "${TMP}/req.txt" >/dev/null 2>&1; then
    echo "  🔴 自测失败：一个已知有 CVE 的版本居然扫不出东西 ⇒ 这道门是假的"
    exit 1
  fi
  echo "  ✅ 自测通过 —— 它真的会红（⛔ 不是"永远绿"）"
  exit 0
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
FILTER='^(sentence-transformers|transformers|locust|ragas|datasets)'
LIGHT="$(mktemp)"; trap 'rm -f "${LIGHT}"' EXIT
grep -vE "${FILTER}" "${REQ}" > "${LIGHT}"

echo "[依赖漏洞] 扫 app/requirements.txt（**过滤后** —— 与 ci.yml / Dockerfile 同一套正则）…"
set +e
"${PY}" -m pip_audit -r "${LIGHT}" --progress-spinner off
rc=$?
set -e
if [ "${rc}" -eq 0 ]; then
  echo "✅ 依赖漏洞门通过 —— 没有已知漏洞。"
  exit 0
fi
if [ "${rc}" -eq 1 ]; then
  echo ""
  echo "🔴 **有已知漏洞** —— 处置："
  echo "   ① 优先**升级到修好的版本**（改 app/requirements.txt）"
  echo "   ② 若升不动：在本文件下方或 SECURITY.md 里**写明为什么接受**（⛔ 不许静默放过）"
  exit 1
fi
echo "⚠️ 依赖漏洞门【未跑】—— pip-audit 自己出错，退出码 ${rc}（⛔ 不算通过）。" >&2
exit 2
