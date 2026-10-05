"""Module permissions, host SDK and developer operations. Storage is injected."""
from __future__ import annotations

import asyncio
import copy

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from zhiyin_data_sdk.repositories.modules import ModuleRepository
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest, KernelError, ResourceNotFound
from zhiyin_kernel.modules import ModuleContext, ModulePolicy, ModuleResult, ModuleView
from zhiyin_business.services.module_contracts import validate_contract


def _module_validation_error(module_id, stage, error):
    if isinstance(error, ValidationError):
        details = "；".join(f"{'/'.join(str(part) for part in item['loc']) or 'value'}: {item['msg']}"
            for item in error.errors(include_input=False, include_url=False)[:10])
    elif isinstance(error, JsonSchemaValidationError):
        details = f"{'/'.join(str(part) for part in error.absolute_path) or 'value'}: {error.message}"
    else:
        details = str(error)
    return InvalidRequest(f"模块 {module_id} {stage} 校验失败：{details}")


class ModulePlatform:
    def __init__(self, *, modules: dict, repository: ModuleRepository, identity, readers: dict,
                 actions: dict, revision: str, environment: str, inspect, agents, capabilities=()):
        self.modules, self.repository, self.identity = modules, repository, identity
        self.readers, self.actions = readers, actions
        self.revision, self.environment = revision, environment
        self.inspect, self.agents = inspect, agents
        self.capabilities = list(capabilities)
        self.flows = None

    async def user(self, token: str):
        # current_user reads the current database account, not only JWT role claims.
        return await self.identity.current_user(token=token)

    async def require(self, token: str, *, admin=False):
        user = await self.user(token)
        if user.role.value not in ({"admin"} if admin else {"admin", "developer"}):
            raise AccessDenied("需要管理员权限" if admin else "需要开发者权限")
        return user

    def definition(self, module_id):
        if module_id not in self.modules:
            raise ResourceNotFound("当前构建未安装这个模块")
        return self.modules[module_id]

    async def policy(self, module_id):
        self.definition(module_id)
        return ModulePolicy.model_validate(await self.repository.policy(module_id))

    async def availability(self, module_id):
        """Read current enablement for the whole ancestry; grants stay local."""
        policy = await self.policy(module_id)
        blocked_by = []
        seen = {module_id}
        parent_id = self.definition(module_id).manifest.parent_id
        while parent_id is not None:
            if parent_id in seen:
                raise InvalidRequest("模块层级不能引用自身或形成循环")
            seen.add(parent_id)
            parent = self.definition(parent_id).manifest
            if parent.kind == "tool":
                raise InvalidRequest("父模块必须是应用或混合模块")
            if not (await self.policy(parent_id)).enabled:
                blocked_by.append(parent_id)
            parent_id = parent.parent_id
        return policy, blocked_by

    async def enabled_policy(self, module_id):
        policy, blocked_by = await self.availability(module_id)
        if not policy.enabled or blocked_by:
            raise AccessDenied("模块或所属父模块已停用")
        return policy

    async def listing(self, *, enabled_only=False, applications_only=False):
        result = []
        for module_id, definition in self.modules.items():
            if applications_only and definition.manifest.kind == "tool":
                continue
            policy, blocked_by = await self.availability(module_id)
            effective_enabled = policy.enabled and not blocked_by
            if not enabled_only or effective_enabled:
                result.append(ModuleView(manifest=definition.manifest, policy=policy,
                    source_revision=self.revision, effective_enabled=effective_enabled, blocked_by=blocked_by))
        return sorted(result, key=lambda x: x.manifest.order)

    async def configure(self, module_id, policy: ModulePolicy, actor):
        m = self.definition(module_id).manifest
        if set(policy.reads) - set(m.reads) or set(policy.actions) - set(m.actions):
            raise InvalidRequest("只能授权模块声明的能力")
        if policy.enabled and set(m.reads) - set(policy.reads):
            raise InvalidRequest("启用前请授予模块需要的数据能力")
        if policy.agents and not m.tool:
            raise InvalidRequest("该模块未提供智能体工具")
        known_agents = {a.id for a in await self.agents()}
        if set(policy.agents) - known_agents:
            raise InvalidRequest("选择的智能体未注册")
        return ModulePolicy.model_validate(await self.repository.save_policy(module_id, policy.model_dump(), actor))

    async def read(self, module_id, user_id, *, mode="live", fixture="normal", preview=False):
        return await self.invoke(module_id, user_id, {}, mode=mode, fixture=fixture, preview=preview)

    def verify_version(self, module_id, expected_version=None):
        definition = self.definition(module_id)
        if expected_version is not None and expected_version != definition.manifest.version:
            raise DuplicateResource("模块版本已变化，请刷新版本后重试")
        for dependency, version in definition.manifest.dependencies.items():
            if self.definition(dependency).manifest.version != version:
                raise DuplicateResource(f"模块依赖版本不匹配：{dependency}@{version}")
        return definition

    async def invoke(self, module_id, user_id, inputs=None, *, expected_version=None,
                     mode="live", fixture="normal", preview=False):
        definition = self.verify_version(module_id, expected_version)
        inputs = copy.deepcopy(inputs or {})
        validate_contract(definition.manifest.input_schema, inputs, f"模块 {module_id} input")
        trace = []
        if mode == "live":
            await self.enabled_policy(module_id)
        if mode == "fixture" and not preview:
            raise AccessDenied("模拟数据只用于开发预览")
        fixtures = definition.fixture(fixture) if mode == "fixture" else {}
        if "error" in fixtures:
            raise InvalidRequest(fixtures["error"])

        async def reader(capability):
            if capability not in definition.manifest.reads:
                raise AccessDenied("模块未声明该数据能力")
            if mode == "fixture":
                value = copy.deepcopy(fixtures[capability])
                contract = next((item for item in self.capabilities if item.id == capability), None)
                if contract:
                    validate_contract(contract.output_schema, value, capability)
                trace.append({"capability": capability, "operation": "read", "mode": mode, "status": "succeeded"})
                return value
            latest = await self.enabled_policy(module_id)
            if capability not in latest.reads:
                raise AccessDenied("模块未获授权或已停用")
            value = await self.readers[capability](user_id)
            latest = await self.enabled_policy(module_id)
            if capability not in latest.reads:
                raise AccessDenied("模块数据授权已撤销")
            value = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            contract = next((item for item in self.capabilities if item.id == capability), None)
            if contract:
                validate_contract(contract.output_schema, value, capability)
            trace.append({"capability": capability, "operation": "read", "mode": mode,
                          "status": "succeeded"})
            return value

        try:
            value = await asyncio.wait_for(definition.load(ModuleContext(user_id, mode, reader, inputs)), timeout=20)
        except KernelError:
            # Preserve permission/conflict classifications from the platform SDK.
            raise
        except (ValueError, JsonSchemaValidationError) as exc:
            raise _module_validation_error(module_id, "backend.py.load", exc) from exc
        if mode == "live":
            await self.enabled_policy(module_id)
        try:
            result = ModuleResult.model_validate(definition.validate(value))
        except KernelError:
            raise
        except (ValueError, JsonSchemaValidationError) as exc:
            raise _module_validation_error(module_id, "backend.py.validate/output", exc) from exc
        validate_contract(definition.manifest.output_schema, result.data, f"模块 {module_id} output")
        return result.model_copy(update={"module_version": definition.manifest.version, "trace": trace})

    async def execute_action(self, module_id, user_id, action, payload, *, expected_version=None):
        definition = self.verify_version(module_id, expected_version)
        policy = await self.enabled_policy(module_id)
        if action not in policy.actions or action not in definition.manifest.actions:
            raise AccessDenied("模块未获准执行该操作")
        if {"user_id", "account", "actor"} & payload.keys():
            raise InvalidRequest("用户身份由平台注入")
        contract = next((capability for capability in self.capabilities if capability.id == action), None)
        if contract:
            validate_contract(contract.input_schema, payload, "action")
        result = await self.actions[action](user_id, payload)
        if contract:
            value = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
            validate_contract(contract.output_schema, value, action)
        return result

    async def perform(self, module_id, user_id, action, payload, *, expected_version=None):
        definition = self.verify_version(module_id, expected_version)
        await self.execute_action(module_id, user_id, action, payload, expected_version=expected_version)
        return await self.invoke(module_id, user_id, {}, expected_version=definition.manifest.version)

    async def tool_names(self, agent_id):
        return [m.manifest.tool for m in await self.listing(enabled_only=True)
                if m.manifest.tool and agent_id in m.policy.agents]

    async def tool(self, module_id, user_id, agent_id, inputs=None):
        manifest = self.definition(module_id).manifest
        policy = await self.enabled_policy(module_id)
        if not user_id or not manifest.tool or agent_id not in policy.agents:
            raise AccessDenied("当前智能体未获得模块授权")
        result = await self.invoke(module_id, user_id, inputs)
        if agent_id not in (await self.enabled_policy(module_id)).agents:
            raise AccessDenied("当前智能体的模块授权已撤销")
        return result

    async def check(self, actor):
        report = self.inspect()
        report["source_revision"] = self.revision
        report["scope"] = "manifest, dependencies, fixtures, output validators"
        for module_id in report["modules"]:
            for fixture in ("normal", "empty"):
                try:
                    inputs = self.definition(module_id).fixture(fixture).get("input", {})
                    await self.invoke(module_id, "fixture", inputs, mode="fixture", fixture=fixture, preview=True)
                except Exception as exc:
                    report["errors"].append({"module": module_id, "file": "backend.py", "message": str(exc)})
        report["passed"] = not report["errors"]
        return await self.repository.record_check(actor, report)

    async def request_release(self, actor, body):
        if self.environment != "workbench":
            raise AccessDenied("发布管理只在开发工作台启用")
        return await self.repository.create_job(actor, body.model_dump())
