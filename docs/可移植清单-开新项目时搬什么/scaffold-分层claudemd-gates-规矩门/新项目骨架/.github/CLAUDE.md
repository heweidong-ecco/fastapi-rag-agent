# `.github/` —— CI 与模板

## 📇 本目录索引
| 条目 | 是什么 |
|---|---|
| `workflows/ci.yml` | **CI 的全部**（见 `workflows/CLAUDE.md`） |

## 🔴 本层特有的规矩
- 🔴 **每个 job 必须带 `timeout-minutes`** —— 有专门的 CI 形状门钉它（`scripts/check_ci_job_timeouts.py`）
- ⚠️ **CI 里没有 `.env`、没有 `.secret-denylist`** ⇒ 凭据门会自动降级为**部分覆盖**，
  结论行会写明覆盖了哪几节 —— ⛔ 别把"通过"读成"和真凭据逐字比过"

## 📍 往上读
- 仓库根 `CLAUDE.md`
