# `app/static/web/` —— 页面（8 个 html）

## 📇 本目录索引
| 页面 | URL | 说明 |
|---|---|---|
| `index.html` | `GET /`（302） | **总览首页** |
| `chat.html` | `GET /chat` | 对话页（登录 → 提问 → 流式逐字 → 引用点开 → 停止 → 每轮 token/费用） |
| `cost.html` | `GET /cost` | 成本看板（面板标题带**口径徽标**：读库/进程内存/配置常量） |
| `lab.html` | `GET /lab` | 检索实验室（5 条检索接口各一个面板） |
| `trace.html` | `GET /trace` | 轨迹页（**两轴分屏**） |
| `approvals.html` | `GET /approvals` | 人工接管队列 |
| `eval.html` | `GET /eval` | 评估页 |
| `eval_gate.html` · `websocket_test.html` | —— | 评测台页面 · WS 调试页 |

## 🔴 本层特有的规矩
- 🔴 **每个页面必须能被点到**（最高判据①）：「**显示了，才知道你有做**」
- 🔴 **守卫在 `app/tests/test_<页>_page.py`** —— 它们钉的是**页面源码**（302 目标在盘上 ·
  不进 OpenAPI · **边界提示条排在提交按钮【之前】**）
- ⚠️ **⛔ 不许引外网 CDN**（首页有专门断言）

## 📍 往上读
- `../CLAUDE.md`（`app/static/`）· `frontend/索引.md` · 仓库根 `CLAUDE.md`
