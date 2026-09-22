"""zhiyin-data-sdk · Data Access SDK 层。

职责：屏蔽底层存储与外部能力差异，向上层（编排层/业务层）提供稳定的
Repository 与 Gateway 接口。本层不承载业务规则，不知道"五环节""画像缺口"
等业务语义。

依赖方向：只允许依赖 zhiyin-infrastructure。
"""

__all__ = ["errors", "repositories", "gateways"]
