"""demo 专属：**访客凭据的发放**（`DEC-143`）。

## 这条端点是干什么的

demo 的访客**不用注册、不用填任何东西**：页面首访时静默来领一把凭据、
存进那个浏览器，之后页面自己带着它。

## 🔴 三条设计约束（⛔ 改这个文件之前先读）

**① 它只存在于【demo 的入口】里。**
本仓跑 `uvicorn main:app` ⇒ **这个模块不会被 import** ⇒ **这条路由不存在**（⇒ 404）。
⚠️ **⛔ 这不是靠 `os.getenv` 判断的，是靠结构** —— 见 `app/demo/__init__.py` 的说明。

**② 🔴 它先撤旧的、再发新的。**
⚠️ **"同一个访客再领就回同一把"【做不到】** —— `access/auth.py` 的 `create_user_api_key`
只往库里写 sha256，它自己的 docstring 写着「**明文 Key 只在生成时显示一次，之后无法找回**」。
⇒ **"只领一把"是【前端】的职责**（本地有就不领）；**这里负责的是"上限"**：
一个访客**最多一把活着的**。

**③ `visitor_id` 必须校验形状。**
它会被**拼进 `user_name`** ⇒ ⛔ 不校验就是往库里灌任意垃圾
（本仓栽过"用户名可枚举"那一族）。

## ⚠️ 本文件里有一处【有意的第二份实现】

`_revoke()` 里那条 `UPDATE`，是本仓 `scripts/issue_api_key.py` 里同一段的**第二份**。
**为什么允许**：业务方选「甲」⇒ **本仓的 `access/auth.py` 不许再动**，
而 demo 这条端点**又要撤旧的** ⇒ 只能在这里写一份。
**代价已认**：同一个概念有两处实现，而**本仓没有任何门能发现"只改了一头"**。
🔴 **若将来要改这条的语义，⛔ 两处都要改**（另一处在 `scripts/issue_api_key.py`）。
"""
import re

from fastapi import APIRouter
from pydantic import BaseModel

from access.auth import create_user_api_key
from core.db import get_db
from core.exceptions import AppException, ErrorCode

router = APIRouter(prefix="/api/v1", tags=["demo"])

#: 🔴 访客标识的形状 —— **必须校验**（见模块 docstring 的约束 ③）。
_VISITOR_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")

#: 访客凭据的有效期（天）。
#: ⚠️ **比 `scripts/issue_api_key.py` 的默认 30 天短，是有意的** ——
#: 访客的凭据本来就"换个浏览器就换一把"，给太长没有意义。
_VISITOR_KEY_DAYS = 7


def _revoke(user_name: str) -> int:
    """把该访客名下**还活着的**凭据置为失效；返回影响行数。

    🔴 **只写 `0`，⛔ 不许写 `NULL`** —— 读侧的判据是 `COALESCE(is_active, 1) = 1`
    （**NULL 当激活**）⇒ 写 `NULL` = **没撤销**，而屏幕上会打一句"已撤销"。
    ⚠️ 末尾那个 `COALESCE(...) = 1` 是让 `rowcount` 报"**真的**撤掉了几把" ——
    去掉它也照样撤（把 0 再写成 0 是幂等的），但**报数会虚高**。

    ⚠️ 见模块 docstring 末尾『**有意的第二份实现**』那一节。
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE api_keys SET is_active = 0 "
                "WHERE user_name = %s AND COALESCE(is_active, 1) = 1",
                (user_name,),
            )
            n = cur.rowcount
            conn.commit()
    return n


class ClaimRequest(BaseModel):
    visitor_id: str


@router.post(
    "/demo/claim",
    summary="demo：给访客发一把临时凭据（⚠️ 只在 demo 的入口下存在）",
    description=(
        "demo 的访客**不用注册**：页面首访时静默调它，领一把临时凭据存进那个浏览器。\n\n"
        "🔴 **它只在 demo 的入口里存在** —— 本仓跑 `main:app` 时**这条路由不存在**（404）。\n\n"
        "⚠️ **同一个 `visitor_id` 再来一次 ⇒ 会换一把新的**（旧的那把被撤掉）—— "
        "因为库里只存哈希，**明文找不回来**。所以「只领一把」由**前端**保证。\n\n"
        "⛔ **响应里不含任何别人的东西**，也不含角色/额度明细（那是别的接口的事）。"
    ),
)
async def demo_claim(req: ClaimRequest):
    vid = (req.visitor_id or "").strip()
    if not _VISITOR_ID_RE.fullmatch(vid):
        # ⚠️ 本仓把 `PARAM_INVALID` 映射成 **422**（不是 400）—— 见 `core/exceptions.py` 的映射表。
        raise AppException(
            ErrorCode.PARAM_INVALID,
            "visitor_id 形状不对（要 8~64 位的 A-Za-z0-9_-）",
        )

    user_name = f"demo-{vid}"

    # 🔴 先撤旧的 ⇒ 保证「一个访客最多一把活着的」（约束 ②）。
    _revoke(user_name)

    # ⚠️ `role` **刻意不传** ⇒ 库里写 `NULL` ⇒ 读侧回退（非 admin ⇒ FREE）。
    #    ⛔ **别填 `"free"`** —— `create_user_api_key` 的 docstring 明写
    #    「别给它一个默认值，那会把『没写』与『写了 free』变成同一件事」。
    api_key = create_user_api_key(user_name, expire_days=_VISITOR_KEY_DAYS)

    return {
        "api_key": api_key,
        "user_name": user_name,
        "expires_in_days": _VISITOR_KEY_DAYS,
    }
