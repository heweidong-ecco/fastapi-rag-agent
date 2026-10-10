# `app/demo/specs/` —— 本组模块的规格

> 📇 **一份 spec 对应一个模块，且【与模块同名】**。
> 判据：`app/demo/<模块>.py` ⇔ `app/demo/specs/<模块>.md`

## 📇 本目录索引

| spec | 对应 |
|---|---|
| `claim.md` | `app/demo/claim.py` 的 spec |

⚠️ **`__init__.py` 已经在 2026-10-10 撤掉** —— 本仓各组**都不放** `__init__.py`
（导入靠 `app/` 在 `sys.path` 上的**命名空间包**，与 `from core.config import X` 同一套）。
它原先那段「⛔ 别挂进 main.py」的说明**搬进了上一层** `app/demo/CLAUDE.md`（更该读到的地方）。

## 🔴 写法（⛔ 别自由发挥）

四段式 —— 模板与说明见 `app/specs/README.md`：
`✅ 做了什么` / `🟡 做到哪缺什么` / **`⚠️ 看代码会误判的地方 ⭐`** / `关联`

⭐ **重头是第三段** —— 前两段读代码也能推出来，**只有第三段推不出来**。
内容要来自**代码里的 ⚠️/🔴 注释**与 `docs/复盘/`、`DEC-*`，⛔ **不是读一遍代码的转录**
（本仓立场：**转录即负债**）。

## 📍 往上读

- `../CLAUDE.md`（本组）· `app/specs/README.md`（模板）· 仓库根 `CLAUDE.md`
