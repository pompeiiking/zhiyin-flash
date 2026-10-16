"""Per-analysis source permissions and persisted provenance of derived values.

The scope is task-local, never a user preference cached on a singleton service.
Normal UI reads and writes remain untouched. Legacy derived values without
provenance are omitted from restricted analysis, not deleted from storage.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from hashlib import sha256
import json

from zhiyin_business.contracts.student import Preferences
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.errors import InvalidRequest


ALL_SOURCES = frozenset({"academic", "material"})
_current: ContextVar[AnalysisScope | None] = ContextVar("analysis_scope", default=None)


def fingerprint(kind, value):
    def serialize(item):
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        raise TypeError(type(item).__name__)

    payload = json.dumps(value, default=serialize, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return f"{kind}:{sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass
class AnalysisScope:
    user_id: str
    sources: frozenset[str]
    state: object
    lineage: dict = field(default_factory=dict)

    @property
    def restricted(self):
        return self.sources != ALL_SOURCES

    def allows(self, kind, value):
        if not self.restricted:
            return True
        required = self.lineage.get(fingerprint(kind, value))
        return required is not None and set(required) <= self.sources

    async def record(self, kind, value, *, sources=None):
        if value is None or self.state is None:
            return
        key = fingerprint(kind, value)
        required = sorted(self.sources if sources is None else sources)

        def change(data):
            data.setdefault("analysis_lineage", {})[key] = required
            return data

        await self.state.update(self.user_id, change)
        self.lineage[key] = required

    def profile(self, profile):
        if profile is None or not self.restricted:
            return profile
        return profile.model_copy(update={
            "fields": [f for f in profile.fields if self.field_allowed(f)],
            "gaps": [g for g in profile.gaps if self.allows("gap", g)],
        })

    def field_allowed(self, item):
        # Recorded derivation takes precedence over a model-provided source label.
        key = fingerprint("profile", item)
        if key in self.lineage:
            return self.allows("profile", item)
        return (item.source == ProfileSource.USER_EDIT
                or (item.source == ProfileSource.RECORD and "academic" in self.sources))


def current_scope(user_id=None):
    scope = _current.get()
    if scope is not None and user_id is not None and scope.user_id != user_id:
        raise InvalidRequest("分析上下文不能访问其他账号的数据")
    return scope


@contextmanager
def activate(scope):
    token = _current.set(scope)
    try:
        yield scope
    finally:
        _current.reset(token)


async def load_scope(state, user_id):
    data = await state.get(user_id) if state is not None else {}
    preferences = Preferences.model_validate(data.get("preferences", {}))
    sources = frozenset(name for name, enabled in (
        ("academic", preferences.academic_analysis),
        ("material", preferences.material_analysis),
    ) if enabled)
    return AnalysisScope(user_id, sources, state, dict(data.get("analysis_lineage", {})))


class AnalysisReadGuard:
    """Wrap a business service; filter only reads made within analysis execution.

    Writes go to the original service. Only exact returned values are marked;
    an accumulated legacy summary cannot acquire clean provenance by appending
    a new permitted turn. Asset content is marked at its atomic write boundary.
    """

    def __init__(self, service, kind):
        self._service = service
        self._kind = kind

    def __getattr__(self, name):
        target = getattr(self._service, name)
        if not callable(target) or name in {"drop_intel_cache"}:
            return target

        async def call(user_id, *args, **kwargs):
            scope = current_scope(user_id)
            if scope is None:
                return await target(user_id, *args, **kwargs)
            kind = self._kind
            if kind == "profile" and name == "update_field":
                # A model cannot turn a derived value into a trusted manual or
                # institutional record merely by choosing its source label.
                kwargs = dict(kwargs)
                if kwargs.get("source") in {"record", "user_edit"}:
                    kwargs["source"] = "conversation"
            if scope.restricted:
                if kind == "academic" and name == "get" and "academic" not in scope.sources:
                    return None
                if kind == "memory" and name in {"get", "list_by_user"}:
                    return None if name == "get" else []
                if kind == "function" and name == "fetch_external_intel":
                    # Fetch public facts using the already filtered topic, never
                    # reuse the personalized cache from a different permission set.
                    return await target(None, *args, **kwargs)
            result = await target(user_id, *args, **kwargs)
            writes = {
                ("profile", "update_field"): "profile",
                ("memory", "record_turn"): "turn",
                ("behavior", "log"): "behavior",
                ("function", "write_calendar_node"): "calendar",
            }
            record_kind = writes.get((kind, name))
            if record_kind:
                await scope.record(record_kind, result)
            if kind == "profile" and name == "replace_gaps":
                for gap in (args[0] if args else kwargs.get("gaps", [])):
                    await scope.record("gap", gap)
            if not scope.restricted:
                return result
            if kind == "profile":
                if name == "get":
                    return scope.profile(result)
                if name == "get_fields":
                    return [f for f in result if scope.field_allowed(f)]
                if name == "get_gaps":
                    return [g for g in result if scope.allows("gap", g)]
            list_reads = {
                ("memory", "list_turns"): "turn",
                ("behavior", "recent"): "behavior",
                ("asset", "list_versions"): "version",
                ("function", "list_calendar_nodes"): "calendar",
            }
            read_kind = list_reads.get((kind, name))
            if read_kind:
                return [item for item in result if scope.allows(read_kind, item)]
            single_reads = {
                ("memory", "find_reply"): "turn",
                ("asset", "get_report"): "report",
                ("asset", "get_action_plan"): "plan",
                ("asset", "get_latest_version"): "version",
                ("asset", "list_direction_plans"): "directions",
            }
            read_kind = single_reads.get((kind, name))
            if read_kind and result is not None and not scope.allows(read_kind, result):
                return [] if name == "list_direction_plans" else None
            return result

        return call


def guarded(service, kind):
    return AnalysisReadGuard(service, kind) if service is not None else None
