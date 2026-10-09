"""Public module protocol. No storage, framework or UI implementation lives here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Awaitable, Callable, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationInfo
from jsonschema import Draft202012Validator


def _schema_contract(value: dict[str, Any]) -> dict[str, Any]:
    def inspect(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in {"$ref", "$dynamicRef", "$id"} and isinstance(child, str) and not child.startswith("#"):
                    raise ValueError("模块 Schema 只允许本地引用，不允许外部引用或外部标识")
                inspect(child)
        elif isinstance(item, list):
            for child in item:
                inspect(child)
    inspect(value)
    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:
        raise ValueError(f"JSON Schema 无效：{exc.message if hasattr(exc, 'message') else exc}") from exc
    return value


JsonContract = Annotated[dict[str, Any], AfterValidator(_schema_contract)]


def _default_kind(data: dict[str, Any]) -> str:
    """Older declarations with a tool also expose their default card."""
    return "hybrid" if data.get("tool") else "application"


def _validate_kind(value: str, info: ValidationInfo) -> str:
    tool = info.data.get("tool")
    if value == "application" and tool is not None:
        raise ValueError("应用模块不能声明工具；同时提供两种入口时使用 hybrid")
    if value in {"tool", "hybrid"} and not tool:
        raise ValueError("工具或混合模块必须声明工具")
    return value


def _default_card(data: dict[str, Any]) -> str | None:
    return None if data.get("kind") == "tool" else "Card.vue"


def _validate_card(value: str | None, info: ValidationInfo) -> str | None:
    kind = info.data.get("kind")
    if kind == "tool" and value is not None:
        raise ValueError("工具模块不能声明首页卡片")
    if kind in {"application", "hybrid"} and value is None:
        raise ValueError("应用或混合模块必须声明卡片")
    return value


def _validate_detail(value: str | None, info: ValidationInfo) -> str | None:
    if info.data.get("kind") == "tool" and value is not None:
        raise ValueError("工具模块不能声明详情入口")
    return value


class ModuleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    owner: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)
    api_version: Literal["1"] = "1"
    parent_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,47}$")
    reads: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    tool: str | None = None
    # Field order matters for the pure cross-field schema validators: tool -> kind -> entries.
    kind: Annotated[Literal["application", "tool", "hybrid"], AfterValidator(_validate_kind)] = Field(
        default_factory=_default_kind, validate_default=True)
    card: Annotated[Literal["Card.vue"] | None, AfterValidator(_validate_card)] = Field(
        default_factory=_default_card, validate_default=True)
    detail: Annotated[Literal["Detail.vue"] | None, AfterValidator(_validate_detail)] = None
    conversation: Literal["Card.vue", "Detail.vue"] | None = None
    weight: float = Field(default=2, ge=1, le=4)
    order: int = Field(default=90, ge=0, le=1000)
    input_schema: JsonContract = Field(default_factory=lambda: {"type": "object"})
    output_schema: JsonContract = Field(default_factory=lambda: {"type": "object"})
    dependencies: dict[str, Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]] = Field(default_factory=dict)
    dataflow: Literal["dataflow.json"] | None = None

class ModuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    empty: bool = False
    module_version: str = ""
    trace: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class ModuleContext:
    user_id: str
    mode: Literal["live", "fixture"]
    read: Callable[[str], Awaitable[dict[str, Any]]]
    input: dict[str, Any] = field(default_factory=dict)


class ModuleInvoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any] = Field(default_factory=dict)
    expected_version: str | None = None
    request_id: str | None = Field(default=None, max_length=100)


class ModuleCapability(BaseModel):
    id: str
    operation: Literal["read", "action"]
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    user_scoped: bool = True


class ModuleFlowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    module_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    module_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    operation: Literal["read", "action"] = "read"
    action: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, str] = Field(default_factory=dict)


class ModuleFlowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_schema: JsonContract = Field(default_factory=lambda: {"type": "object"})
    nodes: list[ModuleFlowNode] = Field(min_length=1, max_length=32)


class ModuleFlowDraft(ModuleFlowDefinition):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    name: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(default=0, ge=0)


class ModuleFlowPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class ModuleFlowView(BaseModel):
    id: str
    name: str
    revision: int
    published_revision: int | None = None
    owner: str
    definition: ModuleFlowDefinition
    updated_at: str = ""


class ModuleFlowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["fixture", "live"] = "fixture"
    confirm_actions: bool = False
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_revision: int | None = Field(default=None, ge=1)


class ModuleFlowRun(BaseModel):
    id: str
    workflow_id: str
    revision: int
    status: Literal["running", "succeeded", "failed"]
    mode: Literal["fixture", "live"]
    outputs: dict[str, ModuleResult] = Field(default_factory=dict)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""
    action_committed: bool = False


class ModulePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    reads: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    revision: int = Field(default=0, ge=0)


class ModuleView(BaseModel):
    manifest: ModuleManifest
    policy: ModulePolicy
    source_revision: str
    effective_enabled: bool
    blocked_by: list[str] = Field(default_factory=list)


class ModuleAgentView(BaseModel):
    id: str
    name: str


class ModuleDeveloperContext(BaseModel):
    user_id: str
    role: str
    revision: str
    environment: str
    agents: list[ModuleAgentView]
    live_preview: bool


class ModuleAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_version: str | None = None


class ModulePreview(ModuleInvoke):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["fixture", "live"] = "fixture"
    fixture: Literal["normal", "empty", "error"] = "normal"


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["deploy", "rollback", "check"] = "deploy"


class ReleaseJob(BaseModel):
    id: str
    commit: str
    kind: str
    status: str
    stage: str = ""
    actor: str
    request_id: str
    lease: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""
