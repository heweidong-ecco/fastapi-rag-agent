#!/usr/bin/env bash
# ============================================================================
# 凭据门 · 提交/开 PR 前跑 —— **命中即 exit 1 中止**
# ============================================================================
#
# ⚠️ 为什么要有这个脚本(2026-09-17):
#   此前"凭据 grep"只是**我临时敲的一行命令** —— 它**只打印命中，不中止 commit**。
#   那不是门，是一份报告。结果:当天我把 3 个历史泄露凭据的字面量**写进了 PUBLIC 文档**,
#   grep 报了 hits=1×3,**commit 照样落地了**(靠 amend 才救回来)。
#   ⇒ **判据 vs 动作** —— 本仓第 N 次栽在同一个坑上。这个脚本就是把它变成【动作】。
#
# 📌 设计约束:**本脚本自身不得含任何凭据字面量**
#   - 真实凭据 → 从 `.env` 现读(该文件已被 gitignore)
#   - 存量黑名单 → 从 `.secret-denylist` 现读(**也被 gitignore**)
#   - 另加一组**通用模式**(不需要知道具体值就能命中)
#
# 用法:
#   bash scripts/check_secrets.sh          # 扫 staged 改动(默认,提交前用)
#   bash scripts/check_secrets.sh --all    # 扫整个工作区
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-staged}"
ENV_FILE="$REPO_ROOT/.env"
DENYLIST="$REPO_ROOT/.secret-denylist"

# 取本次要扫的文本。
# ⚠️ 只扫【新增行】 —— 泄漏只可能发生在"写进去"的时候。
#    v1 曾扫整份 diff,结果:**我删掉一个存量凭据字面量时,门报了红** ——
#    因为它连 `-` 删除行一起扫了。**删掉密钥是好事,不该拦。**
#    (这个缺陷是门第一次真上岗时抓到的,已修。)
if [ "$MODE" = "--all" ]; then
    SCAN_TEXT="$(git grep -h -I -e '' -- . 2>/dev/null || true)"
    echo "[凭据门] 扫描范围: 整个工作区(全部内容)"
else
    # 去掉 diff 头(`+++ b/...`)与删除行(`-`),只留新增行(`+`)
    SCAN_TEXT="$(git diff --cached -U0 2>/dev/null | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
    echo "[凭据门] 扫描范围: staged 的【新增行】(git diff --cached | grep '^+')"
fi

if [ -z "$SCAN_TEXT" ]; then
    echo "[凭据门] staged 区为空 —— 没有要提交的内容。"
    exit 0
fi

HITS=0
FAILED_NAMES=()

# ---- ① 真实凭据:从 .env 现读(报告只写【名字】,绝不写值)----------------------
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key val; do
        case "$key" in ''|\#*) continue ;; esac
        val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
        [ "${#val}" -lt 6 ] && continue           # 太短的不算(避免误报)
        if printf '%s' "$SCAN_TEXT" | grep -qF -- "$val"; then
            echo "  ❌ 命中: .env 中的 $key"
            HITS=$((HITS+1)); FAILED_NAMES+=("$key")
        fi
    done < <(grep -E '^[A-Z_][A-Z0-9_]*=' "$ENV_FILE" 2>/dev/null)
else
    echo "  ⚠️ 未找到 .env —— 跳过真实凭据检查(不能确认它们没泄漏)"
fi

# ---- ② 存量黑名单:历次已泄漏/已作废的字面量 --------------------------------
# ⚠️ 该文件**必须**在 .gitignore 里 —— 它装的是"绝不能再进仓库"的值本身
if [ -f "$DENYLIST" ]; then
    while IFS= read -r lit; do
        case "$lit" in ''|\#*) continue ;; esac
        if printf '%s' "$SCAN_TEXT" | grep -qF -- "$lit"; then
            echo "  ❌ 命中: .secret-denylist 中的某个存量字面量(第 $(grep -nF -- "$lit" "$DENYLIST" | head -1 | cut -d: -f1) 行)"
            HITS=$((HITS+1)); FAILED_NAMES+=("denylist")
        fi
    done < "$DENYLIST"
else
    echo "  · 未找到 .secret-denylist —— 跳过存量字面量检查(可选文件)"
fi

# ---- ③ 通用模式:不需要知道具体值 -------------------------------------------
declare -a PATTERNS=(
    'sk-[A-Za-z0-9]{16,}'                  # OpenAI/DashScope 风格
    'ghp_[A-Za-z0-9]{20,}'                 # GitHub PAT
    'gho_[A-Za-z0-9]{20,}'                 # GitHub OAuth
    'AKIA[0-9A-Z]{16}'                     # AWS Access Key ID
    'BEGIN [A-Z ]*PRIVATE KEY'             # PEM 私钥
    'eyJhbGciOi[A-Za-z0-9_-]{10,}'         # JWT(裸的,不带 Bearer 前缀时也算)
)
for p in "${PATTERNS[@]}"; do
    if printf '%s' "$SCAN_TEXT" | grep -qE -- "$p"; then
        echo "  ❌ 命中通用模式: $p"
        HITS=$((HITS+1)); FAILED_NAMES+=("pattern:$p")
    fi
done

# ---- ④ 结论 -----------------------------------------------------------------
echo ""
if [ "$HITS" -gt 0 ]; then
    echo "⛔ 凭据门: 未通过 —— $HITS 处命中: ${FAILED_NAMES[*]}"
    echo "   ⚠️ 命中项已【不打印值】(那会让这份日志本身变成泄漏源)"
    echo "   ⇒ 请先脱敏再提交。规则:报告扫描结果【只写名字,不写值】。"
    exit 1
fi
echo "✅ 凭据门: 通过 —— 0 命中"
exit 0
