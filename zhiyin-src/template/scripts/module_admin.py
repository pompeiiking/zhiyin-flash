"""Bootstrap a developer/admin account, or add synthetic data in isolated environments."""
from __future__ import annotations

import argparse
import asyncio
import os

from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
from zhiyin_kernel.enums import UserRole


async def main(args):
    container = build_container(Settings.from_env())
    try:
        user = await container.users.get_by_id(args.account)
        password = os.environ.get("PLATFORM_ACCOUNT_PASSWORD", "")
        if user is None or args.reset_password:
            minimum = 6 if os.environ.get("ZHIYIN_MODULE_ENV") in {"workbench", "staging"} else 12
            if len(password) < minimum:
                raise ValueError(f"请通过 PLATFORM_ACCOUNT_PASSWORD 设置至少 {minimum} 位密码")
        if user is None:
            await container.identity_service.register(args.account, password, args.account)
            user = await container.users.get_by_id(args.account)
        elif args.reset_password:
            await container.auth.set_password(args.account, password)
        user.role = UserRole(args.role)
        await container.users.create(user)
        if args.seed:
            if os.environ.get("ZHIYIN_MODULE_ENV") not in {"workbench", "staging"}:
                raise ValueError("只能向隔离环境写入合成测试数据")
            if await container.asset_service.get_action_plan(user.id) is None:
                await container.asset_service.save_action_plan(user.id, ActionPlan(id=f"sample-{user.id}", phases=[
                    ActionPhase(name="本周", date_range="示例数据", tasks=[
                        ActionTask(id="sample-project", text="整理项目经历", done=True),
                        ActionTask(id="sample-intro", text="练习自我介绍")])]))
        print(f"Account {args.account}: role={args.role}, synthetic_data={args.seed}")
    finally:
        for value in reversed(container.extra.get("closables", [])):
            close = getattr(value, "aclose", None)
            if close:
                await close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account")
    parser.add_argument("--role", choices=["student", "developer", "admin"], default="developer")
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--reset-password", action="store_true", help="使用环境变量中的密码重置已有账号")
    asyncio.run(main(parser.parse_args()))
