#!/usr/bin/env bash
#
# list_endpoints.sh —— 列出本服务【当前真实存在】的接口
#
# ## 为什么要有它
#
# 本仓 ROADMAP 的规矩：**接口清单【不写进文档】**。
# 理由是手写的清单**必然过期** —— 本仓有现成的反例：
# `CLAUDE.md` 里那张路由表已经跟实际对不上了（见 `docs/复盘/2026-09-29-结果为空就断言能力不存在.md`）。
#
# ⇒ 谁要看接口，**跑这条命令**。数据源是运行中的服务自己的 `/openapi.json`，
#    FastAPI 从装饰器生成，**不可能过期**。
#
# ## 用法
#
#     bash scripts/list_endpoints.sh                      # 默认 http://127.0.0.1:8000
#     bash scripts/list_endpoints.sh http://host:8000     # 指定别的地址
#     bash scripts/list_endpoints.sh | grep agent         # 只看 agent 相关
#
# ⚠️ 服务没起来时会明确报错退出，不会静默输出空清单。
#
# ## ⚠️ 本脚本踩过的两个坑（**改它之前先读**）
#
# ① **中文全角标点【紧贴】变量名 ⇒ `set -u` 报 unbound variable**
#    实测：`echo "取不到 $URL （HTTP $code）"` ⇒ 报 `code<乱码字节>: unbound variable`。
#    根因：中文 locale 下 bash 把全角括号的前导字节当成了**标识符的一部分**。
#    ✅ **规矩：变量后面凡是紧跟非 ASCII 字符，一律写 `${VAR}`**（花括号定界）。
#    📌 这与 `CLAUDE.md`「判据」六条第 6 条同族（那条讲的是引号，这条讲的是标点）。
#
# ② **`cmd | python3 - <<'PY'` 里，heredoc 会【抢走 stdin】，管道失效**
#    实测：python 读到的是脚本本身，报 `JSONDecodeError: Expecting value: line 1 column 1`。
#    ✅ **规矩：要喂 JSON 给 python，先落临时文件，再把【路径】当参数传**（见下方）。
#
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
URL="${BASE%/}/openapi.json"

# ---- 先确认服务可达（判据：HTTP 码，不是"我以为它在跑"）----
# ⚠️ 这里**不能**写 `curl ... || echo 000` —— curl 连不上时自己就会往 stdout 打 `000`，
#    再加一个 `|| echo 000` 会拼成 `000000`（实测踩过）。改为只在**完全没输出**时兜底。
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "${URL}" || true)"
code="${code:-000}"
if [ "${code}" != "200" ]; then
  # ⚠️ 下面这些 ${} 不是多余的 —— 见文件头「坑①」
  echo "❌ 取不到 ${URL}   （HTTP ${code}）" >&2
  echo "" >&2
  echo "   服务起来了吗？判据：" >&2
  echo "     docker compose ps                              # 看 rag-api 是否 Up" >&2
  echo "     curl -s -o /dev/null -w '%{http_code}\\n' ${BASE}/health" >&2
  exit 1
fi

# ---- 落临时文件（**不要用管道**，见文件头「坑②」）----
tmp="$(mktemp -t openapi)"
trap 'rm -f "${tmp}"' EXIT
curl -s --max-time 15 "${URL}" -o "${tmp}"

# ---- 解析并分组 ----
# 分组口径：路径里 /api/v1/<这里> 那一段；没有则取第一段。
# ⚠️ 不用 OpenAPI 自带的 tags —— 实测 57 个端点里 **36 个没有 tag**，分组会变成一坨。
python3 - "${BASE}" "${tmp}" <<'PY'
import sys, json

base, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    d = json.load(fh)

paths = d.get("paths", {})
METHODS = ("get", "post", "put", "delete", "patch")
groups = {}

for p in sorted(paths):
    for m in paths[p]:
        if m not in METHODS:
            continue
        op = paths[p][m]
        seg = [s for s in p.split("/") if s]
        # /api/v1/<g>/...  ->  g ；否则取第一段
        g = seg[2] if len(seg) >= 3 and seg[1] == "v1" else (seg[0] if seg else "(root)")
        groups.setdefault(g, []).append(
            (m.upper(), p, (op.get("summary") or "").strip())
        )

info = d.get("info", {})
total = sum(len(v) for v in groups.values())

print(f"服务      : {base}")
print(f"API 标题  : {info.get('title')}  版本 {info.get('version')}")
print(f"数据源    : {base}/openapi.json   （FastAPI 从装饰器生成，不会过期）")
print(f"端点总数  : {total}")
print()

for g in sorted(groups, key=lambda k: (-len(groups[k]), k)):
    items = groups[g]
    pad = "-" * max(1, 46 - len(g) - len(str(len(items))))
    print(f"--- {g}  ({len(items)}) {pad}")
    for m, p, s in items:
        print(f"  {m:6} {p:48} {s[:52]}")

print()
print(f"合计 {total} 个端点，分 {len(groups)} 组。")
PY
