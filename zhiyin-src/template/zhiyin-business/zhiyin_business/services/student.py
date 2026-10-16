"""学生交互能力：真实计划修改、复盘、设置、量化记录及历史。"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

from zhiyin_business.contracts.common import AssetUpdateDraft
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
from zhiyin_kernel.enums import AssetType
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_business.contracts.student import (
    TaskValues,
    PhaseValues,
    Preferences,
    DirectionWeights,
    MeasurementBatch,
    Semester,
)


def now():
    return datetime.now(timezone.utc)


def phase_id(plan, phase):
    return phase.id or uuid5(NAMESPACE_URL, f"{plan.id}:{phase.name}").hex


def normalize(plan):
    for phase in plan.phases:
        phase.id = phase_id(plan, phase)
        for task in phase.tasks:
            task.id = task.id or f"{phase.name}:{task.text}"
    return plan


class StudentService:
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        state,
        assets,
        asset_service,
        notifications,
        academic,
        sessions,
        object_store=None,
        document_renderer=None,
        behaviors=None,
        read_cache=None,
        ai_tasks=None,
    ):
        self.state = state
        self.assets = assets
        self.asset_service = asset_service
        self.notifications = notifications
        self.academic = academic
        self.sessions = sessions
        self.object_store = object_store
        self.document_renderer = document_renderer
        self.behaviors = behaviors
        self.read_cache = read_cache
        self.ai_tasks = ai_tasks

    async def preferences(self, user_id):
        return Preferences.model_validate((await self.state.get(user_id)).get("preferences", {}))

    async def save_preferences(self, user_id, body):
        previous = await self.preferences(user_id)
        await self.state.update(
            user_id, lambda s: {**s, "preferences": body.model_dump(mode="json")}
        )
        if self.ai_tasks is not None and (
            previous.academic_analysis != body.academic_analysis
            or previous.material_analysis != body.material_analysis
        ):
            await self.ai_tasks.invalidate(user_id)
        return body

    async def can_notify(self, user_id):
        prefs = await self.preferences(user_id)
        if not prefs.proactive_reminders:
            return False
        clock = now().astimezone(ZoneInfo(prefs.timezone)).strftime("%H:%M")
        start, end = prefs.quiet_start, prefs.quiet_end
        if start and end:
            quiet = start <= clock < end if start < end else clock >= start or clock < end
            if quiet:
                return False
        return True

    async def edit_task(self, user_id, body, task_id=None):
        changed = False
        completed_id = None
        identity = task_id or (f"task_{uuid5(NAMESPACE_URL, user_id + chr(58) + body.client_request_id).hex}" if body.client_request_id else f"task_{uuid4().hex}")

        def change(plan):
            nonlocal changed, completed_id
            if plan is None:
                raise ResourceNotFound("请先创建一个阶段")
            normalize(plan)
            phase = next((p for p in plan.phases if p.id == body.phase_id), None)
            if phase is None:
                raise ResourceNotFound("所属阶段不存在")
            tasks = {t.id: t for p in plan.phases for t in p.tasks}
            old = tasks.get(identity)
            if task_id and old is None:
                raise ResourceNotFound("行动任务不存在")
            if old:
                old_phase = next(p.id for p in plan.phases if any(t.id == identity for t in p.tasks))
                current = TaskValues(**{key: (old_phase if key == "phase_id" else getattr(old, key)) for key in TaskValues.model_fields})
                desired = TaskValues.model_validate(body.model_dump(exclude={"expected_task", "client_request_id"}))
                if current == desired:
                    return plan
                if not task_id:
                    raise InvalidRequest("首次创建已保存，请重新读取任务后编辑；本次重试不会重复创建或覆盖已保存的内容。")
                if body.expected_task is not None and current != body.expected_task:
                    raise InvalidRequest("这项任务已在其他页面更新。你的输入仍保留，请重新读取最新任务后核对修改，避免覆盖他人的更新。")
            if body.parent_task_id:
                parent = tasks.get(body.parent_task_id)
                if parent is None:
                    raise ResourceNotFound("被拆分任务不存在")
                seen = {task_id}
                while parent:
                    if parent.id in seen:
                        raise InvalidRequest("拆分关联不能形成循环")
                    seen.add(parent.id)
                    parent = tasks.get(parent.parent_task_id)
            values = body.model_dump(exclude={"phase_id", "expected_task", "client_request_id"})
            values.update(
                id=identity,
                done=body.status == "completed",
                done_at=(old.done_at if old and old.done else now())
                if body.status == "completed"
                else None,
            )
            item = ActionTask.model_validate(values)
            if old == item and any(t.id == task_id for t in phase.tasks):
                return plan
            changed = True
            if item.done and not (old and old.done):
                completed_id = item.id
            if old:
                for p in plan.phases:
                    p.tasks = [t for t in p.tasks if t.id != task_id]
            phase.tasks.append(item)
            return plan

        plan = await self.assets.update_action_plan(user_id, change)
        if changed:
            await self._version(user_id, "手动新增或调整任务", plan)
            if completed_id:
                await self._completed(user_id, completed_id)
        return plan

    async def edit_phase(self, user_id, body, selected_id=None):
        changed = False
        identity = selected_id or (f"phase_{uuid5(NAMESPACE_URL, user_id + ':' + body.client_request_id).hex}" if body.client_request_id else f"phase_{uuid4().hex}")

        def change(plan):
            nonlocal changed
            plan = normalize(plan or ActionPlan(id=f"act_{uuid4().hex}"))
            phases = {p.id: p for p in plan.phases}
            if selected_id and selected_id not in phases:
                raise ResourceNotFound("阶段不存在")
            existing = phases.get(identity)
            desired = PhaseValues.model_validate(body.model_dump(exclude={"expected_phase", "client_request_id"}))
            if existing:
                current = PhaseValues(**{key: getattr(existing, key) for key in PhaseValues.model_fields})
                if current == desired:
                    return plan
                if not selected_id:
                    raise InvalidRequest("首次创建阶段已保存，请重新读取后编辑；重试不会重复创建或覆盖已有内容。")
                if body.expected_phase is not None and current != body.expected_phase:
                    raise InvalidRequest("这个阶段已在其他页面更新。你的输入仍保留，请重新读取最新阶段后核对修改。")
            if any(dep not in phases or dep == identity for dep in body.depends_on):
                raise InvalidRequest("依赖阶段不存在或指向自身")
            graph = {p.id: p.depends_on for p in plan.phases}
            graph[identity] = body.depends_on

            def visit(node, trail):
                if node in trail:
                    raise InvalidRequest("阶段依赖不能形成循环")
                for dep in graph.get(node, []):
                    visit(dep, trail | {node})

            visit(identity, set())
            existing = phases.get(identity)
            item = ActionPhase(
                id=identity,
                date_range=existing.date_range if existing else "",
                tasks=existing.tasks if existing else [],
                **desired.model_dump(),
            )
            plan.phases = (
                [item if p.id == identity else p for p in plan.phases]
                if existing
                else [*plan.phases, item]
            )
            changed = True
            return plan

        plan = await self.assets.update_action_plan(user_id, change)
        if changed:
            await self._version(user_id, "调整阶段与依赖关系", plan)
        return plan

    async def _version(self, user_id, description, plan):
        await self.asset_service.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.ACTION_PLAN,
                diff_from_previous=description,
                reason="用户主动编辑",
            ),
            snapshot_content=plan.model_dump(mode="json"),
        )
        await self.invalidate(user_id)

    async def _completed(self, user_id, task_id):
        if self.behaviors is not None:
            from zhiyin_business.contracts.common import BehaviorEventDraft
            from zhiyin_kernel.enums import BehaviorEventType

            await self.behaviors.log(
                user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.TASK_DONE, payload={"task_id": task_id}
                ),
            )

    async def invalidate(self, user_id):
        if self.read_cache is not None:
            await self.read_cache.invalidate_for_event("asset_state_changed")
        if self.ai_tasks is not None:
            await self.ai_tasks.invalidate_for_event(user_id, "asset_state_changed")

    async def list_notifications(self, user_id):
        return await self.notifications.list_all(user_id)

    async def change_notification(self, user_id, message_id, body):
        if body.status == "later" and body.snoozed_until <= now():
            raise InvalidRequest("稍后提醒时间必须晚于现在")
        if not await self.notifications.set_state(
            user_id, message_id, body.status, body.snoozed_until
        ):
            raise ResourceNotFound("提醒不存在")
        return next(n for n in await self.list_notifications(user_id) if n["id"] == message_id)

    async def reviews(self, user_id):
        entries = list((await self.state.get(user_id)).get("reviews", {}).values())
        entries.sort(key=lambda r: r["updated_at"], reverse=True)
        return {"items": entries, "reasons": dict(Counter(r["reason"] for r in entries))}

    async def save_review(self, user_id, body, review_id=None):
        plan = await self.assets.get_action_plan(user_id)
        task = (
            next((t for p in normalize(plan).phases for t in p.tasks if t.id == body.task_id), None)
            if plan
            else None
        )
        if task is None:
            raise ResourceNotFound("复盘关联的任务不存在")
        identity = review_id or (f"review_{uuid5(NAMESPACE_URL, user_id + ':' + body.client_request_id).hex}" if body.client_request_id else f"review_{uuid4().hex}")
        values = body.model_dump(mode="json", exclude={"expected_updated_at", "expected_task", "client_request_id"})
        current_phase = next(p.id for p in plan.phases if any(t.id == task.id for t in p.tasks))
        task_snapshot = body.expected_task or TaskValues(**{
            key: current_phase if key == "phase_id" else getattr(task, key)
            for key in TaskValues.model_fields
        })

        def change(s):
            records = s.setdefault("reviews", {})
            previous = records.get(identity)
            lease = s.get("review_leases", {}).get(identity)
            if lease and datetime.fromisoformat(lease["until"]) > now():
                raise InvalidRequest("这条复盘正在应用，请稍后修订")
            if review_id and previous is None:
                raise ResourceNotFound("复盘不存在")
            if previous:
                if all(previous.get(key) == value for key, value in values.items()) and (body.expected_task is None or previous.get("task_snapshot") == task_snapshot.model_dump(mode="json")):
                    return s
                if not review_id:
                    raise InvalidRequest("首次复盘已保存，请重新读取后修订；本次重试不会重复创建或覆盖内容。")
                if body.expected_updated_at is not None and datetime.fromisoformat(previous["updated_at"]) != body.expected_updated_at:
                    raise InvalidRequest("这条复盘已在其他页面更新。你的输入仍保留，请重新读取并核对后再修订。")
            item = {
                **values,
                "task_snapshot": task_snapshot.model_dump(mode="json"),
                "id": identity,
                "task_text": task.text,
                "updated_at": now().isoformat(),
                "applied_at": None,
                "history": [
                    *previous.get("history", []),
                    {k: v for k, v in previous.items() if k != "history"},
                ]
                if previous
                else [],
            }
            records[identity] = item
            return s

        return (await self.state.update(user_id, change))["reviews"][identity]

    async def apply_review(self, user_id, review_id):
        from zhiyin_business.contracts.student import TaskEdit

        token = uuid4().hex

        def claim(s):
            review = s.get("reviews", {}).get(review_id)
            if review is None:
                raise ResourceNotFound("复盘不存在")
            if review.get("applied_at"):
                return s
            lease = s.setdefault("review_leases", {}).get(review_id)
            if lease and datetime.fromisoformat(lease["until"]) > now():
                raise InvalidRequest("这条复盘正在应用，请稍后刷新")
            s["review_leases"][review_id] = {
                "token": token,
                "until": (now() + timedelta(minutes=2)).isoformat(),
            }
            return s

        review = (await self.state.update(user_id, claim))["reviews"][review_id]
        if review.get("applied_at"):
            return review
        try:
            snapshot = review.get("task_snapshot")
            if not snapshot:
                raise InvalidRequest("这条历史复盘缺少任务原值，请重新读取任务并修订复盘后再应用。")
            if review["result"] == "complete":
                await self.edit_task(user_id, TaskEdit.model_validate({
                    **snapshot, "status": "completed", "progress": 100,
                    "expected_task": snapshot,
                }), review["task_id"])
            elif review["result"] == "adjust" and review.get("adjustment"):
                await self.edit_task(
                    user_id, TaskEdit.model_validate({**review["adjustment"], "expected_task": snapshot}), review["task_id"]
                )
            else:
                raise InvalidRequest("此复盘没有可应用的任务调整")
            await self.invalidate(user_id)
            if self.behaviors is not None:
                from zhiyin_business.contracts.common import BehaviorEventDraft
                from zhiyin_kernel.enums import BehaviorEventType

                await self.behaviors.log(
                    user_id,
                    BehaviorEventDraft(
                        event_type=BehaviorEventType.REVIEW,
                        payload={"review_id": review_id, "task_id": review["task_id"]},
                    ),
                )

            def finish(s):
                s["reviews"][review_id]["applied_at"] = now().isoformat()
                return s

            return (await self.state.update(user_id, finish))["reviews"][review_id]
        finally:

            def release(s):
                leases = s.get("review_leases", {})
                if leases.get(review_id, {}).get("token") == token:
                    leases.pop(review_id, None)
                return s

            await self.state.update(user_id, release)

    async def snapshot(self, user_id, asset_type, version):
        snapshot = (
            (await self.state.get(user_id))
            .get("asset_snapshots", {})
            .get(f"{asset_type}:{version}")
        )
        if snapshot is None:
            raise ResourceNotFound("该历史版本未保存正文快照，不能使用最新正文替代")
        return snapshot

    async def session_snapshot(self, user_id, task_id):
        session = await self.sessions.get(task_id)
        if session is None or session.user_id != user_id:
            raise ResourceNotFound("会话不存在")
        return (await self.state.get(user_id)).get("session_snapshots", {}).get(task_id)

    async def store_session_snapshot(self, user_id, task_id, view, client_msg_id=None):
        def change(s):
            seen = s.setdefault("snapshot_messages", {}).setdefault(task_id, [])
            if client_msg_id and client_msg_id in seen:
                return s
            if client_msg_id:
                seen.append(client_msg_id)
                s.setdefault('conversation_reply_snapshots', {}).setdefault(task_id, {})[client_msg_id] = view
            s.setdefault("session_snapshots", {})[task_id] = view
            return s

        await self.state.update(user_id, change)

    async def conversation_reply_snapshots(self, user_id, task_id):
        session = await self.sessions.get(task_id)
        if session is None or session.user_id != user_id:
            raise ResourceNotFound('会话不存在')
        state = await self.state.get(user_id)
        snapshots = dict(state.get('conversation_reply_snapshots', {}).get(task_id, {}))
        # Older installations retained only the latest complete response.
        seen = state.get('snapshot_messages', {}).get(task_id, [])
        latest = state.get('session_snapshots', {}).get(task_id)
        if latest and seen:
            snapshots.setdefault(seen[-1], latest)
        return snapshots

    async def save_measurements(self, user_id, body: MeasurementBatch):
        if body.asset_type == "report":
            report = await self.assets.get_report(user_id, body.version)
            if report is None or report.version != body.version or report.id != body.subject_id:
                raise ResourceNotFound("报告版本不存在")
            allowed = {str(item.index) for group in report.dimensions for item in group.items}
        else:
            latest = await self.assets.get_latest_version(user_id, AssetType.DIRECTION_PLAN)
            if latest and latest.version == body.version:
                plans = await self.assets.list_direction_plans(user_id)
                ids = {p.id for p in plans}
            else:
                snapshot = await self.snapshot(user_id, "direction_plan", body.version)
                ids = {p["id"] for p in snapshot["content"]}
            if body.subject_id not in ids:
                raise ResourceNotFound("方向版本不存在")
            allowed = {
                "major",
                "jobs",
                "salary",
                "stability",
                "location",
                "opportunity",
                "feasibility",
            }
        if any(m.key not in allowed for m in body.measurements):
            raise InvalidRequest("量化维度不属于此资产")
        # Student submissions are always self-reported, even when citing external assessments.
        for m in body.measurements:
            m.origin = "self_report"
        key = f"{body.asset_type}:{body.version}:{body.subject_id}"

        def change(s):
            old = s.setdefault("measurements", {}).get(key)
            if old:
                s.setdefault("measurement_history", []).append(old)
            s["measurements"][key] = {
                **body.model_dump(mode="json"),
                "recorded_at": now().isoformat(),
            }
            return s

        return (await self.state.update(user_id, change))["measurements"][key]

    async def measurements(self, user_id):
        data = await self.state.get(user_id)
        return {
            "items": list(data.get("measurements", {}).values()),
            "history": data.get("measurement_history", []),
        }

    async def weights(self, user_id, body=None):
        if body is not None:
            await self.state.update(
                user_id, lambda s: {**s, "direction_weights": body.model_dump()}
            )
        return DirectionWeights.model_validate(
            (await self.state.get(user_id)).get("direction_weights", {})
        )

    async def compare(self, user_id):
        weights = (await self.weights(user_id)).model_dump()
        plans = await self.assets.list_direction_plans(user_id)
        version = await self.assets.get_latest_version(user_id, AssetType.DIRECTION_PLAN)
        records = (await self.state.get(user_id)).get("measurements", {})
        result = []
        for p in plans:
            batch = records.get(f"direction_plan:{version.version}:{p.id}", {}) if version else {}
            values = {m["key"]: m for m in batch.get("measurements", [])}
            missing = [k for k, w in weights.items() if w > 0 and k not in values]
            normalized = {
                k: (m["value"] - m["minimum"]) / (m["maximum"] - m["minimum"])
                for k, m in values.items()
            }
            score = (
                None
                if missing
                else sum(normalized.get(k, 0) * w for k, w in weights.items())
                / sum(weights.values())
            )
            result.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "score": score,
                    "missing": missing,
                    "measurements": list(values.values()),
                    "opportunity": normalized.get("opportunity"),
                    "feasibility": normalized.get("feasibility"),
                }
            )
        result.sort(key=lambda p: (p["score"] is None, -(p["score"] or 0)))
        return {
            "version": version.version if version else None,
            "weights": weights,
            "plans": result,
            "method": "各维度按其量表归一化后加权平均；来源和量表不同的记录不能视作客观排名",
        }

    async def semester(self, user_id, body=None):
        if body is not None:
            await self.state.update(
                user_id, lambda s: {**s, "semester": body.model_dump(mode="json")}
            )
        return (await self.state.get(user_id)).get("semester")

    async def require_analysis_consent(self, user_id):
        # Source permissions are enforced at analysis reads, not by disabling AI.
        return await self.preferences(user_id)

    async def require_material_analysis(self, user_id):
        if not (await self.preferences(user_id)).material_analysis:
            error = InvalidRequest("上传材料参与分析已关闭，请移除附件后发送，或在资料偏好中开启。")
            error.user_facing = True
            raise error

    async def export(self, user_id, asset_type, fmt):
        import asyncio

        lines = []
        if asset_type == "report":
            report = await self.assets.get_report(user_id)
            if report is None:
                raise ResourceNotFound("还没有可导出的报告")
            title = f"诊断报告 · 第 {report.version} 版"
            lines.extend([report.verdict.title, report.verdict.summary])
            for group in report.dimensions:
                lines.append(group.group_method)
                for item in group.items:
                    lines.extend(
                        [
                            f"{item.index}. {item.name} · {item.tag}",
                            item.conclusion,
                            f"依据：{item.evidence}",
                        ]
                    )
            for key, label in (
                ("strength", "优势"),
                ("weakness", "短板"),
                ("opportunity", "机会"),
                ("risk", "风险"),
            ):
                lines.extend([label, *getattr(report.swot, key)])
            lines.extend(["来源", *report.sources, "方法", *report.methodologies])
        elif asset_type == "direction_plan":
            plans = await self.assets.list_direction_plans(user_id)
            if not plans:
                raise ResourceNotFound("还没有可导出的方向方案")
            title = "方向方案"
            for p in plans:
                lines.extend(
                    [
                        p.name + ("（已选择）" if p.selected else ""),
                        p.target_desc,
                        p.fit_reason,
                        f"主要风险：{p.main_risk}",
                    ]
                )
                for gap in p.gaps:
                    lines.extend(
                        [
                            f"要求：{gap.requirement}",
                            f"当前：{gap.current_state}",
                            f"建议：{gap.suggestion}",
                        ]
                    )
        elif asset_type == "action_plan":
            plan = await self.assets.get_action_plan(user_id)
            if plan is None:
                raise ResourceNotFound("还没有可导出的行动计划")
            title = "行动计划"
            phase_names = {phase_id(plan, p): p.name for p in plan.phases}
            for phase in plan.phases:
                lines.append(f"{phase.name} {phase.date_range}")
                if phase.starts_at or phase.ends_at:
                    lines.append(
                        f"阶段时间：{phase.starts_at or '未设置'} — {phase.ends_at or '未设置'}"
                    )
                if phase.depends_on:
                    lines.append(
                        "前置阶段："
                        + "、".join(phase_names.get(dep, "已移除阶段") for dep in phase.depends_on)
                    )
                lines.extend("阻塞条件：" + item for item in phase.blocking_conditions)
                lines.extend("交接要求：" + item for item in phase.handoff_requirements)
                for t in phase.tasks:
                    state = (
                        "已完成"
                        if t.done
                        else {
                            "pending": "待执行",
                            "in_progress": "进行中",
                            "waiting": "等待中",
                        }.get(t.status, "待执行")
                    )
                    lines.append(f"{state} · {t.text}（{100 if t.done else t.progress}%）")
                    if t.waiting_reason:
                        lines.append("等待原因：" + t.waiting_reason)
                    if t.due_date:
                        lines.append(f"截止：{t.due_date.isoformat()}")
                    if t.scheduled_at:
                        lines.append(
                            f"排期：{t.scheduled_at.isoformat()}，预计 {t.estimated_minutes or '未填写'} 分钟"
                        )
        else:
            raise InvalidRequest("不支持导出此类资产")
        content = await asyncio.to_thread(self.document_renderer, title, lines, fmt)
        export_id = uuid4().hex
        mime = (
            "application/pdf"
            if fmt == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        key = self.object_store.build_named_key(user_id, "exports", export_id, fmt)
        await self.object_store.put(key, content, content_type=mime)

        def change(s):
            s.setdefault("exports", {})[export_id] = {
                "key": key,
                "format": fmt,
                "mime": mime,
                "filename": f"{title}.{fmt}",
                "created_at": now().isoformat(),
            }
            return s

        await self.state.update(user_id, change)
        return {"available": True, "message": "文件已生成，可下载。", "object_key": export_id}

    async def download(self, user_id, export_id):
        record = (await self.state.get(user_id)).get("exports", {}).get(export_id)
        if record is None:
            raise ResourceNotFound("导出文件不存在")
        return await self.object_store.get(record["key"]), record

    async def workload(self, user_id, start):
        raw = await self.semester(user_id)
        if not raw:
            return {
                "configured": False,
                "weeks": [],
                "conflicts": [],
                "missing": ["请先设置学期首周和节次钟点"],
            }
        semester = Semester.model_validate(raw)
        zone = ZoneInfo(semester.timezone)
        academic = await self.academic.get(user_id)
        plan = await self.assets.get_action_plan(user_id)
        tasks = [t for p in plan.phases for t in p.tasks] if plan else []
        periods = {p.number: p for p in semester.periods}
        intervals, missing = [], []
        for task in tasks:
            if task.done:
                continue
            if task.scheduled_at and task.estimated_minutes:
                begin = task.scheduled_at.astimezone(zone)
                intervals.append(
                    (
                        begin,
                        begin + timedelta(minutes=task.estimated_minutes),
                        "task",
                        task.id,
                        task.text,
                    )
                )
            else:
                missing.append(f"任务「{task.text}」缺少排期或预计用时")
        # Course fields are explicit imported weekdays, periods and teaching weeks.
        for course in academic.courses if academic else []:
            if (
                not course.weekday
                or not course.start_period
                or not course.end_period
                or not course.weeks
            ):
                missing.append(f"课程「{course.name}」缺少星期、节次或教学周")
                continue
            import re

            raw_weeks = course.weeks.replace("周", "").replace("，", ",")
            weeks = set()
            if not re.fullmatch(r"[0-9,\s\-单双()（）]+", raw_weeks):
                missing.append(f"课程「{course.name}」教学周无法识别")
                continue
            for lo, hi in re.findall(r"(\d+)(?:\s*-\s*(\d+))?", raw_weeks):
                if not 1 <= int(lo) <= int(hi or lo) <= 53:
                    missing.append(f"课程「{course.name}」教学周超出范围")
                    continue
                weeks.update(range(int(lo), int(hi or lo) + 1))
            if "单" in raw_weeks:
                weeks = {w for w in weeks if w % 2}
            if "双" in raw_weeks:
                weeks = {w for w in weeks if not w % 2}
            for week in sorted(weeks):
                day = semester.first_monday + timedelta(weeks=week - 1, days=course.weekday - 1)
                if week > semester.weeks:
                    continue
                for num in range(course.start_period, course.end_period + 1):
                    slot = periods.get(num)
                    if not slot:
                        missing.append(f"课程「{course.name}」缺少第 {num} 节钟点")
                        continue
                    begin = datetime.fromisoformat(f"{day}T{slot.start}").replace(tzinfo=zone)
                    end = datetime.fromisoformat(f"{day}T{slot.end}").replace(tzinfo=zone)
                    intervals.append(
                        (begin, end, "course", f"{course.name}:{week}:{num}", course.name)
                    )
        origin = datetime.combine(start, datetime.min.time(), tzinfo=zone)
        stop = origin + timedelta(days=21)
        intervals = [i for i in intervals if i[0] < stop and i[1] > origin]
        conflicts = []
        for i, a in enumerate(intervals):
            for b in intervals[i + 1 :]:
                if max(a[0], b[0]) < min(a[1], b[1]):
                    conflicts.append(
                        {"first": a[4], "second": b[4], "at": max(a[0], b[0]).isoformat()}
                    )
        weeks = []
        for index in range(3):
            begin = origin + timedelta(weeks=index)
            end = begin + timedelta(weeks=1)
            counts = {
                kind: sum(
                    max(0, (min(i[1], end) - max(i[0], begin)).total_seconds() / 60)
                    for i in intervals
                    if i[2] == kind
                )
                for kind in ("course", "task")
            }
            weeks.append(
                {
                    "start": begin.date().isoformat(),
                    "course_minutes": counts["course"],
                    "task_minutes": counts["task"],
                    "remaining_minutes": None
                    if semester.weekly_available_minutes is None
                    else semester.weekly_available_minutes - counts["task"],
                }
            )
        return {
            "configured": True,
            "weeks": weeks,
            "conflicts": conflicts,
            "missing": list(dict.fromkeys(missing)),
            "capacity_method": "剩余时间＝本人填写的每周课外可用时间－已排期任务用时；课程用时单列",
        }
