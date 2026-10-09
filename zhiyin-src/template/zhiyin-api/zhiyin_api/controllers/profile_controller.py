"""画像字段的用户更正接口（issue #26 第三条）。

调用链：Controller → Facade → ProfileService → ProfileRepository。

为什么单开这条写路径
--------------------
画像此前只有"系统去记"的写路径：① 采集（模型按对话产出 field_updates）、
学信网核验、教务系统导入。三条都是**系统**在写。用户发现记错了
（他说的是"计算机大类"，系统却把它当成"计算机科学与技术"记了下来）时，
界面上只能看、一个字也改不了 —— 他能做的只有再跟对话说一遍，而那句话
又进了同一台推断机，出来的仍然是替他挑好的一条具体专业。于是错值留在画像里，
后面每一份报告、每一个方向推荐都按它算。

这一条补的是**他自己写的**那一条：来源记成 `user_edit`，界面上说"你自己填的"。

本文件只接参数、包信封。"键在不在登记表里""值空不空、超不超过长度"这些判断
全在业务层（`DefaultProfileService.correct_field`）—— 接口层一旦自己判一遍，
别的入口（对话里说一句）就会绕开同一套口径。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.workspace import ProfileFieldUpdateRequest, ProfileFieldView
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["profile"])


@router.post("/app/profile/fields/{key}", response_model=ApiResponse[ProfileFieldView])
async def update_profile_field(
    request: Request, key: str, body: ProfileFieldUpdateRequest
) -> ApiResponse[ProfileFieldView]:
    """更正一条画像字段，返回更正后的那一条。

    回包给的是**服务端存下来的那一条**，不是把请求里的值原样弹回去：
    界面据此做乐观更新与回滚，刷新之后看到的是同一份事实。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.update_profile_field(user_id, key, body))


__all__ = ["router"]
