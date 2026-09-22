"""zhiyin-boot · 启动装配层。

职责：读配置 → 实例化基础设施实现 → 注入到各层 → 挂载路由。
这是唯一允许 import 全部层的地方（其它包都必须遵守依赖方向）。

替换一个能力只改本层，不改业务代码。

包结构：

    container/ports.py         有哪些能力位
    container/gateways.py      外部能力用哪套实现
    container/repositories.py  数据访问与动态资源
    container/services.py      编排原语 / 业务服务 / Worker
    container/__init__.py      Container、装配入口、ASGI 装配
    report.py                  装配报告与分级门禁
    settings.py                环境与连接参数（不放文案 / 开关 / 规则）
    __main__.py                CLI：serve / check --phase=N / worker <name>
"""

from zhiyin_boot.container import (
    Container,
    assert_minimum_viable,
    build_container,
    wire_application,
)
from zhiyin_boot.report import (
    GateResult,
    PhaseGate,
    describe_assembly,
    evaluate_gate,
    load_gates,
    load_ownership,
)
from zhiyin_boot.settings import Settings

__all__ = [
    "Container",
    "GateResult",
    "PhaseGate",
    "Settings",
    "assert_minimum_viable",
    "build_container",
    "describe_assembly",
    "evaluate_gate",
    "load_gates",
    "load_ownership",
    "wire_application",
]
