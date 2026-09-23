"""启动入口（CLI）。

用法：

    python -m zhiyin_boot                        # 启动本地服务（默认 127.0.0.1:8000）
    python -m zhiyin_boot --port 8080 --reload

    python -m zhiyin_boot --check                # 打印装配报告，不启动服务
    python -m zhiyin_boot --check --strict       # 全绿才算通过（发布门禁）
    python -m zhiyin_boot --check --phase=1      # 只校验里程碑 1 的退出条件
    python -m zhiyin_boot --check --phase=2      # 里程碑 2：业务主干端到端

    python -m zhiyin_boot worker impact --once   # 手动跑一轮某个 Worker
    python -m zhiyin_boot worker active_event    # 独立部署某个 Worker（常驻）

第一期定位是"本地可启动、可演示、可调试"：读配置 → build_container →
交给 uvicorn。任何装配缺失都在启动时暴露，不做静默降级。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from zhiyin_boot.ai_bootstrap import hydrate_ai_config
from zhiyin_boot.container import build_container, wire_application
from zhiyin_boot.logging_setup import configure_logging
from zhiyin_boot.registry_bootstrap import hydrate_registry_content
from zhiyin_boot.report import describe_assembly, evaluate_gate, load_gates
from zhiyin_boot.runtime_config import hydrate_runtime_config
from zhiyin_boot.settings import Settings
from zhiyin_boot.workers import run_forever


def _ensure_utf8_stdout() -> None:
    """Windows 控制台默认可能是 GBK，打印中文装配报告会乱码或抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - 流的类型不支持时忽略
                pass


def _run_check(container, *, phase: int | None, strict: bool) -> int:
    """装配检查。返回进程退出码：0 通过 / 1 未通过。"""
    report = describe_assembly(container)
    payload = {"assembly": report.to_dict(), "cache": {}}
    if getattr(container, "read_cache", None) is not None:
        # 缓存自述与 `/healthz` 同源：哪几片、各多长 TTL、被哪些事件失效。
        # 冷启动时命中率为 null 是正常的（还没有请求），能看见的是策略装没装上。
        payload["cache"] = container.read_cache.stats()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if phase is not None:
        gates = load_gates(container.settings.local_registry_dir)
        gate = next((item for item in gates if item.phase == phase), None)
        if gate is None:
            print(
                f"未找到里程碑 {phase} 的门禁定义，请检查 "
                "data/registry/assembly_gates.json",
                file=sys.stderr,
            )
            return 2
        result = evaluate_gate(report, gate)
        print(json.dumps({"gate": result.to_dict()}, ensure_ascii=False, indent=2))
        return 0 if result.passed else 1

    # 不带 --phase 时：默认是信息输出（第一期业务尚未实现属预期），
    # 需要 CI 门禁时显式加 --strict（全绿）。
    return 0 if (report.healthy or not strict) else 1


def _run_worker(argv: list[str]) -> int:
    """独立运行一个 Worker：与同进程部署复用同一个 container。"""
    parser = argparse.ArgumentParser(prog="zhiyin worker", description="职引 · Worker")
    parser.add_argument("name", help="Worker 名称（见装配报告 workers 分组）")
    parser.add_argument(
        "--once", action="store_true", help="只跑一轮后退出（可配合外部 cron）"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="轮询间隔秒数，默认取 Settings.worker_interval_s",
    )
    args = parser.parse_args(argv)

    # AI 配置以库为准，而密钥可能只存在库里 ——
    # 所以"读库"必须在装配之前（详见 zhiyin_boot.ai_bootstrap 的说明）。
    settings = Settings.from_env()
    asyncio.run(hydrate_ai_config(settings))
    # 装配口径（能力位归属 / 分级门禁）同样以库为准 —— 它们以前是运行时直接读文件
    asyncio.run(hydrate_runtime_config(settings))
    # 动态资源（提示词 / 编排规则 / 文案 / 环节口径等）启动时导一次并核对：
    # 靠"第一次读"懒加载会让新库里的表建出来是空的，查库的人分不清
    # "还没导"和"本来就没配置"。
    asyncio.run(hydrate_registry_content(settings))
    container = build_container(settings)
    registry = {getattr(worker, "name", ""): worker for worker in container.workers}
    worker = registry.get(args.name)
    if worker is None:
        available = sorted(name for name in registry if name) or ["（当前未注册任何 Worker）"]
        print(
            f"未找到 Worker：{args.name}；已注册：{', '.join(available)}",
            file=sys.stderr,
        )
        return 2

    if args.once:
        processed = asyncio.run(worker.run_once())
        print(f"{args.name}：本轮处理 {processed} 条")
        return 0

    interval = args.interval or container.settings.worker_interval_s
    asyncio.run(run_forever(worker, interval))
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    # 启动期的几句话（读库口径 / 迁移生效 / 动态资源对账）都是 logging 发出的，
    # 不配 handler 就一句也看不到 —— 详见 zhiyin_boot/logging_setup.py。
    configure_logging()
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "worker":
        return _run_worker(argv[1:])

    parser = argparse.ArgumentParser(prog="zhiyin", description="职引 · 第一期服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发热重载（改代码即时生效）")
    parser.add_argument(
        "--reload-dir",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "热重载只监听这个目录，可重复；不传就监听整个工作目录。"
            "本仓的工作目录里带着 `.venv` 与 `build/`（实测 5875 个 .py 文件、"
            "遍历一遍 20 秒），默认值下会出现「改了代码却像没生效」—— "
            "开发时按包目录传几个，轮询就回到亚秒级"
        ),
    )
    parser.add_argument(
        "--resync-registry",
        action="store_true",
        help=(
            "以 data/registry/*.json 为准强制重导动态资源（运维动作）。"
            "默认口径是「以库为准」，所以仓库里改好的种子不会自动进环境 —— "
            "启动日志出现「动态资源与 ... 不一致」时用它对齐"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只做装配检查并打印报告，不启动服务",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="配合 --check：有部件未装配时以非 0 退出（用于 CI 门禁）",
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=None,
        help="配合 --check：只校验某个里程碑的退出条件（见 assembly_gates.json）",
    )
    args = parser.parse_args(argv)

    # AI 配置以库为准，而密钥可能只存在库里 ——
    # 所以"读库"必须发生在装配之前（详见 zhiyin_boot.ai_bootstrap 的说明）。
    settings = Settings.from_env()
    asyncio.run(hydrate_ai_config(settings))
    asyncio.run(hydrate_runtime_config(settings, resync=args.resync_registry))
    asyncio.run(hydrate_registry_content(settings, resync=args.resync_registry))
    container = build_container(settings)

    if args.check:
        return _run_check(container, phase=args.phase, strict=args.strict)

    app = wire_application(container)
    try:
        import uvicorn
    except ModuleNotFoundError:  # pragma: no cover - 依赖缺失时给出明确指引
        print(
            "缺少 uvicorn，请先安装运行依赖：pip install -e .[dev]",
            file=sys.stderr,
        )
        return 2

    # `--reload` 必须真的生效 —— 声明了却不生效比没有这个参数更坏：
    # 用的人会以为"改了代码没生效"是缓存问题。
    #
    # uvicorn 的热重载要求传 import string（它要能重新导入模块），所以这条分支
    # 走 `zhiyin_boot.asgi:app`；不带 --reload 时仍用已经装配好的实例，
    # 避免重复读库与重复建连接池。
    if args.reload:
        uvicorn.run(
            "zhiyin_boot.asgi:app",
            host=args.host,
            port=args.port,
            reload=True,
            # 传空列表 uvicorn 会当成"没有目录"；不传才是"默认整个工作目录"。
            reload_dirs=list(args.reload_dir) or None,
        )
    else:
        uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
