"""安全实现包：真加密 / 脱敏 / 审计。

包内只有一件东西：`CryptoSecurity`（AES-GCM 加密 + 脱敏 + 结构化审计）。
鉴权是**另一个能力位**，它的 JWT 实现在 `zhiyin_infrastructure.auth`。

历史注：本文件此前 import 的是 `security.jwt_auth` —— 那个模块从来没存在过，
于是"import 这个包"必炸。之所以一直没暴露，是因为没人从这个包入口取东西；
补测试时才撞上。这里把它改成导出真实存在的东西，别再指向空气。
"""

from zhiyin_infrastructure.security.crypto import CryptoSecurity

__all__ = ["CryptoSecurity"]
