"""Model-led dialogue. No keyword routing, stage forcing or textual write shortcuts.

Business writes use one durable action boundary. Modules remain read-only.
"""
from __future__ import annotations

from zhiyin_business.services.academic_preview import AcademicPreviewChanged

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Literal, Any
import logging
import asyncio
import time

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_business.contracts.common import AgentBadge, BehaviorGuide, BehaviorEventDraft, ConversationMessage, GuideOption, IntelRef, TheoryRef
from zhiyin_business.ports.orchestrator import TurnResult
from zhiyin_business.contracts.dialogue_actions import DialogueOperation
from zhiyin_business.policies.renderers import validate_renderables
from zhiyin_business.services.conversation_ledger import ConversationLedger, digest, utcnow
from zhiyin_business.services.unit_of_work import atomic_repository
from zhiyin_business.services.dialogue_exploration import ExplorationUpdate, privacy_stamp
from zhiyin_business.services.memory_policy import MemoryPolicyService
from zhiyin_kernel import profile_taxonomy
from zhiyin_kernel.report_quality import report_verdict_issue
from zhiyin_kernel.assets import ActionPlan, Report, DirectionPlan, CalendarNode
from zhiyin_kernel.blackboard import ProfileClue
from zhiyin_kernel.enums import LoopStage, BehaviorEventType, ProfileSource
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_kernel.privacy import redact_sensitive
from zhiyin_kernel.streaming import emit_progress
from zhiyin_orchestration import AgentRequest

log = logging.getLogger(__name__)
active_dialogue: ContextVar[Any] = ContextVar("active_dialogue", default=None)


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: DialogueOperation
    payload: dict = Field(default_factory=dict)
    authorization: Literal["automatic", "explicit", "proposal"] = "proposal"
    evidence: str = Field(default="", max_length=16000)
    expected_version: str = ""
    action_id: str = ""
    supersedes_action_id: str = ""


def serial(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [serial(item) for item in value]
    return value


def context_cost(text):
    """Conservative mixed-language token estimate, independent of a vendor tokenizer."""
    non_ascii = sum(ord(ch) > 127 for ch in text)
    return non_ascii * 2 + (len(text) - non_ascii + 2) // 3


def field_stamp(action, key):
    field = next((f for f in (action.get("before") or {}).get("fields", []) if f["key"] == key), None)
    return datetime.fromisoformat(field["updated_at"]) if field else None


def profile_time(payload: dict, name: str) -> datetime | None:
    """画像写入里的可选时间：只接受带时区的 ISO 时间，未知不补当前时间。"""
    raw = payload.get(name)
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        parsed = raw
    else:
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidRequest(f"{name} 不是有效的时间格式") from exc
    if parsed.tzinfo is None:
        raise InvalidRequest(f"{name} 需要带时区")
    return parsed


class DialogueRuntime:
    AGENT = "career_advisor"
    LABELS = {"academic.import": "导入课表或成绩", "profile.update": "更新画像", "task.set_done": "更新任务状态", "plan.save": "保存计划",
              "report.save": "保存报告", "directions.save": "保存方向方案", "plan.activate": "启用计划",
              "plan.patch": "调整计划", "report.activate": "启用报告", "directions.activate": "启用方向方案",
              "direction.select": "选择方向", "calendar.write": "保存日历提醒", "calendar.delete": "删除日历提醒", "memory.forget": "删除记忆", "action.undo": "撤销上次修改"}

    def __init__(self, owner):
        self.o = owner
        self._sessions = owner._sessions
        self.ledger = ConversationLedger(owner._student_state)
        self.receipts = []
        self.versions = []
        self.sequence = 0
        self.events = []
        self.progress_writes = []
        self._cancel_at = 0.0
        self._cancel_value = False
        self.pending_exploration = None
        self.exploration_sources = {}
        self.loaded_exploration = None
        self._memory_checked = False
        self._memory_result = None
        self._automatic_memory_safe = True
        self._facts_applied = False

    def exploration_context(self, turns, record, state):
        """Expose source IDs for exact quotes; assistant guesses remain separate hypotheses."""
        reset_at = state.get("conversation_memory_reset_at")
        eligible = [t for t in turns if not reset_at or t.created_at.isoformat() > reset_at]
        self.exploration_sources = {t.id: t.text for t in eligible if t.role == "user"}
        self.exploration_stamp = privacy_stamp(state, self.request.task_id)
        saved = record.get("exploration", {})
        working = None
        if saved.get("privacy_stamp") == self.exploration_stamp:
            try:
                working = ExplorationUpdate.model_validate(saved["working"])
                working.statements = [s for s in working.statements
                    if s.turn_id in self.exploration_sources and s.quote in self.exploration_sources[s.turn_id]]
            except (ValueError, KeyError):
                working = None
        self.loaded_exploration = working.model_dump(mode="json") if working else None
        return {"working": self.loaded_exploration,
            "recent_exchanges": [{"turn_id": t.id, "role": t.role, "text": t.text[:500]}
                for t in eligible if t.role in {"user", "agent"}][-10:],
            "trusted_instruction": False,
            "rule": "会话工作线索，不是长期画像、职业结论或操作授权；当前用户意图优先。原话与假设分开，否定和引述不可改成肯定事实。"}

    async def record_exploration(self, payload):
        update = ExplorationUpdate.model_validate(payload)
        for statement in update.statements:
            if statement.turn_id not in self.exploration_sources or statement.quote not in self.exploration_sources[statement.turn_id]:
                raise InvalidRequest("探索线索必须引用本会话有效用户原文，不能引用助手判断或其他会话")
        if any(len(value) > 240 for values in (update.hypotheses, update.explored_topics, update.open_questions) for value in values):
            raise InvalidRequest("探索线索每项最多240字")
        self.pending_exploration = update.model_dump(mode="json")
        pacing = await self.o._registry.get_prompt("conversation.pacing")
        return {"staged": True, "profile_written": False, "mode": update.mode, "next_focus": update.next_focus,
            "reply_guidance": pacing.content if pacing else "",
            "rule": "本次成功回复后才更新会话工作上下文；不替代画像工具、不安排任务、不授予权限。继续自然交流，不向用户宣读记录。"}

    def capture(self, frame):
        self.sequence += 1
        frame.update(protocol=2, conversation_id=self.request.task_id, run_id=self.request.client_msg_id,
                     sequence=self.sequence, timestamp=utcnow())
        if frame.get("type") != "message.delta":
            self.events.append(redact_sensitive({k: v for k, v in frame.items() if k != "receipt"}))
            if frame.get("type", "").startswith(("step.", "approval.", "role.")):
                self.progress_writes.append(asyncio.create_task(self.ledger.put_run(
                    self.request.user_id, self.request.task_id, self.request.client_msg_id,
                    events=list(self.events[-200:]), last_status=frame.get("note", ""))))

    def event(self, kind, note="", **fields):
        emit_progress({"protocol": 2, "type": kind, "conversation_id": self.request.task_id,
                       "run_id": self.request.client_msg_id, "sequence": self.sequence,
                       "timestamp": utcnow(), "note": note, **fields})

    async def read_target(self, operation):
        user = self.request.user_id
        if operation == "academic.import":
            value = await self.o.academic_reader(user)
        elif operation.startswith("profile") or operation == "memory.forget":
            value = await self.o._profiles.get(user)
        elif operation.startswith("direction"):
            value = await self.o._assets.list_direction_plans(user)
        elif operation.startswith("report"):
            value = await self.o._assets.get_report(user)
        elif operation.startswith("calendar"):
            value = await self.o._functions.list_calendar_nodes(user)
        else:
            value = await self.o._assets.get_action_plan(user)
        return serial(value)

    async def earlier_context(self, turns, record, reset_at):
        """Compact older messages on demand; summaries never authorize writes.

        Keep recent complete messages outside the summary. Every retained item
        cites stored source turns, and a memory reset invalidates the old summary.
        """
        summary = record.get("context_summary", {})
        if summary.get("reset_at") != reset_at:
            summary = {}
        eligible = [t for t in turns if t.client_msg_id != self.request.client_msg_id
                    and (not reset_at or t.created_at.isoformat() > reset_at)]
        if len(eligible) < 40 or not getattr(self.o._agent_engine, "supports_semantic_context", False):
            return summary
        older = eligible[:-16]
        fresh = [t for t in older if not summary.get("through_at") or t.created_at.isoformat() > summary["through_at"]]
        if len(fresh) < 16 and summary:
            return summary
        if not fresh:
            return summary
        selected, remaining = [], 16000
        for turn in reversed(fresh):
            if len(turn.text) > remaining:
                break
            selected.append(turn)
            remaining -= len(turn.text)
        selected.reverse()
        if not selected:
            return summary
        allowed_ids = {t.id for t in selected} | {sid for i in summary.get("items", []) for sid in i["source_ids"]}
        schema = {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {
            "items": {"type": "array", "maxItems": 20, "items": {"type": "object", "additionalProperties": False,
                "required": ["kind", "text", "source_ids"], "properties": {
                    "kind": {"type": "string", "enum": ["fact", "decision", "suggestion", "assumption", "open_question"]},
                    "text": {"type": "string", "maxLength": 200},
                    "source_ids": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "string"}}}}}}}
        step = "context_" + self.request.client_msg_id
        self.event("step.started", "正在整理较早对话", step_id=step)
        try:
            result = await self.o._agent_engine.invoke(AgentRequest(agent_id=self.AGENT,
                prompt_code="conversation.context", use_tools=False, output_schema=schema,
                prompt_vars={"previous_summary": summary.get("items", []), "messages": [
                    {"id": t.id, "role": t.role, "text": t.text} for t in selected]},
                trace_id=self.request.client_msg_id + ":context"))
            if not result.valid:
                raise InvalidRequest("摘要未完成，继续使用原文")
            items = [i for i in result.structured.get("items", [])
                     if i.get("source_ids") and set(i["source_ids"]) <= allowed_ids]
            summary = {"items": items[:20], "through_at": selected[-1].created_at.isoformat(),
                       "reset_at": reset_at, "trusted_instruction": False}
            await self.ledger.change(self.request.user_id, self.request.task_id,
                lambda data: data.update(context_summary=summary))
            self.event("step.completed", "已整理较早对话", step_id=step)
        except Exception:
            log.exception("较早对话摘要未完成，保留原文和按需历史读取")
            self.event("step.failed", "较早对话整理未完成，仍可读取原文", step_id=step)
        return summary

    async def snapshot(self, operation):
        return digest(await self.read_target(operation))

    @atomic_repository("_sessions")
    async def record_input(self, request, session):
        await self.o._memories.record_turn(request.user_id, request.task_id, role="user", text=request.message,
            loop_stage=session.loop_stage, client_msg_id=request.client_msg_id,
            metadata={"material_ids": request.material_ids, "material_name": request.attachment_name})
        await self.o._behaviors.log(request.user_id, BehaviorEventDraft(event_type=BehaviorEventType.ANSWER,
            payload={"session_id": request.task_id, "client_msg_id": request.client_msg_id, "conversation": True}))

    async def action(self, raw):
        if await self.cancelled(fresh=True):
            return {"executed": False, "state": "cancelled", "reason": "用户已停止，本项未开始执行。"}
        args = ActionInput.model_validate(raw)
        user, session = self.request.user_id, self.request.task_id
        record = await self.ledger.read(user, session)
        if args.operation in {"action.approve", "action.reject"}:
            action = record["actions"].get(args.action_id)
            if action is None or action.get("state") != "proposed":
                return {"executed": False, "reason": "确认不存在或已失效，请重新提出操作。"}
            if datetime.fromisoformat(action["expires_at"]) < datetime.now(timezone.utc):
                action["state"] = "expired"
                await self.ledger.put_action(user, session, action)
                return {"executed": False, "reason": "确认已过期，没有执行。"}
            if not args.evidence or args.evidence not in self.request.message:
                return {"executed": False, "reason": "必须由当前用户明确确认。"}
            if args.operation == "action.approve" and not self.request.option_id:
                pending_count = sum(a["state"] == "proposed" and datetime.fromisoformat(a["expires_at"]) > datetime.now(timezone.utc)
                                    for a in record["actions"].values())
                if pending_count > 1:
                    return {"executed": False, "reason": "有多项待确认变更，请点击对应的确认按钮，避免改错对象。"}
            if args.operation == "action.reject":
                action["state"] = "rejected"
                await self.ledger.put_action(user, session, action)
                return {"executed": False, "state": "rejected", "action_id": action["id"]}
            # Confirmation authorizes the persisted parameters, never fresh model arguments.
            return await self.execute(action, approved=True)

        if not args.evidence or args.evidence not in self.request.message:
            args.authorization = "proposal"
        normalized = await self.validate_action(args)
        superseded = None
        if args.supersedes_action_id:
            superseded = record["actions"].get(args.supersedes_action_id)
            if not superseded or superseded["state"] != "proposed" or superseded["operation"] != args.operation:
                raise InvalidRequest("待调整的提案不存在或已失效")
            # 取代必须落在同一个对象上。只校验操作名时，一次批量 profile.update
            # 可以把任意字段的提案取代掉：没被重新提出的字段会永久停在 superseded，
            # 用户原话里逐项说清楚的资料就此静默丢失（#38）。
            if args.operation == "profile.update":
                before_key = str((superseded.get("payload") or {}).get("key") or "")
                after_key = str(normalized.get("key") or "")
                if before_key != after_key:
                    raise InvalidRequest("只能替换同一字段的上一版提案；其他字段请分别提出，不能借一次写入取代")
            if not args.evidence or args.evidence not in self.request.message:
                raise InvalidRequest("调整提案需要本轮用户要求")
        action_id = "action_" + digest({"run": self.request.client_msg_id, "op": args.operation,
                                        "payload": normalized})[:24]
        previous = record["actions"].get(action_id)
        if previous:
            return {"action_id": action_id, "state": previous["state"], "executed": previous["state"] == "succeeded",
                    "receipt": previous.get("receipt"), "reason": "已登记的操作不重复执行。"}
        scope_operation = normalized.get("scope_operation", args.operation)
        before = await self.read_target(scope_operation)
        version = digest(before)
        if args.expected_version and args.expected_version != version:
            return {"executed": False, "reason": "资料版本已变化，请重新读取后再操作。"}
        action = {"id": action_id, "run_id": self.request.client_msg_id, "operation": args.operation, "payload": normalized,
                  "scope_operation": scope_operation, "before": before,
                  "authorization": args.authorization, "evidence": args.evidence,
                  "supersedes_action_id": args.supersedes_action_id or "",
                  "base_version": version, "state": "proposed", "created_at": utcnow(),
                  "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}
        await self.ledger.put_action(user, session, action)
        if superseded and superseded["id"] != action_id:
            superseded.update(state="superseded", superseded_by=action_id)
            await self.ledger.put_action(user, session, superseded)
        # Only narrow, recoverable changes can use direct semantic authorization.
        direct = args.authorization == "explicit" and args.operation in {
            "profile.update", "task.set_done", "plan.save", "report.save", "directions.save"}
        direct = direct or (args.authorization == "explicit" and args.operation == "plan.patch" and len(normalized["updates"]) <= 3)
        automatic = args.authorization == "automatic" and args.operation == "profile.update"
        if direct or automatic:
            return await self.execute(action)
        self.event("approval.required", "等待你确认" + self.LABELS[args.operation], action_id=action_id)
        return {"executed": False, "state": "proposed", "action_id": action_id,
                "change": normalized, "reason": "已保存具体变更，等待用户确认。"}

    async def cancelled(self, fresh=False):
        if not fresh and time.monotonic() - self._cancel_at < 0.25:
            return self._cancel_value
        record = await self.ledger.read(self.request.user_id, self.request.task_id)
        self._cancel_at = time.monotonic()
        self._cancel_value = bool(record.get("delete_requested") or record["runs"].get(self.request.client_msg_id, {}).get("cancel_requested"))
        return self._cancel_value

    async def extract_facts(self, *, policy_only=False):
        """Resolve privacy before the tool loop; persist fallback facts after it.

        No string classifiers. It cannot grant approval, execute other writes or
        promote a statement from an attachment into a personal fact.
        """
        if not getattr(self.o._agent_engine, "supports_semantic_memory", False) or await self.cancelled():
            return
        state = await self.o._student_state.get(self.request.user_id)
        automatic = state.get("preferences", {}).get("automatic_memory", True)
        temporary = state.get("conversation_settings", {}).get(self.request.task_id, {}).get("temporary")
        schema = {"type": "object", "additionalProperties": False, "required": ["updates"], "properties": {
            "updates": {"type": "array", "maxItems": 24, "items": {"type": "object", "additionalProperties": False,
                "required": ["key", "value", "evidence", "assertion_type"], "properties": {"key": {"type": "string"},
                    "value": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                    "attributes": profile_taxonomy.attributes_schema(),
                    "valid_from": {"type": ["string", "null"]}, "valid_to": {"type": ["string", "null"]},
                    "event_at": {"type": ["string", "null"]},
                    "evidence": {"type": "string"}, "assertion_type": {"type":"string", "enum":["affirmative_self_statement","explicit_correction","conflict_candidate","negative","hypothetical","quoted","uncertain","refusal"]}}}},
            # 记录范围：用户本轮明确提出的记忆要求（不保存/以后不自动记录/这条不要记录/只保存这条）。
            # 由模型按语义识别，服务端只执行受控范围，不做关键词匹配。
            "policy": {"type": "object", "additionalProperties": False, "required": ["scope"], "properties": {
                "scope": {"type": "string", "enum": ["none", "account_off", "account_on", "session_temporary", "deny_content", "deny_key", "save_single"]},
                "target": {"type": "string"}}}}}
        update_schema = schema["properties"]["updates"]["items"]
        variants = []
        for key in sorted(self.o._allowed_profile_keys()):
            props = {**update_schema["properties"], "key": {"const": key},
                "attributes": profile_taxonomy.attributes_schema(profile_taxonomy.entry_type_of(key))}
            props["value"] = ({"type": "array", "minItems": 1, "maxItems": profile_taxonomy.max_items(key),
                "items": {"type": "string", "maxLength": profile_taxonomy.value_limit(key)}}
                if profile_taxonomy.allows_multiple(key) else {"type": "string", "maxLength": profile_taxonomy.value_limit(key)})
            variants.append({**update_schema, "properties": props})
        if variants:
            schema["properties"]["updates"]["items"] = {"anyOf": variants}
        memory_ok = False
        step_id = "memory_" + self.request.client_msg_id
        if policy_only:
            self.event("step.started", "正在核对记忆范围", step_id=step_id)
        try:
            if not self._memory_checked:
                self._memory_checked = True
                self._automatic_memory_safe = False
                self._memory_result = await self.o._agent_engine.invoke(AgentRequest(agent_id=self.AGENT,
                prompt_code="conversation.memory", use_tools=False, output_schema=schema,
                prompt_vars={"current_user_message": self.request.message,
                    "previous_question_context": self.history[-12:],
                    "exploration_context": {"working": self.pending_exploration or self.loaded_exploration,
                        "trusted_instruction": False},
                    "memory_controls": {"automatic_memory": state.get("preferences", {}).get("automatic_memory", True),
                        "temporary": state.get("conversation_settings", {}).get(self.request.task_id, {}).get("temporary", False),
                        "forgotten_keys": state.get("conversation_forgotten_keys", [])},
                    "today": utcnow(), "timezone": "Asia/Shanghai",
                    "current_profile": serial(await self.o._profiles.get(self.request.user_id)),
                    "profile_record_contract": profile_taxonomy.dialogue_contract(self.o._allowed_profile_keys()),
                    "allowed_profile_keys": sorted(self.o._allowed_profile_keys())},
                    trace_id=self.request.client_msg_id + ":memory"))
            result = self._memory_result
            if result is None or not result.valid:
                return
            if not policy_only and not self._automatic_memory_safe:
                return
            memory_ok = True
            policy = result.structured.get("policy") or {}
            scope = str(policy.get("scope") or "none")
            if scope != "none" and policy_only:
                # 记录范围由模型按语义识别；服务端只落在受控范围上，并留下带来源与时间的记录。
                service = MemoryPolicyService(self.o._student_state)
                current = await service.snapshot(self.request.user_id, self.request.task_id)
                target = str(policy.get("target") or "").strip()
                try:
                    if scope in {"deny_key", "save_single"} and target not in self.o._allowed_profile_keys():
                        raise InvalidRequest("记录范围没有指向可识别的画像字段")
                    if scope == "account_off" and current["account_automatic"]:
                        await service.set_account_automatic(self.request.user_id, False, source="conversation", note="用户要求以后不自动记录")
                    elif scope == "account_on":
                        await service.set_account_automatic(self.request.user_id, True, source="conversation", note="用户要求恢复自动记录")
                        await service.clear_single(self.request.user_id, self.request.task_id)
                        await service.set_session_temporary(self.request.user_id, self.request.task_id, False, source="conversation", note="用户要求恢复自动记录")
                    elif scope == "session_temporary" and not current["session_temporary"]:
                        await service.set_session_temporary(self.request.user_id, self.request.task_id, True, source="conversation", note="用户要求本次会话不保存长期画像")
                    elif scope == "deny_content":
                        fingerprint = digest({"user_id": self.request.user_id, "message": self.request.message})
                        if fingerprint not in current["content_denials"]:
                            await service.deny_content(self.request.user_id, fingerprint, source="conversation", note="用户要求这条内容不要记录")
                    elif scope == "deny_key" and target and target not in current["denied_keys"]:
                        await service.deny_key(self.request.user_id, target, source="conversation", note="用户要求这个字段不要记录")
                    elif scope == "save_single" and target and target not in current["single_keys"]:
                        await service.grant_single(self.request.user_id, self.request.task_id, target, source="conversation", note="用户要求只保存明确那一条")
                except Exception:  # noqa: BLE001 - 策略没记上不能把本轮对话打成失败
                    memory_ok = False
                    log.warning("记录范围未保存（scope=%s）", scope, exc_info=True)
                    return
            self._automatic_memory_safe = True
            if policy_only:
                return
            if self._facts_applied:
                return
            self._facts_applied = True
            state = await self.o._student_state.get(self.request.user_id)
            automatic = state.get("preferences", {}).get("automatic_memory", True)
            temporary = state.get("conversation_settings", {}).get(self.request.task_id, {}).get("temporary")
            fields = {f.key: f for f in await self.o._profiles.get_fields(self.request.user_id)}
            for item in result.structured.get("updates", []):
                if not automatic or temporary:
                    break
                if item.get("assertion_type") not in {"affirmative_self_statement", "explicit_correction", "conflict_candidate"}:
                    continue
                if item.get("evidence") not in self.request.message or not item.get("evidence"):
                    continue
                key = item.get("key")
                try:
                    if item["assertion_type"] != "conflict_candidate" and key in fields and fields[key].value == profile_taxonomy.normalize_value(key, item.get("value")) and (
                        not item.get("attributes") or item["attributes"] == dict(fields[key].attributes or {})) and all(
                            not item.get(name) or profile_time(item, name) == getattr(fields[key], name)
                            for name in ("valid_from", "valid_to", "event_at")):
                        continue
                    await self.action({"operation": "profile.update", "payload": {k: v for k, v in item.items() if k != "evidence"},
                        "authorization": "explicit" if item["assertion_type"] == "explicit_correction" else "automatic", "evidence": item["evidence"]})
                except InvalidRequest:
                    log.info("自动事实未通过写入条件，不覆盖已有记录")
        except Exception:
            log.exception("语义事实提取未完成；保持本轮对话理解")
        finally:
            if policy_only:
                self.event("step.completed" if memory_ok else "step.failed",
                    "已核对记忆范围" if memory_ok else "记忆范围未能核对，本轮仍可继续交流", step_id=step_id)

    async def validate_action(self, args):
        payload = dict(args.payload)
        user = self.request.user_id
        if args.operation == "academic.import":
            preview = await self.o.academic_previews.read(user, str(payload.get("preview_id", "")))
            return preview.model_dump(mode="json")
        stable_id = digest({"user": user, "session": self.request.task_id, "run": self.request.client_msg_id, "operation": args.operation, "payload": payload})[:20]
        if args.operation == "action.undo":
            record = await self.ledger.read(user, self.request.task_id)
            original = record["actions"].get(str(payload.get("target_id", "")))
            if not original or original["state"] != "succeeded" or original["operation"] in {"memory.forget", "action.undo", "direction.select", "academic.import"}:
                raise InvalidRequest("该操作不支持自动撤销，请明确说明新的修改要求")
            if original.get("after_version") != await self.snapshot(original["scope_operation"]):
                raise InvalidRequest("操作之后数据已变化，不能覆盖后续修改")
            if original.get("before") is None and original["operation"] != "profile.update":
                raise InvalidRequest("该操作没有可恢复的上一版，请明确提出调整要求")
            return {"target_id": original["id"], "scope_operation": original["scope_operation"],
                    "operation": original["operation"], "before": original.get("before"),
                    "original_payload": original["payload"], "draft_only": bool(original.get("receipt", {}).get("draft_saved"))}
        if args.operation == "profile.update":
            key = str(payload.get("key", ""))
            if key not in self.o._allowed_profile_keys():
                raise InvalidRequest("该字段不在允许自动维护的画像字段中")
            value = payload.get("value")
            if not isinstance(value, (str, int, float, list)):
                raise InvalidRequest("画像值无效")
            # 长度不在这里另立口径：键/类别上限在 kernel.profile_taxonomy 一处定义，
            # 对话预检与画像服务必须同一份（此前预检 2000 字会挡掉合法的长经历）。
            limit = profile_taxonomy.value_limit(key)
            items = value if isinstance(value, list) else [value]
            if any(len(str(item)) > limit for item in items):
                raise InvalidRequest(f"这条画像最多 {limit} 个字，请拆成一条读得完的事实")
            attributes = payload.get("attributes") or {}
            if not isinstance(attributes, dict):
                raise InvalidRequest("画像属性无效")
            # 预检与画像服务共用同一份词表校验：取值形状、条数、属性都在这里先拒，
            # 不把错误留到事务里变成“结果未知”。
            entry_type = profile_taxonomy.entry_type_of(key)
            normalized_value = profile_taxonomy.normalize_value(key, value, entry_type)
            profile_taxonomy.normalize_attributes(entry_type, attributes)
            valid_from = profile_time(payload, "valid_from")
            valid_to = profile_time(payload, "valid_to")
            event_at = profile_time(payload, "event_at")
            if valid_from is not None and valid_to is not None and valid_from > valid_to:
                raise InvalidRequest("有效范围的开始时间不能晚于结束时间")
            if not args.evidence or args.evidence not in self.request.message:
                raise InvalidRequest("画像更新必须引用本轮用户的明确自述")
            if isinstance(value, str) and key in {"major", "school", "study_year", "student_name", "degree_level"} and value not in args.evidence:
                raise InvalidRequest("身份类画像须使用原话中的肯定值，不将否定概括成新身份")
            memory = await MemoryPolicyService(self.o._student_state).snapshot(user, self.request.task_id)
            if memory["session_temporary"]:
                raise InvalidRequest("本次是临时会话，不会保存长期画像；请先明确恢复记录。")
            current: dict[str, Any] = {}
            if args.authorization == "automatic":
                if not self._automatic_memory_safe:
                    raise InvalidRequest("本轮记忆范围未能核对，暂不自动保存画像；仍可继续交流。")
                # 所有自动写入前统一读服务端持久化策略（账号/会话/内容拒绝/只保存一条），
                # 不靠提示词或最近几条消息维持限制。
                allowed, reason = await MemoryPolicyService(self.o._student_state).check_auto_write(
                    user,
                    self.request.task_id,
                    key,
                    fingerprint=digest({"user_id": user, "message": self.request.message}),
                )
                if not allowed:
                    raise InvalidRequest(reason)
                if key in {"courses", "scores"}:
                    raise InvalidRequest("课表和成绩需单独导入或用户明确保存；咨询某门课不等于已提供课表")
                current = {f.key: f for f in await self.o._profiles.get_fields(user)}
                if key in current and current[key].source.value in {"record", "user_edit"} and payload.get("assertion_type") != "conflict_candidate":
                    raise InvalidRequest("已有手动或核验字段需要用户明确更正")
                if payload.get("assertion_type") not in {"affirmative_self_statement", "explicit_correction", "conflict_candidate"}:
                    raise InvalidRequest("只有肯定本人自述或明确更正可自动记录")
            # 新说法与当前值不一致、又没有被用户明确更正：并存标记，不覆盖当前事实。
            # 设计第 7 节：能并存就先并存，只有影响当前服务时才向用户澄清。
            record_conflict = False
            wants_conflict = payload.get("assertion_type") == "conflict_candidate"
            if wants_conflict:
                current = {f.key: f for f in await self.o._profiles.get_fields(user)}
                if key not in current:
                    raise InvalidRequest("还没有可供核对的当前记录，不能把候选说法直接当成事实")
            if entry_type.value in {"interest", "career_focus"} and payload.get("assertion_type") != "explicit_correction":
                # 兴趣/职业关注先合并再落库：首次写入也要走同一套极性拆分与去重，
                # 否则「喜欢…但不喜欢…」会在第一轮把否定项直接写进兴趣（#40）。
                before_preference = current.get(key)
                if before_preference is None:
                    before_preference = next((field for field in await self.o._profiles.get_fields(user) if field.key == key), None)
                value, attributes, record_conflict = profile_taxonomy.merge_preferences(
                    key, before_preference, normalized_value, attributes)
            elif args.authorization == "automatic" and key in current:
                record_conflict = profile_taxonomy.normalize_value(key, current[key].value) != normalized_value and payload.get("assertion_type") != "explicit_correction"
            record_conflict = record_conflict or wants_conflict
            save_scope = str(payload.get("save_scope") or "")
            if save_scope not in {"", "single"}:
                raise InvalidRequest("保存范围无效")
            if save_scope == "single" and args.authorization != "explicit":
                raise InvalidRequest("“只保存这一条”需要你明确要求保存这一条")
            # 原话引用：把这一轮真实用户消息的身份写进记录，而不是只留一段可被改写的文字。
            origin_ref = f"conversation:{self.request.task_id}:{self.request.client_msg_id}"
            return {"key": key, "value": value, "label": next((spec.label for spec in self.o._profile_vocabulary() if spec.key == key), key),
                    "attributes": attributes, "origin_ref": origin_ref, "save_scope": save_scope,
                    "record_conflict": record_conflict,
                    "valid_from": valid_from.isoformat() if valid_from else None,
                    "valid_to": valid_to.isoformat() if valid_to else None,
                    "event_at": event_at.isoformat() if event_at else None}
        if args.operation == "task.set_done":
            plan = await self.o._assets.get_action_plan(user)
            found = [t for p in (plan.phases if plan else []) for t in p.tasks if t.id == payload.get("task_id")]
            title = payload.get("task_text")
            if len(found) == 1 and title and title != found[0].text:
                raise InvalidRequest("任务编号与标题不一致，请重新核对")
            if not found and isinstance(title, str) and title and title in self.request.message:
                found = [t for p in (plan.phases if plan else []) for t in p.tasks if t.text == title]
            if len(found) != 1 or not isinstance(payload.get("done"), bool):
                raise InvalidRequest("必须定位唯一的真实任务并指定完成状态")
            return {"task_id": found[0].id, "done": payload["done"], "task": found[0].text}
        if args.operation == "plan.patch":
            plan = await self.o._assets.get_action_plan(user)
            if plan is None:
                raise InvalidRequest("当前没有可调整的计划")
            updates = payload.get("updates", [])
            if not isinstance(updates, list) or not 1 <= len(updates) <= 30:
                raise InvalidRequest("请指定需要修改的任务")
            tasks = {t.id: t for p in plan.phases for t in p.tasks}
            changed = []
            for update in updates:
                task = tasks.get(update.get("task_id"))
                fields = update.get("fields", {})
                if task is None or not fields or set(fields) - {"text", "due_date", "estimated_minutes", "scheduled_at"}:
                    raise InvalidRequest("任务或修改字段无效")
                validated = type(task).model_validate({**task.model_dump(mode="json"), **fields})
                changed.append({"task_id": task.id, "before": task.model_dump(mode="json"),
                                "after": validated.model_dump(mode="json")})
            if len({i["task_id"] for i in changed}) != len(changed):
                raise InvalidRequest("同一任务不能在提案中重复修改")
            return {"updates": changed}
        if args.operation == "plan.save":
            plan = ActionPlan.model_validate({**payload, "id": "plan_" + stable_id,
                                             "reminders_synced": False})
            if not plan.phases or not any(p.tasks for p in plan.phases):
                raise InvalidRequest("计划必须包含真实可执行的任务")
            current = await self.o._assets.get_action_plan(user)
            existing = {t.id: t for p in (current.phases if current else []) for t in p.tasks}
            for pi, phase in enumerate(plan.phases):
                for ti, task in enumerate(phase.tasks):
                    if task.id not in existing or existing[task.id].text != task.text:
                        task.id = f"t_{stable_id[:8]}_{pi}_{ti}"
                        task.done, task.done_at, task.status, task.progress = False, None, "pending", 0
                    else:
                        previous = existing[task.id]
                        task.done, task.done_at, task.status, task.progress = previous.done, previous.done_at, previous.status, previous.progress
            ids = [t.id for p in plan.phases for t in p.tasks]
            if len(ids) != len(set(ids)):
                raise InvalidRequest("计划任务编号重复")
            return plan.model_dump(mode="json")
        if args.operation == "report.save":
            report = Report.model_validate({**payload, "user_id": user, "id": "report_" + stable_id,
                "version": 1, "generated_at": utcnow()})
            issue = report_verdict_issue(report.verdict)
            if issue:
                raise InvalidRequest(issue)
            return report.model_dump(mode="json")
        if args.operation == "directions.save":
            plans = [DirectionPlan.model_validate({**p, "id": f"direction_{stable_id}_{index}",
                       "selected": False, "match_score": None}) for index, p in enumerate(payload.get("plans", []))]
            if not 1 <= len(plans) <= 6:
                raise InvalidRequest("方向方案数量应为1至6个")
            return {"plans": serial(plans)}
        if args.operation in {"plan.activate", "report.activate", "directions.activate"}:
            record = await self.ledger.read(user, self.request.task_id)
            source = record["actions"].get(str(payload.get("draft_id", "")))
            source_op = args.operation.replace(".activate", ".save")
            if not source or source["operation"] != source_op or source["state"] != "succeeded":
                raise InvalidRequest("找不到已保存的草稿")
            return {"draft_id": source["id"], "content": source["payload"]}
        if args.operation == "direction.select":
            plans = await self.o._assets.list_direction_plans(user)
            selected = next((p for p in plans if p.id == payload.get("plan_id")), None)
            if selected is None:
                raise InvalidRequest("找不到该方向方案")
            return {"plan_id": selected.id, "name": selected.name, "target_desc": selected.target_desc}
        if args.operation in {"calendar.write", "calendar.delete"}:
            if self.o._functions is None:
                raise InvalidRequest("日历服务尚未装配")
            nodes = await self.o._functions.list_calendar_nodes(user)
            node_id = str(payload.get("node_id", ""))
            current = next((n for n in nodes if n.node_id == node_id), None)
            if args.operation == "calendar.delete":
                if current is None:
                    raise InvalidRequest("找不到该日历提醒")
                return current.model_dump(mode="json")
            if node_id and current is None:
                raise InvalidRequest("修改前请读取并核对日历条目")
            node = CalendarNode.model_validate({**payload, "user_id": user,
                "node_id": current.node_id if current else "calendar_" + stable_id, "source": "manual"})
            if not node.title.strip() or len(node.title) > 200 or node.due_at is None or node.due_at.tzinfo is None:
                raise InvalidRequest("提醒需要明确标题和含时区的日期时间，请先澄清时间")
            return node.model_dump(mode="json")
        if args.operation == "memory.forget":
            if payload.get("key") not in self.o._allowed_profile_keys():
                raise InvalidRequest("画像字段无效")
            fields = {f.key: f for f in await self.o._profiles.get_fields(user)}
            field = fields.get(payload["key"])
            return {"key": payload["key"], "label": field.label if field else payload["key"], "value": field.value if field else "未保存"}
        raise InvalidRequest("未知操作")

    @atomic_repository("_sessions")
    async def execute(self, action, approved=False):
        # The operation and its receipt are committed in the same local transaction.
        async with self.o._assets.mutation_scope(self.request.user_id):
            return await self._execute_transaction(action, approved)

    async def _restore_superseded(self, action):
        """A replacement that never landed must not leave the old proposal dead.

        被取代的提案在新提案执行失败后原本永久停在 superseded：用户既看不到它，
        也不能再确认，而新提案也失败了 —— 一次写入失败会连带吞掉上一条可用提案。
        """
        target_id = str(action.get("supersedes_action_id") or "")
        if not target_id:
            return
        record = await self.ledger.read(self.request.user_id, self.request.task_id)
        target = record["actions"].get(target_id)
        if target is None or target.get("state") != "superseded" or target.get("superseded_by") != action["id"]:
            return
        target["state"] = "proposed"
        target["superseded_by"] = ""
        await self.ledger.put_action(self.request.user_id, self.request.task_id, target)

    async def _has_version_conflict(self, action):
        """执行前的版本校验。

        profile.update 只比较**目标字段**自己的时间戳：同一轮里模型连续写学校、专业、
        学制等不同字段时，第一条写入会改变整份画像快照，但不应让同轮其他字段全部
        被判成「数据已变化」而静默 superseded（#38）。同一字段被并发改写仍然会拦住。
        """
        if action.get("scope_operation") == "profile.update" or action.get("operation") == "profile.update":
            key = str((action.get("payload") or {}).get("key") or "")
            current = next((field for field in await self.o._profiles.get_fields(self.request.user_id)
                            if field.key == key), None)
            return (current.updated_at if current else None) != field_stamp(action, key)
        return await self.snapshot(action.get("scope_operation", action["operation"])) != action["base_version"]

    async def _execute_transaction(self, action, approved):
        user, session = self.request.user_id, self.request.task_id
        if await self.cancelled(fresh=True):
            action["state"] = "rejected"
            await self.ledger.put_action(user, session, action)
            await self._restore_superseded(action)
            return {"executed": False, "state": "cancelled", "reason": "用户已停止，本项未开始执行。"}
        if await self._has_version_conflict(action):
            action["state"] = "superseded"
            await self.ledger.put_action(user, session, action)
            await self._restore_superseded(action)
            return {"executed": False, "reason": "数据已变化，本次确认未执行。"}
        action.update(state="executing", approved=approved)
        await self.ledger.put_action(user, session, action)
        self.event("step.started", "正在" + self.LABELS[action["operation"]], step_id=action["id"])
        try:
            receipt = await self.apply(action)
        except AcademicPreviewChanged as exc:
            action["state"] = "superseded"
            await self.ledger.put_action(user, session, action)
            await self._restore_superseded(action)
            self.event("step.failed", "预览已失效，请重新核对", step_id=action["id"])
            result = {"executed": False, "action_id": action["id"], "state": "superseded", "reason": str(exc)}
        except InvalidRequest as exc:
            action["state"] = "rejected"
            await self.ledger.put_action(user, session, action)
            await self._restore_superseded(action)
            self.event("step.failed", str(exc), step_id=action["id"])
            result = {"executed": False, "action_id": action["id"], "state": "rejected", "reason": str(exc)}
        except Exception:
            log.exception("对话操作失败：%s", action["id"])
            action["state"] = "outcome_unknown"
            await self.ledger.put_action(user, session, action)
            await self._restore_superseded(action)
            self.event("step.failed", "操作未能确认完成，请查看记录后核对", step_id=action["id"])
            result = {"executed": False, "action_id": action["id"], "state": "outcome_unknown"}
        else:
            action.update(state="succeeded", receipt=serial(receipt),
                after_version=await self.snapshot(action.get("scope_operation", action["operation"])))
            await self.ledger.put_action(user, session, action)
            result = {"executed": True, "action_id": action["id"], "state": "succeeded", "receipt": serial(receipt)}
            self.event("step.completed", "已" + self.LABELS[action["operation"]], step_id=action["id"], receipt=result)
        self.receipts.append(result)
        return result

    async def apply(self, action):
        user, payload, operation = self.request.user_id, action["payload"], action["operation"]
        if operation == "academic.import":
            return await self.o.academic_writer(user, payload["preview_id"])
        if operation == "action.undo":
            old_op, before, original = payload["operation"], payload["before"], payload["original_payload"]
            if payload.get("draft_only"):
                pass  # Withdraw an unactivated draft without rewriting active data.
            elif old_op == "profile.update":
                field = next((f for f in (before or {}).get("fields", []) if f["key"] == original["key"]), None)
                if field:
                    await self.o._profiles.correct_field(user, field["key"], field["value"], check_version=True,
                        expected_updated_at=field_stamp(action, field["key"]))
                else:
                    await self.o._profiles.drop_field(user, original["key"], check_version=True,
                        expected_updated_at=field_stamp(action, original["key"]))
            elif old_op == "task.set_done":
                task = next(t for p in before["phases"] for t in p["tasks"] if t["id"] == original["task_id"])
                writer = getattr(self.o, "task_writer", None)
                if writer:
                    await writer(user, task["id"], done=task["done"])
                else:
                    await self.o._assets.mark_action_task_done(user, task["id"], done=task["done"])
            elif old_op.startswith("calendar"):
                node = next((n for n in before if n["node_id"] == original["node_id"]), None)
                if node:
                    await self.o._functions.write_calendar_node(user, CalendarNode.model_validate(node))
                else:
                    await self.o._functions.delete_calendar_node(user, original["node_id"])
            elif old_op.startswith("plan"):
                self.versions.append(await self.o._assets.save_action_plan(user, ActionPlan.model_validate(before), diff_from_previous="用户确认撤销上次修改", preserve_task_state=False))
            elif old_op.startswith("report"):
                self.versions.append(await self.o._assets.save_report(user, Report.model_validate(before), diff_from_previous="用户确认恢复上一版报告"))
            elif old_op.startswith("direction"):
                self.versions.append(await self.o._assets.save_direction_plans(user, [DirectionPlan.model_validate(p) for p in before], diff_from_previous="用户确认恢复上一版方向"))
            else:
                raise InvalidRequest("该操作不支持恢复")
            record = await self.ledger.read(user, self.request.task_id)
            target = record["actions"][payload["target_id"]]
            target["state"] = "reverted"
            await self.ledger.put_action(user, self.request.task_id, target)
            return {"restored_action": target["id"]}
        if operation == "profile.update":
            payload = dict(payload)
            for name in ("valid_from", "valid_to", "event_at"):
                payload[name] = profile_time(payload, name)
            save_scope = str(payload.pop("save_scope", "") or "")
            record_conflict = bool(payload.pop("record_conflict", False))
            policy = MemoryPolicyService(self.o._student_state)
            if record_conflict:
                # 与当前记录不一致：保存为冲突提案，当前事实保持不变，等用户裁定。
                revision = await self.o._profiles.record_conflict(
                    user,
                    payload["key"],
                    payload["value"],
                    confidence=0.9,
                    source="conversation",
                    label=payload.get("label", ""),
                    evidence=[action["evidence"]],
                    attributes=payload.get("attributes") or {},
                    origin_ref=payload.get("origin_ref", ""),
                    valid_from=payload.get("valid_from"),
                    valid_to=payload.get("valid_to"),
                    event_at=payload.get("event_at"),
                )
                return {"conflict": True, "revision_id": revision.id,
                        "message": "这次说法与已记录的不一致，已单独保存待你核对；当前记录没有改。"}
            old = {f.key: f for f in await self.o._profiles.get_fields(user)}
            if action["authorization"] == "automatic" and payload["key"] in old:
                if old[payload["key"]].source.value in {"user_edit", "record"}:
                    raise InvalidRequest("已有手动或核验字段需要用户明确更正")
            if action["authorization"] == "explicit":
                result = await self.o._profiles.correct_field(user, payload["key"], payload["value"],
                    check_version=True, expected_updated_at=field_stamp(action, payload["key"]),
                    attributes=payload.get("attributes") or {}, origin_ref=payload.get("origin_ref", ""),
                    evidence=[action["evidence"]], valid_from=payload.get("valid_from"),
                    valid_to=payload.get("valid_to"), event_at=payload.get("event_at"))
                def restore(state):
                    state["conversation_forgotten_keys"] = [k for k in state.get("conversation_forgotten_keys", []) if k != payload["key"]]
                    return state
                await self.o._student_state.update(user, restore)
                if save_scope == "single":
                    # “只保存这一条”：只放行这一条，不恢复其他自动记录。
                    await policy.grant_single(user, self.request.task_id, payload["key"])
                return result
            result = await self.o._profiles.update_field(user, **payload, confidence=0.9,
                source="conversation", evidence=[action["evidence"]], check_version=True,
                expected_updated_at=field_stamp(action, payload["key"]))
            # 一次单条授权只用于一次自动写入；其他自动记录仍保持关闭。
            await policy.consume_single(user, self.request.task_id, payload["key"])
            return result
        if operation == "task.set_done":
            writer = getattr(self.o, "task_writer", None)
            if writer is not None:
                return await writer(user, payload["task_id"], done=payload["done"])
            return await self.o._assets.mark_action_task_done(user, payload["task_id"], done=payload["done"])
        if operation == "calendar.write":
            return await self.o._functions.write_calendar_node(user, CalendarNode.model_validate(payload))
        if operation == "calendar.delete":
            return {"deleted": await self.o._functions.delete_calendar_node(user, payload["node_id"])}
        if operation == "memory.forget":
            # Existing profile service owns actual field deletion and derived invalidation.
            await self.o._profiles.drop_field(user, payload["key"], check_version=True,
                expected_updated_at=field_stamp(action, payload["key"]))
            # 删除一项记忆后，本会话基于它产生的「系统理解」也不能继续展示。
            try:
                await self.o._profiles.replace_session_clues(user, self.request.task_id, [])
            except Exception:  # noqa: BLE001 - 字段已删除，线索收尾失败不阻断回执
                log.warning("删除记忆后清理待验证线索失败", exc_info=True)
            def forget(state):
                state["conversation_memory_reset_at"] = utcnow()
                state["conversation_forgotten_keys"] = sorted(set(state.get("conversation_forgotten_keys", [])) | {payload["key"]})
                return state
            await self.o._student_state.update(user, forget)
            return {"forgotten": payload["key"]}
        if operation == "plan.save":
            current = await self.o._assets.get_action_plan(user)
            if current is not None:
                return {"draft_saved": True, "draft_id": action["id"], "plan": payload, "active_changed": False}
            version = await self.o._assets.save_action_plan(user, ActionPlan.model_validate(payload),
                depends_on_profile_keys=[f.key for f in await self.o._profiles.get_fields(user)],
                diff_from_previous="用户明确创建计划；未写入额外日历提醒")
            self.versions.append(version)
            return {"version": serial(version), "active_changed": True, "calendar_written": False}
        dependencies = [f.key for f in await self.o._profiles.get_fields(user)]
        if operation == "plan.activate":
            version = await self.o._assets.save_action_plan(user, ActionPlan.model_validate(payload["content"]),
                depends_on_profile_keys=dependencies,
                diff_from_previous="用户确认启用计划草稿")
        elif operation in {"report.save", "report.activate"}:
            if operation == "report.save" and await self.o._assets.get_report(user) is not None:
                return {"draft_saved": True, "draft_id": action["id"], "active_changed": False}
            report = Report.model_validate(payload.get("content", payload))
            issue = report_verdict_issue(report.verdict)
            if issue:
                raise InvalidRequest(issue)
            version = await self.o._assets.save_report(user, report,
                depends_on_profile_keys=dependencies,
                diff_from_previous="用户请求生成报告")
        elif operation in {"directions.save", "directions.activate"}:
            if operation == "directions.save" and await self.o._assets.list_direction_plans(user):
                return {"draft_saved": True, "draft_id": action["id"], "active_changed": False}
            source = payload.get("content", payload)
            version = await self.o._assets.save_direction_plans(user,
                [DirectionPlan.model_validate(p) for p in source["plans"]], depends_on_profile_keys=dependencies,
                diff_from_previous="用户请求方向方案")
        elif operation == "plan.patch":
            plan = await self.o._assets.get_action_plan(user)
            changes = {c["task_id"]: c["after"] for c in payload["updates"]}
            for phase in plan.phases:
                phase.tasks = [type(t).model_validate(changes[t.id]) if t.id in changes else t for t in phase.tasks]
            version = await self.o._assets.save_action_plan(user, plan,
                depends_on_profile_keys=dependencies, diff_from_previous="用户确认调整计划", preserve_task_state=False)
        elif operation == "direction.select":
            writer = getattr(self.o, "direction_writer", None)
            if writer is None:
                raise InvalidRequest("方向选择的业务链未完整装配")
            return await writer(user, payload["plan_id"])
        else:
            raise InvalidRequest("此操作未装配")
        self.versions.append(version)
        return {"version": serial(version)}

    async def run(self, request):
        self.request = request
        state = await self.o._student_state.get(request.user_id)
        if request.task_id in state.get("deleted_conversations", []):
            raise ResourceNotFound("会话已删除，请创建新会话")
        session = await self.o._sessions.get(request.task_id)
        if session is None:
            # 会话 id 只能由服务端签发。未知 id 直接拒绝，不能按「咨询对话」静默建会话：
            # 过期/串号的 task_id 会让用户的消息进入一条看似全新的会话，原历史像是消失，
            # 而界面没有任何提示（#35）。需要新对话时走 POST /app/task/enter。
            raise ResourceNotFound("会话不存在或已失效，请从任务入口重新进入")
        if session.user_id != request.user_id:
            raise ResourceNotFound("会话不属于当前账号，请从任务入口重新进入")
        request_hash = digest(request.model_dump(mode="json", exclude={"client_msg_id"}))
        data = await self.ledger.read(request.user_id, request.task_id)
        prior = data["runs"].get(request.client_msg_id)
        if prior:
            if prior["request_hash"] != request_hash:
                raise InvalidRequest("重复请求标识对应的内容不同")
            if prior.get("result"):
                return TurnResult.model_validate(prior["result"])
            if prior.get("archived"):
                stored = await self.o._memories.find_reply(request.user_id, request.client_msg_id)
                metadata = stored.metadata if stored else {}
                result = metadata.get("result", {})
                if metadata.get("request_hash") == request_hash and result.get("task_id") == request.task_id:
                    return TurnResult.model_validate(result)
            # An interrupted request may have written. Never blindly re-run it.
            raise InvalidRequest("上一轮结果尚待核对，请查看会话和操作记录，不要重复执行。")
        await self.ledger.put_run(request.user_id, request.task_id, request.client_msg_id,
            request_hash=request_hash, state="running")
        self.event("run.started", "正在分析你的问题")
        from zhiyin_kernel.privacy import SENSITIVE
        if SENSITIVE.search(request.message + request.attachment_text + request.attachment_name):
            text = "消息包含敏感信息，未保存原文，也未交给模型。请脱敏后重新发送。"
            safe_request = request.model_copy(update={"message": "[敏感信息已拦截]", "attachment_text": "", "attachment_name": ""})
            return await self.finish(safe_request, session, text)
        await self.record_input(request, session)
        if self.o._cache:
            await self.o._cache.invalidate_for_event("session_changed")
        turns = await self.o._memories.list_turns(request.user_id, request.task_id, limit=100)
        state = await self.o._student_state.get(request.user_id)
        reset_at = state.get("conversation_memory_reset_at")
        earlier = await self.earlier_context(turns, data, reset_at)
        history, budget = [], 12000
        for t in reversed(turns):
            if reset_at and t.created_at and t.created_at.isoformat() <= reset_at:
                continue
            if t.client_msg_id == request.client_msg_id and t.role == "user":
                continue
            cost = context_cost(t.text)
            if t.role not in {"user", "agent", "system"} or cost > budget:
                continue
            history.append({"role": "user" if t.role == "user" else "assistant", "content": t.text,
                "agent_id": t.agent_id or '',
                "focus": str(getattr(t.loop_stage, 'value', t.loop_stage) or '')})
            budget -= cost
        history.reverse()
        self.history = history
        profile = await self.o._profiles.get(request.user_id)
        pending = [a for a in data["actions"].values() if a["state"] == "proposed"
                   and datetime.fromisoformat(a["expires_at"]) > datetime.now(timezone.utc)]
        self.pending_summary = [{"id": a["id"], "operation": a["operation"]} for a in pending]
        token = active_dialogue.set(self)
        try:
            if request.option_id and request.option_id.startswith("action."):
                parts = request.option_id.split(".")
                if len(parts) != 3:
                    raise InvalidRequest("确认操作格式无效")
                receipt = await self.action({"operation": "action.approve" if parts[2] == "accept" else "action.reject",
                    "action_id": parts[1], "evidence": request.message})
                text = "操作已完成。" if receipt.get("executed") else receipt.get("reason", "本次操作未执行。")
                return await self.finish(request, session, text)
            variables = {"chosen_option": {"option_id": request.option_id, "value": request.option_value,
                                           "label": request.message}} if request.option_id else {}
            # Resolve persistent memory preferences before the model can execute
            # any write. Reuse the semantic result for fallback extraction later.
            self.exploration_context(turns, data, state)
            await self.extract_facts(policy_only=True)
            profile = await self.o._profiles.get(request.user_id)
            state = await self.o._student_state.get(request.user_id)
            images = []
            if request.material_ids:
                from zhiyin_business.services.analysis_access import current_scope
                scope = current_scope(request.user_id)
                if scope is not None and 'material' not in scope.sources:
                    raise InvalidRequest("本轮未允许使用材料")
                for material_id in request.material_ids:
                    body = await self.o._memories.material_body(request.user_id, material_id)
                    if body.image_data_url:
                        images.append(body.image_data_url)
                if len(images) > 4:
                    raise InvalidRequest("每轮最多分析4张图片，请分次发送。")
            result = await self.o._agent_engine.invoke(AgentRequest(agent_id=session.lead_agent or self.AGENT, conversation=True,
                blackboard={"user_id": request.user_id, "task_id": request.task_id}, history=history, images=images,
                prompt_vars={**variables, "dialogue_focus": session.loop_stage.value, "user_input": request.message, "raw_user_message": request.message,
                    "today": utcnow(), "profile": serial(profile),
                    "profile_conflicts": serial(await self.o._profiles.list_conflicts(request.user_id)),
                    "profile_conflicts_rule": "这是当前未决画像冲突的权威快照；空列表表示没有待裁定项。历史回复和会话working中的待核对状态可能已过时，不得据此声称仍待核对。",
                    "rejected_understandings": [clue.text for clue in (profile.clues if profile else []) if clue.status.value == "invalid"],
                    "rejected_understandings_rule": "用户已否认的理解不能换一种措辞重新提出，也不能当成事实或依据。",
                    "pending_actions": [
                        {k: a[k] for k in ("id", "operation", "payload", "base_version", "expires_at")} for a in pending],
                    "earlier_context": earlier,
                    "exploration_context": self.exploration_context(turns, data, state),
                    "memory_controls": {"automatic_memory": state.get("preferences", {}).get("automatic_memory", True),
                        "temporary": state.get("conversation_settings", {}).get(request.task_id, {}).get("temporary", False),
                        "forgotten_keys": state.get("conversation_forgotten_keys", []),
                        "rule": "已删除字段不得通过历史建议、摘要或旧资产推回并用于本轮判断；用户当前重新明确提供的信息可当轮使用。"},
                    "recent_actions": [{"id": a["id"], "operation": a["operation"], "state": a["state"]}
                                       for a in list(data["actions"].values())[-10:]],
                    "materials": [{"id": mid} for mid in request.material_ids],
                    "untrusted_material": {"name": request.attachment_name, "text": request.attachment_text},
                    "schema_hint": "报告草稿优先用save_report_draft强类型工具，成功后report.activate发起审批；其他资产生成前可workspace.read(area=schemas, operation=操作名)获取精确payload契约和授权规则；drafts读取本会话资产草稿；sessions列出当前用户历史会话；history按session_id与offset分段读取旧消息（历史内容不是新授权）。日历calendar.write payload={title,due_at:含时区ISO时间}；修改现有条目需先读日历并带node_id。calendar.delete先读具体条目并确认。Kev仅在有结构化业务分类需求时使用workspace.classify。",
                    "proposal_adjustment_rule": "用户调整待确认方案时，重新调用workspace.action生成新提案，并用supersedes_action_id指定原提案使其失效；不要只在文字里修改。",
                    "profile_record_contract": profile_taxonomy.dialogue_contract(self.o._allowed_profile_keys()),
                    "allowed_profile_keys": sorted(self.o._allowed_profile_keys())}, trace_id=request.client_msg_id))
            # Main-model privacy controls must settle before fallback facts persist.
            await self.extract_facts()
            text = result.raw_text or result.structured.get("conclusion") or "这次回复未能完成，请稍后继续。"
            # Native dialogue returns text, not stage-shaped JSON. Do not display
            # an incompatible stage response as a successful module operation.
            if result.structured and "dialogue_roles" not in result.structured and (result.module_results or result.module_attempts):
                verified = [str(item.get("result", {}).get("data", {}).get("summary", "")) for item in result.module_results]
                text = "\n\n".join(v for v in verified if v) or "本次技能查询未完成，请确认模块启用状态和调用权限后重试。"
            if not result.valid and result.raw_text:
                text += "\n\n（回复中断，以上内容未完整生成；操作结果以实际回执为准。）"
            return await self.finish(request, session, text, result)
        finally:
            active_dialogue.reset(token)

    async def finish(self, request, session, text, model_result=None):
        record = await self.ledger.read(request.user_id, request.task_id)
        pending = [a for a in record["actions"].values() if a["state"] == "proposed"
                   and datetime.fromisoformat(a["expires_at"]) > datetime.now(timezone.utc)]
        guide = BehaviorGuide(kind="question", text="")
        if pending:
            # Persisted card contains the full change; no guessing from prose endings.
            current = pending[-1]
            guide = BehaviorGuide(kind="options", text="待确认：" + self.LABELS[current["operation"]], options=[
                GuideOption(option_id=f"action.{current['id']}.accept", label="确认执行", value={"action_id": current["id"]}),
                GuideOption(option_id=f"action.{current['id']}.decline", label="暂不执行", value={"action_id": current["id"]})])
        system_receipts = []
        profile_labels = [record["actions"][r["action_id"]]["payload"].get("label", "个人信息")
            for r in self.receipts if r.get("executed") and not (isinstance(r.get("receipt"), dict) and r["receipt"].get("conflict")) and record["actions"].get(r["action_id"], {}).get("operation") == "profile.update"]
        if len(profile_labels) > 1:
            system_receipts.append(ConversationMessage(role="system", text="已更新画像：" + "、".join(dict.fromkeys(profile_labels)) + "。"))
        for receipt in self.receipts:
            action = record["actions"].get(receipt["action_id"], {})
            if receipt.get("executed") and isinstance(receipt.get("receipt"), dict) and receipt["receipt"].get("conflict"):
                system_receipts.append(ConversationMessage(role="system", text="另一种说法已保留待核对，当前记录没有覆盖。"))
                continue
            if len(profile_labels) > 1 and receipt.get("executed") and action.get("operation") == "profile.update":
                continue
            if receipt.get("executed") and isinstance(receipt.get("receipt"), dict) and receipt["receipt"].get("draft_saved"):
                name = {"plan.save": "计划", "report.save": "报告", "directions.save": "方向方案"}.get(action.get("operation"), "内容")
                system_receipts.append(ConversationMessage(role="system", text=f"已保存{name}草稿，正式版本尚未替换。"))
                continue
            name = self.LABELS.get(action.get("operation"), "执行操作")
            system_receipts.append(ConversationMessage(role="system", text=("已" + name + "。")
                if receipt.get("executed") else "操作结果待核对，请查看当前数据后再继续。"))
        from zhiyin_kernel.enums import DIALOGUE_ROLE_FOCUS as ROLE_FOCUS
        lead = session.lead_agent or self.AGENT
        stage = session.loop_stage
        if model_result and model_result.valid and model_result.structured.get("dialogue_roles"):
            candidate = model_result.agent_id
            focus = model_result.structured.get("dialogue_stage")
            if candidate in ROLE_FOCUS and focus in ROLE_FOCUS[candidate]:
                lead, stage = candidate, LoopStage(focus)
                await self.o._sessions.update_stage(session.id, stage, lead)
                session = (await self.o._sessions.get(session.id)) or session
        descriptor = await self.o._registry.get_agent(lead)
        # Preserve the actual author of partial text without committing its
        # provisional focus as the conversation's confirmed state.
        speaker = lead
        if model_result and not model_result.valid and model_result.raw_text:
            partial_speaker = model_result.structured.get('dialogue_partial_speaker')
            if partial_speaker in ROLE_FOCUS and partial_speaker != 'info_scout':
                partial_descriptor = await self.o._registry.get_agent(partial_speaker)
                if partial_descriptor and str(getattr(partial_descriptor.status, 'value', partial_descriptor.status)) == 'enabled':
                    speaker = partial_speaker
        result = TurnResult(task_id=request.task_id, conversation=True, session=session, stage=stage,
            badge=AgentBadge(agent_id=lead, name=descriptor.name if descriptor else "知音",
                             role_summary=descriptor.role_summary if descriptor else "职业发展顾问"),
            messages=system_receipts + [ConversationMessage(role="agent", agent_id=speaker, text=text,
                clues=model_result.structured.get("dialogue_clues", []) if model_result else [],
                theory_refs=[TheoryRef.model_validate(ref) for ref in model_result.structured.get("dialogue_theories", [])] if model_result else [],
                intel_refs=[IntelRef.model_validate(ref) for ref in model_result.source_refs] if model_result else [],
                renderables=validate_renderables(model_result.renderables if model_result else []))],
            guide=guide, asset_versions=self.versions)
        for receipt in system_receipts:
            await self.o._memories.record_turn(request.user_id, request.task_id, role="system", text=receipt.text,
                loop_stage=session.loop_stage, client_msg_id=request.client_msg_id)
        await self.o._memories.record_turn(request.user_id, request.task_id, role="agent", text=text,
            loop_stage=stage, agent_id=speaker, client_msg_id=request.client_msg_id,
            renderables=[serial(r) for r in result.messages[-1].renderables],
            metadata={"result": result.model_dump(mode="json"), "request_hash": record["runs"][request.client_msg_id]["request_hash"],
                      "actions": pending, "receipts": self.receipts})
        cancelled = await self.cancelled()
        allow_clues, _ = await MemoryPolicyService(self.o._student_state).check_auto_write(
            request.user_id, request.task_id, "__profile_clue__",
            fingerprint=digest({"user_id": request.user_id, "message": request.message}))
        if self.pending_exploration and model_result and model_result.valid and not cancelled:
            current_state = await self.o._student_state.get(request.user_id)
            if privacy_stamp(current_state, request.task_id) == self.exploration_stamp:
                await self.ledger.change(request.user_id, request.task_id, lambda data: data.update(
                    exploration={"working": self.pending_exploration, "privacy_stamp": self.exploration_stamp,
                                 "updated_at": utcnow(), "trusted_instruction": False}))
                # 设计第 3.2 节：AI 的有限理解单独保存为「待验证线索」，与事实字段分开；
                # 同一会话整体替换，反复分析不会让同一处理解看起来像被多次验证过。
                # Session work context remains available even when long-term
                # profile publication is forbidden. Do not log a refusal as an error.
                if allow_clues and self._automatic_memory_safe:
                    await self.persist_profile_clues(request)
        if self.progress_writes:
            await asyncio.gather(*self.progress_writes)
        await self.ledger.put_run(request.user_id, request.task_id, request.client_msg_id,
            events=self.events[-200:], state="cancelled" if cancelled else "waiting_approval" if pending else "completed", result=result.model_dump(mode="json"))
        await self.ledger.compact(request.user_id, request.task_id)
        changes = set()
        for receipt in self.receipts:
            if not receipt.get("executed"):
                continue
            action = record["actions"][receipt["action_id"]]
            operation = action["payload"]["operation"] if action["operation"] == "action.undo" else action["operation"]
            changes.add("calendar_changed" if operation.startswith("calendar") else
                "profile_field_updated" if operation in {"profile.update", "memory.forget"} else
                "asset_state_changed" if operation in {"task.set_done", "direction.select"} else "asset_version_changed")
        for event in changes:
            try:
                if self.o._cache:
                    await self.o._cache.invalidate_for_event(event)
                invalidate = getattr(self.o, "conversation_invalidator", None)
                if invalidate:
                    await invalidate(request.user_id, event)
            except Exception:
                log.exception("对话变更已落库，派生缓存失效待重试：%s", event)
        self.event("run.completed", "回复完成", state="waiting_approval" if pending else "completed")
        return result

    async def persist_profile_clues(self, request):
        try:
            statements = self.pending_exploration.get("statements") or []
            policy = await MemoryPolicyService(self.o._student_state).snapshot(request.user_id, request.task_id)
            # A later turn must not publish a quote from an earlier denied message.
            if any(digest({"user_id": request.user_id, "message": self.exploration_sources.get(item.get("turn_id"), "")})
                   in policy["content_denials"] for item in statements):
                return
            hypotheses = [str(item).strip() for item in (self.pending_exploration.get("hypotheses") or []) if str(item).strip()]
            quotes = [str(item.get("quote", "")).strip() for item in statements if str(item.get("quote", "")).strip()]
            session_prefix = f"conversation:{request.task_id}:"
            linked_keys = [field.key for field in await self.o._profiles.get_fields(request.user_id)
                           if (field.origin_ref or "").startswith(session_prefix)][:20]
            record = await self.ledger.read(request.user_id, request.task_id)
            linked_keys = list(dict.fromkeys(linked_keys + [action["payload"]["key"]
                for action in record["actions"].values() if action["operation"] == "profile.update"]))[:20]
            if set(linked_keys).intersection(policy["denied_keys"]):
                return
            clues = [ProfileClue(id="", user_id=request.user_id, session_id=request.task_id,
                                text=text[:240], evidence=quotes[:12], field_keys=linked_keys,
                                source=ProfileSource.ASSESSMENT, created_at=utcnow(), updated_at=utcnow())
                     for text in hypotheses]
            await self.o._profiles.replace_session_clues(request.user_id, request.task_id, clues)
        except Exception:  # noqa: BLE001 - 线索旁路失败不阻断回复
            log.warning("待验证线索保存失败；本轮对话仍保留工作快照", exc_info=True)
