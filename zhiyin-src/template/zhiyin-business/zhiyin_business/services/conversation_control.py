"""Account-bound lifecycle operations outside the model's long-running lock."""
from datetime import datetime, timezone

from zhiyin_business.services.conversation_ledger import ConversationLedger
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound


class ConversationControl:
    def __init__(self, owner):
        self.owner = owner
        self.ledger = ConversationLedger(owner._student_state)

    async def require_session(self, user_id, task_id):
        session = await self.owner._sessions.get(task_id)
        if session is None or session.user_id != user_id:
            raise ResourceNotFound("会话不存在")
        return session

    async def delete(self, user_id, task_id):
        await self.require_session(user_id, task_id)
        await self.ledger.change(user_id, task_id, lambda record: record.update(delete_requested=True))
        async with self.owner._serialized(user_id):
            await self.owner._memories.delete_session(user_id, task_id)
            await self.owner._sessions.delete(task_id)
            await self.ledger.remove_session(user_id, task_id)
            def deleted(state):
                state.get("conversation_settings", {}).pop(task_id, None)
                ids = state.setdefault("deleted_conversations", [])
                if task_id not in ids:
                    ids.append(task_id)
                return state
            await self.owner._student_state.update(user_id, deleted)

    async def read(self, user_id, task_id, *, run_id="", cancel=False, settings=None):
        await self.require_session(user_id, task_id)
        if settings is not None:
            if set(settings) - {"temporary"} or not isinstance(settings.get("temporary"), bool):
                raise InvalidRequest("会话设置无效")
            def update(state):
                state.setdefault("conversation_settings", {}).setdefault(task_id, {}).update(settings)
                return state
            await self.owner._student_state.update(user_id, update)
        record = await self.ledger.read(user_id, task_id)
        for key, run in record["runs"].items():
            updated_at = datetime.fromisoformat(run["updated_at"])
            if run.get("state") == "running" and (datetime.now(timezone.utc) - updated_at).total_seconds() > 180:
                run.update(state="failed", last_status="上次运行已中断；请先核对操作记录，再继续咨询。")
                await self.ledger.put_run(user_id, task_id, key, **run)
        if run_id:
            run = record["runs"].get(run_id)
            if run is None:
                raise ResourceNotFound("本轮运行不存在")
            if cancel and run.get("state") not in {"completed", "failed", "cancelled"}:
                await self.ledger.put_run(user_id, task_id, run_id, cancel_requested=True)
                run["cancel_requested"] = True
            return run
        state = await self.owner._student_state.get(user_id)
        return {"runs": [{"id": k, "state": v.get("state"), "events": v.get("events", []),
                    "last_status": v.get("last_status", ""), "cancel_requested": v.get("cancel_requested", False)}
                for k, v in record["runs"].items()],
                "actions": list(record["actions"].values()),
                "settings": state.get("conversation_settings", {}).get(task_id, {"temporary": False})}
