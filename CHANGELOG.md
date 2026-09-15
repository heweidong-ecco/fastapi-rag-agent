# Changelog

All notable changes to this project will be documented in this file.

> **起点说明**:本文件自 **2026-09-15** 起建立。**此前的项目历史以 `git log` 为准,不追溯补写** —— 避免编造未曾记录过的条目。
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。本仓库当前无版本标签,故条目一律记在 `[Unreleased]` 下。
> 相关机制:决策进 `docs/decisions/`、过程错误进 `docs/复盘/`、改动进本文件(见 `ROADMAP.md`「当前指针」)。

## [Unreleased]

### Added

- **CI 骨架** `.github/workflows/ci.yml` —— 跑 `python -m compileall api/ -q`,Python 钉 **3.10**(与 `api/Dockerfile` 的基础镜像一致,否则"本机能跑、容器里 SyntaxError"拦不住)。**暂不含 pytest** —— 待本项目重构/裁决定案后接入。首次运行 `success`(run `34966390842`,commit `9c844aa`)。
- **`ROADMAP.md`** —— 接续锚点:当前指针 / 交接 / 里程碑 M0–M7 / 已登记待办。格式对齐 `agent-eval-gate`、`product-agent-dev-os`。
- **`docs/CODE_INVENTORY.md`** —— M5 代际盘点产出:**8 组**代际并存(最核心是 Agent 图 **4 套实现同时挂在线上**)、代码量(`api/*.py` 53 个文件 **8,294 行**;含 `locustfile*` 与 `archive/` 的 Python 合计 **≈9,280 行**)、工作量评估(删完约 −2,000 行 / 5–8 天)、逐处裁决建议。
- **`docs/decisions/`** —— 决策记录机制,含本项目首批 4 份:
  - `DEC-001` 公开仓库硬编码登录口令的处理路线(A 补数据层 / B 取消口令登录 / **C 环境变量**)
  - `DEC-002` 三处预算闸门失效的修法(**乙 消耗折 Token** + **(a) 新增 Token 预估表**)
  - `DEC-003` 压测口径修复改哪一侧(**改脚本** / 改端点;`mode` 取 `accurate_norerank`)
  - `DEC-004` 本项目过程记录机制选型(**三套全建**)
- **`docs/复盘/`** —— 过程错误记录机制,含 `模板-复盘.md` 与当日 3 份复盘。
- **`CHANGELOG.md`** —— 本文件。

### Changed

- **`ROADMAP.md`** —— M4(CI 骨架)状态 `▶ → ✔`;M5 由"项目重构"按业务方口径**重述**为「**代码盘点与裁决合并**」(盘点 → 逐处裁决 → 代码量/工作量评估 → 删到能跑);新增 **M6 单模块完整测试闭环**;M7 全量测试与评估接入延后。
- **`docs/CODE_INVENTORY.md`** —— §0-1 中的口令**原文改为脱敏占位**(事实描述与风险说明全部保留)。
  ⚠️ 该文件位于 **PUBLIC 仓库**,初版直接引用了口令原文 —— 起因、根因与防错措施见 `docs/复盘/2026-09-15-为记录漏洞而制造新漏洞.md`。

### Removed

- 本地残留分支 `docs/api-doc-final-review`(已并入 `main`,远端无此分支)。

### Security

- ⚠️ **尚未处理,已登记**(详见 `DEC-001`「影响与后续行动」):
  - `api/auth.py` 硬编码登录口令（明文，原文见 git 历史），共散落 **10 处**（含 3 个 locustfile、`conftest.py`、`test_auth.py`、`test_integration.py`、Postman ×4、`schemas.py` 的 Swagger 示例）。
  - `api/ rag-agent-api.postman_collection.json`(已被 git 跟踪)内含一个 **35 字符真实形态的 API Key**,出现 **2 处**(L1159、L3293)。
  - **改代码不等于止血** —— 凭据在 `git log -p` 与任何已 fork 的克隆里永久留存。**部署实例必须轮换口令;该 API Key 须在 `api_keys` 表删行并重新签发。**
