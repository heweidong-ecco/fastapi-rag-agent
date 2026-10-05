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
    fi
}

run_gate() {   # $1=仓根 ⇒ 打退出码
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
out4=$(bash "$R4/scripts/check_doc_links.sh" 2>&1); rc4=$?
if [ "$rc4" -eq 2 ] && printf '%s' "$out4" | grep -q "无法判定"; then
    ok "T4 不是 git 仓 ⇒ exit 2（没法判定 ≠ 通过），且确认是【无法判定】那一支"
else
    bad "T4 不是 git 仓 ⇒ exit ${rc4}（应为 2）；文案含'无法判定'? $(printf '%s' "$out4" | grep -c '无法判定') 次"
fi

echo
echo "结果: $PASS 通过 / $FAIL 失败"
if [ "$FAIL" -ne 0 ]; then
    echo "⛔ 有用例失败"
    exit 1
fi
echo "✅ 全部通过"
