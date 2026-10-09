"""Versioned developer workspace contracts. Identity and execution are server owned."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.modules import ModuleManifest


class DeveloperProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)


class DeveloperProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    members: list[str] = Field(default_factory=list, max_length=50)
    trusted: bool = False
    auto_deploy: bool = False


class DeveloperProjectView(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    members: list[str]
    trusted: bool
    auto_deploy: bool
    revision: int
    created_at: str


class DeveloperUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_base64: str = Field(min_length=1, max_length=2_800_000)
    channel: str = Field(default="main", pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    base_version_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class DeveloperVersionView(BaseModel):
    id: str
    project_id: str
    version: str
    channel: str
    base_version_id: str | None
    base_commit: str
    digest: str
    actor: str
    manifest: ModuleManifest
    status: Literal["queued", "running", "passed", "failed"]
    stage: str
    report: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    candidate_commit: str = ""
    release_job_id: str = ""
    created_at: str


class DeveloperWorkerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease: str = Field(pattern=r"^[a-f0-9]{32}$")
    status: Literal["passed", "failed"] | None = None
    stage: str | None = Field(default=None, max_length=80)
    candidate_commit: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    report: dict[str, Any] = Field(default_factory=dict)
    event: dict[str, Any] | None = None


class DeveloperWorkerHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment_revision: str = ""
    worker_id: str = Field(max_length=80)
    rules_version: str = Field(default="2", max_length=40)


class DeveloperPlatformStatus(BaseModel):
    base_commit: str = ""
    worker: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    pending_versions: int = 0
