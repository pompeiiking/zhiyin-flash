"""身份解析契约（业务侧）。

为什么需要这一层
----------------
身份解析的**能力**来自自有鉴权实现（当前 `DefaultPassAuth`），
契约由 `zhiyin_data_sdk.gateways.security.AuthGateway` 定义——那是数据访问契约，
**api 层按依赖矩阵不许 import data_sdk**（`test_api_does_not_touch_data_sdk`）。

于是 api 的 Facade 若要拿到"当前用户"，只有两条路：

1. 放宽矩阵，允许 api 直连 `AuthGateway`——把跨层直连的口子重新打开；
2. 由业务层包装出一个身份 Port，api 只面对业务抽象 ← **已采用**

第 2 条同时把该做的事留在了正确的位置：**"认证主体"到"本地用户记录"的补齐**
（首次登录建号、演示用户落库、登录后合并游客数据）是业务行为，不是 HTTP 适配，
也不是鉴权网关的职责。

分层口径
--------
- 本 Port 不认识 HTTP：**不要**在这里出现 `Request` / header / cookie；
  "从请求里取 token"是 api 层的事，api 取到 token 后传进来。
- 返回类型只能是内核形状（`UserAccount` / `UserRole`），不得返回 data_sdk 的类型，
  否则 api 会被迫认识数据访问契约，第 2 条路就白走了。

同类通道不止一个
----------------
与此同源的还有 `ports/registry.py::RegistryService`（动态资源读侧：菜单 / 路由 /
任务入口 / 文案 / 开关）。判据是同一个：**api 需要、契约却在 data_sdk**。
两条通道的分工是 "我是谁"（Identity）与 "页面长什么样"（Registry）；
若将来再出现第三个同类需求，按同一模式加 Port，不要放宽 api → data_sdk 的矩阵。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from zhiyin_kernel.identity import UserAccount


class IdentityService(ABC):
    """当前用户解析。"""

    @abstractmethod
    async def current_user(self, *, token: Optional[str] = None) -> UserAccount:
        """解析当前用户。

        行为约定：
        - `token` 为空时按"默认通过"口径取本地演示用户（第一期），
          第二期应改为抛 `PermissionError`（由 api 映射为 401）；
        - 认证主体在本地用户表没有记录时必须**补齐记录**再返回，
          否则下游（画像 / 行为 / 资产）会写到一个不存在的 user_id 上；
        - 游客同样走本方法（`role=guest`），不与登录用户分叉。

        TODO：游客会话合并（`GuestSession`）与登录态刷新接进来。
        """

    @abstractmethod
    async def login(self, account: str, password: str) -> dict:
        """账号密码登录：校验凭证 → 签发 JWT。返回 {token, user_id, role}。"""

    @abstractmethod
    async def account(self, user_id: str) -> UserAccount:
        """按 `user_id` 取本地用户记录（不存在则补齐）。

        为什么需要它：调用方**已经**通过 `current_user()` 拿到 `user_id` 之后，
        还要再取一次身份形状（启动装配 / 工作台标题等）时，不能再拿
        `token=None` 去重新认证一次 —— 那等于把刚验过的凭证丢掉，
        在真实 JWT 下必然失败。身份只认证一次，之后按 id 取记录。
        """

    @abstractmethod
    async def register(self, account: str, password: str, nickname: str = "") -> str:
        """注册账号（user_id 即账号名）。已存在抛 ValueError。"""


__all__ = ["IdentityService"]
