"""智能工作台接口（R-API-004）。

按 ①-⑤ 聚合返回活资产，不做实时对话。
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.workspace import (
    AcademicImportAck,
    AcademicImportRequest,
    AcademicImportUpload,
    AcademicRevokeAck,
    IntelListView,
    WorkspacePageView,
)
from zhiyin_api.facade import get_facade
from zhiyin_kernel.errors import InvalidRequest

router = APIRouter(tags=["workspace"])


@router.get("/app/workspace", response_model=ApiResponse[WorkspacePageView])
async def get_workspace(request: Request) -> ApiResponse[WorkspacePageView]:
    """工作台聚合视图：画像 / 报告 / 方案 / 计划 / 跟踪 + 功能块。

    进入工作台属于持久化行为，游客在此处被登录拦截。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.get_workspace(user_id))


@router.post("/app/academic/import", response_model=ApiResponse[AcademicImportAck])
async def import_academic(
    request: Request, body: AcademicImportRequest
) -> ApiResponse[AcademicImportAck]:
    """导入课表与成绩单（学生自己贴原文）。

    这条路是产品有意选的：不做替学生登录学校系统，也不经手他校内账号的密码。
    用户的体验压在解析上 —— 贴进来的东西读不出来时，回执要说清楚**改哪里**。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.import_academic(user_id, body))


"""单个文件的大小上限（2 MB）。

课表与成绩单本身只有几十 KB；到 MB 量级的多半是"另存整页"带上了别的东西。
限流不是防用户，是防一次误操作把解析器拖住（解析是纯文本处理，几百 KB 的无意义输入
会白烧 CPU）。超了如实说，让他确认传的是哪一份 —— 比默默接收再跑一遍解析诚实。
"""
_MAX_UPLOAD_BYTES = 2_000_000


@router.post("/app/academic/import/file", response_model=ApiResponse[AcademicImportAck])
async def import_academic_files(
    request: Request,
    courses_file: UploadFile | None = File(default=None),
    grades_file: UploadFile | None = File(default=None),
    courses_text: str = Form(default="", max_length=200_000),
    grades_text: str = Form(default="", max_length=200_000),
    school: str = Form(default="", max_length=120),
    term: str = Form(default="", max_length=40),
) -> ApiResponse[AcademicImportAck]:
    """导入课表与成绩单（**上传文件**那一版：multipart/form-data）。

    为什么和上面那条并存，而不是合成一条：粘贴与上传是两种真实动作，
    表单上也是两个不同的入口。合成一条的话，每次都要把"这次有没有文件"编码进
    同一种请求体里，读的人得先解码一遍才知道这条路在做什么。两条路共用同一条业务
    链路（`import_files` → `import_`），所以"同一份数据读出来必须一样"这件事
    由业务层保证，不靠接口形状。

    文件在这一层只做一件事：**限大小**。编码识别与二进制格式拒绝都在网关里
    （见 `AcademicImportGateway.read_text`）—— 那一层才知道"读不出来"该怎么说。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    body = AcademicImportUpload(
        courses_file=await _read_upload(courses_file),
        grades_file=await _read_upload(grades_file),
        courses_name=courses_file.filename if courses_file else "",
        grades_name=grades_file.filename if grades_file else "",
        courses_text=courses_text,
        grades_text=grades_text,
        school=school,
        term=term,
    )
    return ApiResponse(data=await facade.import_academic_files(user_id, body))


async def _read_upload(file: UploadFile | None) -> bytes | None:
    """把上传的文件读成字节。多读一个字节用来判断"超没超"，因此超限时不会截断。"""
    if file is None:
        return None
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        label = file.filename or "这个文件"
        raise InvalidRequest(
            f"「{label}」超过 2MB，读起来会拖住这一屏。"
            "课表和成绩单正常的导出只有几十 KB —— 确认一下传的是哪一份。"
        )
    return data


@router.delete("/app/academic", response_model=ApiResponse[AcademicRevokeAck])
async def revoke_academic(request: Request) -> ApiResponse[AcademicRevokeAck]:
    """清空导入的课表与成绩（画像里那两条摘要一起删）。

    只清快照不删摘要的话，采集清单会一直显示"课程表已拿到"，
    用户再也回不到导入入口 —— 那是"看起来清掉了"。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.revoke_academic(user_id))


async def _optional_user(request: Request) -> str | None:
    """**尽力**认人：认得出就个性化，认不出就按公开取数。

    情报这一层是爬公开数据的，登录态与"能看到哪些公开信息"本来就没有关系 ——
    所以这里吞掉鉴权失败，而不是把未登录的人挡在门外。
    """
    from zhiyin_kernel.errors import AccessDenied

    try:
        return await get_facade().resolve_user_id(request)
    except AccessDenied:
        return None


@router.get("/app/intel", response_model=ApiResponse[IntelListView])
async def get_intel(request: Request, q: str = "") -> ApiResponse[IntelListView]:
    """外部情报：公开事实（学职平台 + 通用网络检索）。

    **不要求登录**：登了录就按你的画像收窄，没登录就按 `?q=` 或平台通用数据取。
    每条都带来源链接 —— 这类信息"凭什么这么说"就是那个链接，
    所以取不到来源的条目在服务层就被丢掉了，不会返回。
    """
    facade = get_facade()
    user_id = await _optional_user(request)
    return ApiResponse(data=await facade.get_external_intel(user_id, topic=q))


@router.post("/app/intel/refresh", response_model=ApiResponse[IntelListView])
async def refresh_intel(request: Request, q: str = "") -> ApiResponse[IntelListView]:
    """现在去取一次（用户主动点）。同样**不要求登录**。

    只在这条路上推通知：后台顺带取到的东西不弹 ——
    浮窗要留给"值得打断他"的事，而"他自己刚点的"就是值得回一句的事。
    （未登录时没有收件人，自然也不推。）
    """
    facade = get_facade()
    user_id = await _optional_user(request)
    return ApiResponse(data=await facade.get_external_intel(user_id, topic=q, refresh=True))
