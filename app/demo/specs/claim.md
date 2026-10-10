# `app/demo/claim.py`

## ✅ 做了什么

**demo 的访客不用注册就拿到凭据**（`DEC-143`）：`POST /api/v1/demo/claim`，
body 是 `{"visitor_id": …}`，回 `{"api_key", "user_name", "expires_in_days"}`。

一次调用做四件事，**顺序不能换**：校验 `visitor_id` 形状 → **先撤旧的** →
`create_user_api_key(user_name, expire_days=7)` → 只回那一把明文。

## 🟡 做到哪 / 缺什么

- **前端已经接上了**（`app/static/js/session.js` 取凭据 · `app/static/js/cred.js` 管页头那块），
  8 个能力页 + 首页横幅都走它。
- **守卫** ⇒ `app/tests/test_demo_claim.py`（10 条）· 每条都做过反证检验。
- ⛔ **没有**的东西：没有"同一个访客领回同一把"（**做不到**，见下 ①）、
  没有"一个访客只发一把"的**后端**保证（那是**前端**的职责，后端只保证**上限**）。

## ⚠️ 看代码会误判的地方 ⭐

1. 🔴🔴 **「同一个访客再来就回同一把」做不到** —— `app/access/auth.py` 的
   `create_user_api_key` **只往库里写 sha256**，明文**只在发的那一刻给一次**。
   ⇒ 所以「**只领一把**」是**前端**的职责（`session.js`：本地有就不领）；
     **本模块负责的是上限**：一个访客**最多一把活着的**（靠先撤旧的）。
   ⚠️ 副作用已认：**清掉浏览器存储 / 换浏览器 ⇒ 会领到新的一把**（旧的被撤）。
2. 🔴 **`_revoke()` 是【有意的第二份实现】** —— 正本在 `scripts/issue_api_key.py`。
   为什么允许：业务方选了「甲」⇒ 红线那一侧的 `access/auth.py` **不许再动**。
   🔴 **代价**：本仓**没有任何门能发现"只改了一头"** ⇒
   **将来改那条 SQL 的语义，两处都要改**（判据：`grep -n "is_active = 0" scripts/issue_api_key.py app/demo/claim.py`）。
   ⚠️ **撤销写的是 `0`，⛔ 不是 `NULL`** —— 读侧是 `COALESCE(is_active, 1) = 1`，
   **`NULL` 当激活** ⇒ 写 `NULL` = **没撤销**，而界面上会说"已撤销"（有守卫钉着）。
3. ⚠️ **形状不对回的是 422，⛔ 不是 400** —— 本仓把 `ErrorCode.PARAM_INVALID`
   映射成 422（`app/core/exceptions.py`）。`visitor_id` 会被**拼进 `user_name`**
   ⇒ 正则 `[A-Za-z0-9_-]{8,64}` 是**安全边界**，⛔ 别放宽。
   ⚠️ 它还要**收得下前端生成的形状**（`crypto.randomUUID()` 那种）——
   收不下时页面**不报错**，只表现为"永远退回自己填"（守卫里有**正控**钉着）。
4. ⚠️ **`role` 是刻意【不传】的** ⇒ 库里写 `NULL` ⇒ 读侧回退 ⇒ 非 admin（FREE）。
   ⛔ **别填 `"free"`** —— `create_user_api_key` 的 docstring 明写：
   「别给它一个默认值，那会把『没写』与『写了 free』变成同一件事」。
5. ⚠️ **有效期 7 天比本机脚本的 30 天短，是有意的** —— 访客的凭据本来就
   "换个浏览器就换一把"，给长了没有意义。⛔ 但**这个数好不好**归 `DEC-098 §二·4`，
   ⛔ 别拿这份 spec 当裁定。
6. 🔴 **这条路由⛔ 不许写进无鉴权基线**（`scripts/route-auth-baseline.txt`）——
   那份基线是**静态文件、没有"环境"这一维**，而 `check_route_auth.py` 扫的是
   **本仓那条路**（那条路上它压根不存在）⇒ 写进去 = 给一条**扫不到的路由**立规矩
   （「**从不命中**」与「没人违规」在机器痕迹上完全一样）。有守卫钉着。
7. ⚠️ **它只存在于 demo 的入口**（`demo_main:app`）。本仓那条路上打过去是 **404**，
   **那是正常的、⛔ 不是故障** —— 前端就是靠这个 404 静默退回"自己填"的。
   ⇒ ⛔ **别把 404 读成"坏了"**。
8. 🔴 **判据里⛔ 不能用子进程去 import `main`** ——
   `main` 一被 import 就拉起 `agent.memory_store` ⇒ `mem0` ⇒ 一个本地 Qdrant
   单实例锁；而 **pytest 那个会话本身已经攥着它** ⇒ 第二个进程当场死在
   `RuntimeError: Storage folder … is already accessed`。
   ⇒ 实测过：**同一条子进程命令，单独跑成功、在 pytest 里跑必失败**。
   📄 `app/tests/test_demo_claim.py` 的文件头写了这是怎么绕开的。

## 关联

- `app/demo_main.py` —— 唯一的入口（它把本模块的 router 挂上去）
- `app/access/specs/auth.md` —— `create_user_api_key` 的**正本**（本模块只是它的调用方）
- `scripts/issue_api_key.py` —— `_revoke()` 的**正本**（那张"两处要一起改"的另一半）
- `app/static/specs/static_frontend.md` —— 前端拿凭据那一侧
- `app/tests/test_demo_claim.py` —— 10 条守卫
- `docs/decisions/DEC-143-demo访客凭据的发放方式.md` · `DEC-142`（默认 = 完整版）
- `docs/复盘/2026-10-10-页面里那段JS没有任何门会去跑它.md`
