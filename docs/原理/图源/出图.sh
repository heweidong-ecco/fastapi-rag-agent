#!/usr/bin/env bash
#
# 出图.sh —— 把本目录的 .mmd 渲染成 docs/*.png
#
# ## 用法
#
#     bash docs/原理/图源/出图.sh            # 全部重出
#     bash docs/原理/图源/出图.sh 02         # 只出文件名含 "02" 的那张
#
# ## 为什么要有它（⛔ 别改成"手画一张贴上去"）
#
# 架构图**一定会烂** —— 本仓有前科：旧图把工具层画成 `rag_search`，而实际是 `fetch_webpage_html`，
# **烂了很久没人知道**（断链门只查路径存不存在，⛔ 不查"图上画的对不对"）。
# ⇒ **图必须是"一条命令能重出的"**，否则下次改动没人会去同步它。
#
# ## 前置
#
# `mmdc`（mermaid-cli）。本机装法（**跳过它自带的 Chromium 下载，复用已有的**）：
#
#     PUPPETEER_SKIP_DOWNLOAD=true npm i -g @mermaid-js/mermaid-cli
#
# ⚠️ 本机的 Chromium 来自 Playwright 的缓存 ⇒ 下面**自动探测**，⛔ 不写死版本号
#    （写死的话，Playwright 升级换了目录名，这脚本就**静默跑不了**）。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"
OUT="${ROOT}/docs"
FILTER="${1:-}"

command -v mmdc >/dev/null 2>&1 || {
  echo "⛔ 没装 mmdc（mermaid-cli）。装法见本脚本头部。" >&2; exit 3; }

# ── 找 Chromium：优先 Playwright 缓存，其次系统 Chrome ──
CHROME="$(find "${HOME}/Library/Caches/ms-playwright" -maxdepth 7 -type f \
            -name "Google Chrome for Testing" 2>/dev/null | sort | tail -1 || true)"
[ -n "${CHROME}" ] || CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "${CHROME}" ] || { echo "⛔ 找不到可用的 Chromium/Chrome（试过 Playwright 缓存与 /Applications）。" >&2; exit 3; }
echo "🔧 Chromium ⇒ ${CHROME}"

PPTR="$(mktemp -t pptrcfg)"
trap 'rm -f "${PPTR}"' EXIT
printf '{"executablePath":%s,"args":["--no-sandbox"]}\n' \
  "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "${CHROME}")" > "${PPTR}"

# ── 逐张渲染 ──
n=0
for src in "${HERE}"/*.mmd; do
  base="$(basename "${src}" .mmd)"
  [ -n "${FILTER}" ] && case "${base}" in *"${FILTER}"*) ;; *) continue ;; esac
  # 文件名 ⇒ 输出名（与 README 里的引用一致）
  case "${base}" in
    00-*) out="architecture.png" ;;
    01-*) out="request-flow.png" ;;
    02-*) out="retrieval-chains.png" ;;
    03-*) out="deploy-topology.png" ;;
    04-*) out="end-to-end.png" ;;
    05-*) out="module-map.png" ;;
    *)    out="${base}.png" ;;
  esac
  echo "🎨 ${base}.mmd  ⇒  docs/${out}"
  mmdc -i "${src}" -o "${OUT}/${out}" \
       -p "${PPTR}" -c "${HERE}/mermaid-config.json" \
       -b white -s 3 --quiet
  n=$((n+1))
done

[ "${n}" -gt 0 ] && echo "✅ 出了 ${n} 张 ⇒ ${OUT}/" || echo "⚠️ 没有匹配的 .mmd"
