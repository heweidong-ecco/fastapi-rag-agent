#!/usr/bin/env bash
# impact.sh —— 「改动前的影响面扫描」
#
# 用途：改任何东西（代码 / 文档 / 配置）之前，先列出**全仓谁会因为这次改动而变成错的**。
#       这是「修了这边漏那边」的机械防线 —— 把"影响面"变成命令输出，而不是靠记忆。
#
# 用法：
#   scripts/impact.sh <关键词> [<关键词> ...]
#   scripts/impact.sh -f api/main.py [api/db.py ...]   # 按文件：自动取 basename 与相对路径
#
# 输出：命中的**被 git 跟踪**文件（git grep ⇒ 天然排除 .gitignore 里的东西），
#       按目录分组 + 明细 + 总数。
#
# 退出码：
#   0 = 扫描完成（有无命中都是 0）
#   1 = 用法错误（没给关键词）
#   2 = 不在 git 仓库里
#
# ⚠️ 局限（自己知道就好，别把它当万能）：
#   - 只搜**文本**。改了行为但没改到任何字符串 ⇒ 它扫不出来（例：改了函数返回值语义）。
#   - 只搜**被跟踪**的文件 ⇒ gitignore 里的（如 archive/）扫不到。**这正是它该有的行为**，
#     但要自己记得：引用 archive/ 的文档会被扫到，而 archive/ 里被引用的东西不会。
set -u

die() { printf '%s\n' "$1" >&2; exit "${2:-1}"; }

git rev-parse --git-dir >/dev/null 2>&1 || die "impact.sh: 当前目录不是 git 仓库" 2

mode=kw
kws=()
for a in "$@"; do
  case "$a" in
    -f|--file) mode=file ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) kws+=("$a") ;;
  esac
done

[ ${#kws[@]} -gt 0 ] || die "用法: scripts/impact.sh <关键词> [...]   或   scripts/impact.sh -f <文件> [...]" 1

# -f 模式：把每个文件展开成「basename」+「相对路径」两个关键词
if [ "$mode" = file ]; then
  expanded=()
  for f in "${kws[@]}"; do
    [ -e "$f" ] || die "impact.sh: 文件不存在 —— $f" 1
    expanded+=("$(basename "$f")")
    expanded+=("$f")
  done
  kws=("${expanded[@]}")
fi

echo "impact.sh · 影响面扫描"
printf '关键词(%d): %s\n' "${#kws[@]}" "${kws[*]}"

hits=""
for k in "${kws[@]}"; do
  # core.quotePath=false ⇒ 中文路径原样输出（否则会是 \351\207... 八进制转义，
  # 既看不懂，也会让下面的「按目录」分组把中文目录全归错）
  h=$(git -c core.quotePath=false grep -l -F -e "$k" -- . 2>/dev/null || true)
  [ -n "$h" ] && hits="${hits}${h}"$'\n'
done

# ⚠️ 必须是 '%s\n' 不是 '%s' —— `wc -l` 数的是【换行数】，`printf '%s'` 会吃掉末尾换行，
# 导致：多个命中时【少 1】，恰好 1 个命中时【报 0】→ 输出"零命中"的**假绿灯**。
# （2026-09-20 实测踩过：`architecture_agent` 只有 1 处引用，被报成 0。）
hits=$(printf '%s\n' "$hits" | sed '/^$/d' | sort -u)
n=$(printf '%s\n' "$hits" | sed '/^$/d' | wc -l | tr -d ' ')

echo "命中 ${n} 个文件"
if [ "$n" = "0" ]; then
  echo "  （零命中 —— ⚠️ 别急着下结论：可能是关键词写法不对，也可能是它真的孤立）"
  exit 0
fi

echo
echo "── 按目录 ──"
printf '%s\n' "$hits" | awk -F/ 'NF==1{print "(仓根)"} NF>1{print $1"/"}' | sort | uniq -c | sort -rn
echo
echo "── 明细 ──"
printf '%s\n' "$hits"
