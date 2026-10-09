"""Membership and immutable-source lifecycle, independent of the execution host."""
from zhiyin_business.services.module_packages import inspect_package
from zhiyin_data_sdk.repositories.developer import DeveloperRepository
from zhiyin_kernel.errors import AccessDenied, InvalidRequest


class DeveloperPlatform:
    def __init__(self, platform, repository: DeveloperRepository, users, template):
        self.platform, self.repository, self.users, self.template = platform, repository, users, template

    async def require(self, token):
        user = await self.platform.require(token)
        if self.platform.environment != "workbench":
            raise AccessDenied("源码上传和版本协作只在开发工作台开放")
        return user

    async def project(self, project_id, user, *, manage=False):
        project = await self.repository.project(project_id)
        if user.role.value == "admin" or project["owner"] == user.id:
            return project
        if not manage and user.id in project["members"]:
            return project
        raise AccessDenied("没有这个模块项目的管理权限" if manage else "不是此项目的开发成员")

    async def create(self, body, user):
        if body.id in self.platform.modules and user.role.value != "admin":
            raise AccessDenied("现有内置模块须由管理员建立维护项目")
        return await self.repository.create_project(body.model_dump(), user.id)

    async def configure(self, project_id, body, user):
        current = await self.project(project_id, user, manage=True)
        if user.role.value != "admin" and (body.trusted != current["trusted"] or body.auto_deploy != current["auto_deploy"]):
            raise AccessDenied("项目信任和自动发布策略由管理员配置")
        if body.auto_deploy and not body.trusted:
            raise InvalidRequest("启用自动发布前必须授权项目运行")
        for member in body.members:
            account = await self.users.get_by_id(member)
            if not account or account.role.value not in {"developer", "admin"}:
                raise InvalidRequest(f"项目成员必须是已注册的开发者或管理员：{member}")
        return await self.repository.update_project(project_id, body.model_dump(), user.id)

    async def upload(self, project_id, body, user):
        await self.project(project_id, user)
        raw, manifest, digest, _ = inspect_package(body.package_base64, project_id)
        return await self.repository.create_version(project_id, user.id, body.model_dump(exclude={"package_base64"}), raw, manifest, digest)

    async def version(self, version_id, user, *, package=False):
        version = await self.repository.version(version_id, package)
        await self.project(version["project_id"], user)
        return version

    async def release(self, version_id, user):
        await self.version(version_id, user)
        status = await self.repository.status()
        if not status["worker"].get("healthy"):
            raise InvalidRequest("执行器离线，无法确认环境版本，请等待恢复")
        return await self.repository.release(version_id, user.id, status["environment"]["revision"])
