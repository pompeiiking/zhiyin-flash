"""Durable conversation run/action journal, using the existing atomic state repository.

State is per account, mutations are atomic, and callers also hold the distributed
conversation lock. Never re-execute an interrupted action with an unknown outcome.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from zhiyin_kernel.errors import InvalidRequest


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class ConversationLedger:
    KEY = "conversation_runtime_v2"

    def __init__(self, repository):
        if repository is None:
            raise InvalidRequest("对话运行记录未装配，禁止执行操作")
        self.repository = repository

    async def read(self, user_id, session_id):
        data = await self.repository.get(user_id)
        record = deepcopy(data.get(self.KEY, {}).get(session_id, {"runs": {}, "actions": {}, "facts": {}}))
        # JSONB object key order is not chronological. Never infer the latest
        # run/proposal from the order returned by a database JSON object.
        for table in ("runs", "actions"):
            record[table] = dict(sorted(record.get(table, {}).items(), key=lambda item: item[1].get("created_at", "")))
        return record

    async def compact(self, user_id, session_id):
        """Keep hot traces bounded; full responses remain in stored turn metadata."""
        def compact(record):
            pending_runs = {a["run_id"] for a in record["actions"].values() if a["state"] == "proposed"}
            for key, run in record["runs"].items():
                if run.get("state") == "waiting_approval" and key not in pending_runs and run.get("result"):
                    run["state"] = "completed"
            terminal = sorted((r for r in record["runs"].values() if r.get("result") and r.get("state") != "waiting_approval"),
                              key=lambda r: r.get("created_at", ""))
            for run in terminal[:-32]:
                run.pop("result", None)
                run.pop("events", None)
                run["archived"] = True
        await self.change(user_id, session_id, compact)

    async def change(self, user_id, session_id, fn):
        def change(state):
            root = state.setdefault(self.KEY, {})
            record = root.setdefault(session_id, {"runs": {}, "actions": {}, "facts": {}})
            fn(record)
            return state
        state = await self.repository.update(user_id, change)
        return deepcopy(state[self.KEY][session_id])

    async def put_run(self, user_id, session_id, run_id, **fields):
        def update(record):
            run = record["runs"].setdefault(run_id, {"created_at": utcnow()})
            run.update(deepcopy(fields), updated_at=utcnow())
        return await self.change(user_id, session_id, update)

    async def put_action(self, user_id, session_id, action):
        def update(record):
            record["actions"][action["id"]] = deepcopy(action)
        return await self.change(user_id, session_id, update)

    async def remove_session(self, user_id, session_id):
        def change(state):
            state.get(self.KEY, {}).pop(session_id, None)
            return state
        await self.repository.update(user_id, change)
