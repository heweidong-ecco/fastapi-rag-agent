#!/usr/bin/env bash
#
# backup.sh —— 备份本项目的数据库（**默认导出到 git 仓之外**）
#
# ## 为什么要它
#
# 🔴 **在它之前，本仓【没有任何备份机制】** —— 无脚本、无 cron、无定时任务。
# 而 `documents` 表（RAG 知识库 + 1536 维向量）是**本仓最不可再生的资产**。
#
# ## 用法
#
#     bash scripts/backup.sh                 # 备份（默认保留最近 7 份）
#     bash scripts/backup.sh --keep 30       # 保留 30 份
#     bash scripts/backup.sh --list          # 只列已有备份
#     bash scripts/backup.sh --dir /some/dir # 换目标目录
#
# ## ⛔ 为什么默认导到【仓外】
#
# 备份里**含全部业务数据**（知识库内容、用户 token 用量…）。
# 本仓是 **PUBLIC 仓库** ⇒ **备份绝不能落在仓里**，哪怕 gitignore 了也不该。
# ⇒ 默认目标：`~/Desktop/Product-external/backups/fastapi-rag-agent/`
#   （那是本仓规矩指定的「**不能进任何 git 仓的东西**」的落点）
#
# ⚠️ **本脚本【只备份，不自动清理生产数据】。** 恢复是**手工**的，见文件末尾。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

BACKUP_DIR="${HOME}/Desktop/Product-external/backups/fastapi-rag-agent"
KEEP=7
DB="${POSTGRES_DB:-rag_db}"
PG_CONTAINER="${PG_CONTAINER:-postgres-rag}"

while [ $# -gt 0 ]; do
  case "$1" in
    --keep)  KEEP="$2"; shift 2 ;;
    --dir)   BACKUP_DIR="$2"; shift 2 ;;
    --list)  ls -lht "${BACKUP_DIR}" 2>/dev/null || echo "（还没有备份）"; exit 0 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/rag_db-${STAMP}.sql"

# ---- ① 容器在吗（判据：docker ps，不是"我以为它在跑"）----
if ! docker ps --format '{{.Names}}' | grep -qx "${PG_CONTAINER}"; then
  echo "❌ 容器 ${PG_CONTAINER} 不在运行 —— 备份中止。" >&2
  echo "   先跑：docker compose up -d postgres" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
echo "▶ 备份 ${DB} → ${OUT}"

# ---- ② 导出 ----
docker compose exec -T postgres pg_dump -U postgres -d "${DB}" --no-owner --no-privileges > "${OUT}"

# ---- ③ ⭐ 校验：**不能只看"命令退出码 0"** ----
#    本仓「判据」纪律第 1 条：改完必须"看结果"，不能只看"动作返回"。
size=$(wc -c < "${OUT}" | tr -d ' ')
tables=$(grep -c '^CREATE TABLE' "${OUT}" || true)
copies=$(grep -c '^COPY ' "${OUT}" || true)

echo "  大小   : ${size} 字节"
echo "  表定义 : ${tables} 个"
echo "  数据段 : ${copies} 个"

problems=0
[ "${size}" -lt 1000 ]  && { echo "  🔴 文件过小（<1KB）—— 很可能没导出来"; problems=1; }
[ "${tables}" -lt 6 ]   && { echo "  🔴 表定义少于 6 个（应为 6）"; problems=1; }

# ⭐ 关键：**数据行数为 0 时不算失败**（空库也是合法状态），但**要提示**
if [ "${copies}" -eq 0 ]; then
  echo "  ⚠️ 没有 COPY 段 —— 数据库是空的？（空库合法，但确认一下）"
fi

if [ "${problems}" -ne 0 ]; then
  echo "❌ 备份【校验未过】—— 文件保留但不可信：${OUT}" >&2
  exit 1
fi

# ---- ④ 轮转（只删本目录里本脚本产出的文件）----
if [ "${KEEP}" -gt 0 ]; then
  n=$(ls -1 "${BACKUP_DIR}"/rag_db-*.sql 2>/dev/null | wc -l | tr -d ' ')
  if [ "${n}" -gt "${KEEP}" ]; then
    ls -1t "${BACKUP_DIR}"/rag_db-*.sql | tail -n +$((KEEP+1)) | while read -r old; do
      rm -f "${old}" && echo "  🗑  轮转删除：$(basename "${old}")"
    done
  fi
fi

echo "✅ 备份完成（保留最近 ${KEEP} 份）"
echo
echo "恢复办法（⚠️ 会覆盖当前数据，先确认）："
echo "  docker compose exec -T postgres psql -U postgres -d ${DB} < ${OUT}"
echo "  ⚠️ 恢复后【必须重建向量索引】—— pg_dump 不含索引，见 docs/说明/运维.md §六"
