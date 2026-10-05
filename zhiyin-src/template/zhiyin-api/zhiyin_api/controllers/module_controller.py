"""Module user API and authenticated developer management API."""
from __future__ import annotations

import hmac
import os
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from zhiyin_api.dto.common import ApiResponse
from zhiyin_kernel.errors import AccessDenied
from zhiyin_kernel.modules import (ModuleAction, ModuleDeveloperContext, ModulePolicy, ModulePreview, ModuleResult,
                                   ModuleView, ReleaseJob, ReleaseRequest, ModuleInvoke, ModuleCapability,
                                   ModuleFlowDraft, ModuleFlowPublish, ModuleFlowView, ModuleFlowRunRequest, ModuleFlowRun)

router = APIRouter(tags=["modules"])


def platform(request: Request):
    service = getattr(request.app.state, "module_platform", None)
    if service is None:
        raise NotImplementedError("模块平台需要 PostgreSQL 与完整业务装配")
    return service


def token(request: Request):
    return request.headers.get("authorization", "").removeprefix("Bearer ").strip()


def public_job(job):
    return {**job, "lease": ""}


@router.get("/app/modules", response_model=ApiResponse[list[ModuleView]])
async def user_modules(request: Request, surface: Literal["application", "conversation"] = "application"):
    service = platform(request)
    await service.user(token(request))
    modules = await service.listing(enabled_only=True, applications_only=surface == "application")
    if surface == "conversation":
        modules = [module for module in modules if module.manifest.conversation]
    return ApiResponse(data=modules)


@router.get("/app/modules/{module_id}/data", response_model=ApiResponse[ModuleResult])
async def module_data(request: Request, module_id: str):
    service = platform(request)
    user = await service.user(token(request))
    return ApiResponse(data=await service.read(module_id, user.id))


@router.post("/app/modules/{module_id}/actions", response_model=ApiResponse[ModuleResult])
async def module_action(request: Request, module_id: str, body: ModuleAction):
    service = platform(request)
    user = await service.user(token(request))
    return ApiResponse(data=await service.perform(module_id, user.id, body.action, body.payload, expected_version=body.expected_version))


@router.post("/app/modules/{module_id}/invoke", response_model=ApiResponse[ModuleResult])
async def invoke_module(request: Request, module_id: str, body: ModuleInvoke):
    service = platform(request)
    user = await service.user(token(request))
    return ApiResponse(data=await service.invoke(module_id, user.id, body.input, expected_version=body.expected_version))


@router.get("/developer/capabilities", response_model=ApiResponse[list[ModuleCapability]])
async def module_capabilities(request: Request):
    service = platform(request)
    await service.require(token(request))
    return ApiResponse(data=service.capabilities)


@router.get("/developer/workflows", response_model=ApiResponse[list[ModuleFlowView]])
async def module_workflows(request: Request):
    service = platform(request)
    await service.require(token(request))
    return ApiResponse(data=await service.flows.repository.list())


@router.post("/developer/workflows", response_model=ApiResponse[ModuleFlowView])
async def save_workflow(request: Request, body: ModuleFlowDraft):
    service = platform(request)
    user = await service.require(token(request))
    return ApiResponse(data=await service.flows.save(body, user.id, admin=user.role.value == "admin"))


@router.post("/developer/workflows/{workflow_id}/publish", response_model=ApiResponse[ModuleFlowView])
async def publish_workflow(request: Request, workflow_id: str, body: ModuleFlowPublish):
    service = platform(request)
    user = await service.require(token(request))
    return ApiResponse(data=await service.flows.publish(workflow_id, body.expected_revision, user.id, admin=user.role.value == "admin"))


@router.post("/developer/workflows/{workflow_id}/unpublish", response_model=ApiResponse[ModuleFlowView])
async def unpublish_workflow(request: Request, workflow_id: str, body: ModuleFlowPublish):
    service = platform(request)
    user = await service.require(token(request))
    return ApiResponse(data=await service.flows.unpublish(workflow_id, body.expected_revision, user.id, admin=user.role.value == "admin"))


@router.get("/developer/workflows/{workflow_id}/runs", response_model=ApiResponse[list[ModuleFlowRun]])
async def workflow_runs(request: Request, workflow_id: str):
    service = platform(request)
    user = await service.require(token(request))
    return ApiResponse(data=await service.flows.repository.runs(workflow_id, None if user.role.value == "admin" else user.id))


@router.post("/developer/workflows/{workflow_id}/run", response_model=ApiResponse[ModuleFlowRun])
async def preview_workflow(request: Request, workflow_id: str, body: ModuleFlowRunRequest):
    service = platform(request)
    user = await service.require(token(request))
    if body.mode == "live" and service.environment not in {"workbench", "staging", "candidate", "integration"}:
        raise AccessDenied("真实调试仅在隔离测试环境开放")
    return ApiResponse(data=await service.flows.run(workflow_id, user.id, body, admin=user.role.value == "admin"))


@router.post("/app/workflows/{workflow_id}/run", response_model=ApiResponse[ModuleFlowRun])
async def run_workflow(request: Request, workflow_id: str, body: ModuleFlowRunRequest):
    service = platform(request)
    user = await service.user(token(request))
    return ApiResponse(data=await service.flows.run(workflow_id, user.id, body, published=True))


@router.get("/developer/context", response_model=ApiResponse[ModuleDeveloperContext])
async def developer_context(request: Request):
    service = platform(request)
    user = await service.require(token(request))
    agents = await service.agents()
    return ApiResponse(data={"user_id": user.id, "role": user.role.value,
                             "revision": service.revision, "environment": service.environment,
                             "agents": [{"id": a.id, "name": a.name} for a in agents],
                             "live_preview": service.environment in {"workbench", "staging"}})


@router.get("/developer/modules", response_model=ApiResponse[list[ModuleView]])
async def developer_modules(request: Request):
    service = platform(request)
    await service.require(token(request))
    return ApiResponse(data=await service.listing())


@router.put("/developer/modules/{module_id}/policy", response_model=ApiResponse[ModulePolicy])
async def module_policy(request: Request, module_id: str, body: ModulePolicy):
    service = platform(request)
    user = await service.require(token(request), admin=True)
    return ApiResponse(data=await service.configure(module_id, body, user.id))


@router.post("/developer/modules/{module_id}/preview", response_model=ApiResponse[ModuleResult])
async def preview_module(request: Request, module_id: str, body: ModulePreview):
    service = platform(request)
    user = await service.require(token(request))
    if body.mode == "live" and service.environment not in {"workbench", "staging"}:
        raise AccessDenied("真实预览仅在隔离测试环境开放")
    return ApiResponse(data=await service.invoke(module_id, user.id, body.input, expected_version=body.expected_version,
        mode=body.mode, fixture=body.fixture, preview=True))


@router.post("/developer/checks", response_model=ApiResponse[dict])
async def check_modules(request: Request):
    service = platform(request)
    user = await service.require(token(request))
    return ApiResponse(data=await service.check(user.id))


@router.get("/developer/checks", response_model=ApiResponse[list[dict]])
async def module_checks(request: Request):
    service = platform(request)
    await service.require(token(request))
    return ApiResponse(data=await service.repository.checks())


@router.get("/developer/releases", response_model=ApiResponse[list[ReleaseJob]])
async def release_jobs(request: Request):
    service = platform(request)
    await service.require(token(request))
    return ApiResponse(data=[public_job(x) for x in await service.repository.jobs()])


@router.post("/developer/releases", response_model=ApiResponse[ReleaseJob])
async def request_release(request: Request, body: ReleaseRequest):
    service = platform(request)
    user = await service.require(token(request))
    return ApiResponse(data=public_job(await service.request_release(user.id, body)))


@router.post("/developer/releases/{job_id}/approve", response_model=ApiResponse[ReleaseJob])
async def approve_release(request: Request, job_id: str):
    service = platform(request)
    user = await service.require(token(request), admin=True)
    if service.environment != "workbench":
        raise AccessDenied("只能从开发工作台发布")
    return ApiResponse(data=public_job(await service.repository.approve(job_id, user.id)))


def executor(request):
    secret = os.environ.get("ZHIYIN_EXECUTOR_TOKEN", "")
    if len(secret) < 32 or not hmac.compare_digest(token(request), secret):
        raise AccessDenied("执行器凭据无效")
    service = platform(request)
    if service.environment != "workbench":
        raise AccessDenied("该环境不接收发布执行器")
    return service


class ExecutorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease: str = Field(min_length=32, max_length=32)
    status: Literal["succeeded", "failed", "rolled_back"] | None = None
    stage: str | None = Field(default=None, max_length=80)
    result: dict = Field(default_factory=dict)
    event: dict | None = None


@router.post("/developer/executor/claim", response_model=ApiResponse[ReleaseJob | None])
async def claim_release(request: Request):
    return ApiResponse(data=await executor(request).repository.claim())


@router.get("/developer/executor/configuration", response_model=ApiResponse[dict])
async def executor_configuration(request: Request):
    service = executor(request)
    return ApiResponse(data={m.manifest.id: m.policy.model_dump() for m in await service.listing()})


@router.post("/developer/executor/{job_id}", response_model=ApiResponse[ReleaseJob])
async def update_release(request: Request, job_id: str, body: ExecutorUpdate):
    values = body.model_dump(exclude_none=True)
    lease = values.pop("lease")
    return ApiResponse(data=await executor(request).repository.update_job(job_id, lease, values))
