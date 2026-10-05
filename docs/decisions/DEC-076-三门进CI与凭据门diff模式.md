# 决策记录：DEC-076 · **把「凭据门 / 断链门 / 孤儿门」接进 CI** + **凭据门新增 `--diff` 模式**

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施**（2026-10-05）—— 待提交 / 待合 |
| **触发** | `docs/待办总表.md` §七·1（本 Agent 自拟候选，业务方 2026-10-05 在两轮选项里**亲口选定**：「把门搬进 CI」→「甲 · 加 `--diff` 模式」） |
| **类型** | 🔴 **接线**（补一个「门存在但没人跑」）· ① 凭据门**加能力**（`--diff`）· ② 修一处**覆盖度过度声明** |
| **落点** | `scripts/check_secrets.sh` · `scripts/test_check_secrets.sh` · `.github/workflows/ci.yml` · `scripts/ci-local.sh` |
| **判据** | `scripts/test_check_secrets.sh`（**17 条**，T11–T17 为本轮新增）· 两道文档门的**负控**（见 §四）· ci-local 逐字跑整块 run |

---

## 一 · 病：**门是真的，但「挂在了别处」**

本仓有四道门住在 `.claude/hooks/pre-commit-gates.py` 里 —— 那是**本地的**，而且：

> ### **`git commit --no-verify` 就能整条绕过。**

`DEC-074`（2026-10-05）已经把**路由鉴权门**接进了 CI。其余三道，**一门都不在 CI 里**：

```bash
# 实测（基线 = 34c26a6，改之前）
git show HEAD:.github/workflows/ci.yml | grep -c check_secrets.sh      # ⇒ 0
git show HEAD:.github/workflows/ci.yml | grep -c check_doc_links.sh    # ⇒ 0
git show HEAD:.github/workflows/ci.yml | grep -c check_doc_orphans.sh  # ⇒ 0
git show HEAD:.github/workflows/ci.yml | grep -c check_route_auth.py   # ⇒ 1  ← DEC-074 接的那道
```

这正是本仓自己那句 **「门挂在别处，就等于没有门」**（`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`）
的又一例 —— 只不过这次"别处"不是另一份文档，而是**另一台机器上的同一个钩子**：
钩子只在**有 `.claude/` 配置的检出**上生效，而 CI 的真值来自**仓库本身**。

### 1.1 附带查出：凭据门的结论行在【过度声明覆盖度】

`check_secrets.sh` 有三节：① 与真实 `.env` 逐字比 · ② 与 `.secret-denylist` 逐字比 · ③ 通用模式。
**没有 `.secret-denylist` 时 ② 整节不跑**（该文件是"可选文件"语义）——
**但结论行把话写死了**：

```bash
echo "✅ 凭据门: 通过 —— 0 命中(覆盖 ①②③)"      # ← ② 没跑也这么写
```

⚠️ **这不是新缺陷，是 `v5 → v6` 那条教训的同型残件**：v6 修的是「① 没跑却声明跑了」，
**没有回头问「同一个形状还有别的入口吗」**。而 **CI 恰恰就是"没有 denylist"的那个环境**
（`.env` 与 `.secret-denylist` **都被 gitignore**）⇒ 那句话会在 CI 里变成**谎话**。

---

## 二 · 决策

### 2.1 放哪：**追加进已有的 `offline-tests` 的 `run:` 块，排在 `pytest` 之前**

⛔ **不新建 job。** 理由与 `DEC-074` 同：两个 job 的**名字就是分支保护的必需检查**，
改 `run:` 块**不碰**分支保护；新建 job 要改（那是**仓外设置**，本 Agent 动不了）。

⚠️ 排在 `pytest` **之前**：本块跑在 `bash -e` 下，**先红的那条会吃掉后面**；
且这四道门都是**秒级**，pytest 是**分钟级**（本仓红过多次）——
放前面才能保证「新引入了没鉴权的路由 / 断链」**一定会被跑到**。

### 2.2 凭据门进 CI 用 **`--diff <range>`**，⛔ 不用 `--all`

| | `--all` | `--diff <base>...<head>` |
|---|---|---|
| 扫什么 | **整个工作区**（含存量行） | 只扫**本 PR 的新增行** |
| 现状 | 🔴 **当场红**（见下） | ✅ 只对"这次写进去的东西"负责 |
| 语义 | 不是"本 PR 引入了什么" | 正是"本 PR 引入了什么" |

`--all` 的实测输出（本仓 2026-10-05）—— **恒红，且 2 处全是良性示例**：

```bash
bash scripts/check_secrets.sh --all
# ⛔ 凭据门: 未通过 —— 2 处命中: pattern:sk-[A-Za-z0-9]{16,} pattern:eyJhbGciOi[A-Za-z0-9_-]{10,}
# 对应位置（git grep 核过）：
#   docs/说明/部署.md:45   DASHSCOPE_API_KEY=sk-<16 个 x>                  ← 文档占位符
#   api/schemas.py:74,80   examples=["eyJhbGciOi…（JWT 示例片段）"]         ← Pydantic 示例串
# 🔴 **上面两行的值【被我改写过、不能逐字照抄】**：
#    本 DEC 的第一版把它们**原样抄了进来** ⇒ **本文档自己命中了这两条通用模式**，
#    提交门当场报红（`❌ 命中通用模式: sk-[A-Za-z0-9]{16,}`）。⇒ 已把中段换成 `<…>`/`…`。
#    ⚠️ **这正是那个古老的坑**：凭据门的前身是"手敲的 grep"，而**记录扫描结果的文档本身**
#    会成为新的泄漏源（见 `scripts/check_secrets.sh` 顶部「为什么要有这个脚本」）。
#    ⛔ 要核对原文，**自己跑那两条 `git grep`**，⛔ 别从本文档里抄。
```

🔑 **凭什么说它们不是真凭据**：**同一次调用里第 ① 节跑了**（本机有 `.env`），
**逐字比对 0 命中** ⇒ 它们与仓库真实凭据**没有一个字相同**。

### 2.3 `--diff` 的两个语法决定

- **范围用三点 `<base>...<head>`，⛔ 不用两点。**
  `git diff A...B` 的基取 `merge-base(A,B)`；而两点在 `git diff` 里等价于 `git diff A B`
  （**端点对端点**）⇒ 主干自己前进的那部分会混成"删除行"，语义就不是"本 PR 的新增行"了。
- **只扫新增行**（保留 `^+`、去掉 `^+++`）—— 同 `v1 → v2` 的教训：**删密钥是好事，不该拦**。
- ⛔ **范围取不到（浅克隆 / 写错）⇒ `exit 2`**，**不许静默压成"空 diff = 通过"**
  （同 `v4 → v5`：门不许退化成 `通过 ⇐ ¬命中`）。

### 2.4 CI 里怎么取范围（5 行，⛔ 不解析事件 JSON）

```bash
SECRETS_RANGE="HEAD~1...HEAD"
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${GITHUB_BASE_REF:-}" ]; then
  SECRETS_RANGE="origin/${GITHUB_BASE_REF}...HEAD"
fi
```

🔑 **为什么 push 那支可以这么简单**：**主干有分支保护** ⇒ **push 到 main 只可能是合并**
⇒ 无论 squash 还是 merge，`HEAD~1...HEAD` 都**正好等于"那个 PR 的全部改动"**
⇒ 那套「解析事件 JSON 取 `before` SHA」（~25 行）**可以整个不要**。

⚠️ **⛔ 别用固定的 `origin/main`**：push 到 main 时它**已被更新成 == HEAD** ⇒ 范围为空 = **假绿**。

### 2.5 检出要 `fetch-depth: 0`（只给 `offline-tests`）

三点范围要 `merge-base`，而**默认浅克隆（depth=1）里既没有 `origin/main` 也没有共同祖先**
⇒ `git diff` 直接报错（门 `exit 2`）。
⛔ **不要改成 `git fetch --depth=1 origin main`** —— depth=1 与 HEAD **无共同祖先**。
⚠️ 代价可忽略：本仓实测 **126 commit / 376 文件 / `size-pack: 0`**。
⛔ `syntax` job 的检出**不动**（它不需要历史）。

### 2.6 CI 里显式降级：`SECRETS_GATE_ALLOW_NO_ENV: "1"`

新鲜检出里**没有 `.env`**（gitignore）⇒ 不设它，门会以 `exit 2`（"扫描未完整执行"）红掉。
设了 ⇒ 走【部分覆盖】那条路，**结论行按实际执行写明覆盖了哪几节**。
⚠️ 这个 `env:` 块被 `scripts/ci-local.sh` **逐字读取**注入 ⇒ 本地与 CI **自动同步，不漂移**。

### 2.7 修覆盖度：**按【实际执行了哪几节】拼，⛔ 不许写死**

加 `COV_ENV` / `COV_DENY` 两个标志，分别在进入 ①/② 两节时置 1；结论行由
`覆盖 ①②③` 改成 `覆盖 ${COVERED}`。

🔴 **CI 里的输出因此变成 `覆盖 ③`** —— ① 和 ② **两节都没跑**，它一次说清两件事。
⚠️ **这里我原先写错过**：计划与本文初稿都写成 `覆盖 ①③`（只想到"CI 没有 denylist"，
忘了 **CI 也没有 `.env`**）⇒ **真跑一遍 CI 形状才纠正过来**，见 §4.1 与 §5.1。

### 2.8 `ci-local.sh`：把 git 指回**主检出**（⛔ 不是绕过门）

`ci-local.sh` 靠 `rsync --exclude='.git'` 复制一棵树来复现 CI 的"没有 `.env`"环境 ⇒
新的凭据门在**临时副本**里会因为"不是 git 仓"而 `exit 2`。修法是**显式**：

```bash
export GIT_DIR="${REPO_ROOT}/.git"
export GIT_WORK_TREE="${REPO_ROOT}"
export GITHUB_EVENT_NAME=pull_request
export GITHUB_BASE_REF=main
```

⇒ 门判的仍是**真实**的提交范围。⛔ 否掉「删掉 `--exclude='.git'`」：
每次要复制几十 MB，还会把 `.git/worktrees` 的元数据一起卷进来。

---

## 三 · 备选与评估（⛔ 都没采纳）

| # | 方案 | 为什么否 |
|---|---|---|
| 1 | 新建一个 CI job 专门跑门 | 要改**分支保护**（仓外设置）；且四道门是秒级，独立 job 只多一份冷启动 |
| 2 | 凭据门在 CI 跑 `--all` | 恒红（§2.2 实测 2 处良性命中）⇒ **红惯了就没人看了** |
| 3 | `--all` + 扩豁免清单 | 要往豁免清单里加**良性示例**；而 `--all` 的语义本来就**不是**"本 PR 新增" |
| 4 | 凭据门整个不进 CI | 它是**后果最重**的一道（`DEC-012` 立它的起因是**真的把 3 个凭据写进了 PUBLIC 文档**） |
| 5 | 解析事件 JSON 取 `before` SHA | 分支保护已让 `HEAD~1...HEAD` 等价，那 ~25 行是**纯增复杂度** |
| 6 | 改 `ci-local.sh` 直接删 `--exclude='.git'` | 每次多复制几十 MB + 卷进 worktree 元数据（§2.8） |

---

## 四 · 判据（**可打印**；⛔ 不接受"退出码 0"当判据）

```bash
# ① 接线确实在 CI 里（不是在 hook 里）
grep -n 'check_secrets.sh --diff\|check_doc_links.sh\|check_doc_orphans.sh\|fetch-depth' .github/workflows/ci.yml
grep -n 'SECRETS_RANGE\|SECRETS_GATE_ALLOW_NO_ENV' .github/workflows/ci.yml
grep -c '\${{' .github/workflows/ci.yml     # ⇒ 0 —— run 块内不许有 GH 表达式（ci-local 要逐字执行）

# ② 凭据门 17 条用例全绿（含负控 T12：范围内合成泄漏 ⇒ exit 1）
bash scripts/test_check_secrets.sh; echo "rc=$?"        # ⇒ 17 通过 / 0 失败, rc=0

# ③ 覆盖度修正生效（⛔ 不再谎称覆盖 ②）
bash scripts/test_check_secrets.sh 2>&1 | grep T16      # ⇒ ✅ 覆盖 ①③

# ④ 两道文档门：绿 + 【负控】（本仓立场：一条测不出"不成立"的守卫 = 没有守卫，DEC-061）
bash scripts/check_doc_links.sh   >/dev/null 2>&1; echo "links=$?"     # ⇒ 0
bash scripts/check_doc_orphans.sh >/dev/null 2>&1; echo "orphans=$?"   # ⇒ 0

# 负控（跑完删掉）。⚠️ 两条纪律：① 样本必须 `git add` —— 两道门都按【已跟踪】的文件枚举；
#   ② 【本文件不写出样本的文件名】—— 那个名字本身就会变成一条真断链，把本判据自己弄红
#      （实测：本 DEC 第一版逐字写了它 ⇒ 断链门立刻报 1 条，来源就是本文档）。
# 做法：造两份样本 —— 一份【正文里指向一个不存在的 .md】（测断链门），
#       一份放进 `docs/说明/`（那是孤儿门认的四个目录之一）且【无人指向它】（测孤儿门）——
#       ⇒ 两门应各 exit 1 并点名各自那份；`git rm --cached` + `rm` 后双双回 0。

# ⑤ ci-local 逐字跑整块 run ⇒ 日志里能看到三道门
bash scripts/ci-local.sh --no-redis 2>&1 | grep -n '凭据门\|没有真断链\|全部有归属'
```

### 4.1 🔴 判据跑出来才发现的（⛔ 不是"读代码看出来的"）

| 发现 | 怎么发现的 |
|---|---|
| **两道文档门按【已跟踪】文件枚举** —— untracked 的新文件**不在扫描范围** | 第一次负控用了 untracked 文件 ⇒ 门**没红**。差点据此得出"门不工作"的错误结论 |
| **`check_doc_links.sh` 只查 `.md` 结尾的路径** | 第二次负控用了 `.sh` ⇒ 门**没红**。⚠️ **是我的负控写错了**，不是门漏了 —— 但这条口径**值得知道**（见 §五） |
| **`check_doc_orphans.sh` 只查 `docs/` 下 契约/说明/原理/规范 四层 + 根级入口** | 第三次负控放在 `docs/` 根 ⇒ 门**没红**；挪进 `docs/说明/` 才红 |
| 🔴 **`ci-local.sh` 里 `` `DEC-076` `` 写在双引号里 ⇒ 被当命令替换执行** | **⑥ 真跑了一次**才发现（`DEC-076: command not found`），**读代码看不出来**。正是本仓 2026-10-01 记过的那条（判据里用「」，⛔ 不用 ASCII 反引号） |
| 🔴 **`${GIT_DIR}` 在横幅里被引用，而导出语句在横幅之后 + 脚本是 `set -u`** ⇒ 脚本**中途死掉**，而外层因末尾有 `echo` 报了 `rc=0` | 同上。⚠️ **这就是"退出码 0 ≠ 跑完了"的活例** |
| 🔴 **CI 的覆盖度是 `③`，不是 `①③`** —— 我（计划 + 本文初稿）**两次都写成 `①③`**，只想到"CI 没有 denylist"，**忘了它也没有 `.env`** | 按 §5.1 那条命令**真造了一个 CI 形状的仓根**跑。⇒ 已补测试 **T17** 钉住这个真形状 |
| 🔴 **`make_diff_shims` 那个【不加引号的 heredoc】体内，一句【注释】里的反引号被执行了** —— 生成 shim 时真的跑了一次 `git diff --cached`，把**整个暂存区 diff（59.5 KB）**塞进 shim 正文、把 `case` 结构冲烂 ⇒ shim 一跑就是 **bash 语法错误 = exit 2** | 提交前复跑 `bash scripts/test_check_secrets.sh` 才现形：**12 通过 / 5 失败**。⚠️ 而**两条「期望 exit 2」的用例（T13/T15）反倒撞巧变绿** —— 语法错误的 2 与「范围取不到」的 2 **不可区分**，正是本表第 1 行那个形状的镜像。⇒ 已在函数体注释与 heredoc 上方各加一条硬约束 |

> 📌 **这一节是本 DEC 里最该被读的部分**：五条判据里有四条**第一次都写错了**，
> 而且**错的方向一致** —— **我以为是门坏了，其实是负控没打中。**
> ⇒ **判据红了要问的第一句是「我打中它了吗」，⛔ 不是「它坏了吗」。**
>
> 🔴 **最后一行还多给一条**：那句反引号是我**在写注释、以为「只是文字」的时候**写进去的 ——
> **注释也会被执行**（在【不加引号】的 heredoc 体内、或在双引号串里）。
> 同族前科：`ci-local.sh` 那次（本表第 4 行）。⇒ **凡在 `<<EOF`（不带引号）或 `"…"` 里写
> 反引号 / `$`，先问一句「这里会不会被展开」。**

> 📌 **这一节是本 DEC 里最该被读的部分**：四条判据里有三条**第一次都写错了**，
> 而且**错的方向一致** —— **我以为是门坏了，其实是负控没打中。**
> ⇒ **判据红了要问的第一句是「我打中它了吗」，⛔ 不是「它坏了吗」。**

---

## 五 · 遗留与边界（⛔ 不许读成"全好了"）

### 5.1 🔴 CI 的凭据门**实际只跑第 ③ 节**

`.env` 与 `.secret-denylist` **都被 gitignore** ⇒ 进不了仓 ⇒ **CI 里只跑【③ 通用模式】**，
① 与 ② **两节都不跑**。
⇒ **CI 的防护语义是**「**PR 的新增行里没有明显密钥形状**」，
⛔ **不是**「和这个仓库的真实凭据逐字比过」。
⇒ 结论行会写成 **`覆盖 ③`**（本轮修的），⛔ **不许再读成"全查过了"**。

📌 **实测判据（可打印）** —— 造一个真正没有 `.env`/denylist 的仓根，跑 CI 那套 env：

```bash
R=/Users/heweidong/Desktop/Product/agent-projects/projects/fastapi-rag-agent
T=$(mktemp -d); mkdir -p "$T/scripts"; cp "$R/scripts/check_secrets.sh" "$T/scripts/"
# 不设降级开关 ⇒ 2 ; 设了 ⇒ 0 且只声明覆盖 ③
( cd "$T" && env GIT_DIR="$R/.git" GIT_WORK_TREE="$R" \
    bash "$T/scripts/check_secrets.sh" --diff 'HEAD~1...HEAD' >/dev/null 2>&1; echo "rc=$?" )
( cd "$T" && env GIT_DIR="$R/.git" GIT_WORK_TREE="$R" SECRETS_GATE_ALLOW_NO_ENV=1 \
    bash "$T/scripts/check_secrets.sh" --diff 'HEAD~1...HEAD' 2>&1 | grep '覆盖' )
# ⇒ ⚠️ 覆盖度: ① 未执行(无 .env) —— 本次结果**仅覆盖 ③**
rm -rf "$T"
```

### 5.2 本轮**登记但没修**的

| # | 东西 | 是什么 | 为什么不动 |
|---|---|---|---|
| 1 | `--all` 的 2 处假阳性 | `docs/说明/部署.md:45` · `api/schemas.py:74,80` | 本轮用 `--diff` **绕开**了它；这两处**本身没修**（本仓规矩：登记，⛔ 不顺手清） |
| 2 | `check_doc_orphans.sh` 缺 `.claude/worktrees/` 剪枝 | `check_doc_links.sh` 有这条路径前缀剪枝，孤儿门没有 | 只在本地（有 worktree）有影响，**CI 是干净检出** |
| 3 | 🔴 **`docs/DEC-选型模板.md` 不存在** | 实测 `ls` 与 `git ls-files` **都为空**，而 outward-guard 钩子的提示里指着它 ⇒ **悬空指针** | 同上，登记不修 |
| 4 | 两道文档门**只扫已跟踪文件** | 见 §4.1 | 对 CI 无影响（CI 跑在提交上）；⚠️ 但**本地**用它当提交前判据时要知道这条 |

### 5.3 已知局限：`ci-local.sh` 里若你**正停在 `main` 上**，凭据门的范围为空

`HEAD == origin/main` ⇒ `origin/main...HEAD` 为空 ⇒ 门报 ✅。
那个 ✅ **是真的**（确实没有本分支新增行），但**不等于你刚改的东西被扫过** ——
那些改动还在工作区/暂存区里。⇒ 想核对未提交的改动，用**不带参数**的
`bash scripts/check_secrets.sh`（扫暂存区）。

---

## 六 · 反悔成本

| 决定 | 反悔要做什么 | 成本 |
|---|---|---|
| 三门进 CI | 从 `ci.yml` 删那三行 | 低 —— 但**等于把门重新变成可 `--no-verify` 绕过的** |
| 用 `--diff` 而非 `--all` | 把 `--diff "${SECRETS_RANGE}"` 换成 `--all`（**当场合红**） | 低（改一行），但要把 2 处假阳性列进豁免清单 |
| `fetch-depth: 0` | 删掉那两行 | **低** —— 本仓 `size-pack: 0`，慢不了多少 |
| `SECRETS_GATE_ALLOW_NO_ENV=1` | 删掉那行 | **低**，但会**恒红**（CI 没有 `.env`） |
| 覆盖度改成动态 | 把 `${COVERED}` 改回写死的 `①②③` | 低 —— 但那是**主动选择说假话** |
| `ci-local.sh` 指回主检出 | 删掉那 4 行 `export` | 低 —— 但凭据门会在 ci-local 里**恒红** |
