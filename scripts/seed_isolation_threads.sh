#!/usr/bin/env bash
#
# seed_isolation_threads.sh —— 让三家隔离用户**各跑一段真对话**，在真库留下带 `thread_id` 的记录
#
# ## 为什么要它
#
# 业务方 2026-10-04 要验的五个维度里，`documents` 那条轴（`seed_isolation_docs.sh`）只能覆盖
# **用户隔离 / 安全 / role / tag** 四条 —— **`thread_id` 覆盖不到**（`documents` 表压根没有这一列）。
# 本脚本补的就是它。
#
# ## 🔴 端点选择：为什么必须是 `/agent/mcp_chat`（这条踩过坑，别改）
#
# 2026-10-04 我先挑的是 `/agent/advanced_chat`，**实测 HTTP 200 但真库新增 0 条**
# —— 因为它走的是 `agent_graph_advanced_learning`（**那份文件里 `record_usage` / `thread_id`
# 零命中**，压根不记账）。而**会记账的 `agent_graph_advanced.py` 是给 `/agent/mcp_chat` 用的**。
#
# 四条链路的对照（都实测过）：
#   `POST /rag/upload_document`   ⛔ 写死 `user_name="system"` / `thread_id="system"`
#   `POST /agent/memory_chat`     ⛔ 记账判据 `hasattr(response,"usage")` **恒为假**（`agent_checkpointer.py:78-83`）
#   `POST /agent/advanced_chat`   ⛔ 走的是不记账的那份图（实测 0 条）
#   `POST /agent/mcp_chat`        ✅ **记**：`user_name` 真实 + `thread_id` = **调用方传进来的原值**
#                                    （路径：端点 `:1306` 注入 state → `agent_graph_advanced.py:360` 记账）
#   `POST /agent/plan_execute`    🟡 记 `user_name`，但 `thread_id` 是**字面量** `"plan_execute"`
#                                    （`plan_execute.py:178`；且一次实测吃 **9,800 token**）
#
# ## 开销（实测 2026-10-04 · `--check` 原样打印）
#
#   isolation_a  2 轮 = 3,329 token（agent_decision 2,472 + answer_generation 857）
#   isolation_b  2 轮 = 3,824 token
#   isolation_c  2 轮 = 3,221 token
# ⇒ **每家 2 轮 ≈ 3,200–3,800** · **三家合计 10,374**；`FREE` 档日额度 10,000 ⇒ 单家放得下。
# ⚠️ **别加轮次**：三家一起烧的是**各自**的日额度，而 `FREE` 只有 10,000
#    —— 一家跑到 ~6 轮就要撞顶了。
#
# ## 用法
#
#     bash scripts/seed_isolation_threads.sh            # 清旧痕迹 → 三段真对话 → 复核
#     bash scripts/seed_isolation_threads.sh --check    # 只查
#
# ## ⚠️ 两件它**做不到**的（⛔ 别当成 bug）
#
#   1. **对话正文不落库** —— `mcp_chat` 的记账只存 `user_name/thread_id/purpose/token`，
#      **不存问题与回答**。追踪轴（`/agent/trace/{thread_id}`）有正文，但那是
#      `api/tool_visualizer.py` 的**进程内字典** `_traces` ⇒ **不 durable**。
#      ⇒ 正文由本脚本**打印出来**，落库的是「谁 / 哪个会话 / 花了多少」。
#   2. **`thread_id` 不落 Redis 的对话历史** —— `persist_turn` 只在**流式**端点被调
#      （`api_v1_agent.py:1396` 属 `mcp_chat/stream`）⇒ 本脚本走非流式，`chat_history:{用户}` 里没有。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
PG_CONTAINER="${PG_CONTAINER:-postgres-rag}"

MODE="seed"
[ "${1:-}" = "--check" ] && MODE="check"

if [ ! -f .env ]; then echo "🔴 找不到 .env（仓根）" >&2; exit 2; fi
set -a; . ./.env; set +a
PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${POSTGRES_DB:-rag_db}"
sql() { docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -Atc "$1"; }

for v in ISOLATION_A_API_KEY ISOLATION_B_API_KEY ISOLATION_C_API_KEY; do
  if [ -z "${!v:-}" ]; then echo "🔴 .env 里缺 ${v}" >&2; exit 2; fi
done
docker inspect "${PG_CONTAINER}" >/dev/null 2>&1 || { echo "🔴 容器 ${PG_CONTAINER} 不在" >&2; exit 2; }

# ── 三段对话：<用户>|<key 变量>|<thread_id>|<第 1 轮>|<第 2 轮> ──
#      ⚠️ 两轮都**不需要工具**（避免触发 `SENSITIVE_TOOLS=web_search` 的人工审批门）。
#      ⚠️ 第 2 轮**刻意追问第 1 轮的内容** —— 它同时验「同一个 thread 记得住」这件事。
CONVERSATIONS=(
  "isolation_a|ISOLATION_A_API_KEY|A-thread-001|你好，请记住：我是晨光咖啡烘焙的店长。|我刚才说我是哪家店的店长？"
  "isolation_b|ISOLATION_B_API_KEY|B-thread-001|你好，请记住：我是萌宠家宠物寄养中心的前台。|我刚才说我在哪个中心当前台？"
  "isolation_c|ISOLATION_C_API_KEY|C-thread-001|你好，请记住：我是恒远工业阀门的质检员。|我刚才说我在哪家厂当质检员？"
)
THREAD_IDS="'A-thread-001','B-thread-001','C-thread-001'"

# ════════════════════════ --check：判据（可打印）════════════════════════
run_check() {
  echo "══════ ① 三家各自的会话记账（真库，肉眼可查）══════"
  sql "SELECT user_name, thread_id, count(*) AS 调用数, sum(total_tokens) AS 合计token
       FROM cost_records WHERE thread_id IN (${THREAD_IDS})
       GROUP BY 1,2 ORDER BY 1;"

  echo
  echo "══════ ② 越界检查（应为 0）：thread_id 与 user_name 是否对得上 ══════"
  sql "SELECT count(*) FROM cost_records WHERE thread_id IN (${THREAD_IDS})
       AND NOT ( (thread_id='A-thread-001' AND user_name='isolation_a')
              OR (thread_id='B-thread-001' AND user_name='isolation_b')
              OR (thread_id='C-thread-001' AND user_name='isolation_c') );"
  echo "   ↑ 必须为 0 —— 非 0 就说明**一个会话的钱记到了别人头上**"

  echo
  echo "══════ ③ 两张表是否都写（本仓记账是双写）══════"
  sql "SELECT 'cost_records' AS 表, count(*) FROM cost_records WHERE thread_id IN (${THREAD_IDS})
       UNION ALL SELECT 'token_usage_logs', count(*) FROM token_usage_logs WHERE thread_id IN (${THREAD_IDS});"

  echo
  echo "══════ ④ 用途分布（看得出这轮真跑了图）══════"
  sql "SELECT user_name, purpose, sum(total_tokens) FROM cost_records
       WHERE thread_id IN (${THREAD_IDS}) GROUP BY 1,2 ORDER BY 1,2;"

  echo
  echo "══════ ⑤ 三家当日额度消耗（对照 role）══════"
  for u in isolation_a isolation_b isolation_c; do
    printf "   %-12s " "$u"
    sql "SELECT coalesce(sum(total_tokens),0) || ' token / 今日' FROM cost_records
         WHERE user_name='${u}' AND created_at >= CURRENT_DATE;"
  done
}

if [ "${MODE}" = "check" ]; then run_check; exit 0; fi

# ════════════════════════ seed：清旧 → 跑三段对话 ════════════════════════
echo "──── ① 清理旧痕迹（只删这三个 thread_id 在【今天】的行）────"
for t in cost_records token_usage_logs; do
  sql "DELETE FROM ${t} WHERE thread_id IN (${THREAD_IDS}) AND created_at >= CURRENT_DATE;" >/dev/null
done
echo "   清后残留：cost=$(sql "SELECT count(*) FROM cost_records WHERE thread_id IN (${THREAD_IDS});") tok=$(sql "SELECT count(*) FROM token_usage_logs WHERE thread_id IN (${THREAD_IDS});")"

echo
echo "──── ② 逐家跑真对话（POST ${API_BASE}/agent/mcp_chat）────"
for row in "${CONVERSATIONS[@]}"; do
  IFS='|' read -r user keyvar tid q1 q2 <<<"${row}"
  eval "k=\$$keyvar"
  echo "   ── ${user} ／ thread_id = ${tid} ──"
  for q in "${q1}" "${q2}"; do
    enc=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$q")
    resp=$(curl -sS --max-time 120 -X POST \
            "${API_BASE}/agent/mcp_chat?question=${enc}&thread_id=${tid}" \
            -H "X-API-Key: ${k}")
    echo "${resp}" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if "answer" not in d:
    print("      🔴 失败：" + str(d)); raise SystemExit(1)
print("      👤 " + d.get("question", ""))
print("      🤖 " + d["answer"].strip().replace(chr(10), " ")[:160])
print("      ↳ requested_by=" + str(d.get("requested_by")) + "  thread_id=" + str(d.get("thread_id")))
' || { echo "   🔴 对话失败：${resp}" >&2; exit 1; }
  done
done

echo
echo "──── ③ 复核 ────"
run_check
