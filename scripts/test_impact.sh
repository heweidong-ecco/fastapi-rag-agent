#!/usr/bin/env bash
# test_impact.sh —— impact.sh 的回归测试
#
# 为什么要有它：impact.sh 是「改动前的影响面扫描」的**唯一防线**。
# 如果它自己悄悄坏了（比如改成了一条零命中却 exit 0 的死命令），
# 那么每次跑它都会给出**"没有影响面"的假绿灯** —— 比没有它还危险。
# ⇒ 所以它必须自己被测。
#
# 跑法：bash scripts/test_impact.sh      （从仓库根跑）
set -u

SELF_DIR=$(cd "$(dirname "$0")" && pwd -P)
REPO=$(cd "$SELF_DIR/.." && pwd -P)
IMPACT="$SELF_DIR/impact.sh"

pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  ✅ %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  ❌ %s\n     %s\n' "$1" "${2:-}"; }

cd "$REPO" || exit 1

echo "test_impact.sh · impact.sh 回归"

# T1 命中已知文件
out=$("$IMPACT" POSTGRES_PASSWORD 2>&1)
case "$out" in
  *"api/config.py"*) ok "T1 命中 api/config.py" ;;
  *) bad "T1 未命中 api/config.py" "$out" ;;
esac

# T2 gitignore 里的**文件本身**不能出现在命中列表里（git grep 只搜被跟踪的）
# ⚠️ 注意断言写精确：提到它的文档 / .gitignore 里那行规则 **是应该**被命中的
#    （那正是影响面的一部分）。要排除的是「被 ignore 的那个文件自己」。
out=$("$IMPACT" GIT_CHECKLIST 2>&1)
if printf '%s\n' "$out" | grep -qx 'GIT_CHECKLIST.md'; then
  bad "T2 被 gitignore 的 GIT_CHECKLIST.md 出现在命中列表里 —— 防线有洞" "$out"
else
  case "$out" in
    *".gitignore"*) ok "T2 被 ignore 的文件扫不到；但引用它的文件（含 .gitignore）能扫到" ;;
    *) ok "T2 被 ignore 的文件扫不到" ;;
  esac
fi

# T3 多关键词取并集（并集 ⊇ 各单关键词）
one=$("$IMPACT" DASHSCOPE_API_KEY 2>&1 | sed -n 's/^命中 \([0-9]*\) 个文件$/\1/p')
two=$("$IMPACT" DASHSCOPE_API_KEY POSTGRES_PASSWORD 2>&1 | sed -n 's/^命中 \([0-9]*\) 个文件$/\1/p')
if [ -n "$one" ] && [ -n "$two" ] && [ "$two" -ge "$one" ]; then
  ok "T3 多关键词取并集 (单=$one 双=$two)"
else
  bad "T3 并集不成立 (单=$one 双=$two)"
fi

# T4 零命中 ⇒ exit 0，且必须明说"别急着下结论"
# ⚠️ 哨兵串必须【运行时生成】：若写成字面量，它就被写进了本测试文件 ⇒ 变得"存在" ⇒
#    这个用例永远构造不出零命中（2026-09-20 实际踩过，T4 因此假失败）。
sentinel="__zz_no_such_token_$$_$(date +%s)__"
out=$("$IMPACT" "$sentinel" 2>&1); rc=$?
if [ "$rc" = "0" ]; then
  case "$out" in
    *"零命中"*) ok "T4 零命中 exit 0 且给出明确提示" ;;
    *) bad "T4 零命中但没给出提示" "$out" ;;
  esac
else
  bad "T4 零命中却 exit $rc（会让人误判为扫描失败）"
fi

# T5 用法错 ⇒ exit 1
"$IMPACT" >/dev/null 2>&1; rc=$?
[ "$rc" = "1" ] && ok "T5 无关键词 exit 1" || bad "T5 无关键词 exit $rc (期望 1)"

# T6 非 git 目录 ⇒ exit 2
tmp=$(mktemp -d)
( cd "$tmp" && "$IMPACT" foo >/dev/null 2>&1 ); rc=$?
rmdir "$tmp" 2>/dev/null || rm -rf "$tmp"
[ "$rc" = "2" ] && ok "T6 非 git 目录 exit 2" || bad "T6 非 git 目录 exit $rc (期望 2)"

# T7 -f 模式：不存在文件 ⇒ exit 1
"$IMPACT" -f 不存在的文件_zzz.xyz >/dev/null 2>&1; rc=$?
[ "$rc" = "1" ] && ok "T7 -f 不存在文件 exit 1" || bad "T7 -f 不存在文件 exit $rc (期望 1)"

# T8 -f 模式：已知文件 ⇒ 命中它自己
out=$("$IMPACT" -f api/config.py 2>&1)
case "$out" in
  *"api/config.py"*) ok "T8 -f 模式命中目标文件" ;;
  *) bad "T8 -f 模式未命中" "$out" ;;
esac

# T9 恰好 1 个命中 ⇒ 必须报 1（这一条是补的：2026-09-20 曾因 printf '%s' 吃掉换行，
#    导致"只有 1 处引用"被报成 0 —— 假绿灯。T3 只测了"并集 ≥ 单个"，漏掉了绝对值。）
#
# ⚠️ 夹具在 scripts/impact_test_fixture.txt（全仓只出现一次它的 token）。
#    **不要改用仓库里现成的词** —— 2026-09-20 用过 `architecture_agent`，
#    后来我自己在 impact.sh 的注释和待办登记里写到了它 ⇒ 变成 3 处 ⇒ 用例假失败。
TOKEN=$(sed -n 's/^\(IMPACT_TEST_UNIQUE_TOKEN_[0-9a-f]*\)$/\1/p' "$SELF_DIR/impact_test_fixture.txt" 2>/dev/null | head -1)
oracle=0
[ -n "$TOKEN" ] && oracle=$(git -c core.quotePath=false grep -l -F -e "$TOKEN" -- . 2>/dev/null | wc -l | tr -d ' ')
if [ -z "$TOKEN" ]; then
  bad "T9 夹具缺失或格式变了：scripts/impact_test_fixture.txt 里找不到 token"
elif [ "$oracle" != "1" ]; then
  bad "T9 夹具已失效：token 现在有 $oracle 处命中（应恰为 1，见 scripts/impact_test_fixture.txt）"
else
  out=$("$IMPACT" "$TOKEN" 2>&1)
  got=$(printf '%s\n' "$out" | sed -n 's/^命中 \([0-9]*\) 个文件$/\1/p')
  if [ "$got" = "1" ]; then
    ok "T9 恰好 1 个命中 ⇒ 报 1（不是 0）"
  else
    bad "T9 恰 1 命中却报 '$got'（期望 1）—— 假绿灯回归" "$out"
  fi
fi

# T10 报告的计数必须 == 【独立 oracle】的计数（不给 impact.sh 用自己的明细自证的机会）
for kw in POSTGRES_PASSWORD "$TOKEN"; do
  out=$("$IMPACT" "$kw" 2>&1)
  got=$(printf '%s\n' "$out" | sed -n 's/^命中 \([0-9]*\) 个文件$/\1/p')
  want=$(git -c core.quotePath=false grep -l -F -e "$kw" -- . 2>/dev/null | wc -l | tr -d ' ')
  if [ "$got" = "$want" ]; then
    ok "T10($kw) 计数 $got == 独立 oracle $want"
  else
    bad "T10($kw) 计数($got) 与独立 oracle($want) 不符" "$out"
  fi
done

echo
printf '结果: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ] || exit 1
