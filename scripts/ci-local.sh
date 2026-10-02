#!/usr/bin/env bash
#
# ci-local.sh —— **在本机复现 CI `offline-tests` 的环境**
#
# ## 它治什么病
#
# **2026-10-01**：`8a5672b` 推上去后 CI 红，而**本地是绿的**。
# 红的那条测试断言「兜底单价 >= 在用模型单价」—— 它**在两种合法部署下答案相反**：
#
#   · 本机：`.env` 里 `LLM_MODEL_CHAT=deepseek-v4-flash`（0.001/0.002）⇒ `0.003 >= 0.001` **过**
#   · CI ：**没有 `.env`** ⇒ `api/config.py:55` 的代码默认值 `qwen-plus`（0.008/0.016）⇒ **红**
#
# ⇒ 根因**不是"CI 玄学"**，是**本地和 CI 是两套环境**。
#   ⚠️ `docs/说明/测试.md` §五 原先只写「CI 跑的是本地命令的子集」——
#      那句话**对"选哪些测试"成立，对"跑在什么环境里"不成立**。（已在该文件 §5.1 更正）
#
# ## 三条轴 · 本脚本对齐了哪两条
#
#   | 轴      | 本机（原先）          | CI                          | 本脚本                    |
#   |---------|-----------------------|-----------------------------|---------------------------|
#   | Redis   | **没有** ⇒ 15 条红    | `redis:7` service 容器（**一次性 pristine**） | 🟡 **复用 `redis-rag`**（长期容器，**不是** pristine —— 见下） |
#   | `.env`  | **有**（真实模型名）  | **没有** ⇒ 落代码默认值     | ✅ **rsync 掉**            |
#   | 依赖    | 本机 venv             | 干净 ubuntu + requirements  | ⛔ **不管**（用你现有 venv）|
#
# ⚠️ **第三条轴本脚本【不复制】** —— 它不跑 `pip install`，用你现有的 venv。
#    ⇒ **"依赖版本"这一层不等价。** 没复现的就明说 —— 见运行时横幅。
#
# ## 🔴 Redis 这一轴：**本机用的是 `redis-rag`，不是新起的容器**（2026-10-02 更正）
#
# 本脚本**原先**会 `docker run --rm --name raci-ci-local-redis` 起一个跑完就删的容器。
# **实测：那条路在本机【一次都没走过】** —— 因为 `ci.yml:114` 把 `REDIS_PORT` 钉死成 `6379`，
# 而本机 `6379` **长期被项目自己的 `redis-rag` 占着**（`127.0.0.1:6379->6379/tcp`）。
# ⇒ `redis_up` 永远为真 ⇒ 永远走"复用"分支 ⇒ **`raci-ci-local-redis` 从来没被创建过**。
#
# 业务方 2026-10-02 裁定：**就认 `redis-rag`** —— 把它当作本机那个 CI redis，按**名字**管理：
#   * 在跑 ⇒ 复用（⛔ 不新建、不抢占 6379）
#   * 停了 ⇒ `docker start redis-rag`
#   * **⛔ 永不删除它**（不再有 `--rm`、不再有 `docker rm -f`）
#   * 镜像以 `ci.yml` 的 `services.redis.image` 为准；**不一致只提示，⛔ 不擅自重建**
#
# ⚠️ **代价（照实说）**：`redis-rag` 是**长期容器**，里头可能留着上一轮/开发期攒下的 key，
# 而 CI 的 service 容器**每次都是全新空的**。⇒ **这一层不等价**，横幅里会打出来。
#
# ## 用法
#
#     bash scripts/ci-local.sh                    # 复用 redis-rag + 无 .env + 跑 CI 那一步
#     bash scripts/ci-local.sh --keep             # 跑完不删临时目录（查现场）
#     bash scripts/ci-local.sh --no-redis         # 不碰 docker（假定 6379 已经有人）
#     bash scripts/ci-local.sh --no-syntax        # 跳过 compileall（syntax job）
#     CI_LOCAL_PYTHON=/path/to/python bash scripts/ci-local.sh     # 指定解释器
#
# ## 判据（**可打印** —— 这才是"环境对上了"）
#
#   1. **跑出来的数字 == CI 日志里的数字**（例：`139 passed, 3 skipped, 11 deselected`）。
#      ⛔ **别只看"绿了"** —— 绿了但条数不同，说明还是两套环境。
#   2. ⭐ **它自证 `.env` 已不在场**：横幅会打印**生效的** `LLM_MODEL_FAST/CHAT`。
#      若你本机 `.env` 写的是 `deepseek-*` 而这里打印 `qwen-turbo/qwen-plus`
#      ⇒ **代码默认值生效 ⇒ `.env` 确实被拿掉了**。这就是自证。
#
# ## ⚠️ 为什么是「rsync 到临时目录」而不是「设个环境变量」
#
# `python-dotenv` 默认**不覆盖**已存在的环境变量 ⇒ **你没法用 `export` 把 `.env` 里
# 已经存在的键"取消"**。要真正模拟"没有 `.env`"，只能让**那个文件在那个路径上不存在**。
# ⇒ `api/config.py:12` 读的是 `dirname(config.py)/../.env`（**写死的相对位置**）
#   ⇒ 把整棵树复制到别处、**唯独不带 `.env`**，是唯一忠实的做法。
#
# ## 设计说明
#
# 1. ⭐ **跑的是 ci.yml 里那一【整块 `run`】** —— ⛔ 不是本脚本自己拼的命令。
#    GitHub Actions 执行 `run:` 的方式就是「写进临时脚本 + `bash -e` 执行」，
#    **本脚本照做**（`bash -e "$RUN_SH"`）⇒ 连"改 ci.yml 忘了同步本脚本"都不会发生，
#    而且 ci.yml 里那段"打印生效配置"（2026-10-01 加）**也被当场执行**，不用等推上去才发现写错。
# 2. **环境变量也从 ci.yml 读**（同一块 step 的 `env:`）—— 不在本脚本里另抄一份。
#    两份清单必然漂移（本仓已立此立场：「一份内容只在一处」）。
# 3. **临时目录里没有 `.git`** —— 已核过 `api/` 不下调 git。若将来有测试要 git，
#    它会**响亮地失败**，而不是静默跳过。
# 4. **本脚本不替代 CI** —— 它是**把发现提前**，⛔ 不是"本地绿了就不用看 CI"。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CI_YML="${REPO_ROOT}/.github/workflows/ci.yml"
JOB="offline-tests"
REDIS_CONTAINER="${CI_LOCAL_REDIS_CONTAINER:-redis-rag}"   # 🔴 本机 CI 用的 redis = 项目自己的那个容器
                              #    （业务方 2026-10-02 裁；⛔ 别改回 `docker run --rm` 那套 —— 见文件头）
                              #    `CI_LOCAL_REDIS_CONTAINER` 是**测试用**的覆盖口：
                              #    拿它指向一个不存在的名字 ⇒ 能验「不存在」那条分支，⛔ 不必去停真的 redis-rag

KEEP=0
USE_REDIS=1
RUN_SYNTAX=1
for a in "$@"; do
  case "$a" in
    --keep)      KEEP=1 ;;
    --no-redis)  USE_REDIS=0 ;;
    --no-syntax) RUN_SYNTAX=0 ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

# ---------- 0. 找解释器 ----------
PY="${CI_LOCAL_PYTHON:-}"
if [ -z "${PY}" ]; then
  if [ -x "${REPO_ROOT}/venv/bin/python" ]; then
    PY="${REPO_ROOT}/venv/bin/python"
  else
    PY="$(command -v python3 || true)"
  fi
fi
if [ -z "${PY}" ] || [ ! -x "${PY}" ]; then
  echo "❌ 找不到可用的 Python。用 CI_LOCAL_PYTHON=/path/to/python 指定。" >&2
  exit 2
fi
if ! "${PY}" -c "import yaml" 2>/dev/null; then
  echo "❌ ${PY} 里没有 pyyaml —— 本脚本靠它从 ci.yml 读命令与环境（有意，见设计说明 ②）。" >&2
  exit 2
fi
PY_BIN_DIR="$(cd "$(dirname "${PY}")" && pwd)"
# ⚠️ `run` 块里写的是裸 `pytest` / 裸 `python` ⇒ 必须让它们解析到**这个**解释器
#    （CI 上它们就是系统 python；本机是 venv）。否则会跑到另一个环境的 python 上。
export PATH="${PY_BIN_DIR}:${PATH}"

# ---------- 1. 从 ci.yml 读【真相】 ----------
# ⚠️ `XXXXXX` 必须放在模板**末尾** —— macOS(BSD) 的 mktemp 不认"X 在中间"的模板，
#    会把它当**字面文件名**（2026-10-01 实测踩过：横幅里打出 `…step.XXXXXX.sh` 才发现）。
RUN_SH="$(mktemp "${TMPDIR:-/tmp}/raci-ci-step.XXXXXX")"
ENV_PAIRS="$("${PY}" - "${CI_YML}" "${JOB}" "${RUN_SH}" <<'PY'
import sys, yaml
path, job, out = sys.argv[1], sys.argv[2], sys.argv[3]
doc = yaml.safe_load(open(path, encoding="utf-8"))
steps = doc["jobs"][job]["steps"]
target = next((s for s in steps if "pytest" in (s.get("run") or "")), None)
if target is None:
    sys.exit(f"{path} 的 jobs.{job} 里没找到跑 pytest 的步骤")
run = target["run"]
if not any(l.strip().startswith("pytest") for l in run.splitlines()):
    sys.exit(f"{path} 的 jobs.{job}：run 块里没有以 pytest 开头的行 —— ci.yml 改了形状，"
             f"本脚本要跟着改，⛔ 不许猜。")
open(out, "w", encoding="utf-8").write(run)
for k, v in (target.get("env") or {}).items():
    print(f"{k}={v}")
PY
)" || { echo "❌ 从 ci.yml 读命令/环境失败。" >&2; rm -f "${RUN_SH}"; exit 2; }
# ⚠️ 两副面孔，各有用途：
#   · `ENV_PAIRS` = **换行分隔**（打印给人看；未加引号时按 IFS 切词，喂 `env` 也对）
#   · `ENV_FLAT`  = **空格分隔**（喂 `env` 时用它，避开换行带来的歧义）
ENV_FLAT="$(printf '%s\n' "${ENV_PAIRS}" | tr '\n' ' ')"
PYTEST_LINE="$(grep -m1 -E '^[[:space:]]*pytest' "${RUN_SH}" | sed 's/^[[:space:]]*//')"

# ⚠️ redis 的**镜像**也从 ci.yml 读（它是 `services:` 段，不在上面那块 run/env 里）。
#    用途：拿它和 `redis-rag` 实际用的镜像比 —— 不一致时**提示**（⛔ 不擅自重建那个容器）。
CI_REDIS_IMAGE="$("${PY}" - "${CI_YML}" "${JOB}" <<'PY'
import sys, yaml
path, job = sys.argv[1], sys.argv[2]
doc = yaml.safe_load(open(path, encoding="utf-8"))
svc = (doc["jobs"][job].get("services") or {}).get("redis") or {}
img = svc.get("image")
if not img:
    sys.exit(f"{path} 的 jobs.{job} 里没有 services.redis.image —— ci.yml 改了形状，"
             f"本脚本要跟着改，⛔ 不许猜。")
print(img)
PY
)" || { echo "❌ 从 ci.yml 读 services.redis.image 失败。" >&2; exit 2; }

# ---------- 2. Redis：**复用 `redis-rag`**（⛔ 本脚本不再新建、不再删除容器） ----------
# 业务方 2026-10-02 裁：「就认 redis-rag」。理由与代价见文件头「Redis 这一轴」。
redis_up() { nc -z 127.0.0.1 6379 >/dev/null 2>&1; }

# 6379 的占用者是哪个【容器】（不是容器 ⇒ 空）
redis_owner() {
  docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null \
    | awk -F'\t' '$2 ~ /127\.0\.0\.1:6379->/ {print $1; exit}'
}
container_exists() { docker inspect -f '{{.Name}}' "$1" >/dev/null 2>&1; }
container_image()  { docker inspect -f '{{.Config.Image}}' "$1" 2>/dev/null || echo "?"; }

REDIS_NOTE=""   # 给横幅用：这一轴到底对齐到什么程度（仅在不对齐时非空）
cleanup() {
  # ⛔ **不再 `docker rm`** —— redis 容器是长期资产，跑完留着（业务方 2026-10-02 裁）。
  rm -f "${RUN_SH:-}"
  if [ "${KEEP}" = "0" ] && [ -n "${TMP:-}" ]; then
    rm -rf "${TMP}"
  fi
}
trap cleanup EXIT

if [ "${USE_REDIS}" = "1" ]; then
  if redis_up; then
    owner="$(redis_owner)"
    if [ "${owner}" = "${REDIS_CONTAINER}" ]; then
      echo "ℹ️  6379 已在听，占用者就是「${REDIS_CONTAINER}」⇒ 复用（⛔ 不新建、不删除）。"
    elif [ -n "${owner}" ]; then
      echo "⚠️  6379 已在听，但占用者是「${owner}」，不是「${REDIS_CONTAINER}」⇒ 照用（不对齐会在横幅里打出来）。"
    else
      echo "⚠️  6379 已在听，但它不是 docker 容器（宿主机上直接跑的？）⇒ 照用。"
    fi
  else
    # 6379 没人听 ⇒ 把 redis-rag 拉起来（⛔ 不新建别的容器）
    command -v docker >/dev/null 2>&1 || {
      echo "❌ 需要 docker 来起 redis（或先自己起一个，再用 --no-redis 跳过本步）。" >&2; exit 2; }
    # ⚠️ 本仓章程：有评测在跑时不许起容器（DEC-033）。
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q eval; then
      echo "🔴 有评测在跑（docker ps 里有 eval）—— 本仓章程不允许此时起容器，已中止。" >&2
      exit 2
    fi
    container_exists "${REDIS_CONTAINER}" || {
      echo "🔴 容器「${REDIS_CONTAINER}」不存在，而本脚本【不会替你新建】。" >&2
      echo "   它由 docker-compose.yml 的 redis 服务定义（127.0.0.1:6379）。建它：" >&2
      echo "     docker compose up -d redis" >&2
      echo "   ⚠️ 只 up redis —— ⛔ 别顺手 up postgres（容器重建会换网络名，打断 agent-eval-gate）。" >&2
      exit 2
    }
    echo "→ 拉起「${REDIS_CONTAINER}」（本机 CI 的那个 redis；⛔ 跑完不删）…"
    docker start "${REDIS_CONTAINER}" >/dev/null
    for _ in $(seq 1 30); do redis_up && break; sleep 0.5; done
    redis_up || { echo "❌ docker start ${REDIS_CONTAINER} 之后 6379 仍不通。" >&2; exit 2; }
  fi

  # 镜像对齐（**只提示，⛔ 不擅自重建长期容器**）
  actual_image="$(container_image "${REDIS_CONTAINER}")"
  if [ "${actual_image}" != "${CI_REDIS_IMAGE}" ]; then
    REDIS_NOTE="不是 CI 那个镜像：本机 ${REDIS_CONTAINER} 用 ${actual_image}，ci.yml 写的是 ${CI_REDIS_IMAGE}（只提示，⛔ 不擅自重建长期容器）"
  fi
fi

# ---------- 3. 复制工作副本，但【不带 .env】 ----------
# ⚠️ 排除 `.claude/worktrees` —— 否则从主检出运行时会把这个 worktree 递归抄进去。
TMP="$(mktemp -d "${TMPDIR:-/tmp}/raci-ci-local.XXXXXX")"
rsync -a \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.claude/worktrees' \
  --exclude='venv' --exclude='venv-ragas' --exclude='.venv' \
  --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.pytest_cache' --exclude='.mypy_cache' \
  --exclude='node_modules' --exclude='htmlcov' \
  "${REPO_ROOT}/" "${TMP}/"

# ---------- 4. 自证 + 横幅 ----------
[ ! -e "${TMP}/.env" ] || { echo "❌ 临时目录里居然有 .env —— rsync 排除没生效。" >&2; exit 2; }

echo
echo "==================== ci-local · 本次复现的边界 ===================="
echo "  仓        : ${REPO_ROOT}"
echo "  临时副本  : ${TMP}"
echo "  解释器    : ${PY}  ($("${PY}" -V 2>&1))"
echo "  ✅ 已对齐 : .env（**已拿掉**）· run 块（**整块照抄 ci.yml**）"
if [ "${USE_REDIS}" = "1" ]; then
  echo "             Redis 有得用（复用「${REDIS_CONTAINER}」，端口按 ci.yml 的 6379）"
  echo "  ⛔ 未对齐 : Redis 是【长期容器】—— ⛔ 不是 CI 那种「每次全新空」的一次性 service 容器，"
  echo "             里头可能留着开发期/上一轮攒下的 key"
  if [ -n "${REDIS_NOTE}" ]; then echo "             ${REDIS_NOTE}"; fi
else
  echo "  ⛔ 未对齐 : Redis（--no-redis：假定 6379 已经有人）"
fi
echo "  ⛔ 未对齐 : 依赖安装（用你现有 venv，**没跑 pip install -r**）"
echo "             OS / 镜像（本机 macOS，CI 是 ubuntu-latest）"
echo "------------------------------------------------------------------"
echo "  跑的是 ci.yml jobs.${JOB} 那一【整块 run】（${RUN_SH} 的内容）:"
sed 's/^/    | /' "${RUN_SH}"
echo "  环境变量（同一步的 env 段，共 $(printf '%s\n' "${ENV_PAIRS}" | grep -c . || true) 个）:"
printf '%s\n' "${ENV_PAIRS}" | sed 's/^/    /'
echo "------------------------------------------------------------------"
echo "  ⭐ 自证「.env 不在场」—— 下面是【临时副本里实际生效】的模型名："
( cd "${TMP}" && env ${ENV_FLAT}"${PY}" -c \
    "import sys; sys.path.insert(0,'api'); import config; print('    LLM_MODEL_FAST =', config.LLM_MODEL_FAST); print('    LLM_MODEL_CHAT =', config.LLM_MODEL_CHAT)" \
    ) || echo "    （打印失败，见上方报错）"
if [ -f "${REPO_ROOT}/.env" ]; then
  echo "  本目录 .env 里写的（作为对照）："
  grep -E '^[[:space:]]*LLM_MODEL_(FAST|CHAT)[[:space:]]*=' "${REPO_ROOT}/.env" | sed 's/^/    /' || true
  echo "  ⇒ **上面两处不一样，就说明 .env 确实没被带进来**（本次红/绿是按【上半】那套算的）。"
else
  echo "  ⚠️ 本目录没有 .env —— 上面那套就是 CI 的那套（代码默认值）。"
fi
echo "=================================================================="
echo

# ---------- 5. 跑（在临时副本里，整块 run） ----------
cd "${TMP}"

if [ "${RUN_SYNTAX}" = "1" ]; then
  # syntax job（另一个 job）也照抄 ci.yml —— 它跟 offline-tests 是并行的两个 job
  echo "→ [syntax job] python -m compileall api/ -q"
  "${PY}" -m compileall api/ -q
  echo "  ✅ syntax 过"
  echo
fi

echo "→ [${JOB}] 执行 ci.yml 的 run 块（其中 pytest 那行是：${PYTEST_LINE}）"
echo
set +e
env ${ENV_FLAT} bash -e "${RUN_SH}"
RC=$?
set -e

echo
if [ "${RC}" = "0" ]; then
  echo "✅ ci-local 通过（退出码 0）。"
  echo "   ⚠️ 这**不等于** CI 一定过 —— 见上方「未对齐」那两条。"
else
  echo "🔴 ci-local 失败（退出码 ${RC}）—— **这个红，就是 CI 会红的那个**。"
fi
[ "${KEEP}" = "1" ] && echo "  （临时副本已保留：${TMP}）"
exit "${RC}"
