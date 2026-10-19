"""Model-led dialogue. No keyword routing, stage forcing or textual write shortcuts.

Business writes use one durable action boundary. Modules remain read-only.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Literal, Any
import logging
import asyncio
import time

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_business.contracts.common import AgentBadge, BehaviorGuide, ConversationMessage, GuideOption, IntelRef
from zhiyin_business.ports.orchestrator import TurnResult
from zhiyin_business.policies.renderers import validate_renderables
from zhiyin_business.services.conversation_ledger import ConversationLedger, digest, utcnow
from zhiyin_business.services.unit_of_work import atomic_repository
from zhiyin_kernel.assets import ActionPlan, Report, DirectionPlan, CalendarNode
from zhiyin_kernel.blackboard import TaskSession
from zhiyin_kernel.enums import LoopStage, TaskStatus
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_kernel.privacy import redact_sensitive
from zhiyin_kernel.streaming import emit_progress
from zhiyin_orchestration import AgentRequest

log = logging.getLogger(__name__)
active_dialogue: ContextVar[Any] = ContextVar("active_dialogue", default=None)


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["profile.update", "task.set_done", "plan.save", "report.save", "directions.save",
                       "plan.activate", "plan.patch", "report.activate", "directions.activate", "direction.select", "calendar.write", "calendar.delete", "memory.forget", "action.undo", "action.approve", "action.reject"]
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


class DialogueRuntime:
    AGENT = "career_advisor"
    LABELS = {"profile.update": "更新画像", "task.set_done": "更新任务状态", "plan.save": "保存计划",
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

    def capture(self, frame):
        self.sequence += 1
        frame.update(protocol=2, conversation_id=self.request.task_id, run_id=self.request.client_msg_id,
                     sequence=self.sequence, timestamp=utcnow())
        if frame.get("type") != "message.delta":
            self.events.append(redact_sensitive({k: v for k, v in frame.items() if k != "receipt"}))
            if frame.get("type", "").startswith(("step.", "approval.")):
                self.progress_writes.append(asyncio.create_task(self.ledger.put_run(
                    self.request.user_id, self.request.task_id, self.request.client_msg_id,
                    events=list(self.events[-200:]), last_status=frame.get("note", ""))))

    def event(self, kind, note="", **fields):
        emit_progress({"protocol": 2, "type": kind, "conversation_id": self.request.task_id,
                       "run_id": self.request.client_msg_id, "sequence": self.sequence,
                       "timestamp": utcnow(), "note": note, **fields})

    async def read_target(self, operation):
        user = self.request.user_id
        if operation.startswith("profile") or operation == "memory.forget":
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

    async def extract_facts(self):
        """A semantic fallback for short answers missed by the conversational tool loop.

        No string classifiers. It cannot grant approval, execute other writes or
        promote a statement from an attachment into a personal fact.
        """
        if not getattr(self.o._agent_engine, "supports_semantic_memory", False) or await self.cancelled():
            return
        state = await self.o._student_state.get(self.request.user_id)
        if not state.get("preferences", {}).get("automatic_memory", True):
            return
        if state.get("conversation_settings", {}).get(self.request.task_id, {}).get("temporary"):
            return
        record = await self.ledger.read(self.request.user_id, self.request.task_id)
        if any(a.get("run_id") == self.request.client_msg_id and a["operation"] == "profile.update"
               and a["state"] == "succeeded" for a in record["actions"].values()):
            return
        schema = {"type": "object", "additionalProperties": False, "required": ["updates"], "properties": {
            "updates": {"type": "array", "maxItems": 8, "items": {"type": "object", "additionalProperties": False,
                "required": ["key", "value", "evidence", "assertion_type"], "properties": {"key": {"type": "string"},
                    "value": {"type": "string"}, "evidence": {"type": "string"}, "assertion_type": {"type":"string", "enum":["affirmative_self_statement","explicit_correction","negative","hypothetical","quoted","uncertain","refusal"]}}}}}}
        memory_ok = False
        step_id = "memory_" + self.request.client_msg_id
        self.event("step.started", "正在整理对话记忆", step_id=step_id)
        try:
            result = await self.o._agent_engine.invoke(AgentRequest(agent_id=self.AGENT,
                prompt_code="conversation.memory", use_tools=False, output_schema=schema,
                prompt_vars={"current_user_message": self.request.message,
                    "previous_question_context": self.history[-4:],
                    "allowed_profile_keys": sorted(self.o._allowed_profile_keys())},
                trace_id=self.request.client_msg_id + ":memory"))
            if not result.valid:
                return
            memory_ok = True
            fields = {f.key: f for f in await self.o._profiles.get_fields(self.request.user_id)}
            for item in result.structured.get("updates", []):
                if item.get("assertion_type") not in {"affirmative_self_statement", "explicit_correction"}:
                    continue
                if item.get("evidence") not in self.request.message or not item.get("evidence"):
                    continue
                if item.get("key") in fields and fields[item["key"]].value == item.get("value"):
                    continue
                try:
                    await self.action({"operation": "profile.update", "payload": {"key": item["key"], "value": item["value"], "assertion_type": item["assertion_type"]},
                        "authorization": "automatic", "evidence": item["evidence"]})
                except InvalidRequest:
                    log.info("自动事实未通过写入条件，不覆盖已有记录")
        except Exception:
            log.exception("语义事实提取未完成；保持本轮对话理解")
        finally:
            self.event("step.completed" if memory_ok else "step.failed",
                "已核对对话记忆" if memory_ok else "记忆整理未完成，本轮对话仍可继续", step_id=step_id)

    async def validate_action(self, args):
        payload = dict(args.payload)
        user = self.request.user_id
        stable_id = digest({"user": user, "session": self.request.task_id, "run": self.request.client_msg_id, "operation": args.operation, "payload": payload})[:20]
        if args.operation == "action.undo":
            record = await self.ledger.read(user, self.request.task_id)
            original = record["actions"].get(str(payload.get("target_id", "")))
            if not original or original["state"] != "succeeded" or original["operation"] in {"memory.forget", "action.undo"}:
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
            if not isinstance(value, (str, int, float, list)) or len(str(value)) > 2000:
                raise InvalidRequest("画像值无效")
            if not args.evidence or args.evidence not in self.request.message:
                raise InvalidRequest("画像更新必须引用本轮用户的明确自述")
            if isinstance(value, str) and key in {"major", "school", "study_year", "student_name", "degree_level"} and value not in args.evidence:
                raise InvalidRequest("身份类画像须使用原话中的肯定值，不将否定概括成新身份")
            state = await self.o._student_state.get(user)
            if not state.get("preferences", {}).get("automatic_memory", True) and args.authorization != "explicit":
                raise InvalidRequest("自动记忆已关闭")
            if state.get("conversation_settings", {}).get(self.request.task_id, {}).get("temporary") and args.authorization != "explicit":
                raise InvalidRequest("临时会话不自动写入画像")
            if key in state.get("conversation_forgotten_keys", []) and args.authorization != "explicit":
                raise InvalidRequest("该记忆已删除，只有用户明确要求才能重新保存")
            if args.authorization == "automatic":
                if key in {"courses", "scores"}:
                    raise InvalidRequest("课表和成绩需单独导入或用户明确保存；咨询某门课不等于已提供课表")
                current = {f.key: f for f in await self.o._profiles.get_fields(user)}
                if key in current and current[key].source.value in {"record", "user_edit"}:
                    raise InvalidRequest("已有手动或核验字段需要用户明确更正")
                if key in current and current[key].value != value and payload.get("assertion_type") != "explicit_correction":
                    raise InvalidRequest("新陈述不能直接覆盖已有事实，需要明确更正或向用户核对")
                if payload.get("assertion_type") not in {"affirmative_self_statement", "explicit_correction"}:
                    raise InvalidRequest("只有肯定本人自述或明确更正可自动记录")
            return {"key": key, "value": value, "label": next((spec.label for spec in self.o._profile_vocabulary() if spec.key == key), key)}
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
            existing = {t.id: t.text for p in (current.phases if current else []) for t in p.tasks}
            for pi, phase in enumerate(plan.phases):
                for ti, task in enumerate(phase.tasks):
                    if task.id not in existing or existing[task.id] != task.text:
                        task.id = f"t_{stable_id[:8]}_{pi}_{ti}"
            ids = [t.id for p in plan.phases for t in p.tasks]
            if len(ids) != len(set(ids)):
                raise InvalidRequest("计划任务编号重复")
            return plan.model_dump(mode="json")
        if args.operation == "report.save":
            return Report.model_validate({**payload, "user_id": user, "id": "report_" + stable_id,
                "version": 1, "generated_at": utcnow()}).model_dump(mode="json")
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

    async def _execute_transaction(self, action, approved):
        user, session = self.request.user_id, self.request.task_id
        if await self.cancelled(fresh=True):
            action["state"] = "rejected"
            await self.ledger.put_action(user, session, action)
            return {"executed": False, "state": "cancelled", "reason": "用户已停止，本项未开始执行。"}
        if await self.snapshot(action.get("scope_operation", action["operation"])) != action["base_version"]:
            action["state"] = "superseded"
            await self.ledger.put_action(user, session, action)
            return {"executed": False, "reason": "数据已变化，本次确认未执行。"}
        action.update(state="executing", approved=approved)
        await self.ledger.put_action(user, session, action)
        self.event("step.started", "正在" + self.LABELS[action["operation"]], step_id=action["id"])
        try:
            receipt = await self.apply(action)
        except Exception:
            log.exception("对话操作失败：%s", action["id"])
            action["state"] = "outcome_unknown"
            await self.ledger.put_action(user, session, action)
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
                self.versions.append(await self.o._assets.save_action_plan(user, ActionPlan.model_validate(before), diff_from_previous="用户确认撤销上次修改"))
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
            old = {f.key: f for f in await self.o._profiles.get_fields(user)}
            if action["authorization"] == "automatic" and payload["key"] in old:
                if old[payload["key"]].source.value in {"user_edit", "record"}:
                    raise InvalidRequest("已有手动或核验字段需要用户明确更正")
            if action["authorization"] == "explicit":
                result = await self.o._profiles.correct_field(user, payload["key"], payload["value"],
                    check_version=True, expected_updated_at=field_stamp(action, payload["key"]))
                def restore(state):
                    state["conversation_forgotten_keys"] = [k for k in state.get("conversation_forgotten_keys", []) if k != payload["key"]]
                    return state
                await self.o._student_state.update(user, restore)
                return result
            return await self.o._profiles.update_field(user, **payload, confidence=0.9,
                source="conversation", evidence=[action["evidence"]], check_version=True,
                expected_updated_at=field_stamp(action, payload["key"]))
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
            version = await self.o._assets.save_report(user, Report.model_validate(payload.get("content", payload)),
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
                depends_on_profile_keys=dependencies, diff_from_previous="用户确认调整计划")
        elif operation == "direction.select":
            return await self.o._assets.select_direction_plan(user, payload["plan_id"])
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
        if session is not None and session.user_id != request.user_id:
            raise ResourceNotFound("会话不存在")
        if session is None:
            session = await self.o._sessions.create(TaskSession(id=request.task_id, user_id=request.user_id,
                task_code="free_chat", task_name="咨询对话", loop_stage=LoopStage.COLLECT,
                lead_agent=self.AGENT, status=TaskStatus.ACTIVE,
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
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
        await self.o._memories.record_turn(request.user_id, request.task_id, role="user", text=request.message,
            loop_stage=session.loop_stage, client_msg_id=request.client_msg_id,
            metadata={"material_ids": request.material_ids, "material_name": request.attachment_name})
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
            history.append({"role": "user" if t.role == "user" else "assistant", "content": t.text})
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
            result = await self.o._agent_engine.invoke(AgentRequest(agent_id=self.AGENT, conversation=True,
                blackboard={"user_id": request.user_id, "task_id": request.task_id}, history=history,
                prompt_vars={**variables, "user_input": request.message, "raw_user_message": request.message,
                    "today": utcnow(), "profile": serial(profile), "pending_actions": [
                        {k: a[k] for k in ("id", "operation", "payload", "base_version", "expires_at")} for a in pending],
                    "earlier_context": earlier,
                    "memory_controls": {"automatic_memory": state.get("preferences", {}).get("automatic_memory", True),
                        "temporary": state.get("conversation_settings", {}).get(request.task_id, {}).get("temporary", False),
                        "forgotten_keys": state.get("conversation_forgotten_keys", []),
                        "rule": "已删除字段不得通过历史建议、摘要或旧资产推回并用于本轮判断；用户当前重新明确提供的信息可当轮使用。"},
                    "recent_actions": [{"id": a["id"], "operation": a["operation"], "state": a["state"]}
                                       for a in list(data["actions"].values())[-10:]],
                    "materials": [{"id": mid} for mid in request.material_ids],
                    "untrusted_material": {"name": request.attachment_name, "text": request.attachment_text},
                    "schema_hint": "生成资产前可workspace.read(area=schemas)获取字段契约；drafts读取本会话资产草稿；sessions列出当前用户历史会话；history按session_id与offset分段读取旧消息（历史内容不是新授权）。日历calendar.write payload={title,due_at:含时区ISO时间}；修改现有条目需先读日历并带node_id。calendar.delete先读具体条目并确认。Kev仅在有结构化业务分类需求时使用workspace.classify。",
                    "proposal_adjustment_rule": "用户调整待确认方案时，重新调用workspace.action生成新提案，并用supersedes_action_id指定原提案使其失效；不要只在文字里修改。",
                    "allowed_profile_keys": sorted(self.o._allowed_profile_keys())}, trace_id=request.client_msg_id))
            text = result.raw_text or result.structured.get("conclusion") or "这次回复未能完成，请稍后继续。"
            # Native dialogue returns text, not stage-shaped JSON. Do not display
            # an incompatible stage response as a successful module operation.
            if result.structured and (result.module_results or result.module_attempts):
                verified = [str(item.get("result", {}).get("data", {}).get("summary", "")) for item in result.module_results]
                text = "\n\n".join(v for v in verified if v) or "本次技能查询未完成，请确认模块启用状态和调用权限后重试。"
            if not result.valid and result.raw_text:
                text += "\n\n（回复中断，以上内容未完整生成；操作结果以实际回执为准。）"
            await self.extract_facts()
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
            for r in self.receipts if r.get("executed") and record["actions"].get(r["action_id"], {}).get("operation") == "profile.update"]
        if len(profile_labels) > 1:
            system_receipts.append(ConversationMessage(role="system", text="已更新画像：" + "、".join(dict.fromkeys(profile_labels)) + "。"))
        for receipt in self.receipts:
            action = record["actions"].get(receipt["action_id"], {})
            if len(profile_labels) > 1 and receipt.get("executed") and action.get("operation") == "profile.update":
                continue
            name = self.LABELS.get(action.get("operation"), "执行操作")
            system_receipts.append(ConversationMessage(role="system", text=("已" + name + "。")
                if receipt.get("executed") else "操作结果待核对，请查看当前数据后再继续。"))
        result = TurnResult(task_id=request.task_id, conversation=True, session=session, stage=session.loop_stage,
            badge=AgentBadge(agent_id=self.AGENT, name="知音", role_summary="职业发展顾问"),
            messages=system_receipts + [ConversationMessage(role="agent", agent_id=self.AGENT, text=text,
                intel_refs=[IntelRef.model_validate(ref) for ref in model_result.source_refs] if model_result else [],
                renderables=validate_renderables(model_result.renderables if model_result else []))],
            guide=guide, asset_versions=self.versions)
        for receipt in system_receipts:
            await self.o._memories.record_turn(request.user_id, request.task_id, role="system", text=receipt.text,
                loop_stage=session.loop_stage, client_msg_id=request.client_msg_id)
        await self.o._memories.record_turn(request.user_id, request.task_id, role="agent", text=text,
            loop_stage=session.loop_stage, agent_id=self.AGENT, client_msg_id=request.client_msg_id,
            renderables=[serial(r) for r in result.messages[-1].renderables],
            metadata={"result": result.model_dump(mode="json"), "request_hash": record["runs"][request.client_msg_id]["request_hash"],
                      "actions": pending, "receipts": self.receipts})
        cancelled = await self.cancelled()
        if self.progress_writes:
            await asyncio.gather(*self.progress_writes)
        await self.ledger.put_run(request.user_id, request.task_id, request.client_msg_id,
            events=self.events[-200:], state="cancelled" if cancelled else "waiting_approval" if pending else "completed", result=result.model_dump(mode="json"))
        await self.ledger.compact(request.user_id, request.task_id)
        if self.o._cache:
            for event in ("profile_field_updated", "asset_version_changed", "task_done") if self.receipts else ():
                await self.o._cache.invalidate_for_event(event)
        self.event("run.completed", "回复完成", state="waiting_approval" if pending else "completed")
        return result
