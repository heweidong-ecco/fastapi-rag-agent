#!/usr/bin/env bash
#
# seed_isolation_docs.sh —— 把三家隔离用户的语料**通过真接口**灌进**真库**，长期保留
#
# ## 为什么要它
#
# 业务方 2026-10-04 原话：
#   「documents 你给它们造好并写文档……调用接口模拟真实用户的操作，写入数据库和向量数据库，
#    **没有真实写入以后怎么用作判断和测试**。我要：**真库里有三家各自的文档、肉眼可查**，
#    且是真实模拟用户传入，这样有记录，能验证用户隔离，安全，role thread_id tag 等等相关的关键信息。」
#
# 🔴 **它与本仓既有的一条口径【相反】**（`DEC-056` 乙段）：那边裁的是
#   「探针文档（`api/test_isolation.py::probe_docs`）每次跑完就删」—— 理由是测试卫生 + 防误写真库。
#   本脚本要的恰好是**留下来的那一种**。⇒ 两件事并存，**⛔ 不是把探针那条改掉**。
#   📄 口径变化记在 `docs/decisions/DEC-071-三家隔离语料常驻真库.md`
#
# ## 用法
#
#     bash scripts/seed_isolation_docs.sh            # 清旧种子 → 重新灌 → 打印计数
#     bash scripts/seed_isolation_docs.sh --check    # 只查（改任何东西之前/之后都跑它）
#
# ## ⛔ 三条纪律
#
#   1. **全程不打印凭据值** —— key 只以 `$VAR` 形式传给 curl。
#   2. **清理范围严格受限** —— 只删 `source LIKE 'isolation-seed/%'`，⛔ 绝不 `TRUNCATE`、
#      ⛔ 绝不碰 `requested_by='admin'` 的 112 条既有数据。
#   3. **`--check` 里的每条判据都必须能打印** —— 写不出命令的，就是还没核过（本仓判据纪律）。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

CORPUS_DIR="testdata/isolation-seed"
SOURCE_PREFIX="isolation-seed/"          # `documents.source` 的前缀 = 本脚本的清理界线
API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
PG_CONTAINER="${PG_CONTAINER:-postgres-rag}"

MODE="seed"
[ "${1:-}" = "--check" ] && MODE="check"

# ── 凭据：只 source 进来，⛔ 不 echo ──
if [ ! -f .env ]; then
  echo "🔴 找不到 .env（仓根）—— 三个 ISOLATION_*_API_KEY 在里面" >&2
  exit 2
fi
set -a; . ./.env; set +a

PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-rag_db}"

sql() { docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -Atc "$1"; }

for v in ISOLATION_A_API_KEY ISOLATION_B_API_KEY ISOLATION_C_API_KEY; do
  if [ -z "${!v:-}" ]; then echo "🔴 .env 里缺 ${v}" >&2; exit 2; fi
done
docker inspect "${PG_CONTAINER}" >/dev/null 2>&1 || { echo "🔴 容器 ${PG_CONTAINER} 不在" >&2; exit 2; }

# ── 语料清单（**写死的三元组**，⛔ 不用 glob —— glob 会把将来误放进来的文件也灌进真库）──
#     格式：<用户名>|<key 变量名>|<语料文件相对本目录的路径>
FIXTURES=(
  "isolation_a|ISOLATION_A_API_KEY|A-01-产品手册.md"
  "isolation_a|ISOLATION_A_API_KEY|A-02-烘焙工艺说明.md"
  "isolation_a|ISOLATION_A_API_KEY|A-03-门店价目表.md"
  "isolation_b|ISOLATION_B_API_KEY|B-01-寄养服务说明.md"
  "isolation_b|ISOLATION_B_API_KEY|B-02-入住与接送流程.md"
  "isolation_b|ISOLATION_B_API_KEY|B-03-收费与常见问题.md"
  "isolation_c|ISOLATION_C_API_KEY|C-01-闸阀产品规格书.md"
  "isolation_c|ISOLATION_C_API_KEY|C-02-质量检测标准.md"
  "isolation_c|ISOLATION_C_API_KEY|C-03-售后与备件清单.md"
)

# ════════════════════════ --check：判据（可打印）════════════════════════
run_check() {
  echo "══════ ① 三家各自的 chunk 数（真库，肉眼可查）══════"
  sql "SELECT requested_by, count(*), count(DISTINCT source), count(embedding)
       FROM documents WHERE source LIKE '${SOURCE_PREFIX}%'
       GROUP BY 1 ORDER BY 1;"
  echo "   ↑ 列 = 用户 | chunk 数 | 文档篇数 | 有向量的行数（三列应相等或成倍）"

  echo
  echo "══════ ② 归属污染检查（应为 0）══════"
  sql "SELECT count(*) FROM documents
       WHERE source LIKE '${SOURCE_PREFIX}%'
         AND requested_by NOT IN ('isolation_a','isolation_b','isolation_c');"
  echo "   ↑ 种子语料里出现非三家归属的行数 —— **必须为 0**"

  echo
  echo "══════ ③ 空向量检查（应为 0）══════"
  sql "SELECT count(*) FROM documents
       WHERE source LIKE '${SOURCE_PREFIX}%' AND (embedding IS NULL);"

  echo
  echo "══════ ④ 每家自己看得到什么（source 清单）══════"
  sql "SELECT requested_by, string_agg(DISTINCT source, ' , ' ORDER BY source)
       FROM documents WHERE source LIKE '${SOURCE_PREFIX}%' GROUP BY 1 ORDER BY 1;"

  echo
  echo "══════ ⑤ 交叉检索：用 A 的 key 搜 B/C 的主题词（应搜不到 B/C 的 source）══════"
  #   ⚠️ `mode=fast`：**故意不走查询改写** —— 那条要调 LLM（花钱），而这里要验的是
  #      「检索是否只在该用户自己的文档内」（`api_v1_rag.py` 的 `user_id=user_name`）。
  #   ⚠️ 同时打印**返回字段名** —— 防空结果被当成"隔离通过"（本仓
  #      `docs/复盘/2026-09-29-结果为空就断言能力不存在.md` 记的就是这个病）。
  for pair in "A|ISOLATION_A_API_KEY|宠物寄养要带什么 遛弯|闸阀 DN100 球墨铸铁"; do
    IFS='|' read -r tag keyvar q_own q_foreign <<<"${pair}"
    eval "k=\$$keyvar"
    for q in "${q_own}" "${q_foreign}"; do
      body=$(printf '{"question":%s,"top_k":20,"generate_answer":false}' \
             "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$q")")
      out=$(curl -sS --max-time 60 -X POST "${API_BASE}/rag/search?mode=fast" \
              -H "X-API-Key: ${k}" -H 'Content-Type: application/json' \
              -d "${body}" || echo '{}')
      echo "$out" | python3 -c '
import json, sys
tag, q = sys.argv[1], sys.argv[2]
try:
    d = json.load(sys.stdin)
except Exception:
    print("  [" + tag + "] " + q + " ⇒ ⚠️ 返回不是 JSON"); raise SystemExit
rows = d.get("results") or d.get("documents") or d.get("docs") or []
print("  [" + tag + "] " + q + " ⇒ 命中 " + str(len(rows)) + " 条")
print("        返回字段 = " + str(sorted(d.keys())))
srcs = sorted({(r.get("source") or r.get("metadata", {}).get("source") or "?") for r in rows})
foreign = [s for s in srcs if s.startswith("isolation-seed/B") or s.startswith("isolation-seed/C")]
print("        来源 = " + str(srcs))
print("        越界来源 = " + (str(foreign) if foreign else "无 ✅"))
' "$tag" "$q"
    done
  done
}

if [ "${MODE}" = "check" ]; then
  run_check
  exit 0
fi

# ════════════════════════ seed：清旧 → 灌新 ════════════════════════
echo "──── ① 清理旧种子（仅 source LIKE '${SOURCE_PREFIX}%'）────"
before=$(sql "SELECT count(*) FROM documents WHERE source LIKE '${SOURCE_PREFIX}%';")
echo "   待删 ${before} 行"
if [ "${before}" -gt 0 ]; then
  sql "DELETE FROM documents WHERE source LIKE '${SOURCE_PREFIX}%';" >/dev/null
fi
echo "   删后剩余：$(sql "SELECT count(*) FROM documents WHERE source LIKE '${SOURCE_PREFIX}%';")"

echo
echo "──── ② 逐篇经真接口上传（POST ${API_BASE}/rag/upload_document）────"
total=0
for row in "${FIXTURES[@]}"; do
  IFS='|' read -r user keyvar fname <<<"${row}"
  path="${CORPUS_DIR}/${fname}"
  src="${SOURCE_PREFIX}${fname}"
  [ -f "${path}" ] || { echo "   🔴 缺语料 ${path}" >&2; exit 1; }
  eval "k=\$$keyvar"
  resp=$(curl -sS --max-time 120 -X POST \
          "${API_BASE}/rag/upload_document?domain=default" \
          -H "X-API-Key: ${k}" \
          -F "file=@${path};filename=${src}")
  echo "${resp}" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("   ✅ " + str(d.get("requested_by")).ljust(12)
      + str(d.get("filename")).ljust(42)
      + " chunks=" + str(d.get("chunks_inserted"))
      + " chars=" + str(d.get("text_length")))
' || { echo "   🔴 上传失败：${resp}" >&2; exit 1; }
  total=$((total+1))
done
echo "   共 ${total} 篇"

echo
echo "──── ③ 会话痕迹（thread_id 轴）—— ⛔ 本脚本【不】自动跑它 ────"
echo "   上传路径的记账写死 user_name='system'（api/embedding_client.py:36-37），"
echo "   ⇒ 拿不到按人的 thread_id。那条轴要单独跑，**而且它花真钱**："
echo "       bash scripts/seed_isolation_threads.sh        # 三家各 2 轮 ≈ 3,200–3,800 token/家（合计 10,374）"
echo "   ⛔ 故意不在这里自动触发 —— 灌文档不该有「顺手烧额度」这个副作用。"

echo
echo "──── ④ 复核 ────"
run_check
