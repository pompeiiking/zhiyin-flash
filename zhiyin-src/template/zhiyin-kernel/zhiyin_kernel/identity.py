"""身份与会话契约。

第一期只做本地演示用户；游客临时会话仅存于 session，登录后合并。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import UserRole


class UserAccount(BaseModel):
    """用户账号。

    约束：第一期禁止写入真实手机号 / 简历 / 身份证，演示数据必须显式标记 DEMO。

    只保留真有生产者与消费者的字段：`email` / `avatar_url` / `profile_summary`
    在仓库里既没人写也没人读（顶栏展示的是 `identity.nickname` 与 `role`），
    留着会让"用户模型有哪些字段"这个问题多出三个假答案。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    phone: Optional[str] = Field(default=None, description="第一期仅允许演示值")
    nickname: str = ""
    role: UserRole = UserRole.STUDENT
    created_at: datetime
    last_login_at: Optional[datetime] = None


class GuestSession(BaseModel):
    """游客临时会话。不落长期业务库，登录合并后清除。

    保留原因：设计文档把"游客答到第 3 问被拦 → 登录后原地继续、合并游客会话"
    写成验收项，本类就是那条流程的数据形状。实现之前它没有生产者是对的，
    **但形状要先冻结**（与 `AuthSession` 的区别是：那条会话的真正载体是
    `infra_auth_session` 表 + JWT，模型重复，已删除）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    temp_profile: dict[str, Any] = Field(
        default_factory=dict, description="游客已采集的画像字段片段"
    )
    answered_collect_steps: int = Field(
        default=0, description="已答采集问数，超过 2 问触发登录拦截"
    )
