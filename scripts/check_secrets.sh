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
# 📌 修订史(每一次都是**门真上岗时抓到的**,不是想出来的):
#   v1 → v2: 原先扫**整份 diff**(含 `-` 删除行) ⇒ **删掉一个存量密钥时门报红**。
#            已改为只扫**新增行**(泄漏只可能发生在"写进去"的时候)。
#   v2 → v3(2026-09-17): 第 ① 段的键过滤原先是"**除了太短的,全扫**" ⇒
#            `POSTGRES_HOST=postgres` / `LLM_MODEL_CHAT=qwen-plus` 被当成凭据,
#            **门把本仓最高频的词全列成了命中**。已加【非机密键】排除名单(见第 ① 段)。
#            ⇒ 两次都是**门的假阳性**,两次都不是"门太松"。
#   v3 → v4(2026-09-17) 🔴 **最严重的一次,而且它不是新增的问题 —— 它自 v1 起就在**:
#            全部三处判定都写成 `printf '%s' "$X" | grep -q…`。`grep -q` **命中即退出**,
#            上游 `printf` 收到 **SIGPIPE(141)**;而本脚本开头有 `set -o pipefail` ⇒
#            **整条管道**的状态变成 141 ⇒ `if` 判成"**没命中**" ⇒ **真实命中被静默丢弃**。
#            ⚠️ 它是**概率性**的 —— 取决于 printf 写完没有(竞态)。
#            **实测:同一份暂存内容连跑 20 次,拦住 11 次、漏报 9 次。**
#            ⇒ 已全部改成 `grep … >/dev/null`(读完再判断,不早退)。
#            📌 这就是一道**看起来在工作、实际是硬币**的门 —— 比"没有门"更坏,
#              因为它会让人以为自己被保护着。复盘见 docs/复盘/2026-09-17-一道硬币做的门.md。
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
#
# 🔴 【非机密键】排除名单 —— 2026-09-17 加,起因是**门第二次真上岗时拦错了**。
#
#   病因:本段原先遍历 .env 的**每一个**键做值匹配。于是这些**基础设施配置**被当成了凭据:
#       POSTGRES_HOST=postgres · POSTGRES_DB=rag_db · LLM_MODEL_CHAT=qwen-plus · LLM_BASE_URL=<dashscope 地址> · LOGIN_USER_NAME=admin
#   —— 而这些**恰恰是本仓文档里最高频的词**。后果:**门会拦下绝大多数正常 commit**
#   (本仓 M6 那次提交就是被它拦下的,两个命中全是它自己 `.env` 里的 postgres / rag_db)。
#
#   ⇒ 做法:**排除"按名字就知道不是机密"的类别,其余键照旧全扫**。
#     取舍写在明处:这是**偏向误报**的 fail-safe 方向 —— 新出现的怪键仍会被拦,
#     而不是静默放过。若要反过来(只扫机密型键名),那是另一种取舍,见 DEC-014。
#   📌 **不静默**:跳过了哪些键,下方会逐条打印出来。
NON_SECRET_KEY_RE='(_HOST|_PORT|_DB|_URL|_MODEL_|_CONN|_USER_NAME|_EXPIRE_)'
SKIPPED_KEYS=()

if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key val; do
        case "$key" in ''|\#*) continue ;; esac
        # 非机密键:跳过,但**记下来待会儿打印**(不静默排除)
        if printf '%s' "$key" | grep -E -- "$NON_SECRET_KEY_RE" >/dev/null; then
            SKIPPED_KEYS+=("$key"); continue
        fi
        val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
        [ "${#val}" -lt 6 ] && continue           # 太短的不算(避免误报)
        # 🔴 **不许用 `grep -q`** —— 见文件头部「修订史 v3→v4」：
        #    `-q` 命中即退出 ⇒ 上游 `printf` 收到 SIGPIPE(141) ⇒ `set -o pipefail` 让
        #    **整条管道**返回 141 ⇒ `if` 判成"没命中" ⇒ **真实命中被静默丢弃**。
        #    ⚠️ 它是**概率性**的:同一份暂存内容连跑 20 次,拦 11 次、漏 9 次(实测)。
        if printf '%s' "$SCAN_TEXT" | grep -F -- "$val" >/dev/null; then
            echo "  ❌ 命中: .env 中的 $key"
            HITS=$((HITS+1)); FAILED_NAMES+=("$key")
        fi
    done < <(grep -E '^[A-Z_][A-Z0-9_]*=' "$ENV_FILE" 2>/dev/null)
    echo "  · 已跳过 ${#SKIPPED_KEYS[@]} 个【非机密键】($NON_SECRET_KEY_RE):"
    echo "      ${SKIPPED_KEYS[*]:-无}"
else
    echo "  ⚠️ 未找到 .env —— 跳过真实凭据检查(不能确认它们没泄漏)"
fi

# ---- ② 存量黑名单:历次已泄漏/已作废的字面量 --------------------------------
# ⚠️ 该文件**必须**在 .gitignore 里 —— 它装的是"绝不能再进仓库"的值本身
if [ -f "$DENYLIST" ]; then
    while IFS= read -r lit; do
        case "$lit" in ''|\#*) continue ;; esac
        # ⚠️ 同样**不许用 `grep -q`**（理由见第 ① 段那处注释）
        if printf '%s' "$SCAN_TEXT" | grep -F -- "$lit" >/dev/null; then
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
    # ⚠️ 同样**不许用 `grep -q`**（理由见第 ① 段那处注释）
    if printf '%s' "$SCAN_TEXT" | grep -E -- "$p" >/dev/null; then
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
