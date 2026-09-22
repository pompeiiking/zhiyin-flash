"""跨层异常类型（api 层唯一能识别的错误分类）。

为什么需要这一层
----------------
api 层是全站唯一把异常翻译成统一信封的地方（`zhiyin_api/app.py`）。
它此前按 **`LookupError` / `PermissionError` 这两个内建基类**注册处理器，后果是：

- 业务链路里任何一次 `KeyError` / `IndexError`（它们都是 `LookupError` 的子类）
  都会变成 404「资源不存在」；
- 任何一处文件系统 `PermissionError` 都会变成 401，把用户弹去登录页。

真实缺陷因此伪装成「正常的业务响应」，既不会被日志报出来，也不会有人去修。

本模块的类型**继承对应的内建异常**，所以：

- 既有调用方与 `pytest.raises(LookupError)` 全部照旧（多继承不改变 `isinstance` 判定）；
- api 层改为只认这几个类型，内建异常重新变回 500 —— 那正是它的真实含义
  （「我们没预料到的错」而不是「资源不存在」）。

`code` 是给上层做名字映射用的字符串：api 层被禁止 import `zhiyin_data_sdk` 与
`zhiyin_business`，所以它按 `code` 而不是按类型翻译（见 `api/controllers/ai_controller.py`
与 `api/app.py` 的映射表）。这与 `zhiyin_data_sdk.errors.SdkError` 的 `code` 口径一致。
"""

from __future__ import annotations


class KernelError(Exception):
    """跨层失败的基类。零依赖，任何层都可以抛与捕。"""

    code: str = "ERROR"


class ResourceNotFound(KernelError, LookupError):
    """目标资源不存在。

    继承 `LookupError` 是为了不破坏既有 `except LookupError` / `pytest.raises(LookupError)`；
    但 api 层只认本类型，所以 `KeyError` 这类内建异常不会再被误判成 404。
    """

    code = "NOT_FOUND"


class AccessDenied(KernelError, PermissionError):
    """未认证或无权访问（包括「令牌无效 / 已撤销 / 已过期」）。"""

    code = "UNAUTHORIZED"


class InvalidRequest(KernelError, ValueError):
    """用户输入不合法（业务规则层面），应由 api 层翻成 1001 而不是 500。"""

    code = "INVALID_PARAM"


class DuplicateResource(KernelError, ValueError):
    """唯一性冲突（如：账号已存在）。"""

    code = "CONFLICT"


__all__ = [
    "AccessDenied",
    "DuplicateResource",
    "InvalidRequest",
    "KernelError",
    "ResourceNotFound",
]
