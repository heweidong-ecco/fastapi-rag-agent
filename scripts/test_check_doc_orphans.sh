#!/usr/bin/env bash
#
# test_check_doc_orphans.sh —— `check_doc_orphans.sh` 的回归测试（2026-10-05 · 批 4 · `DEC-080`）
#
# ## 为什么有这个文件
#
# 孤儿门一直**没有自测** —— 它本来就是"顺手多查一遍"的那道，没人给它写用例。
# 2026-10-05 批 4 把它**改了**（`DEC-076` §5.2 第 2 / 4 条）：
# 口径从**问磁盘**改成**问 git**（与断链门同构）。
#
# 🔴 **改了却没有用例 ⇒ 下一次谁再把它改回去，没人会发现。**
# 本仓立场：**一条测不出"不成立"的守卫 = 没有守卫**（`DEC-061`）。
#
# ## 钉住的三条不变量
#
#   1. **「算不算数」=【会不会随 clone 一起下来】**（`git ls-files`），⛔ 不是问磁盘
#      ⇒ 未入库的 .md **既不算来源、也不算候选**（T2 / T5）
#   2. **拿不到 git ⇒ exit 2【不得当作通过】** —— ⛔ 不许把"没能判定"压成"没有孤儿"（T4）
#   3. **真孤儿仍然要报**（T3，防"改口径把门改瞎了"）
#
# ⚠️ **外加一条，钉的是夹具自己**（2026-10-05 批 4 加）：**继承来的 `GIT_DIR` 不许污染夹具**（T6）
#    —— 理由见下面 `unset` 那一段：不摘掉它，夹具里的 `git add` 会打到**主检出**上。
#
# ## 为什么要造临时"仓根"
#
# 门把自己所在目录的**上一级**当成仓根（`BASH_SOURCE/..`）。
# 直接在本仓上测 = 拿**真实数据**当夹具 ⇒ 结论随仓里文档增删而漂。
# ⇒ 每例造一个**独立小仓**（同 `test_check_doc_links.sh` 的做法）。
#
# ⚠️ **本文件故意不用 git shim**：要测的**恰恰是"git 说了什么"**，
#    shim 掉 git 等于把被测对象换掉。⇒ 用**真的 `git init` + `git add`**。
#
# ⚠️ **夹具必须"最小自洽"**：门会检查三个【关键入口】互相指向
#    （`docs/文档地图.md` 要 3 个入口里至少 2 个提到；`ROADMAP.md`/`CLAUDE.md` 要有人提）。
#    不自洽 ⇒ 每条用例都因为**入口**而 exit 1，**把要测的那件事淹掉**。
#
# 🔴 2026-10-05 加（批 4 · `DEC-080`）：**先把继承来的 git 定位变量摘掉**。
#
# 本文件用【真 git】造夹具（`git -C <临时仓> init/add`）。
# 而 `GIT_DIR` **一旦被继承就会盖过 `-C`** —— 实测（2026-10-05，本机）：
#
#     export GIT_DIR=<主检出>/.git GIT_WORK_TREE=<主检出>
#     git -C <临时仓> init -q          ⇒ **返回 0，却不建那个仓**（`<临时仓>/.git` 始终没出现）
#     git -C <临时仓> add CLAUDE.md    ⇒ **打到【主检出】上**：实测 `git status --short`
#                                        从 ` M CLAUDE.md`（未暂存）变成 `M  CLAUDE.md`（已暂存）
#
# ⚠️ **这不是假想的场景**：`scripts/ci-local.sh:252` 就是这么 export 的
#    （为了让凭据门的 `git diff` 在"没有 `.git` 的副本"里能跑，见该脚本 §3.5）。
#    一旦本文件被 ci-local 调用，夹具就会打到**真仓**上：
#      · 轻 ⇒ 用例全红（`git ls-files` 答的是主检出 ⇒ 夹具里"一份都没入库"）;
#      · 重 ⇒ **把主检出里未提交的改动悄悄暂存进真索引**（就是上面实测那一行）。
#
# ⇒ 夹具要**自证干净**：摘掉这几个变量，让 `-C` 重新说了算。
# ⛔ **别改到调用方去**（在 ci.yml / ci-local 里写 `env -u GIT_DIR …`）——
#    那样"从别的入口跑"照样中招；**这条知识属于夹具自己，谁跑都得是对的**。
# 📌 判据：本文件的 **T6**（故意把这两个变量指向一个**诱饵仓**，核结论不变）。
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/check_doc_orphans.sh"
[ -f "$GATE" ] || { echo "⛔ 找不到 $GATE" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

make_root() {   # $1=仓根 · $2=是否 git init(yes/no)
    mkdir -p "$1/scripts"
    cp "$GATE" "$1/scripts/check_doc_orphans.sh"
    if [ "$2" = yes ]; then
        git -C "$1" init -q
        # ⚠️ 判据**不是**"`init` 返回了 0"（本仓纪律：拿动作成功当结果正确）——
        #    被继承的 `GIT_DIR` 下，`init` **就是返回 0 却什么都不建**（实测，见文件头）。
        #    ⇒ 必须**去问那个仓真的在了没有**。
        [ -d "$1/.git" ] || { echo "⛔ 夹具仓没建起来：$1/.git 不存在（GIT_DIR 被继承了？）" >&2; exit 2; }
    fi
    return 0
}

# 最小自洽仓：三个关键入口互相指向，且 docs/文档地图.md 有两个入口指向它
base() {        # $1=仓根
    mkdir -p "$1/docs"
    printf '# CLAUDE\n见 `ROADMAP.md` · `docs/文档地图.md`\n' > "$1/CLAUDE.md"
    printf '# ROADMAP\n见 `CLAUDE.md` · `docs/文档地图.md`\n' > "$1/ROADMAP.md"
    printf '# README\n见 `CLAUDE.md`\n'                    > "$1/README.md"
    printf '# 文档地图\n（索引）\n'                        > "$1/docs/文档地图.md"
}

# 调门时**也要**摘掉那几个变量 —— ⛔ 这不是重复劳动，是另一半：
#   · 上面那个 `unset` 管的是【夹具自己的 git 调用】；
#   · 这里管的是【门这个子进程】：它继承环境，而门**必须**能按 `-C`/cwd 发现夹具那个仓。
# 少了这一半 ⇒ 门会去问**别的仓**（实测：T6 就是这么红的 —— 它答的是诱饵仓）。
# 📌 判据 = T6。
run_gate() {    # $1=仓根 ⇒ 打退出码
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
        bash "$1/scripts/check_doc_orphans.sh" >/dev/null 2>&1
    echo $?
}

echo "孤儿门 · 回归测试"
echo "门 = $GATE"
echo

# ------------------- T1 有人指向 ⇒ 不算孤儿（该绿的不红）
R1="$TMP/r1"; make_root "$R1" yes; base "$R1"
mkdir -p "$R1/docs/说明"
printf '# 甲\n' > "$R1/docs/说明/甲.md"
printf '# README\n见 `CLAUDE.md` · `docs/说明/甲.md`\n' > "$R1/README.md"
git -C "$R1" add CLAUDE.md ROADMAP.md README.md docs/
rc=$(run_gate "$R1")
[ "$rc" -eq 0 ] && ok "T1 有人指向 ⇒ exit 0（未矫枉过正）" \
                || bad "T1 有人指向 ⇒ exit ${rc}（应为 0）"

# ------------------- T2 🔴【本轮修的就是这条】未入库的 .md **不算来源**
# 盘上有 `docs/杂.md` 提到了 丙.md，但它**没入库** ⇒ 克隆者拿不到它 ⇒ **等于没人指向**。
# ⛔ 若本条变绿(exit 0)，说明门又在"问磁盘" —— 那就是"本机绿、CI 红"的成因。
R2="$TMP/r2"; make_root "$R2" yes; base "$R2"
mkdir -p "$R2/docs/说明"
printf '# 丙\n' > "$R2/docs/说明/丙.md"
printf '# 杂\n见 `docs/说明/丙.md`\n' > "$R2/docs/杂.md"     # ⚠️ 故意 **不** git add
git -C "$R2" add CLAUDE.md ROADMAP.md README.md docs/文档地图.md docs/说明/丙.md
rc=$(run_gate "$R2")
[ "$rc" -eq 1 ] && ok "T2 只被【未入库】的文档指向 ⇒ exit 1（⛔ 不许算通过）" \
                || bad "T2 只被【未入库】的文档指向 ⇒ exit ${rc}（应为 1；0 = 又在问磁盘）"

# ------------------- T3 真孤儿 ⇒ exit 1（回归：别把门改瞎了）
R3="$TMP/r3"; make_root "$R3" yes; base "$R3"
mkdir -p "$R3/docs/说明"
printf '# 丁\n（没人指向我）\n' > "$R3/docs/说明/丁.md"
git -C "$R3" add CLAUDE.md ROADMAP.md README.md docs/
rc=$(run_gate "$R3")
[ "$rc" -eq 1 ] && ok "T3 真孤儿 ⇒ exit 1" \
                || bad "T3 真孤儿 ⇒ exit ${rc}（应为 1）"

# ------------------- T4 🔴 拿不到 git ⇒ exit 2（⛔ 不许把"没能判定"压成"通过"）
# 没有 .git ⇒ `git ls-files` 失败。这正是 ci-local 那种"复制树但没带 .git"的形状。
# ⚠️ 判据不能只看码：要认文案（2 也可能是别的分支出错）。
R4="$TMP/r4"; make_root "$R4" no; base "$R4"
# ⚠️ 这里**必须**摘掉 GIT_DIR：本条要的就是"git 问不到"。
#    不摘的话，被继承的 GIT_DIR 会让 `git ls-files` **照样成功** ⇒ 这条永远测不出 exit 2。
out4=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
       bash "$R4/scripts/check_doc_orphans.sh" 2>&1); rc4=$?
if [ "$rc4" -eq 2 ] && printf '%s' "$out4" | grep -q "无法判定"; then
    ok "T4 不是 git 仓 ⇒ exit 2（没法判定 ≠ 通过），且确认是【无法判定】那一支"
else
    bad "T4 不是 git 仓 ⇒ exit ${rc4}（应为 2）；文案含'无法判定'? $(printf '%s' "$out4" | grep -c '无法判定') 次"
fi

# ------------------- T5 🔴 `.claude/worktrees/` 下的整仓副本 **不许把真孤儿"救活"**
#
# 这是副本最阴的那一面（`check_doc_links.sh` 顶部记过同一条）：
# **副本里那份提到了 `丁.md` 的文件，会把索引喂饱 ⇒ 真孤儿被判成"有人指向" ⇒ 门静默变绿。**
# ⇒ 主检出有个**真孤儿** `docs/说明/丁.md`，副本里有一份提到它的 README。
#    **正确答案是 exit 1**（副本不算数）。
#
# ⚠️ **本条是本文件里唯一能钉住"worktrees 剪枝 + 只算入库"的那条** ——
#    若它变绿(exit 0)，说明副本又被算进来源了。
R5="$TMP/r5"; make_root "$R5" yes; base "$R5"
mkdir -p "$R5/docs/说明" "$R5/.claude/worktrees/w1"
printf '# 丁\n（真孤儿：没有任何【入库】的文档指向我）\n' > "$R5/docs/说明/丁.md"
printf '# 副本 README\n见 `docs/说明/丁.md` —— 我在副本里，⛔ 不算数\n' > "$R5/.claude/worktrees/w1/README.md"
git -C "$R5" add CLAUDE.md ROADMAP.md README.md docs/
out5=$(bash "$R5/scripts/check_doc_orphans.sh" 2>&1); rc5=$?
if [ "$rc5" -eq 1 ] && printf '%s' "$out5" | grep -q "丁.md"; then
    ok "T5 副本里的文件不许把真孤儿救活 ⇒ exit 1 且点名它"
else
    bad "T5 副本 ⇒ exit ${rc5}（应为 1 —— 0 = 副本又参与进来了）；点名丁.md? $(printf '%s' "$out5" | grep -c '丁.md') 次"
fi

# ------------------- T6 🔴 继承来的 GIT_DIR / GIT_WORK_TREE 不许改变结论
#
# **模拟 `ci-local.sh:252` 那个形状**（它为了让凭据门能跑，把这两个变量显式指回主检出），
# 但**不用真仓**当诱饵 —— 诱饵仓里只有一个不相干的文件，
# ⇒ 一旦门去问了诱饵仓，答案必然从 0 变成 1（那个仓里没有夹具的文档）。
#
# ⛔ **正确答案仍是 exit 0**：门判的必须是【夹具】这个仓。
#    本条变红 ⇒ 说明 `run_gate` 里那半 scrub 没了 ⇒ **门会去问别的仓**。
#    ⚠️ 另有一半（夹具自己的 `git add` 打到真仓上）**在本条里测不到** ——
#       它只在"整个脚本是被脏环境【启动】的"时候才发作（那正是 ci-local 的形状）；
#       那半由 `make_root` 的自证 + `scripts/mutate-orphan-gate.py` 的 M6 钉住。
R6="$TMP/r6"; make_root "$R6" yes; base "$R6"
mkdir -p "$R6/docs/说明"
printf '# 己\n' > "$R6/docs/说明/己.md"
printf '# README\n见 `CLAUDE.md` · `docs/说明/己.md`\n' > "$R6/README.md"
git -C "$R6" add CLAUDE.md ROADMAP.md README.md docs/
DECOY="$TMP/decoy"; mkdir -p "$DECOY"; git -C "$DECOY" init -q
printf '诱饵\n' > "$DECOY/诱饵.md"; git -C "$DECOY" add 诱饵.md
GIT_DIR="$DECOY/.git"; GIT_WORK_TREE="$DECOY"     # ⚠️ 就设在这里，让 run_gate 去摘
rc6=$(run_gate "$R6")
unset GIT_DIR GIT_WORK_TREE
[ "$rc6" -eq 0 ] && ok "T6 继承 GIT_DIR/WORK_TREE ⇒ 仍按【夹具】判 ⇒ exit 0（⛔ 不是问诱饵仓）" \
                 || bad "T6 继承 GIT_DIR ⇒ exit ${rc6}（应为 0 —— 门去问了诱饵仓，run_gate 那半 scrub 没了）"

echo
echo "结果: $PASS 通过 / $FAIL 失败"
if [ "$FAIL" -ne 0 ]; then
    echo "⛔ 有用例失败"
    exit 1
fi
echo "✅ 全部通过"
