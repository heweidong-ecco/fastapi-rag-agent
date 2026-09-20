# 决策记录：DEC-022 · `archive/` 该入多少进 git

- 日期：2026-09-20
- 状态：**已采纳并执行**
- 关联：`docs/待办登记-2026-09-20-全仓审计与方向更正.md` §四·**4**（原「唯一还没裁的一条」）

## 决策事项

`archive/` 被 `.gitignore` 挡住（`git ls-files archive/` = 0），但 `CHANGELOG`/`ROADMAP`/`CODE_INVENTORY`
**都在引用它** —— 克隆者拿不到、文档却在引用。**该入多少进 git？**

**业务方原话**：「**RAGAS，archive/ 是全部入库吗？有必要吗**」

## 背景与约束

- **审计给的原始两条路**：① `git add -f archive/` 整体入库 ② 改掉那几处引用。**两条都没被采纳。**
- **`archive/` 实测 3.8 MB**，构成极不均衡：

  | 内容 | 大小 | 占比 |
  |---|---:|---:|
  | `original-agent/docs/*.png`（2 张架构图） | 2.6 MB | 68% |
  | `original-logs/`（13 个运行日志） | 1.0 MB | 26% |
  | 其余全部（脚本 + 数据集 + 报告 + 文档） | ~0.2 MB | 6% |

- **约束一**：`.gitignore` 排除 `archive/` 是**有意设计** —— `archive/README.md` 自述
  「本目录已加入 `.gitignore`，**不会提交到 git**」，与 README 的「**轻量版**」定位一致。
- **约束二**：业务方向是「**完整明了、简洁的交付**」（`待办登记` §〇），**不是"把所有历史塞进仓库"**。
- **约束三**：本仓是 **PUBLIC**。往里加东西要先过凭据门。
- **判据**：**「删了谁会要加回？」** —— 逐项过一遍。

## 备选方案

| 方案 | 一句话 | 大小 |
|---|---|---|
| **甲 · 只入 RAGAS 4 件套**（**采纳**） | 只把有对外承诺支撑的那条链路移进 `api/` | **51 KB** |
| 乙 · 只改引用，不入库 | 保留库外状态，把文档里所有引用改成「未随本次交付入库」 | 0 |
| 丙 · 整体入库 | `git add -f archive/` | 3.8 MB |

**逐项判据（决定甲为什么只含 4 个文件）**：

| 内容 | 判据结论 | 甲的处理 |
|---|---|---|
| **RAGAS 4 件套** | README 技术栈表**列了它** · `requirements.txt` **装着它** · ROADMAP M7 **写着复跑** ⇒ **背着一个对外承诺** | ✅ **入** |
| `data_retention.py` | ⚠️ `CODE_INVENTORY` §8 说它是 `db.py` 里 `cost_records_archive` 表的**唯一操作者** ⇒ 删了那张表永远是死表 | ❌ 本次未入（**见下方「遗留」**） |
| `experiment_chunking` / `extract_financial_table` / `seed_documents` | 都依赖本地 PDF / 跑着的服务，实验脚本 | ❌ |
| `tool_health_1.0.0.py` · `drafts/requirements.in` · `artifacts/rag-api-*.json` | 旧版快照 / 过时草稿 / 导出快照 | ❌ |
| `original-agent/` 7 文件 | **已在 git 历史 `2c1a922` 里**（且该提交**可达**、`gc` 不会删）⇒ 入库**不增加任何保障** | ❌ |
| `original-logs/` 13 日志 | 运行日志；`.gitignore` 本来就有 `*.log` | ❌ |
| `original-notes/重构目录表.txt` | 原系统目录表 | ❌ |

## 决策与理由

**甲。** 三条理由：

1. **只有 RAGAS 一条能过「删了谁会要加回」这把尺子** —— 其余 3.7 MB 按同一把尺子过，没有一条能过。
2. **丙会推翻一层有意设计** —— `archive/` 被 gitignore 与「轻量版」定位是配套的；
   整体入库等于把这层设计作废，**且把 1 MB 运行日志塞进 PUBLIC 仓**。
3. **乙是假的两条路中的一条** —— 但 RAGAS 那条链路**有真实的历史评估证据**（2026-06-29 跑出的分数），
   直接放弃评估能力过于可惜；`CODE_INVENTORY` §8 也早就建议「恢复进 `api/`」。

**🔴 执行时新增的一项约束（原方案里没有）**：脚本原本**内置默认登录口令**，而该字面量
**在 `.secret-denylist` 黑名单里** ⇒ **不修就过不了凭据门**。已改为从环境变量读
（`LOGIN_USER_NAME` / `LOGIN_PASSWORD`，**不设可用默认值**），并在 `get_auth_token()` 加快速失败提示。
（📌 讽刺的是，我第一版**在注释里把这个字面量又写了一遍**，被凭据门当场抓住 —— 正是本仓
`docs/复盘` 记录过的「为记录漏洞而制造新漏洞」那一类。）

## 反悔成本

- **改成丙（整体入库）**：低 —— 文件都还在盘上，`git add -f archive/` 即可。
- **改成乙（全不入）**：低 —— `git rm --cached` 那 4 个文件 + 改回 README/CHANGELOG，一个 commit。
- **⚠️ 不可逆的部分**：若日后 `archive/` 目录在**本机被删**，则 `original-logs/`（1 MB）
  与 `重构目录表.txt` **会真正丢失** —— 它们**不在 git 历史里**（`original-agent/` 那 7 个文件**在**，不受影响）。
  这正是本次把它们移进 `archive/original-*` 落盘的原因。

## 遗留（本次未处理，已登记）

1. **`data_retention.py` 未入** —— 它有 `CODE_INVENTORY` §8 给的独立理由（`cost_records_archive` 表的唯一操作者）。
   本次按业务方「只入 RAGAS」执行，**未擅自扩大范围**。要不要跟进，待业务方定。
2. **RAGAS **未实跑验证** —— `ragas`/`datasets` 在 `requirements.txt` 里但**本机 venv 未装**，
   且脚本需 API 在跑。**"已入库" ≠ "跑通了"**。这是 ROADMAP M7「RAGAS 复跑」的**前置已就位**，不是复跑本身。
