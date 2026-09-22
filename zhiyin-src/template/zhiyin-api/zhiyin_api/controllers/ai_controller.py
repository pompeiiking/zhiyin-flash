"""AI 任务接口（SSE 传输约定见设计文档第六章 6.2）。

八个端点与草稿前端 `draft-frontend/src/ai/registry.ts` 一一对应：
进度帧 `{"pct","note","text"}` … 终帧 `{"result": {data, citations, meta, rationale}}`。

**鉴权与依赖检查发生在流开始之前。**
未登录 / 令牌无效 / Facade 未装配 / 任务未登记时，返回的是普通的 `ApiResponse` 信封
（带正确的 HTTP 状态码与 `X-Trace-Id`），而不是一条中途断掉的 SSE 连接 ——
否则前端只能看到 `incomplete chunked read`，既拿不到错误码也没法引导登录。
流一旦开始，后续失败只能以错误帧下发：`{"error": {"code": ..., "message": ...}}`。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from zhiyin_api.context import current_trace_id
from zhiyin_api.dto.common import ApiResponse, ErrorCode
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["ai"])
_log = logging.getLogger(__name__)


def _sse(frames: AsyncIterator[dict]) -> StreamingResponse:
    async def _gen() -> AsyncIterator[str]:
        async for frame in frames:
            result = frame.get("result")
            if result is not None and hasattr(result, "model_dump"):
                # 终帧按 alias 序列化：ifYouSkip / from / to 与前端 TS 形状对齐
                frame = {**frame, "result": result.model_dump(by_alias=True, mode="json")}
            yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


# 核验失败的类别 → 统一错误码。
#
# 分两类处理：用户自己能修的（码写错、报告过期、参数不对）报参数错误，
# 让前端在原地提示重填；不是用户能修的（学信网不可达、页面读不出来）报依赖不可用，
# 前端该提示"稍后再试"而不是让用户反复改码。
#
# 后半段的键是业务/基础设施层 `SdkError` 自带的 `.code`。本层用**名字**映射而不是
# import 那些异常类型：api 层被禁止 import `zhiyin_data_sdk`（见 tests/test_architecture.py），
# 而异常自带 code 正是为了让上层不必认识它的类型。
_ERROR_CODE: dict[str, ErrorCode] = {
    "malformed_code": ErrorCode.INVALID_PARAM,
    "invalid_code": ErrorCode.INVALID_PARAM,
    "expired": ErrorCode.INVALID_PARAM,
    "unreachable": ErrorCode.DEPENDENCY_UNAVAILABLE,
    "unparseable": ErrorCode.INTERNAL,
    "MISSING_CONFIG": ErrorCode.DEPENDENCY_UNAVAILABLE,
    "UNAVAILABLE": ErrorCode.DEPENDENCY_UNAVAILABLE,
    "NOT_FOUND": ErrorCode.NOT_FOUND,
    "CONFLICT": ErrorCode.CONFLICT,
    "VALIDATION": ErrorCode.INVALID_PARAM,
}


def _code_of(exc: BaseException, *, default: ErrorCode = ErrorCode.INTERNAL) -> ErrorCode:
    """异常 → 统一错误码。业务异常自带 `.code` 就按它映射。"""
    return _ERROR_CODE.get(str(getattr(exc, "code", "")), default)


# 对外只说用户能懂的话。
#
# 层间的异常消息是写给我们自己看的：「未登记的生成类任务：dim」「画像中没有维度：
# interest_riasec」这类话把内部标识摆到了用户面前。所以规则是：
#   1. 业务异常自己声明 `user_facing = True` 时才原样透传（如学信网核验失败 ——
#      那几句话是让用户改码 / 重新申请的，换掉反而让人没法行动）；
#   2. 其余一律按错误码给一句用户能行动的话，原始消息进日志。
#
# 这样既守住"界面上不出现开发文本"，又不会把可行动的提示也一起抹平。
_USER_MESSAGE: dict[ErrorCode, str] = {
    ErrorCode.INVALID_PARAM: "这一步填的内容我们没读懂，改一下再试。",
    ErrorCode.NOT_FOUND: "这一条现在还没有可看的内容。",
    ErrorCode.CONFLICT: "刚才已经提交过一次了，稍等一下再看。",
    ErrorCode.UNAUTHORIZED: "登录状态过期了，重新登录后再试。",
    ErrorCode.GUEST_LIMIT: "先登录再继续 —— 游客能问的次数用完了。",
    ErrorCode.STAGE_UNCERTAIN: "还没判断出你现在处在哪一步，再多说一句。",
    ErrorCode.DEPENDENCY_UNAVAILABLE: "这一步暂时算不了，请稍后再试。",
    ErrorCode.INTERNAL: "这一步没成功，请稍后再试。",
}


def _user_message(exc: BaseException, code: ErrorCode) -> str:
    """把异常翻成一句能直接给用户看的话。"""
    if getattr(exc, "user_facing", False):
        return str(exc)
    return _USER_MESSAGE.get(code, _USER_MESSAGE[ErrorCode.INTERNAL])


def _envelope(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
    """流开始之前的失败：按统一信封返回，并带上 trace id。"""
    return JSONResponse(
        status_code=status_code,
        content=ApiResponse[None](code=code, message=message).model_dump(mode="json"),
        headers={"X-Trace-Id": current_trace_id()},
    )


async def _frames(facade, user_id: str, key: str, arg: str = "") -> AsyncIterator[dict]:
    """流内的帧。流已经开始了，所以这里只能把失败翻译成错误帧。"""
    try:
        async for frame in facade.run_ai_task(user_id, key, arg):
            yield frame
    except Exception as exc:  # noqa: BLE001 - 流内任何失败都必须变成帧，不能撕连接
        code = _code_of(exc)
        _log.warning(
            "AI 任务 %s 失败（trace=%s, code=%s）：%s",
            key,
            current_trace_id(),
            code.name,
            exc,
        )
        yield {"error": {"code": int(code), "message": _user_message(exc, code)}}


async def _stream(request: Request, key: str, arg: str = "") -> Response:
    """鉴权与依赖检查先在流外做完，失败就给信封。"""
    from zhiyin_api.facade.facade import FacadeNotConfiguredError

    try:
        facade = get_facade()
        user_id = await facade.resolve_user_id(request)
    except FacadeNotConfiguredError as exc:
        return _envelope(
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            _user_message(exc, ErrorCode.DEPENDENCY_UNAVAILABLE),
            503,
        )
    except PermissionError as exc:
        return _envelope(
            ErrorCode.UNAUTHORIZED, _user_message(exc, ErrorCode.UNAUTHORIZED), 401
        )
    except LookupError as exc:
        return _envelope(ErrorCode.NOT_FOUND, _user_message(exc, ErrorCode.NOT_FOUND), 404)
    except Exception as exc:  # noqa: BLE001 - 流外失败同样必须走信封
        code = _code_of(exc)
        _log.warning("AI 任务 %s 前置检查失败（trace=%s）：%s", key, current_trace_id(), exc)
        return _envelope(
            code,
            _user_message(exc, code),
            503 if code is ErrorCode.DEPENDENCY_UNAVAILABLE else 500,
        )
    return _sse(_frames(facade, user_id, key, arg))


@router.post("/app/brief/today")
async def brief_today(request: Request) -> Response:
    """今日简报：今天为什么是这两件事。"""
    return await _stream(request, "brief.today")


@router.post("/app/dimensions/{dimension_id}")
async def dimension(request: Request, dimension_id: str) -> Response:
    """维度解读（点开才生成，后端缓存）。"""
    return await _stream(request, "dim", dimension_id)


@router.post("/app/portrait/analysis")
async def portrait_analysis(request: Request) -> Response:
    """「对你的分析」：整份画像合起来的一段判断（打开画像时生成）。

    与「维度解读」的分工：那一条回答"这条字段是什么、凭什么"，
    这一条回答"这些合起来说明我现在是个什么处境"。两件都要有 ——
    只有前者的时候，画像看起来就是一张信息标签表。
    """
    return await _stream(request, "portrait.analysis")


@router.post("/app/day/{day}/advice")
async def day_advice(request: Request, day: str) -> Response:
    """「这一天的建议」：日历里点开某一天时生成（`day` 是 YYYY-MM-DD）。

    日历上其余的东西都是事实（那天有哪几门课、哪个节点到期、哪件事该做完），
    前端直接读；这一条是那一天**怎么用**的建议，要模型下判断。

    请求体里的 `arg` 是客户端的时区偏移（分钟，东为正）—— "那一天"是用户
    手表上的那一天，不带这个偏移，傍晚以后的事会被算到前一天。
    """
    tz = "0"
    try:
        body = await request.json()
        if isinstance(body, dict) and body.get("arg") not in (None, ""):
            tz = str(body["arg"])
    except ValueError:
        tz = "0"
    return await _stream(request, "day.advice", f"{day}|{tz}")


@router.post("/app/gaps/{gap_key}/clarify")
async def gap_clarify(request: Request, gap_key: str) -> Response:
    """缺口追问话术。"""
    return await _stream(request, "gap", gap_key)


@router.post("/app/report/summary")
async def report_summary(request: Request) -> Response:
    """整份报告的结论段。"""
    return await _stream(request, "report.summary")


@router.post("/app/chsi/bind")
async def chsi_bind(request: Request) -> Response:
    """学信网绑定管线：核验在线验证码 → 读学籍 → 写画像。

    请求体 `arg` 是用户在学信档案申请到的**在线验证码**。
    不接收、也不要求用户的学信网账号密码 —— 那条路既不合法，也不必要。
    """
    code = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            code = str(body.get("arg") or body.get("code") or "")
    except ValueError:
        code = ""
    return await _stream(request, "bind.chsi", code)


@router.post("/app/plan/timetable")
async def plan_timetable(request: Request) -> Response:
    """课表 → 可投入时间。"""
    return await _stream(request, "plan.timetable")


@router.post("/app/plan/todos/suggestions")
async def plan_todo_suggestions(request: Request) -> Response:
    """待办建议（可采纳 / 可否决，回流画像）。"""
    return await _stream(request, "plan.todos")


@router.post("/app/match/careers")
async def match_careers(request: Request) -> Response:
    """学职网匹配：矩阵 + 排名 + 推荐。"""
    return await _stream(request, "match.careers")


__all__ = ["router"]
