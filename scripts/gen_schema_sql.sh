#!/usr/bin/env bash
#
# gen_schema_sql.sh —— 重新生成 `app/schema.sql`（**手写头 + pg_dump 正文**的拼接）
#
# ## 为什么要有它
#
# 🔴 **2026-10-08（`N12`）之前，这一步靠"人记得"** —— 文件头自己写着生成命令：
#
#     docker compose exec -T postgres pg_dump -U postgres -d rag_db --schema-only \
#       --no-owner --no-privileges > app/schema.sql
#
# ⚠️ **那条命令会把这文件【约 80 行手写头】当场冲掉** —— 头是手写的、`pg_dump` 不产它。
# 🔴 `N12` 那次是**手工 `cat` 拼的**（`sed -n '1,71p'` 取头 + dump），
#    下一个人照文件头那条命令跑，**头就没了，而且不报错**。
# ⇒ 本脚本把"拼接"这一步**变成结构**（本仓立场：**只有文字就漏，结构才执行**）。
#
# ## 切分点 = 文件里的【哨兵行】
#
# 头与正文之间有一行哨兵（`app/schema.sql` 里那行 ⛔⛔ 切分哨兵）。
# **本脚本按它切**，⛔ 不按"第 N 行"（行号会随头的增删漂）。
# 📌 找不到哨兵 ⇒ **exit 2「判不了」**，⛔ 不是"凑合生成"（三态：0 过 / 1 失败 / 2 判不了）。
#
# ## 用法
#
#     bash scripts/gen_schema_sql.sh            # 生成并覆盖 app/schema.sql
#     bash scripts/gen_schema_sql.sh --check    # ⛔ 不写文件，只报「与活库是否一致」
#
# ## 前置
#
#     docker compose up -d postgres            # ⚠️ 要一个【活着的】PG
#
# ## 🔴 本脚本是**真跑过反证的**（2026-10-08 · ⛔ 别当成"写完了没验"）
#
#   | 反证 | 期望 | 实测 |
#   |---|---|---|
#   | 把哨兵行删掉 | exit **2**（判不了） | ✅ `🔴 找不到切分哨兵` / 退出码 2 |
#   | 把哨兵**复制成两行** | exit **2** | ✅ `🔴 出现了 2 次` / 退出码 2 |
#   | **PG 停掉** | exit **1**（⛔ 不凑合生成） | ✅ `🔴 不在或未 healthy` / 退出码 1 |
#   | 正常 | `--check` 报**一致** | ✅ 退出码 0 |
#
#   ⚠️ **写这个脚本时【它自己先抓到一个真 bug】**：初版把哨兵放在手写头的**倒数第 4 行**
#      （后面还跟着 3 行说明）⇒ `--check` 报 `74,76d73` ⇒ **那 3 行会被切掉**。
#      ⇒ 改成「**哨兵必须是手写头的最后一行**」，并在文件里用大字写着。
#   ⚠️ 另一处：`\restrict` 的**随机 nonce** 让 `--check` **永远报不一致**（等于这个检查没用）
#      ⇒ 比对前**归一化掉那两行**（它**不是凭据**，是 pg_dump 的注入防护串）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

TARGET="app/schema.sql"
SENTINEL='切分哨兵'
CONTAINER="postgres-rag"
DB="${POSTGRES_DB:-rag_db}"

MODE="write"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

# ---------- 0. 哨兵必须唯一 ----------
# ⚠️ 两条：存在 + 只出现一次。出现两次 ⇒ 切出来的是"半个文件"，⚔️ 而且不报错。
n_sentinel="$(grep -c -- "${SENTINEL}" "${TARGET}" || true)"
if [ "${n_sentinel}" -eq 0 ]; then
  echo "🔴 在 ${TARGET} 里找不到切分哨兵（含「${SENTINEL}」的那行）⇒ 无法判定头到哪结束。" >&2
  echo "   ⛔ 不凑合生成 —— 硬切会把手写头冲掉。" >&2
  exit 2
fi
if [ "${n_sentinel}" -ne 1 ]; then
  echo "🔴 切分哨兵出现了 ${n_sentinel} 次（应为 1）⇒ 切出来的是半个文件且【不报错】。" >&2
  exit 2
fi

# ---------- 1. 活库必须真的在 ----------
# ⚠️ 判据是【容器在且健康】，⛔ 不是"docker ps 有输出" ——
#    `docker ps` 读的是缓存，Docker Desktop 的 VM 卡死时它照样秒回。
if ! docker inspect -f '{{.State.Health.Status}}' "${CONTAINER}" 2>/dev/null | grep -q '^healthy$'; then
  echo "🔴 ${CONTAINER} 不在或未 healthy ⇒ 先起库（--check 也同样需要）。" >&2
  echo "   ⛔ 这里【不替你起】—— 起停容器是使用者的动作（业务方 2026-10-08 定的口径）。" >&2
  exit 1
fi

# ---------- 2. 取头（含哨兵行）----------
HEAD_END="$(grep -n -- "${SENTINEL}" "${TARGET}" | head -1 | cut -d: -f1)"
TMPDIR_LOCAL="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_LOCAL}"' EXIT

sed -n "1,${HEAD_END}p" "${TARGET}" > "${TMPDIR_LOCAL}/head.sql"
# 头与正文之间【两个空行】—— 与原文件形态一致（pg_dump 自己也以 `--` 开头）
printf '\n\n' >> "${TMPDIR_LOCAL}/head.sql"

# ---------- 3. 导正文 ----------
docker compose exec -T postgres \
  pg_dump -U postgres -d "${DB}" --schema-only --no-owner --no-privileges \
  > "${TMPDIR_LOCAL}/dump.sql"

cat "${TMPDIR_LOCAL}/head.sql" "${TMPDIR_LOCAL}/dump.sql" > "${TMPDIR_LOCAL}/new.sql"

# ---------- 4. 自证：切出来的头必须真的是"头" ----------
# 🔴 别只看"命令成功了" —— 头要是被切短了，正文照样拼得出来、文件照样合法。
#    判据：头里必须【有】那句手写说明、且【没有】`CREATE TABLE`。
if ! grep -q '本文件是【生成的】' "${TMPDIR_LOCAL}/head.sql"; then
  echo "🔴 切出来的头里没有那句「本文件是【生成的】」⇒ 切点太靠前，头被切短了。" >&2
  exit 1
fi
if grep -q '^CREATE TABLE' "${TMPDIR_LOCAL}/head.sql"; then
  echo "🔴 切出来的头里【已经有】CREATE TABLE ⇒ 切点太靠后，把正文切进头里了。" >&2
  exit 1
fi

# ---------- 5. 写 / 比 ----------
if [ "${MODE}" = "check" ]; then
  # 🔴 比之前必须【归一化】`\restrict` / `\unrestrict` 那两行：
  #    pg_dump 17.10 起每次生成一个【随机 nonce】放进去 ⇒ 不比掉它，
  #    「一致」这两个字**永远不会出现**（每次都报"不一致"）⇒ 那个检查形同虚设。
  #    ⚠️ 它**不是凭据**（是注入防护用的随机串），所以在这里丢掉是安全的。
  # ⚠️ 用 sed 而不是 grep：这里的反斜杠层数很容易数错，
  #    而**数错的后果是"过滤不掉、checks 永远报不一致"** —— `sed` 的 BRE `\\` 就是一层，好核。
  norm() { sed '/^\\restrict /d; /^\\unrestrict /d' "$1"; }
  norm "${TARGET}"               > "${TMPDIR_LOCAL}/old.norm"
  norm "${TMPDIR_LOCAL}/new.sql" > "${TMPDIR_LOCAL}/new.norm"
  if diff -q "${TMPDIR_LOCAL}/old.norm" "${TMPDIR_LOCAL}/new.norm" >/dev/null; then
    echo "✅ ${TARGET} 与活库【一致】（已忽略 pg_dump 的随机 \\restrict nonce）。"
    exit 0
  fi
  echo "🔴 ${TARGET} 与活库【不一致】—— 活库有了它没有的东西（或反过来）。"
  diff "${TMPDIR_LOCAL}/old.norm" "${TMPDIR_LOCAL}/new.norm" | head -40
  echo "   ⛔ 修法：跑一次 \`bash scripts/gen_schema_sql.sh\`（会重写本文件）。"
  exit 1
fi

cp "${TMPDIR_LOCAL}/new.sql" "${TARGET}"

# ---------- 6. 生成后【自证】----------
# ⚠️ 行首锚 `^` 是【故意】的：不带锚的 `grep -c 'approval_events'` 会把
#    "说明这段判据的文字"自己也数进去（`N12` 那次连踩两次，见 `DEC-115 §三`）。
tables="$(grep -c '^CREATE TABLE public\.' "${TARGET}" || true)"
echo "✅ 已重新生成 ${TARGET} —— 第 ${HEAD_END} 行处切分 · 正文含 ${tables} 张表。"
echo "   📌 活库实际表数："
docker compose exec -T postgres psql -U postgres -d "${DB}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
echo "   ⚠️ 两个数应当相等。⛔ 不等就说明切/导出了问题，别提交。"
echo
echo "🔴 还要手动做一件事（脚本 ⛔ 不替你改手写头）："
echo "   把 ${TARGET} 头里的「生成时间」那一行改成今天。"
