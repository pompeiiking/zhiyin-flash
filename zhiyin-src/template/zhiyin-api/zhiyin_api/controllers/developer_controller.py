"""Developer project API; uploaded source never executes in a request handler."""
from typing import Literal

from fastapi import APIRouter, Query, Request, Response

from zhiyin_api.controllers.module_controller import executor, public_job, token
from zhiyin_api.dto.common import ApiResponse
from zhiyin_kernel.developer import (DeveloperPlatformStatus, DeveloperProjectCreate, DeveloperProjectUpdate,
    DeveloperProjectView, DeveloperUpload, DeveloperVersionView, DeveloperWorkerHeartbeat, DeveloperWorkerUpdate)
from zhiyin_kernel.modules import ReleaseJob

router = APIRouter(tags=["developer-projects"])


def service(request: Request):
    value = getattr(request.app.state, "developer_platform", None)
    if value is None:
        raise NotImplementedError("开发者工作台未装配")
    return value


@router.get("/developer/projects", response_model=ApiResponse[list[DeveloperProjectView]])
async def projects(request: Request):
    platform = service(request)
    user = await platform.require(token(request))
    return ApiResponse(data=await platform.repository.projects(user.id, user.role.value == "admin"))


@router.post("/developer/projects", response_model=ApiResponse[DeveloperProjectView])
async def create_project(request: Request, body: DeveloperProjectCreate):
    platform = service(request)
    return ApiResponse(data=await platform.create(body, await platform.require(token(request))))


@router.put("/developer/projects/{project_id}", response_model=ApiResponse[DeveloperProjectView])
async def update_project(request: Request, project_id: str, body: DeveloperProjectUpdate):
    platform = service(request)
    return ApiResponse(data=await platform.configure(project_id, body, await platform.require(token(request))))


@router.get("/developer/projects/{project_id}/versions", response_model=ApiResponse[list[DeveloperVersionView]])
async def versions(request: Request, project_id: str):
    platform = service(request)
    await platform.project(project_id, await platform.require(token(request)))
    return ApiResponse(data=await platform.repository.versions(project_id))


@router.post("/developer/projects/{project_id}/versions", response_model=ApiResponse[DeveloperVersionView])
async def upload_version(request: Request, project_id: str, body: DeveloperUpload):
    platform = service(request)
    return ApiResponse(data=await platform.upload(project_id, body, await platform.require(token(request))))


@router.get("/developer/versions/{version_id}", response_model=ApiResponse[DeveloperVersionView])
async def version(request: Request, version_id: str):
    platform = service(request)
    return ApiResponse(data=await platform.version(version_id, await platform.require(token(request))))


@router.get("/developer/versions/{version_id}/package", response_class=Response)
async def package(request: Request, version_id: str):
    platform = service(request)
    value = await platform.version(version_id, await platform.require(token(request)), package=True)
    return Response(value["package"], media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{value["project_id"]}-{value["version"]}.zip"'})


@router.post("/developer/versions/{version_id}/retry", response_model=ApiResponse[DeveloperVersionView])
async def retry(request: Request, version_id: str):
    platform = service(request)
    user = await platform.require(token(request))
    await platform.version(version_id, user)
    return ApiResponse(data=await platform.repository.retry(version_id, user.id))


@router.post("/developer/versions/{version_id}/release", response_model=ApiResponse[ReleaseJob])
async def release(request: Request, version_id: str):
    platform = service(request)
    return ApiResponse(data=public_job(await platform.release(version_id, await platform.require(token(request)))))


@router.get("/developer/templates", response_class=Response)
async def template(request: Request, kind: Literal["application", "tool", "hybrid"] = "hybrid",
                   module_id: str = Query(pattern=r"^[a-z][a-z0-9_]{1,47}$"),
                   name: str = Query(min_length=1, max_length=80), owner: str = Query(min_length=1, max_length=80)):
    platform = service(request)
    await platform.require(token(request))
    return Response(platform.template(module_id, name, owner, kind), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{module_id}.zip"'})


@router.get("/developer/platform-status", response_model=ApiResponse[DeveloperPlatformStatus])
async def platform_status(request: Request):
    platform = service(request)
    await platform.require(token(request))
    return ApiResponse(data=await platform.repository.status())


@router.post("/developer/source-worker/heartbeat", response_model=ApiResponse[dict])
async def heartbeat(request: Request, body: DeveloperWorkerHeartbeat):
    executor(request)
    await service(request).repository.heartbeat(body.model_dump())
    return ApiResponse(data={"ok": True})


@router.post("/developer/source-worker/claim", response_model=ApiResponse[dict | None])
async def claim(request: Request):
    executor(request)
    return ApiResponse(data=await service(request).repository.claim())


@router.get("/developer/source-worker/ready", response_model=ApiResponse[list[DeveloperVersionView]])
async def ready(request: Request):
    executor(request)
    return ApiResponse(data=await service(request).repository.ready())


@router.get("/developer/source-worker/versions/{version_id}/package", response_class=Response)
async def worker_package(request: Request, version_id: str):
    executor(request)
    value = await service(request).repository.version(version_id, package=True)
    return Response(value["package"], media_type="application/zip")


@router.get("/developer/source-worker/versions/{version_id}", response_model=ApiResponse[DeveloperVersionView])
async def worker_version(request: Request, version_id: str):
    executor(request)
    return ApiResponse(data=await service(request).repository.version(version_id))


@router.post("/developer/source-worker/versions/{version_id}", response_model=ApiResponse[DeveloperVersionView])
async def worker_update(request: Request, version_id: str, body: DeveloperWorkerUpdate):
    executor(request)
    values = body.model_dump(exclude_none=True)
    lease = values.pop("lease")
    return ApiResponse(data=await service(request).repository.update_version(version_id, lease, values))


@router.post("/developer/source-worker/versions/{version_id}/release", response_model=ApiResponse[ReleaseJob])
async def worker_release(request: Request, version_id: str):
    executor(request)
    repository = service(request).repository
    version = await repository.version(version_id)
    project = await repository.project(version["project_id"])
    if not project["auto_deploy"] or version["channel"] != "main":
        from zhiyin_kernel.errors import AccessDenied
        raise AccessDenied("此版本不适用自动发布策略")
    status = await repository.status()
    return ApiResponse(data=public_job(await repository.release(version_id, "source-worker", status["environment"]["revision"], internal_worker=True)))


@router.post("/developer/source-worker/versions/{version_id}/retry", response_model=ApiResponse[DeveloperVersionView])
async def worker_retry(request: Request, version_id: str):
    executor(request)
    return ApiResponse(data=await service(request).repository.retry(version_id, "source-worker", internal_worker=True))


@router.get("/developer/executor/{job_id}/authorization", response_model=ApiResponse[dict])
async def release_authorization(request: Request, job_id: str):
    return ApiResponse(data=await executor(request).repository.authorization(job_id))
