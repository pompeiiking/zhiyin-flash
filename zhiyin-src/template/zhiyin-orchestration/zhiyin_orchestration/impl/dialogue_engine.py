"""Native text/tool stream, isolated from asset contracts and stage instructions."""
from functools import wraps
from hashlib import sha256
import asyncio
import json
import logging
from uuid import uuid4

from pydantic import ValidationError
from agno.agent import Agent
from agno.models.message import Message
from agno.run.agent import RunOutput
from zhiyin_kernel.streaming import emit_progress, is_streaming, cancellation_requested
from zhiyin_kernel.privacy import redact_sensitive
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration.agent import AgentResult

log = logging.getLogger(__name__)


def traced(handler, name):
    @wraps(handler)
    async def call(*args, **kwargs):
        if await cancellation_requested():
            return '{"executed":false,"state":"cancelled"}'
        step = "tool_" + uuid4().hex[:16]
        areas = {"profile": "画像", "plan": "计划", "report": "报告", "academic": "成绩",
                 "calendar": "日历", "directions": "方向方案", "notes": "记录"}
        label = "正在读取" + areas.get(kwargs.get("area"), "资料") if name == "workspace.read" else {
            "profile.read": "正在读取画像", "plan.read": "正在读取计划", "behavior.recent": "正在读取行为记录",
            "material.read": "正在读取材料", "xuezhi.search": "正在查询学职平台",
            "web.search": "正在搜索资料", "kb.search": "正在检索知识库",
            "chart.render": "正在生成图表", "workspace.action": "正在核对操作权限",
            "workspace.classify": "正在分析业务意图",
            "workspace.exploration": "正在整理对话线索", "workspace.report_draft": "正在保存报告草稿",
        }.get(name, "正在读取模块资料")
        parameters = redact_sensitive({k: v for k, v in kwargs.items()
            if k in {"area", "offset", "session_id", "material_id", "query", "question"}})
        emit_progress({"type": "step.started", "step_id": step, "note": label,
                       "tool": name, "parameters": parameters})
        try:
            if name in {"workspace.action", "workspace.report_draft"}:
                # Never apply a read timeout across a write and its receipt.
                value = await handler(*args, **kwargs)
            else:
                async with asyncio.timeout(3 if name == "workspace.classify" else 8):
                    value = await handler(*args, **kwargs)
        except TimeoutError:
            emit_progress({"type": "step.failed", "step_id": step, "note": "本次资料查询超时"})
            return json.dumps({"executed": False, "available": False, "status": "timeout",
                "reason": "查询超时，不代表没有数据；可先回答能够确认的部分，不要重复相同查询。", "retry": False}, ensure_ascii=False)
        except ValidationError as exc:
            emit_progress({"type": "step.failed", "step_id": step, "note": "内容格式需要调整"})
            return json.dumps({"executed": False, "state": "validation_failed",
                "errors": [{"path": list(error["loc"]), "type": error["type"], "message": error["msg"]}
                    for error in exc.errors(include_input=False, include_url=False)[:12]],
                "retry": "只修正列出的字段；报告生成优先用 save_report_draft，verdict和swot必须同级。不要重复提交原来的无效结构。"}, ensure_ascii=False)
        except InvalidRequest as exc:
            emit_progress({"type": "step.failed", "step_id": step, "note": "操作条件尚未满足"})
            return json.dumps({"executed": False, "reason": str(exc), "retry": "先重新读取资料，核对对象和版本；不要盲目重试。"}, ensure_ascii=False)
        except Exception:
            log.exception("对话工具失败：%s", name)
            emit_progress({"type": "step.failed", "step_id": step, "note": "本次操作未完成"})
            return json.dumps({"executed": False, "error": "工具未完成，请核对权限和数据后再继续。"}, ensure_ascii=False)
        completed = label.replace("正在", "已", 1)
        if name in {"workspace.action", "workspace.report_draft"}:
            completed = "已核对操作回执"
        emit_progress({"type": "step.completed", "step_id": step, "note": completed})
        return value
    return call


async def dialogue_tool_names(engine, agent_id):
    """The native dialogue and capability inspection use the same installed pool."""
    from .dialogue_specialists import ROLE_FOCUS
    names = ["workspace.read", "material.read", "workspace.action", "workspace.memory", "workspace.classify", "workspace.exploration", "workspace.report_draft"]
    for role_id in ROLE_FOCUS:
        descriptor = await engine._registry.get_agent(role_id)
        if descriptor and str(getattr(descriptor.status, "value", descriptor.status)) == "enabled":
            names.extend(descriptor.tools)
    if engine.module_tool_names is not None:
        names.extend(await engine.module_tool_names(agent_id))
    legacy = {"workspace.task.set_done", "plan.read", "profile.read", "behavior.recent"}
    return list(dict.fromkeys(name for name in names if name in engine._tools and name not in legacy))


async def invoke_dialogue(engine, request):
    from zhiyin_orchestration.impl.agno_engine import (
        _required_prompt, _renderables_from_run_context, _module_results_from_run_context,
        _module_attempts_from_run_context,
    )
    if engine.refresh_model is not None:
        await engine.refresh_model()
    prompt = await _required_prompt(engine._registry, "conversation.main")
    from .dialogue_specialists import specialist_tools
    presentation = {"lead": request.agent_id, "stage": request.prompt_vars.get("dialogue_focus", ""), "roles": [],
                    "methods": {}, "clues": [], "theories": []}
    names = await dialogue_tool_names(engine, request.agent_id)
    tools = []
    for name in dict.fromkeys(names):
        if name in {"workspace.task.set_done", "plan.read", "profile.read", "behavior.recent"}:
            continue
        handler = engine._tools.get(name)
        if handler is None:
            if name != "web.search":
                log.error("对话工具未装配：%s", name)
            continue
        tools.append(traced(handler, name))
    tools.extend(specialist_tools(engine._registry, presentation))
    kwargs = engine._run_context_kwargs(request)
    model = engine._model_factory(**{k: v for k, v in (prompt.params or {}).items()
                                      if k in {"timeout_s", "temperature", "retries"}})
    fingerprint = sha256(json.dumps({"content": prompt.content, "params": prompt.params},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    emit_progress({"type": "run.model", "model": getattr(model, "id", ""),
                   "prompt_code": prompt.code, "prompt_fingerprint": fingerprint})
    agent = Agent(model=model, instructions=[prompt.content], tools=tools, telemetry=False,
                  tool_call_limit=12, use_json_mode=False, parse_response=False)
    messages = [Message(role=i["role"], content=redact_sensitive(i["content"])) for i in request.history]
    current = request.prompt_vars.get("raw_user_message", request.prompt_vars.get("user_input"))
    if isinstance(current, str):
        # Keep the actual user utterance last, outside the large context JSON.
        # Context remains untrusted user-role data, never a system instruction.
        context = request.model_copy(update={"prompt_vars": {k: v for k, v in request.prompt_vars.items()
            if k not in {"raw_user_message", "user_input"}}})
        messages.append(Message(role="user", content=engine._compose_input(context, {"guide": None})))
        messages.append(Message(role="user", content=redact_sensitive(current)))
    else:
        messages.append(Message(role="user", content=engine._compose_input(request, {"guide": None})))
    text, output, after_tool = "", None, False
    try:
        if is_streaming():
            async for event in agent.arun(input=messages, stream=True, stream_events=True, yield_run_output=True, **kwargs):
                if await cancellation_requested():
                    break
                if isinstance(event, RunOutput):
                    output = event
                elif str(getattr(event, "event", "")) == "ToolCallStarted":
                    # Assistant preambles belong to the earlier model turn.
                    # The next post-tool answer replaces that turn; concatenating
                    # both can repeat the whole answer (e.g. after record_clues).
                    after_tool = True
                elif str(getattr(event, "event", "")) == "RunContent":
                    delta = getattr(event, "content", "")
                    if isinstance(delta, str) and delta:
                        if after_tool:
                            text, after_tool = "", False
                        text += delta
                        emit_progress({"type": "message.delta", "text": text, "delta": delta, "note": "正在回复"})
        else:
            output = await agent.arun(input=messages, **kwargs)
        if output is not None:
            status = getattr(output, "status", None)
            if str(getattr(status, "value", status)).lower() == "error":
                raise RuntimeError("模型返回错误状态")
            messages_out = getattr(output, "messages", None) or []
            last = messages_out[-1] if messages_out else None
            if (getattr(last, "role", None) == "assistant" and not getattr(last, "tool_calls", None)
                    and isinstance(getattr(last, "content", None), str) and last.content.strip()):
                text = last.content
            elif not text:
                text = str(getattr(output, "content", "") or "")
        return AgentResult(agent_id=presentation["lead"], raw_text=text, valid=bool(text.strip()),
            structured={"dialogue_stage": presentation["stage"], "dialogue_roles": presentation["roles"],
                "dialogue_clues": presentation["clues"], "dialogue_theories": [
                    {"theory_id": key, "name": presentation["methods"][key].name,
                     "stage": presentation["stage"]} for key in presentation["theories"]]},
            renderables=_renderables_from_run_context(kwargs), module_results=_module_results_from_run_context(kwargs),
            module_attempts=_module_attempts_from_run_context(kwargs), source_refs=list(kwargs["dependencies"].get("source_refs", [])))
    except Exception:
        log.exception("自然对话模型调用失败")
        return AgentResult(agent_id=request.agent_id, valid=False, degraded=True, raw_text=text,
            errors=["对话模型未能完成"], renderables=_renderables_from_run_context(kwargs))
