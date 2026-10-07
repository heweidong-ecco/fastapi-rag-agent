#!/usr/bin/env bash
#
# check_lint_baseline.sh —— 静态检查（ruff）的 **基线棘轮门**
#
# ## 它治什么病
#
# 本仓**从来没有 lint 门**（`docs/规范/开发规范.md:10-11` 原文：「本仓【没有 linter】」）
# ⇒ **攒出了 100+ 条未使用导入**，而且**没人知道什么时候多出来的**。
# 这正是本仓那句老话：**「门挂在别处，就等于没有门」**。
#
# ## 为什么是「棘轮」而不是「全绿」
#
# 存量认了（业务方 2026-10-04 裁 T6「**先挂起**」），但**不许再变多**。
# 直接开 `F401` 接 CI ⇒ **立刻红 101 条**，等于没接。
#
# ## 🔴 判据是【集合】，⛔ 不是【计数】
#
# 基线存的是 **`<文件>\t<规则号>` 的集合**，不是 `F401 = 101` 这样一个数。
# **为什么**：计数量不到"**这里修掉一条、那里新增一条**" —— 总数不变 ⇒ 门绿 ⇒
# **而它本该拦的那件事恰好发生了**。
# 本仓 `docs/复盘/2026-10-05-拿代理量当判据.md` 记的正是这个病：
# **「把结论取反，这条命令的输出会变吗？」** —— 用计数，答案是**不会**。
#
# ⛔ **所以别"简化"成 `wc -l` 比个数。**
#
# ⚠️ **键取 `(文件, 规则)`，⛔ 不带行号** —— 带行号的话，随便改一行代码
#    （下面的行整体下移）就会打出一堆"新条目"，那是噪声，不是回归。
#
# ## 用法
#
# ```bash
# bash scripts/check_lint_baseline.sh                  # 和基线比，出现新条目 ⇒ exit 1
# bash scripts/check_lint_baseline.sh --write-baseline  # 把当前结果写成新基线
# ```
#
# ⚠️ **它跑的是【工作区】，不是 staged** —— 与第 ⑤ 道门（路由鉴权）同口径
#    （那道门也是 import 磁盘上的 `main`）。⇒ **提交前先存盘。**
#
# ⚠️ **基线记了 ruff 版本**，版本对不上 ⇒ 直接红。
#    **为什么**：`F401` 这类规则集**各版本并不相同**（新增/合并规则会改判定）
#    ⇒ 换版本后基线会**静默失真**（要么假红一片，要么该拦的不拦）。
#    ⇒ 升级 ruff 时**必须**重跑 `--write-baseline`，并**逐条看一眼变了什么**。
#
# ⚠️ **没装 ruff 时【放行 + 大声警告】，⛔ 不是静默通过** ——
#    本地 hook 那条规矩是「门跑不起来时不阻止」（否则 hook 坏了会把人锁死）。
#    **真正的兜底在 CI**：`.github/workflows/ci.yml` 的 `syntax` job 里
#    `pip install ruff==<钉住的版本>` 之后无条件跑本脚本 ⇒ 那边 ruff 缺了会真红。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ⚠️ 两个 env 覆盖点**只给 `--self-test` 用**（它要拿假的 ruff 和假的基线跑真流程）。
#    ⛔ 日常别设 —— 设了就等于绕过门。
BASELINE="${LINT_BASELINE:-${REPO}/scripts/ruff-baseline.txt}"
cd "${REPO}" || exit 0

# ── 找 ruff：仓里的 venv 优先（版本与写基线时一致的概率最高）──
RUFF="${RUFF_BIN:-}"
if [ -z "${RUFF}" ]; then
    for cand in "${REPO}/venv/bin/ruff" "${REPO}/venv/Scripts/ruff.exe"; do
        if [ -x "${cand}" ]; then RUFF="${cand}"; break; fi
    done
fi
if [ -z "${RUFF}" ] && command -v ruff >/dev/null 2>&1; then RUFF="$(command -v ruff)"; fi

# 🔴 **退出码 3 = 「本门没跑」**（环境缺件），与「跑过且通过（0）」「跑过且不通过（1）」是**三件事**。
#    为什么要单开一个码：本地 hook 只读退出码 ⇒ 若这里 exit 0，汇总行会打
#    **`静态检查门 ✅`** —— ⛔ **那是假的**，与"跑了、真没有新条目"在机器痕迹上一模一样
#    （本仓原话：「**『从不命中』与『没人违规』在机器痕迹上完全一样**」）。
#    ⇒ 本地：hook 把它标 **⏭ 未跑**（不锁死人，同「四条克制」②）；
#      CI ：**任何非 0 都算失败** ⇒ 缺件在那里会**真红** ⇒ 兜底成立。
EXIT_NOTRUN=3

if [ -z "${RUFF}" ]; then
    echo "⚠️ 静态检查门【未跑】（按「未跑」计，⛔ 不是通过）—— 找不到 ruff。" >&2
    echo "   它既不在 venv/bin/ 里，也不在 PATH 上。" >&2
    echo "   装法：venv/bin/pip install ruff    （⛔ 别写进 api/requirements.txt，那会进 demo 镜像）" >&2
    echo "   本地会把它标成 ⏭；CI 的 syntax job 会装上它并把它跑成真判据。" >&2
    exit "${EXIT_NOTRUN}"
fi

# ────────────────────────────────────────────────────────────────────────────
# `--self-test` —— **验这道门自己会不会红**（本仓已记两次的教训：`DEC-061`/`DEC-066`
# 「写了守卫 ≠ 守卫有效」）。它拿**假 ruff + 假基线**跑**真流程**，逐个分支验退出码。
# CI 的 `syntax` job 无条件跑它（与 `check_remote_sync.sh --self-test` 同款做法）。
# ────────────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--self-test" ]; then
    TMPD="$(mktemp -d)"; trap 'rm -rf "${TMPD}"' EXIT
    # 假 ruff：`--version` 回 FAKE_VER；其余情况原样吐 FAKE_OUT。
    # ⚠️ heredoc **必须带引号**（`<<'SHIM'`）—— 不加引号的话，反引号会被**真的执行**
    #    （本仓 2026-10-05 一天栽两次，见 memory「backtick-in-unquoted-heredoc-executes」）。
    cat > "${TMPD}/ruff" <<'SHIM'
#!/usr/bin/env bash
for a in "$@"; do
    if [ "$a" = "--version" ]; then echo "ruff ${FAKE_VER}"; exit 0; fi
done
cat "${FAKE_OUT}"
exit "${FAKE_RC:-0}"
SHIM
    chmod +x "${TMPD}/ruff"

    printf 'api/a.py:1:1: F401 [*] unused\napi/a.py:9:1: F401 [*] unused\napi/b.py:3:2: F541 [*] f-string\n' > "${TMPD}/out.base"
    printf 'api/a.py:1:1: F401 [*] unused\napi/a.py:9:1: F401 [*] unused\napi/b.py:3:2: F541 [*] f-string\napi/c.py:5:5: F401 [*] unused\n' > "${TMPD}/out.extra"
    # 🔴 这一对是**本门存在的理由**：组数都是 1，**只是文件换了** ⇒ 计数法判绿、集合法判红。
    printf 'api/d.py:1:1: F401 [*] unused\n' > "${TMPD}/out.swap"
    printf '# ruff %s\napi/a.py\tF401\n' "0.16.10" > "${TMPD}/base.swap"

    printf '# ruff %s\napi/a.py\tF401\napi/b.py\tF541\n' "0.16.10" > "${TMPD}/base.ok"
    printf '# ruff %s\napi/a.py\tF401\napi/b.py\tF541\n' "9.9.9"  > "${TMPD}/base.oldver"

    run_case() {  # $1=名字 $2=期望退出码 $3=FAKE_OUT $4=BASELINE [$5=FAKE_RC]
        local got
        RUFF_BIN="${TMPD}/ruff" LINT_BASELINE="$4" FAKE_OUT="$3" FAKE_VER="0.16.10" \
            FAKE_RC="${5:-0}" bash "${BASH_SOURCE[0]}" >/dev/null 2>&1
        got=$?
        if [ "${got}" -eq "$2" ]; then
            printf '  ✅ %-42s 退出码 %s（期望 %s）\n' "$1" "${got}" "$2"
            return 0
        fi
        printf '  🔴 %-42s 退出码 %s（期望 %s）\n' "$1" "${got}" "$2"
        return 1
    }

    printf '静态检查门自测（拿假 ruff + 假基线跑【真流程】）：\n'
    rc=0
    run_case "① 清单一致 ⇒ 绿【①是②的反证】"        0 "${TMPD}/out.base"  "${TMPD}/base.ok"     || rc=1
    run_case "② 多出一组 ⇒ 红"                        1 "${TMPD}/out.extra" "${TMPD}/base.ok"     || rc=1
    run_case "③ 组数不变、只换了文件 ⇒ 红"            1 "${TMPD}/out.swap"  "${TMPD}/base.swap"   || rc=1
    run_case "④ ruff 版本对不上 ⇒ 红"                 1 "${TMPD}/out.base"  "${TMPD}/base.oldver" || rc=1
    run_case "⑤ ruff 自己出错(rc=2) ⇒ 未跑(⛔不是绿)"  3 "${TMPD}/out.base"  "${TMPD}/base.ok"     "2" || rc=1
    run_case "⑥ 基线文件不存在 ⇒ 未跑(⛔不是绿)"       3 "${TMPD}/out.base"  "${TMPD}/nope"        || rc=1

    if [ "${rc}" -eq 0 ]; then
        printf '✅ 自测通过（6/6）—— 这道门【会红】，且 ③ 证明它量的是【集合】不是【计数】。\n'
    else
        printf '🔴 自测未通过 —— 这道门此刻不可信，⛔ 别信它的绿灯。\n' >&2
    fi
    exit "${rc}"
fi

RUFF_VER="$("${RUFF}" --version 2>/dev/null | awk '{print $2}')"

# ── 跑【一次】ruff，落成原始输出；后面两份统计都从它派生 ──
# `--output-format concise` ⇒ `路径:行:列: RULE [*] 说明`
#
# 🔴 **必须看退出码**（2026-10-07 自己审出来的一个洞）：
#    ruff 的退出码 **0 = 没违规 · 1 = 有违规 · 2 = 它自己出错了**（配置坏 / 参数错）。
#    原先写法是 `ruff ... 2>/dev/null | sed ...` —— **只看管道输出、不看退出码**
#    ⇒ ruff 报 2 时输出为空 ⇒ 集合为空 ⇒ 打 **`✅ 通过`**
#    ⇒ **一声不响地假通过**，正是本仓栽过多次的那一类。
#    ⇒ 现在 `2|其它` 一律按「**未跑**」计（exit 3），⛔ 不按"通过"算。
RUFF_OUT="$(mktemp)"
trap 'rm -f "${RUFF_OUT}"' EXIT
"${RUFF}" check . --output-format concise > "${RUFF_OUT}" 2>/dev/null
RUFF_RC=$?
if [ "${RUFF_RC}" -ne 0 ] && [ "${RUFF_RC}" -ne 1 ]; then
    echo "⚠️ 静态检查门【未跑】（按「未跑」计，⛔ 不是通过）—— ruff 自己出错，退出码 ${RUFF_RC}。" >&2
    echo "   （0 = 没违规 · 1 = 有违规 · 2 = **ruff 出错**：配置坏 / 参数错 / `ruff.toml` 读不了）" >&2
    echo "   ⇒ 手工复现：${RUFF} check ." >&2
    exit "${EXIT_NOTRUN}"
fi

# ── 从原始输出派生两份统计 ──
# 只取「路径」和「RULE」，丢掉行列（见文件头上那条：带行号会打出一片噪声）
collect() {
    sed -n 's/^\([^:]*\):[0-9][0-9]*:[0-9][0-9]*: \([A-Z][0-9][0-9]*\).*/\1\t\2/p' "${RUFF_OUT}" \
        | LC_ALL=C sort -u
}

# ⚠️ 两个量必须分开报，⛔ 别混：
#   · 唯一「文件×规则」组数 —— **门判的就是这个**
#   · 违规总行数           —— 给人看的规模
# 2026-10-07 实测：**40 组 / 103 行**（38 个文件有 F401、2 个文件有 F541，很多文件里同一条规则命中多行）
# ⇒ 光看"103"会以为门在数 103 个东西 ⇒ **那是另一个口径**。
collect_raw_count() {
    grep -c '^[^:]*:[0-9][0-9]*:[0-9][0-9]*: [A-Z][0-9][0-9]*' "${RUFF_OUT}" || true
}

if [ "${1:-}" = "--write-baseline" ]; then
    {
        echo "# 静态检查基线（scripts/check_lint_baseline.sh --write-baseline 生成）"
        echo "# 格式：<仓内相对路径>\t<ruff 规则号>   —— 🔴 是【集合】，⛔ 不是计数（原因见脚本头）"
        echo "# ruff ${RUFF_VER}"
        collect
    } > "${BASELINE}"
    printf '✅ 基线已写入 %s\n' "scripts/ruff-baseline.txt"
    printf '   ruff %s · 共 %s 条 · 按规则数：\n' "${RUFF_VER}" "$(grep -vc '^#' "${BASELINE}")"
    grep -v '^#' "${BASELINE}" | cut -f2 | LC_ALL=C sort | uniq -c | LC_ALL=C sort -rn | sed 's/^/     /'
    exit 0
fi

# ── 比 ──
if [ ! -f "${BASELINE}" ]; then
    echo "⚠️ 静态检查门【未跑】（按「未跑」计，⛔ 不是通过）—— 基线文件不存在：${BASELINE}" >&2
    echo "   ⇒ 先跑：bash scripts/check_lint_baseline.sh --write-baseline" >&2
    echo "   🔴 **为什么这不算通过**：基线是棘轮的「齿」，没了它这道门就【什么都没有在拦】；" >&2
    echo "      而「什么都没拦」和「没有违规」在机器痕迹上完全一样。" >&2
    exit "${EXIT_NOTRUN}"
fi

BASE_VER="$(sed -n 's/^# ruff //p' "${BASELINE}" | head -1)"
if [ -n "${BASE_VER}" ] && [ "${BASE_VER}" != "${RUFF_VER}" ]; then
    echo "🔴 静态检查门**未通过** —— ruff 版本和基线不一致。" >&2
    echo "   基线记的是 ${BASE_VER}，当前跑的是 ${RUFF_VER}。" >&2
    echo "   ⇒ 规则集在不同版本间会变 ⇒ **基线此刻不可信**（可能假红一片，也可能该拦的不拦）。" >&2
    echo "   ⇒ 要么装回 ${BASE_VER}，要么重写基线并**逐条看一眼变了什么**：" >&2
    echo "        bash scripts/check_lint_baseline.sh --write-baseline && git diff scripts/ruff-baseline.txt" >&2
    exit 1
fi

CUR="$(mktemp)"
BASE="$(mktemp)"
# ⚠️ 这里**必须把 RUFF_OUT 也带上** —— `trap ... EXIT` 是**覆盖**不是追加，
#    漏了它 RUFF_OUT 那份临时文件就永远留在 /tmp（同一族：见 memory「临时文件 + trap」）。
trap 'rm -f "${CUR}" "${BASE}" "${RUFF_OUT}"' EXIT

collect > "${CUR}"
grep -v '^#' "${BASELINE}" | grep -v '^[[:space:]]*$' | LC_ALL=C sort -u > "${BASE}"

NEW="$(comm -13 "${BASE}" "${CUR}")"

TOTAL_NOW="$(wc -l < "${CUR}" | tr -d ' ')"
TOTAL_BASE="$(wc -l < "${BASE}" | tr -d ' ')"

if [ -z "${NEW}" ]; then
    printf '✅ 静态检查门通过 —— 唯一（文件×规则）%s 组 · 违规行 %s 条 · 没有新组（基线 %s 组）。\n' \
        "${TOTAL_NOW}" "$(collect_raw_count)" "${TOTAL_BASE}"
    printf '   按规则（组数）：'
    cut -f2 "${CUR}" | LC_ALL=C sort | uniq -c | LC_ALL=C sort -rn | awk '{printf "%s×%s ", $2, $1}'
    printf '\n'
    printf '   ⚠️ 门判的是【组】，⛔ 不是【行数】—— 同一个文件里同一条规则命中多行，只算一组。\n'
    exit 0
fi

echo "🔴 静态检查门**未通过** —— 出现了基线里没有的条目：" >&2
echo "" >&2
while IFS=$'\t' read -r f rule; do
    [ -z "${f}" ] && continue
    echo "   🔴 ${rule}  ${f}" >&2
    # 顺带把 ruff 的原文打出来（含行列），不然还得自己再跑一遍
    "${RUFF}" check "${f}" --output-format concise 2>/dev/null \
        | sed -n 's/^[^:]*:[0-9][0-9]*:[0-9][0-9]*: /        /p' | head -5 >&2
done <<< "${NEW}"
echo "" >&2
echo "   （文件×规则）组数：基线 ${TOTAL_BASE} → 现在 ${TOTAL_NOW}" >&2
echo "   ⇒ 三种处置，⛔ 别直接改基线了事：" >&2
echo "     ① **修掉它**（最常对）—— 未使用导入就删 import；F841 就删那个变量" >&2
echo "     ② 确认它**必须存在**（如框架要求的 import）⇒ 在代码里显式说明，或" >&2
echo "        在 scripts/ruff-baseline.txt 里加一行并**在提交信息里写明理由**" >&2
echo "     ③ 整批重写基线：bash scripts/check_lint_baseline.sh --write-baseline" >&2
echo "        ⚠️ 这条会**一次性把新条目全认下来** ⇒ 只在对着一份 diff 逐条看过之后才用" >&2
exit 1
