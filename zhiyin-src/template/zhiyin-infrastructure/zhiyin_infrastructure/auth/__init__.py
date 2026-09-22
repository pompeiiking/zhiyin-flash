"""鉴权基础设施实现。

认证凭证、令牌、登录会话与密码校验都在本层；业务层只消费认证主体。
"""

from zhiyin_infrastructure.auth.gateway import JwtAuthGateway

__all__ = ["JwtAuthGateway"]
