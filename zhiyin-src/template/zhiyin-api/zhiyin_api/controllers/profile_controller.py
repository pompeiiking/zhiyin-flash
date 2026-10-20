"""画像字段的用户更正、删除与线索否认接口。

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

删除与否认是同一组用户控制的另一半（《个人画像设计-2026-10-20》第 7、9 节）：
- `DELETE /app/profile/fields/{key}`：删除一条他自己提供/被记录的信息；
- `DELETE /app/profile/clues/{clue_id}`：否认一条"系统的理解"（待验证线索），
  线索不是事实，所以是"否认"而不是"删除" —— 被否认的线索留在原位并写明原因，
  同类理解不会被悄悄重新提出。

本文件只接参数、包信封。"键在不在登记表里""值空不空、超不超过长度"这些判断
全在业务层（`DefaultProfileService`）—— 接口层一旦自己判一遍，别的入口
（对话里说一句）就会绕开同一套口径。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.workspace import (
    ProfileClueDenyAck,
    ProfileFieldDeleteAck,
    ProfileFieldUpdateRequest,
    ProfileFieldView,
)
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


@router.delete(
    "/app/profile/fields/{key}", response_model=ApiResponse[ProfileFieldDeleteAck]
)
async def delete_profile_field(
    request: Request, key: str, expected_updated_at: datetime | None = None
) -> ApiResponse[ProfileFieldDeleteAck]:
    """删除一条画像信息（用户自己的控制入口）。

    `expected_updated_at` 可选：带了就按"我看到的是哪一版"校验，版本对不上返回
    冲突（409 / 1003），不静默删掉另一个标签页刚改过的值；不带就是普通删除。
    删除后依据这一格的待验证线索一并失效（业务层负责）。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(
        data=await facade.delete_profile_field(
            user_id, key, expected_updated_at=expected_updated_at
        )
    )


@router.delete(
    "/app/profile/clues/{clue_id}", response_model=ApiResponse[ProfileClueDenyAck]
)
async def deny_profile_clue(
    request: Request, clue_id: str
) -> ApiResponse[ProfileClueDenyAck]:
    """否认一条「系统的理解」（待验证线索）。

    线索不是用户提供的事实，所以不能说"删除" —— 他否认的是这条理解。
    回执只回 id：界面据此把那一张卡片改成"已否认"，不需要重读整份画像。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.deny_profile_clue(user_id, clue_id))


__all__ = ["router"]
