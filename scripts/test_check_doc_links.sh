#!/usr/bin/env bash
#
# test_check_doc_links.sh —— `check_doc_links.sh` 的回归测试
#
# ## 为什么有这个文件（2026-10-05 · `DEC-076 §2.9`）
#
# 把断链门接进 CI 的那一轮，**CI 报出 10 处真断链，而本机报 0 处**。
# 根因不是内容，是**门自己的判定口径**：
# 它用 `os.path.exists()` 判"目标存在吗" —— 那是**问磁盘**，
# 而磁盘上有**一堆没入库的东西**（`archive/`、`GIT_CHECKLIST.md` 都被 `.gitignore` 有意排除）。
# ⇒ **同一个仓，两台机器给出两个结论。**
#
# 本文件钉住的就是这条：**判存在的口径必须是「会不会随 clone 一起下来」**。
# ⛔ 不变量：**目标在盘上但不在代码库里 ⇒ 必须算断链。**
#
# ## 为什么要造临时"仓根"
#
# 门把自己所在目录的**上一级**当成仓库根（`BASH_SOURCE/..`）。
# 直接在本仓上测，等于拿**真实数据**当夹具 —— 结论会随仓里文档增删而漂。
# ⇒ 每例都造一个**独立的小仓**，只放门脚本 + 几份构造出来的 .md。
#
# ⚠️ 本文件**故意不用 git shim**（与 `test_check_secrets.sh` 不同）：
#    这里要测的**恰恰是"git 说了什么"**，shim 掉 git 就等于把被测对象换掉了。
#    用**真的 `git init` + `git add`**（`ls-files` 读的是索引，不需要 commit）。
#
# ──────────────────────────────────────────────────────────────────
# 🔴 2026-10-05 加（批 4 · `DEC-080`）：**夹具与门，各给一个干净的 git 环境**
#
# 「用真 git 造夹具」意味着**环境会进来**。而 `GIT_DIR` **一旦被继承就盖过 `-C`** ——
# 实测（2026-10-05，本机）：
#
#     export GIT_DIR=<主检出>/.git GIT_WORK_TREE=<主检出>
#     git -C <临时仓> init -q          ⇒ **返回 0，却不建那个仓**（`<临时仓>/.git` 始终没出现）
#     git -C <临时仓> add CLAUDE.md    ⇒ **打到【主检出】上**：实测 `git status --short`
#                                        从 ` M CLAUDE.md`（未暂存）变成 `M  CLAUDE.md`（已暂存）
#
# ⚠️ **这不是假想的**：`scripts/ci-local.sh:252` 就是这么 export 的（为了让凭据门的
#    `git diff` 在"没有 `.git` 的副本"里能跑）。⇒ 一旦本文件被 ci-local / ci.yml 调用：
#      · 夹具自己的 `git add` 会**悄悄暂存你主检出里未提交的改动**；
#      · 门这个子进程会**去问主检出**，答的不是夹具。
#
# ⇒ **两半都要**（少一半都还漏，T5 就是钉后一半的）：
#   ① 本文件开头 `unset` × 3 —— 管【夹具自己的 git 调用】；
#   ② `run_gate` 里的 `env -u` —— 管【门这个子进程】（它继承环境，必须能发现夹具那个仓）。
# ⛔ 别只在调用方（ci.yml / ci-local）写 `env -u` —— 换个入口跑照样中招；
#    这条知识属于**夹具自己**。
# ──────────────────────────────────────────────────────────────────
#
# 先摘掉（⛔ 必须在任何 git 调用之前）：
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/check_doc_links.sh"
[ -f "$GATE" ] || { echo "⛔ 找不到 $GATE" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# 造一个临时仓根：$1=目录 · $2=是否 git init(yes/no)
make_root() {
    mkdir -p "$1/scripts"
    cp "$GATE" "$1/scripts/check_doc_links.sh"
    if [ "$2" = yes ]; then
        git -C "$1" init -q
        # ⚠️ 判据**不是**"`init` 返回了 0"（本仓纪律：拿动作成功当结果正确）——
        #    被继承的 `GIT_DIR` 下，`init` **就是返回 0 却什么都不建**（实测，见文件头）。
        [ -d "$1/.git" ] || { echo "⛔ 夹具仓没建起来：$1/.git 不存在（GIT_DIR 被继承了？）" >&2; exit 2; }
    fi
}

# 调门时**也要**摘掉那几个变量 —— 见文件头 ①② 那两半。
# 📌 判据 = T5。
run_gate() {   # $1=仓根 ⇒ 打退出码
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
        bash "$1/scripts/check_doc_links.sh" >/dev/null 2>&1
    echo $?
}

echo "断链门 · 回归测试"
echo "门 = $GATE"
echo

# ------------------- T1 目标【被 git 跟踪】⇒ 不算断链（该绿的不红）
R1="$TMP/r1"; make_root "$R1" yes
mkdir -p "$R1/docs"
printf '# 甲\n见 `docs/tracked.md`\n' > "$R1/docs/a.md"
printf '# 乙\n'                     > "$R1/docs/tracked.md"
git -C "$R1" add docs/a.md docs/tracked.md
rc=$(run_gate "$R1")
[ "$rc" -eq 0 ] && ok "T1 目标已入库 ⇒ exit 0（未矫枉过正）" \
                || bad "T1 目标已入库 ⇒ exit ${rc}（应为 0）"

# ------------------- T2 🔴【本次修的就是这条】目标【在盘上但没入库】⇒ 必须算断链
# ⛔ 若本条变绿(exit 0)，说明门又在"问磁盘" ——
#    那就是「本机绿、CI 红」的成因（实测：CI 报 10 处，本机报 0 处）。
R2="$TMP/r2"; make_root "$R2" yes
mkdir -p "$R2/docs"
printf '本行制造一个未入库的目标\n'   > "$R2/docs/未入库.md"
printf '# 丙\n见 `docs/未入库.md`\n'  > "$R2/docs/b.md"
git -C "$R2" add docs/b.md                 # ⚠️ 故意 **不** add 未入库.md
rc=$(run_gate "$R2")
[ "$rc" -eq 1 ] && ok "T2 目标在盘上但【未入库】⇒ exit 1（⛔ 不许算通过）" \
                || bad "T2 目标在盘上但【未入库】⇒ exit ${rc}（应为 1；0 = 又在问磁盘）"

# ------------------- T3 目标【既不在盘上也不入库】⇒ 断链（回归：别把它弄丢）
R3="$TMP/r3"; make_root "$R3" yes
mkdir -p "$R3/docs"
printf '# 丁\n见 `docs/从来没有过.md`\n' > "$R3/docs/c.md"
git -C "$R3" add docs/c.md
rc=$(run_gate "$R3")
[ "$rc" -eq 1 ] && ok "T3 目标根本不存在 ⇒ exit 1" \
                || bad "T3 目标根本不存在 ⇒ exit ${rc}（应为 1）"

# ------------------- T4 🔴 git 用不了 ⇒ exit 2（⛔ 不许把"没能判定"压成"通过"）
# 没有 .git ⇒ `git ls-files` 失败。这正是 ci-local 那种"复制树但没带 .git"的形状。
# ⚠️ 判据不能只看码：要认文案（2 也可能是别的分支出错）。
R4="$TMP/r4"; make_root "$R4" no
mkdir -p "$R4/docs"
printf '# 戊\n见 `docs/x.md`\n' > "$R4/docs/d.md"
# ⚠️ 这里**必须**摘掉 GIT_DIR：本条要的就是"git 问不到"。
#    不摘的话，被继承的 GIT_DIR 会让 `git ls-files` **照样成功** ⇒ 这条永远测不出 exit 2。
out4=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
       bash "$R4/scripts/check_doc_links.sh" 2>&1); rc4=$?
if [ "$rc4" -eq 2 ] && printf '%s' "$out4" | grep -q "无法判定"; then
    ok "T4 不是 git 仓 ⇒ exit 2（没法判定 ≠ 通过），且确认是【无法判定】那一支"
else
    bad "T4 不是 git 仓 ⇒ exit ${rc4}（应为 2）；文案含'无法判定'? $(printf '%s' "$out4" | grep -c '无法判定') 次"
fi

# ------------------- T5 🔴 继承来的 GIT_DIR / GIT_WORK_TREE 不许改变结论
# 模拟 `ci-local.sh:252` 的形状（把这两个变量指回主检出），但**不用真仓**当诱饵：
# 诱饵仓里只有一个不相干的文件 ⇒ 门一旦去问了它，答案必从 0 变成 1。
# ⛔ **正确答案仍是 exit 0**（门判的必须是【夹具】）。本条变红 ⇒ `run_gate` 那半 scrub 没了。
# ⚠️ 另一半（夹具的 `git add` 打到真仓上）在本条里测不到 —— 它只在"整个脚本被脏环境
#    【启动】"时才发作，由 `make_root` 的自证钉住（见文件头）。
R5="$TMP/r5"; make_root "$R5" yes
mkdir -p "$R5/docs"
printf '# 己\n见 `docs/tracked.md`\n' > "$R5/docs/e.md"
printf '# 庚\n'                      > "$R5/docs/tracked.md"
git -C "$R5" add docs/e.md docs/tracked.md
DECOY="$TMP/decoy"; mkdir -p "$DECOY"; git -C "$DECOY" init -q
printf '诱饵\n' > "$DECOY/诱饵.md"; git -C "$DECOY" add 诱饵.md
GIT_DIR="$DECOY/.git"; GIT_WORK_TREE="$DECOY"     # ⚠️ 就设在这里，让 run_gate 去摘
rc5=$(run_gate "$R5")
unset GIT_DIR GIT_WORK_TREE
[ "$rc5" -eq 0 ] && ok "T5 继承 GIT_DIR/WORK_TREE ⇒ 仍按【夹具】判 ⇒ exit 0（⛔ 不是问诱饵仓）" \
                 || bad "T5 继承 GIT_DIR ⇒ exit ${rc5}（应为 0 —— 门去问了诱饵仓，run_gate 那半 scrub 没了）"

echo
echo "结果: $PASS 通过 / $FAIL 失败"
if [ "$FAIL" -ne 0 ]; then
    echo "⛔ 有用例失败"
    exit 1
fi
echo "✅ 全部通过"
