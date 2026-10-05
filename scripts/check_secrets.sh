#!/usr/bin/env bash
# ============================================================================
# 凭据门 · 提交/开 PR 前跑 —— **三态退出码**(v6 起):
#   0 = **执行了 且 0 命中**(部分覆盖时结论行会标注)
#   1 = **命中** ⇒ 中止提交
#   2 = **无法判定 / 扫描未完整执行** ⇒ **不得当作通过**
#   🔴 判据是 `通过 ⇐ 执行 ∧ ¬命中` —— **不许退化成** `通过 ⇐ ¬命中`。
#      本文件的 v4 与 v5 各自栽在这条上的一次(见「修订史」)。
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
#   v4 → v5(2026-09-20) 🔴 也是**自 v1 起就在**的另一条同类路径 —— v3→v4 只修了
#            "症状所在的那一处",没修**形状**:
#            `SCAN_TEXT` 取自管道,而 `2>/dev/null` + `|| true` 把「生产者失败」压成了
#            「产出为空」⇒ **扫描没跑,门照样绿**。最狠的一个变体是:若 `git diff`
#            **输出一部分之后才失败**,`SCAN_TEXT` 非空 ⇒ 走正常路径 ⇒ 打出**货真价实的**
#            `✅ 凭据门: 通过 —— 0 命中`,而扫的是**被截断的内容** —— **绿得毫无破绽**。
#            ⇒ 已改为**单独取 `git diff`/`git grep` 自身的退出码**,失败即 `exit 2`(不得当作通过);
#              并新增 **③-0 自证(positive control)**:喂一个运行时拼接的合成样本,
#              断言模式匹配机制抓得住它 —— 抓不住即 `exit 2`。
#            📌 判据形式的修正:`通过 ⇐ 执行 ∧ ¬命中`,**不许退化成** `通过 ⇐ ¬命中`。
#              复盘见 docs/复盘/2026-09-20-查不到不等于不存在.md。
#            ⚠️ 回归测试:scripts/test_check_secrets.sh(断言**退出码**,不断言文案)。
#   v5 → v6(2026-09-20) ⚠️ **v5 是半拉子修复,当天被合并前评审当场抓到**:
#            v5 只堵了「SCAN_TEXT 生产者失败」**那一条**未执行路径,却漏了同一个形状的另两条 ——
#            **① 真实凭据(无 .env)** 与 **② 存量黑名单(无 denylist)** 整段不跑时,
#            门仍打印**无限定语**的 `✅ 通过 —— 0 命中` + `exit 0`。
#            实测(仓根无 .env 无 denylist):三节里两节没跑,输出与"全跑了没命中"**不可区分**。
#            ⇒ ① 改为 **`.env` 缺失 ⇒ ⛔ 扫描未完整执行 + `exit 2`**(不得当作通过);
#              显式设 `SECRETS_GATE_ALLOW_NO_ENV=1` 可降级为【部分覆盖】(结论行会标注)。
#              ② 保持"可选文件"语义(它是补充检查),但**结论行现在会带覆盖度**。
#            📌 **教训(比缺陷本身重要)**:修"某条路径"时,必须回头问
#               「**同一个形状还有别的入口吗?**」—— 否则下一轮评审还会抓到同型残件。
#               （本次就是:同一份文件里,同一个形状,连着两版各修掉一条。）
#   v6 → v7(2026-10-05 · `DEC-076`) 两件事,都是为了**把本门接进 CI**:
#            ⓐ 新增 `--diff <range>` 模式(**三点**范围)。CI 里没有"暂存区"这个东西,
#               `--all` 又扫**存量行**(当场命中 2 处良性示例 ⇒ 恒红)且语义不是"本 PR 新增"。
#               ⇒ 只扫 `git diff <base>...<head>` 的新增行;范围取不到即 exit 2(⛔ 不静默变绿)。
#            ⓑ 🔴 **修掉结论行的【覆盖度过度声明】** —— 见下方 COV_ENV/COV_DENY 处注释:
#               原先写死 `覆盖 ①②③`,而没有 `.secret-denylist` 时 ② 整节根本没跑。
#               这**不是新缺陷**,是与 v5→v6 **同一个形状**的残件(v6 只修了①那条,没修②)。
#               ⚠️ 它偏偏会在 CI 里现形:CI 的新鲜检出**既没有 .env 也没有 denylist**。
#
#   v7 → v8(2026-10-05 · 批 4 · `DEC-080`) 把「**这道门还抓不抓得住**」做成可执行的 `--selftest`:
#            ⓐ 判定逻辑抽成**唯一一份** `match_re`/`match_lit`,① ② ③ 三处调用点**全部**改走它。
#               理由:自测若验的是**复制出来的另一份**判定,那等于「**用硬币验硬币**」——
#               生产那行改坏了,自测照样绿。
#            ⓑ 新增 `--selftest [N]`:每个模式一个合成样本 × **连跑 N 次**,**任一次漏报即 exit 1**。
#               ⚠️ 载荷取 **256 KiB**(> 管道缓冲区)—— 这是 v4 那个竞态**唯一的复现条件**。
#                  **实测**(本机,变异自证):把 `match_re` 改回 `grep -E -q` ⇒ **120/120 次全部漏报**(红);
#                  而把载荷缩到 4 KiB、同一条 `grep -q` ⇒ **一次都不漏**(绿)
#                  ⇒ **小样本上的自测永远绿**。承重件是**载荷大小**,⛔ 不是次数。
#            📌 与 ③-0 自证的分工:③-0 每次跑一遍(挡"机制整体失灵");
#               `--selftest` 靠"大载荷 × 连跑"专抓**概率性**漏报。**两者缺一不可。**
#            出处:待办总表 §五·5 · `docs/复盘/2026-09-17-一道硬币做的门.md`
#
# 用法:
#   bash scripts/check_secrets.sh          # 扫 staged 改动(默认,提交前用)
#   bash scripts/check_secrets.sh --all    # 扫整个工作区
#   bash scripts/check_secrets.sh --diff origin/main...HEAD
#                                          # 扫某范围里的新增行(CI 用;**三点**范围)
#   bash scripts/check_secrets.sh --selftest [N]
#                                          # 自测**这道门本身**(默认连跑 20 次;⛔ 不扫任何内容)
#                                          # 退出码:0=每次都抓住 · 1=**有漏报**(门现在是硬币) · 2=用法错
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-staged}"
DIFF_RANGE="${2:-}"       # 仅 --diff 模式用;缺了 ⇒ 用法错误(exit 2),见下
ENV_FILE="$REPO_ROOT/.env"
DENYLIST="$REPO_ROOT/.secret-denylist"

# ---- ③ 通用模式:不需要知道具体值 -------------------------------------------
# ⚠️ 本数组定义在【全部调用点之前】—— ③-0 自证与 `--selftest` 都要拿它当唯一真值。
declare -a PATTERNS=(
    'sk-[A-Za-z0-9]{16,}'                  # OpenAI/DashScope 风格
    'ghp_[A-Za-z0-9]{20,}'                 # GitHub PAT
    'gho_[A-Za-z0-9]{20,}'                 # GitHub OAuth
    'AKIA[0-9A-Z]{16}'                     # AWS Access Key ID
    'BEGIN [A-Z ]*PRIVATE KEY'             # PEM 私钥
    'eyJhbGciOi[A-Za-z0-9_-]{10,}'         # JWT(裸的,不带 Bearer 前缀时也算)
)

# ---- ③-1 合成样本表:第 k 项 = 【能且只能】被 PATTERNS[k] 抓住的串 ------------
# ⛔ **一个字面量都不许写成真的"密钥样子"** —— 写成真的，**本文件自己就会命中自己的模式**
#    （门自噬：提交这个脚本时报红）。⇒ 一律**运行时拼接**。
declare -a CANARY_SAMPLES=(
    "sk-$(printf 'D%.0s' {1..20})CANARY"
    "ghp_$(printf 'B%.0s' {1..24})CANARY"
    "gho_$(printf 'B%.0s' {1..24})CANARY"
    "AKIA$(printf 'A%.0s' {1..16})"
    "BEGIN $(printf 'RSA') PRIVATE KEY"
    "eyJhbGciOi$(printf 'C%.0s' {1..16})CANARY"
)

# 🔴 两表必须**一一对应** —— 加了新模式却没加对应样本 ⇒ 自测只测了前一半，
#    而"只测一半的自测"与"没有自测"在机器痕迹上一样（本仓 `DEC-061`）。
if [ "${#PATTERNS[@]}" -ne "${#CANARY_SAMPLES[@]}" ]; then
    echo "⛔ 凭据门: **自测表与模式表不对齐** —— ${#PATTERNS[@]} 个模式 vs ${#CANARY_SAMPLES[@]} 个合成样本"
    echo "   ⇒ 【不得当作通过】。加模式时**必须同时加**一个能被它抓住的合成样本。"
    exit 2
fi

# ---- 判定用的唯一实现（⛔ 全文件只有这一份）----------------------------------
# ⚠️ 为什么抽成函数：**`--selftest` 验的必须是【生产用的那一行】,不是一份复制品。**
#    复制一份去测 = "用硬币验硬币" —— 生产那行改坏了,自测照样绿。
# 🔴 里面**不许用 `grep -q`**（v3→v4 那个坑,见文件头修订史）:
#    `-q` 命中即退出 ⇒ 上游 `printf` 收到 SIGPIPE(141) ⇒ `pipefail` 把**整条管道**判成失败
#    ⇒ 真实命中被**静默丢弃**。⚠️ 它是**概率性**的（实测:连跑 20 次,拦 11 次、漏 9 次）。
#    ⇒ `>/dev/null`（读完再判断,不早退）。📌 判据 = `--selftest`。
match_re()  { grep -E -- "$1" >/dev/null; }   # stdin=被扫文本 · $1=ERE
match_lit() { grep -F -- "$1" >/dev/null; }   # stdin=被扫文本 · $1=字面量

# ---- `--selftest`：合成凭据**连跑 N 次**，任一次漏报即 exit 1 ------------------
# 📄 出处：`docs/复盘/2026-09-17-一道硬币做的门.md` · 待办总表 §五·5。
# 它回答的是「**这道门现在还抓得住吗**」，⛔ 不是"这次抓到没有"——
# 两者被混为一谈时,门可以整体失灵而每次都报 ✅。
if [ "$MODE" = "--selftest" ]; then
    N="${2:-20}"
    case "$N" in ''|*[!0-9]*) echo "⛔ 凭据门 --selftest: 次数必须是正整数(收到 '$N')"; exit 2 ;; esac
    [ "$N" -ge 1 ] || { echo "⛔ 凭据门 --selftest: 次数必须 ≥1"; exit 2; }

    # 🔴 载荷必须**远大于管道缓冲区**，且**金丝雀在前、后面还压着一大堆** ——
    #    这是 v4 那个竞态的**唯一复现条件**：命中后 `grep -q` 早退，而生产者还没写完 ⇒ SIGPIPE。
    #    ⛔ **别把它改小**：小样本上生产者早写完了，**那种自测永远绿**（= 测不出"不成立"，`DEC-061`）。
    #
    # ⚠️ **生产者用 `cat <文件>`，⛔ 不是 `printf '%s' "$BIG"`** —— 实测（2026-10-05，本机）:
    #    bash 的 **内建 printf** 写 1 MiB 要 **759 ms**（写小片、走内建路径）,
    #    而 `cat` 一个同样大的文件只要 **~5 ms** ⇒ 20 次 × 6 模式的差距是 **91s vs 0.6s**。
    #    ⚠️ 更要紧的是**忠实度**:v4 那次的生产者（`git diff`）是**外部命令**,
    #    `cat` 同样会在管道破裂时被信号打死 ⇒ **竞态照样复现**（下面的变异自证验的就是这条）。
    SELFTEST_TMP="$(mktemp -d)"
    trap 'rm -rf "$SELFTEST_TMP"' EXIT
    FILLER_FILE="$SELFTEST_TMP/filler"
    # ⚠️ 256 KiB —— **不是随手取的数**：它必须 > 管道缓冲区（macOS 16 KiB / Linux 64 KiB），
    #    否则 `cat` 一次 write() 就把整个样本灌进缓冲区、**根本不会阻塞** ⇒ 竞态不复现
    #    ⇒ 自测变成"永远绿"。256 KiB 对 Linux 那个 64 KiB 还有 4 倍余量。
    #    实测代价（本机）：20 次 × 6 模式 = **2.9s**；1 MiB 则要 10.4s（余量换不来收益）。
    yes x | head -c 262144 > "$FILLER_FILE"
    for k in "${!PATTERNS[@]}"; do
        printf '%s' "${CANARY_SAMPLES[$k]}" >  "$SELFTEST_TMP/sample.$k"
        cat "$FILLER_FILE"                >> "$SELFTEST_TMP/sample.$k"
    done
    echo "凭据门 · --selftest：${#PATTERNS[@]} 个模式 × 连跑 ${N} 次（每次载荷 $(( $(wc -c < "$SELFTEST_TMP/sample.0") )) 字节）"

    MISS=0
    for i in $(seq 1 "$N"); do
        for k in "${!PATTERNS[@]}"; do
            # ⚠️ 判定走的就是生产那一份 `match_re`（⛔ 不是复制出来的另一份）。
            if ! cat "$SELFTEST_TMP/sample.$k" | match_re "${PATTERNS[$k]}"; then
                MISS=$((MISS+1))
                echo "  ❌ 第 $i 次：模式 ${PATTERNS[$k]} **没抓住**它的合成样本（漏报）"
            fi
        done
    done
    rm -rf "$SELFTEST_TMP"; trap - EXIT

    if [ "$MISS" -ne 0 ]; then
        echo "⛔ 凭据门 · --selftest 未通过：${MISS} 次漏报。"
        echo "   ⇒ **这道门现在是硬币** —— 它报的「没命中」不能采信。"
        echo "   📄 docs/复盘/2026-09-17-一道硬币做的门.md"
        exit 1
    fi
    echo "✅ 凭据门 · --selftest 通过：每次、每个模式都抓住了合成样本（0 漏报）"
    exit 0
fi


# 取本次要扫的文本。
# ⚠️ 只扫【新增行】 —— 泄漏只可能发生在"写进去"的时候。
#    v1 曾扫整份 diff,结果:**我删掉一个存量凭据字面量时,门报了红** ——
#    因为它连 `-` 删除行一起扫了。**删掉密钥是好事,不该拦。**
#    (这个缺陷是门第一次真上岗时抓到的,已修。)
#
# 🔴 2026-09-20(v4→v5) **取 SCAN_TEXT 必须单独拿【生产者自己的退出码】**。
#    此前写成 `$(git diff … 2>/dev/null | grep … || true)` —— `2>/dev/null` 吞掉错误、
#    `|| true` 抹平退出码 ⇒ **「git diff 失败」与「产出为空」压成同一个结果**
#    ⇒ **扫描压根没跑，门照样绿**。形式化:门从 `通过 ⇐ 执行 ∧ ¬命中`
#    **退化成** `通过 ⇐ ¬命中`。（复盘见 docs/复盘/2026-09-20-查不到不等于不存在.md）
#    ⛔ **不许拿【管道状态】判成败** —— 脚本是 `set -uo pipefail`，而暂存区只有
#       删除行/重命名(无 `+` 行)时 `git diff` 成功、两个 `grep` 均返回 1 ⇒ 管道状态 = 1
#       ⇒ **合法空集会被误判成"没执行"**。（这正是 v1→v2 记过的同一个坑。）
if [ "$MODE" = "--all" ]; then
    ALL_OUT="$(git grep -h -I -e '' -- .)"
    ALL_RC=$?
    # git grep 的语义: 0=有匹配 · 1=无匹配(**合法的空**) · ≥2=出错
    if [ "$ALL_RC" -ge 2 ]; then
        echo "⛔ 凭据门: **扫描没有执行** —— git grep 失败(exit $ALL_RC)"
        echo "   ⇒ 【不得当作通过】。⚠️ 这不是'扫过了没命中',是'压根没扫成'。"
        exit 2
    fi
    SCAN_TEXT="$ALL_OUT"
    echo "[凭据门] 扫描范围: 整个工作区(全部内容)"
elif [ "$MODE" = "--diff" ]; then
    # 🔴 CI 走的一支(2026-10-05 加,`DEC-076`)。范围语法 **<base>...<head>(三点)**。
    #    · `git diff A...B` 的基取 merge-base(A,B) ⇒ 只含"本分支相对分叉点引入的改动"。
    #    · ⛔ 两点 `A..B`:在 git diff 里等价于 `git diff A B` = 端点对端点 ——
    #      主干自己前进的那部分会混成"删除行",语义就不是"本 PR 的新增行"了。
    #    · ⛔ 基提交取不到(浅克隆 / 范围写错)时 git diff 会失败 ⇒ 下面 exit 2(**响亮的红**)。
    #      这正是要的:**不许把"没扫成"静默压成"空 diff = 通过"**(v4→v5 的同一条教训)。
    if [ -z "$DIFF_RANGE" ]; then
        echo "⛔ 凭据门: **用法错误** —— --diff 需要一个范围参数(例:--diff origin/main...HEAD)"
        echo "   ⇒ 【不得当作通过】。"
        exit 2
    fi
    DIFF_OUT="$(git diff "$DIFF_RANGE" -U0)"
    DIFF_RC=$?
    if [ "$DIFF_RC" -ne 0 ]; then
        echo "⛔ 凭据门: **扫描没有执行** —— git diff $DIFF_RANGE 失败(exit $DIFF_RC)"
        echo "   ⇒ 【不得当作通过】。⚠️ 常见原因:范围写错 / 浅克隆里取不到基提交。"
        exit 2
    fi
    SCAN_TEXT="$(printf '%s' "$DIFF_OUT" | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
    echo "[凭据门] 扫描范围: $DIFF_RANGE 的【新增行】(git diff <range> | grep '^+')"
else
    DIFF_OUT="$(git diff --cached -U0)"
    DIFF_RC=$?
    if [ "$DIFF_RC" -ne 0 ]; then
        echo "⛔ 凭据门: **扫描没有执行** —— git diff 读取暂存区失败(exit $DIFF_RC)"
        echo "   ⇒ 【不得当作通过】。⚠️ 这不是'暂存区为空'。"
        exit 2
    fi
    # 走到这里才允许出现"空集":git diff 已被确认成功,空就是**真的**空。
    # （下面的 `|| true` 是安全的 —— 它只吸收"grep 无匹配(exit 1)";
    #   生产者失败已在上面拦掉了,不会漏到这里。）
    SCAN_TEXT="$(printf '%s' "$DIFF_OUT" | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
    echo "[凭据门] 扫描范围: staged 的【新增行】(git diff --cached | grep '^+')"
fi

# ---- ③-0 自证(positive control) ---------------------------------------------
# 🔴 2026-09-20 加。**判据能说"没查到"的前提,是它抓得住已知该命中的东西。**
#    对**每一个**模式,喂它【自己的】合成样本(运行时拼接,见 ③-1),断言抓得住。
#    ⛔ 样本写成字面量的话,**本文件自己就会命中自己的模式**(门自噬)。
#    形式化:本段提供 `通过 ⇐ 执行 ∧ ¬命中` 里「**匹配机制确实在工作**」那一半的证据。
#    ⚠️ 它必须跑在下面"空集即 exit 0"**之前** —— 否则暂存区为空时根本走不到这里。
# 📌 与 `--selftest` 的分工:**同一张样本表、同一套 `match_*` 实现** ——
#    本段是「每次跑一遍」（快,挡"机制整体失灵"）;
#    `--selftest` 是「N 次 × 大载荷」（专抓 v4 那种**概率性**漏报）。缺一不可。
CANARY_HIT=1
for k in "${!PATTERNS[@]}"; do
    if ! printf '%s' "${CANARY_SAMPLES[$k]}" | match_re "${PATTERNS[$k]}"; then
        CANARY_HIT=0
        echo "  ❌ 自证失败:模式 ${PATTERNS[$k]} 没抓住它的合成样本"
    fi
done
if [ "$CANARY_HIT" -ne 1 ]; then
    echo "⛔ 凭据门: **自证失败** —— 已知该命中的合成样本没被抓住。"
    echo "   ⇒ **模式匹配机制本身失灵,本次'没命中'不能采信。**"
    exit 2
fi
echo "  · 自证通过(${#PATTERNS[@]} 个模式各自抓住了自己的合成样本;样本非真实凭据)"

# ⚠️ 此处的"空"与上面的"失败"是两回事 —— 前者是【已确认执行且确实为空】。
if [ -z "$SCAN_TEXT" ]; then
    if [ "$MODE" = "--all" ]; then
        echo "[凭据门] 工作区没有可扫内容 —— **扫过了,确实为空**。"
    elif [ "$MODE" = "--diff" ]; then
        # ⚠️ 范围里只有删除行是【好事】(删密钥不该拦,v1→v2 的教训);
        #    但必须说清"git diff 确已成功执行",别让它与"没扫成"混为一谈。
        echo "[凭据门] 范围 $DIFF_RANGE 没有新增行(或全是删除行) —— **git diff 已确认执行成功($DIFF_RANGE)**,确实没有要扫的内容。"
    else
        echo "[凭据门] staged 区为空(或全是删除行/重命名) —— **git diff 已确认执行成功**,确实没有要提交的内容。"
    fi
    exit 0
fi

HITS=0
FAILED_NAMES=()
COVERAGE_PARTIAL=0     # 1 = 有节点未执行(仅允许在显式降级时置位；见 ① 段)
# 🔴 2026-10-05 加(`DEC-076`):**覆盖度必须按【实际执行了哪几节】拼,⛔ 不许写死**。
#    前科:结论行写死「覆盖 ①②③」,而没有 .secret-denylist 时 ② 整节没跑 ——
#    实测输出与"三节全跑了"不可区分。⚠️ 而 **CI 恰恰就是"没有 denylist"的那个环境**
#    (`.secret-denylist` 与 `.env` 一样被 gitignore)⇒ 那句话会在 CI 里变成谎话。
#    📌 与 v5→v6 同一条教训:修"某条路径"时要问「同一个形状还有别的入口吗」——
#       这次是"**没跑的那一节也被算进覆盖里**"。
COV_ENV=0              # 1 = ① 真实凭据那一节确实执行了
COV_DENY=0             # 1 = ② 存量黑名单那一节确实执行了

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
    COV_ENV=1          # 本节确实执行了 —— 覆盖度按事实记,见结论段
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
        if printf '%s' "$SCAN_TEXT" | match_lit "$val"; then
            echo "  ❌ 命中: .env 中的 $key"
            HITS=$((HITS+1)); FAILED_NAMES+=("$key")
        fi
    done < <(grep -E '^[A-Z_][A-Z0-9_]*=' "$ENV_FILE" 2>/dev/null)
    echo "  · 已跳过 ${#SKIPPED_KEYS[@]} 个【非机密键】($NON_SECRET_KEY_RE):"
    echo "      ${SKIPPED_KEYS[*]:-无}"
else
    # 🔴 2026-09-20(v5→v6) **本节未执行 ⇒ 不得当作通过**。
    #    v5 只堵了"SCAN_TEXT 生产者失败"那一条【未执行】路径,却漏了这里:
    #    没有 .env 时本节整段不跑,门仍打印【无限定语】的 `✅ 通过 —— 0 命中` + exit 0
    #    —— 与 v4 的缺陷**是同一个形状**,只是换了一条路径。
    #    ⚠️ 实测(仓根无 .env 无 .secret-denylist):三节里两节没跑,输出与"全跑了没命中"不可区分。
    echo "  ⚠️ 未找到 .env —— **真实凭据检查(本门最关键的一节)没有执行**"
    if [ "${SECRETS_GATE_ALLOW_NO_ENV:-0}" = "1" ]; then
        echo "     · 已按 SECRETS_GATE_ALLOW_NO_ENV=1 降级为【部分覆盖】—— 结论行会注明"
        COVERAGE_PARTIAL=1
    else
        echo "⛔ 凭据门: **扫描未完整执行** —— 没有 .env,无法核对本仓的真实凭据有没有泄漏"
        # ⚠️ 判据里**不许用 ASCII 反引号** —— 双引号内它会被当【命令替换】执行,
        #    实测打出 `通过: command not found` 且那段文字被换成空(2026-10-01 修)。
        #    正是本仓复盘第 6 条那个形状:命令里写中文,用「」不用反引号。
        echo "   ⇒ 【不得当作通过】(判据是「通过 ⇐ 执行 ∧ ¬命中」;本节点未执行 ⇒ 不成立)"
        echo "   处置:① 到含 .env 的工作副本上跑(正常情况);"
        echo "         ② 若确属新鲜克隆、只想跑通用模式 ⇒ 显式设 SECRETS_GATE_ALLOW_NO_ENV=1,"
        echo "            结论会标注为【部分覆盖】,不会被误读成'全查过了'。"
        exit 2
    fi
fi

# ---- ② 存量黑名单:历次已泄漏/已作废的字面量 --------------------------------
# ⚠️ 该文件**必须**在 .gitignore 里 —— 它装的是"绝不能再进仓库"的值本身
if [ -f "$DENYLIST" ]; then
    COV_DENY=1         # 本节确实执行了 —— 覆盖度按事实记,见结论段
    while IFS= read -r lit; do
        case "$lit" in ''|\#*) continue ;; esac
        # ⚠️ 同样**不许用 `grep -q`**（理由见第 ① 段那处注释）
        if printf '%s' "$SCAN_TEXT" | match_lit "$lit"; then
            echo "  ❌ 命中: .secret-denylist 中的某个存量字面量(第 $(grep -nF -- "$lit" "$DENYLIST" | head -1 | cut -d: -f1) 行)"
            HITS=$((HITS+1)); FAILED_NAMES+=("denylist")
        fi
    done < "$DENYLIST"
else
    echo "  · 未找到 .secret-denylist —— 跳过存量字面量检查(可选文件)"
fi

# ---- ③ 通用模式:不需要知道具体值 -------------------------------------------
# ⚠️ PATTERNS 数组已上移到文件前部(在「自证」之前)——
#    自证必须先于"空集即 exit 0"执行,否则暂存区为空时根本走不到自证。
for p in "${PATTERNS[@]}"; do
    # ⚠️ 同样**不许用 `grep -q`**（理由见第 ① 段那处注释）
    if printf '%s' "$SCAN_TEXT" | match_re "$p"; then
        echo "  ❌ 命中通用模式: $p"
        HITS=$((HITS+1)); FAILED_NAMES+=("pattern:$p")
    fi
done

# ---- ④ 结论 -----------------------------------------------------------------
echo ""
# 🔴 覆盖度**按实际执行拼**（③ 是必跑的真值,①② 看本节有没有跑）。⛔ 不许写死。
COVERED=""
if [ "$COV_ENV" -eq 1 ]; then COVERED="${COVERED}①"; fi
if [ "$COV_DENY" -eq 1 ]; then COVERED="${COVERED}②"; fi
COVERED="${COVERED}③"
# ⚠️ 结论必须带【覆盖度】—— 否则"三节跑了两节"与"三节全跑了"在输出上不可区分。
if [ "$COVERAGE_PARTIAL" -eq 1 ]; then
    echo "⚠️ 覆盖度: ① 未执行(无 .env) —— 本次结果**仅覆盖 ${COVERED}**"
fi
if [ "$HITS" -gt 0 ]; then
    echo "⛔ 凭据门: 未通过 —— $HITS 处命中: ${FAILED_NAMES[*]}"
    echo "   ⚠️ 命中项已【不打印值】(那会让这份日志本身变成泄漏源)"
    echo "   ⇒ 请先脱敏再提交。规则:报告扫描结果【只写名字,不写值】。"
    exit 1
fi
if [ "$COVERAGE_PARTIAL" -eq 1 ]; then
    # ⚠️ 只有【显式降级】才走到这里;把"部分"两个字写在结论行上,不许省。
    echo "⚠️ 凭据门: 通过 (**部分覆盖** —— 真实凭据未检查,实际只覆盖 ${COVERED})"
    echo "   ⇒ 「通过 ⇐ 执行 ∧ ¬命中」**未完全成立**;这是你显式设了 SECRETS_GATE_ALLOW_NO_ENV=1 的结果。"
    exit 0
fi
echo "✅ 凭据门: 通过 —— 0 命中(覆盖 ${COVERED})"
exit 0
