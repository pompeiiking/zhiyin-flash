"""核心对话页接口（R-API-002 / R-API-003）。

调用链：Controller → Facade → Orchestrator.handle_message
（会话上下文 → 模型自主调用 → 服务端权限与版本校验 → 实际回执）
"""

from __future__ import annotations

import codecs
import re
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import APIRouter, Body, File, Request, UploadFile

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.conversation import (
    ConversationMessageView,
    ConversationMaterialView,
    ConversationTurnView,
    MessageRequest,
    SessionListView,
    SessionRenameRequest,
    TaskEnterRequest,
    TaskSessionView,
)
from zhiyin_api.facade import get_facade
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_kernel.streaming import progress_channel
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging

router = APIRouter(tags=["conversation"])
_conversation_jobs: set[asyncio.Task] = set()


@router.get("/app/sessions", response_model=ApiResponse[SessionListView])
async def list_sessions(request: Request) -> ApiResponse[SessionListView]:
    """左栏会话列表（并行任务会话，按任务/环节命名）。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_sessions(user_id))


@router.patch("/app/sessions/{task_id}", response_model=ApiResponse[SessionListView])
async def rename_session(
    request: Request, task_id: str, body: SessionRenameRequest
) -> ApiResponse[SessionListView]:
    """会话改名：只改展示名，不改变环节、消息与已有资产。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.rename_session(user_id, task_id, body.task_name))


@router.delete("/app/sessions/{task_id}", response_model=ApiResponse[SessionListView])
async def delete_session(request: Request, task_id: str) -> ApiResponse[SessionListView]:
    """删除会话及其逐轮原文；返回删除后的列表。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.delete_session(user_id, task_id))


@router.get(
    "/app/sessions/{task_id}/turns",
    response_model=ApiResponse[list[ConversationMessageView]],
)
async def list_session_turns(
    request: Request, task_id: str, limit: int = 200
) -> ApiResponse[list[ConversationMessageView]]:
    """一条会话的逐轮原文。

    会话列表点进去要能看见"这条会话发生过什么" —— 此前只有一张清单，
    因为逐轮原文压根没落库（库里只有累积摘要）。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_session_turns(user_id, task_id, limit=limit))


@router.post("/app/task/enter", response_model=ApiResponse[TaskSessionView])
async def enter_task(
    request: Request, body: TaskEnterRequest
) -> ApiResponse[TaskSessionView]:
    """从首页任务入口进入微循环。

    编排器判定目标环节与主理；已存在进行中的同一任务时执行"续接"而非重建。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.enter_task(user_id, body))


@router.post("/app/conversation/message", response_model=ApiResponse[ConversationTurnView])
async def send_message(
    request: Request, body: MessageRequest
) -> ApiResponse[ConversationTurnView]:
    """发送自然对话一轮，返回正文和实际业务操作回执。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.send_message(user_id, body))


@router.post('/app/conversation/message/stream', response_class=StreamingResponse)
async def stream_message(request: Request, body: MessageRequest):
    """Model text arrives incrementally; cards are released only after persistence."""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    await facade.check_analysis_consent(user_id)

    async def frames():
        from zhiyin_api.controllers.ai_controller import _code_of, _user_message
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        connected = True

        sequence = 0
        run_id = body.client_msg_id
        def publish(frame):
            nonlocal sequence, run_id
            if not connected:
                return
            run_id = frame.get("run_id") or run_id
            sequence += 1
            # Text frames carry cumulative text. Slow receivers may skip an
            # intermediate frame; the final result and durable journal recover it.
            if queue.full():
                queue.get_nowait()
            queue.put_nowait({**frame, "protocol": 2, "sequence": sequence,
                "run_id": run_id, "conversation_id": body.task_id})

        async def run():
            try:
                with progress_channel(publish):
                    result = await facade.send_message(user_id, body)
                publish({'result': result.model_dump(mode='json')})
            except Exception as exc:
                logging.getLogger(__name__).exception('Conversation stream failed')
                code = _code_of(exc)
                publish({'error': {'code': int(code), 'message': _user_message(exc, code)}})
            finally:
                if connected:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(None)

        worker = asyncio.create_task(run())
        _conversation_jobs.add(worker)
        worker.add_done_callback(_conversation_jobs.discard)
        try:
            yield 'data: {"note":"正在分析你的问题"}\n\n'
            while True:
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield ': keep-alive\n\n'
                    continue
                if frame is None:
                    break
                yield 'data: ' + json.dumps(frame, ensure_ascii=False) + '\n\n'
        finally:
            connected = False
            # Closing the stream only stops reception. The approved turn must
            # finish its bounded execution and persist a result for retry/readback.
            # In particular do not cancel between a write and its receipt.
            if worker.done():
                await asyncio.gather(worker, return_exceptions=True)

    return StreamingResponse(frames(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
    })


@router.get('/app/sessions/{task_id}/runtime', response_model=ApiResponse[dict])
async def conversation_runtime(request: Request, task_id: str, run_id: str = ""):
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.conversation_control(user_id, task_id, run_id=run_id))


@router.post('/app/sessions/{task_id}/runs/{run_id}/cancel', response_model=ApiResponse[dict])
async def cancel_conversation_run(request: Request, task_id: str, run_id: str):
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.conversation_control(user_id, task_id, run_id=run_id, cancel=True))


@router.patch('/app/sessions/{task_id}/settings', response_model=ApiResponse[dict])
async def conversation_settings(request: Request, task_id: str, body: dict = Body(...)):
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.conversation_control(user_id, task_id, settings=body))


"""一份材料的体积上限（2 MB）与正文字数上限（20 万字）。

两个上限说的是**两件不同的事**：
- 2 MB 是**文件大小** —— 用户看到的是"这个文件多大"，改法是只截取/另存相关部分；
- 20 万字是**读出来的正文字符数** —— 用户看到的是"我贴了多长一段"，改法是删掉无关内容。
混成一句"内容过大"时，用户不知道是压小文件还是删短文字，所以文案必须分开。
"""
_MAX_MATERIAL_BYTES = 2_000_000
_MAX_MATERIAL_CHARS = 200_000

"""材料只收**文本类**文件。

为什么要有白名单而不只是"能解码就收"：二进制文件（Excel/PDF/图片/音视频/可执行文件）
经 GB18030 兜底解码后**不会报错**，会得到一串看起来像字的乱码一路进模型上下文；
用户以为"传上去了"，模型读到的却是垃圾。扩展名是用户自己知道、也能自己改的一件事，
所以先在扩展名这一层说清楚"另存为文本再传"。
"""
_TEXT_SUFFIXES: frozenset[str] = frozenset({
    ".txt", ".text", ".csv", ".tsv", ".json", ".md", ".markdown", ".log",
    ".xml", ".yaml", ".yml", ".sql", ".py", ".js", ".mjs", ".cjs", ".ts",
    ".tsx", ".jsx", ".html", ".htm", ".css", ".ini", ".cfg", ".conf",
    ".rst", ".tex",
})

"""明确读不了的二进制格式 → 给用户看的中文名字（按后缀，用户自己改得了）。"""
_BINARY_SUFFIX_LABELS: dict[str, str] = {
    ".pdf": "PDF",
    ".doc": "Word 文档", ".docx": "Word 文档",
    ".xls": "Excel 工作簿", ".xlsx": "Excel 工作簿", ".xlsm": "Excel 工作簿",
    ".ppt": "PPT 演示文稿", ".pptx": "PPT 演示文稿",
    ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包", ".tar": "压缩包",
    ".gz": "压缩包", ".bz2": "压缩包", ".xz": "压缩包",
    ".png": "图片", ".jpg": "图片", ".jpeg": "图片", ".gif": "图片",
    ".webp": "图片", ".bmp": "图片", ".heic": "图片", ".svg": "矢量图",
    ".mp3": "音频", ".wav": "音频", ".flac": "音频", ".aac": "音频",
    ".ogg": "音频", ".m4a": "音频", ".wma": "音频",
    ".mp4": "视频", ".avi": "视频", ".mov": "视频", ".mkv": "视频",
    ".webm": "视频", ".wmv": "视频", ".flv": "视频",
    ".exe": "可执行文件", ".dll": "动态库", ".msi": "安装包",
    ".bin": "二进制文件", ".iso": "光盘镜像", ".apk": "安装包",
    ".jar": "Java 包", ".class": "编译后的字节码", ".so": "动态库",
    ".dylib": "动态库", ".dmg": "磁盘镜像", ".pkg": "安装包",
    ".deb": "安装包", ".rpm": "安装包",
}

_ALLOWED_SUFFIX_HINT = "txt / csv / tsv / json / md / log / xml / yaml / sql / py / js / ts 等文本类文件"


@router.post("/app/conversation/material", response_model=ApiResponse[ConversationMaterialView])
async def upload_material(request: Request, file: UploadFile = File(...)) -> ApiResponse[ConversationMaterialView]:
    """交一份材料（multipart 上传）。

    为什么材料要**上传**而不是在浏览器里读成文本再塞进消息：

    · 编码（教务/办公软件导出的 GBK 文本）与二进制格式都由服务端统一处理，
      浏览器那一侧不做第二份解码实现；
    · 正文不进对话气泡 —— 回执只有"它是什么"，正文留在服务端、只在用到它的
      那一轮进模型输入。

    这一层负责的边界（都在拿到字节之后、落库之前说清楚）：
    文件大小 → 是否为空 → 扩展名白名单/二进制后缀拒绝 → 内容嗅探（空字节/控制字节）
    → 编码可解码性 → 正文字数。读不出来时给的都是**用户能照着做**的一句中文。
    文件名只用来拼提示（取 basename、去控制字符、限长），不进日志正文。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    data = await _read_material(file)
    # 对外只用处理过的名字：路径分隔符与换行已在 _material_display_name 里去掉，
    # 避免文件名成为提示词/日志里的注入面。
    return ApiResponse(data=await facade.upload_material(user_id, name=_material_display_name(file.filename or ""), data=data))


def _material_display_name(raw: str) -> str:
    """文件名 → 只用于提示的短名字（basename、可打印、限长 120）。

    文件名是不可信输入：可能带路径（C:\\Users\\...）、换行、控制字符或超长内容。
    它只该出现在"「简历.txt」读不出来"这类提示里，不该带着路径或控制字符
    进提示词、日志或对象键。multipart 头里的换行会被百分号编码成 `%0A`，
    所以这里连"百分号编码的控制字符"一起去掉。
    """
    value = (raw or "").replace("\\", "/")
    base = PurePosixPath(value).name or PureWindowsPath(raw or "").name
    base = re.sub(r"%(?:0[0-9A-Fa-f]|1[0-9A-Fa-f]|7[Ff])", "", base)
    base = "".join(ch for ch in base if ch.isprintable() and ch not in "\x00\r\n\t")
    base = base.strip()[:120]
    return base or "这个文件"


def _guard_material_suffix(name: str) -> None:
    """扩展名白名单：文本类放行，已知二进制明确拒绝，其余按"不支持的类型"说清楚。"""
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        return
    if not suffix:
        raise InvalidRequest(
            f"「{name}」没有扩展名，看不出是什么文件 —— 请另存为文本类文件（{_ALLOWED_SUFFIX_HINT}）后再传。"
        )
    label = _BINARY_SUFFIX_LABELS.get(suffix)
    if label:
        if suffix in {".xls", ".xlsx", ".xlsm"}:
            next_step = "请在 Excel 里另存为 CSV 后再传，或把表格内容复制粘贴进来"
        elif suffix in {".pdf", ".doc", ".docx"}:
            next_step = "请把需要分析的文字复制出来保存为 TXT 再传，扫描件需先识别为文字"
        elif label in {"图片", "矢量图"}:
            next_step = "对话材料只收文字：请把图片里的文字复制成文本，或用文字说明"
        elif label in {"音频", "视频"}:
            next_step = "对话材料只收文字：请把音视频里的要点写成文字再传"
        elif label in {"压缩包"}:
            next_step = "请先解压，再上传其中的 TXT/CSV 等文本文件"
        elif label in {"可执行文件", "动态库", "安装包", "二进制文件", "光盘镜像", "Java 包", "编译后的字节码", "磁盘镜像"}:
            next_step = "出于安全考虑，对话材料不接收可执行/二进制文件；请上传文本资料"
        else:
            next_step = "请换一份文本类文件再传"
        raise InvalidRequest(f"「{name}」是{label}，读不出文字 —— {next_step}。")
    if suffix not in _TEXT_SUFFIXES:
        raise InvalidRequest(
            f"「{name}」的文件类型（{suffix}）不在支持范围内 —— 对话材料只收文本类文件（{_ALLOWED_SUFFIX_HINT}）。"
            "请另存为这些格式之一，或把内容复制成文字再传。"
        )


def _looks_binary(data: bytes) -> bool:
    """没有可依的后缀时（或后缀撒谎时）按字节判断：NUL/控制字符占比 >10% 视为二进制。"""
    sample = data[:4096]
    if not sample:
        return False
    control = sum(1 for byte in sample if byte == 0 or byte < 9 or 13 < byte < 32)
    return control / len(sample) > 0.10


def _decode_material(data: bytes, name: str) -> str:
    """把材料字节解成文本；两种常见编码都解不开时给可操作的中文提示。

    为什么不能只靠下游"尽力解码"：`decode_text` 用 `errors="replace"` 保证永远有输出，
    于是"编码坏了"会变成一串替换字符走进模型 —— 用户以为传成功了。这里先严格试一次，
    解不开就在这里说"另存为 UTF-8"，不把乱码放进去。
    """
    for bom, encoding in (
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                break
    for encoding in ("utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidRequest(
        f"「{name}」的文字编码无法识别（既不是 UTF-8 也不是 GBK/GB18030）—— "
        "请在记事本/Excel 里另存为 UTF-8 编码的 TXT，或把里面的文字复制粘贴进来。"
    )


async def _read_material(file: UploadFile) -> bytes:
    """读文件字节并做完这一层的全部边界检查。

    多读一个字节用来判断"超没超"（超限时不截断，如实说超过了）。
    检查顺序是"先便宜、后昂贵"，同时保证每条提示说的是**用户能改的那件事**。
    """
    data = await file.read(_MAX_MATERIAL_BYTES + 1)
    name = _material_display_name(file.filename or "")
    if len(data) > _MAX_MATERIAL_BYTES:
        # 这一条说的是**文件大小**：改法是"只截取/另存相关部分"，不是"删掉几段正文"。
        raise InvalidRequest(
            f"「{name}」这个文件有 {len(data) / 1_000_000:.1f} MB，超过 2MB 上限 —— "
            "对话材料请只截取这件事用得上的那一段，或另存更小的文本再传。"
        )
    if not data:
        raise InvalidRequest(f"「{name}」是空的，换一份再试。")
    _guard_material_suffix(name)
    if PurePosixPath(name).suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        # Content validation/normalization happens in the shared material service.
        return data
    if _looks_binary(data):
        raise InvalidRequest(
            f"「{name}」看起来是二进制文件（含大量不可读字节），读不出文字 —— "
            "请上传文本类文件，或把里面的文字复制粘贴进来。"
        )
    text = _decode_material(data, name)
    if not text.strip():
        raise InvalidRequest(
            f"「{name}」里没有读到文字 —— 确认传的是导出出来的那一份，或把内容复制粘贴进来。"
        )
    if len(text) > _MAX_MATERIAL_CHARS:
        # 这一条说的是**正文字符数**：文件可能不到 2MB，但读出来是一段超长文本。
        raise InvalidRequest(
            f"「{name}」读出来的正文有 {len(text)} 个字，超过 20 万字上限 —— "
            "请只保留这件事用得上的部分再传。"
        )
    return data
