"""学信网在线验证报告核验契约。

为什么是"在线验证码"，不是账号密码
----------------------------------
学信网**没有**任何面向第三方的个人数据接口：
学生的学籍 / 学历 / 学位数据只有本人登录学信档案（需实人认证）才看得到，
机构想批量读，只能走商务签约的数据接口。

但学信网为"机构核验"这件事单独开了一条官方通道：
报告权属人自己在学信档案申请《教育部学籍在线验证报告》/
《教育部学历证书电子注册备案表》/《中国高等教育学位在线验证报告》，
得到一串在线验证码；任何机构都可以凭这串码，在学信网官方验证页读到报告内容，
免费、可重复、有有效期。这正是第三方该走的那条路。

所以本契约只需要**一串码**：

- 不要用户的学信网账号密码 —— 那既不合规，也等于替用户保管一把万能钥匙；
- 不绕过任何登录与实人认证 —— 实名这件事由学信网对用户做，我们只核验结果；
- 不缓存报告原文 —— 有效期是学信网定的，过期就该重新申请。

契约边界
--------
本契约只回答"这串码对应一份什么报告"，不回答"要不要写进画像"——
那是业务层的事（见 `zhiyin_business.services.ai_tasks` 的 bind 任务）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChsiReportKind(str, Enum):
    """报告类型。三类报告的字段不完全一样，业务层据此决定能补哪些画像字段。"""

    ENROLLMENT = "学籍"      # 教育部学籍在线验证报告（在读期间）
    EDUCATION = "学历"       # 教育部学历证书电子注册备案表（已毕业）
    DEGREE = "学位"          # 中国高等教育学位在线验证报告
    UNKNOWN = "未知"


class ChsiVerifyErrorKind(str, Enum):
    """核验失败的类别。业务层按它决定是"让用户重填"还是"稍后再试"。"""

    MALFORMED_CODE = "malformed_code"    # 码的格式就不对，根本没发请求
    INVALID_CODE = "invalid_code"        # 学信网明确回"此在线验证码无效"
    EXPIRED = "expired"                  # 报告已过有效期
    UNREACHABLE = "unreachable"          # 网络或对方服务不可达
    UNPARSEABLE = "unparseable"          # 页面拿到了但读不出字段（多为站点改版）


class ChsiVerifyError(Exception):
    """核验失败。`kind` 给业务层分流，`detail` 留给排查（不外露给用户）。

    `code` 与 `user_facing` 是给 api 层的：它按 `.code` 把异常翻成统一错误码，
    并在 `.user_facing` 为真时原样下发这句话（见 `api/controllers/ai_controller`）。
    api 层被禁止 import 本模块，所以这两个属性是**跨层的声明**，不是内部细节。

    此前这里只有 `kind`，api 层取不到 `.code`，于是所有核验失败一律兜成
    1999「内部错误」：用户改一串码就能好的事，界面上报成"我们的问题"，
    而真正该走"稍后再试"的不可达也分不出来。
    """

    def __init__(
        self,
        message: str,
        *,
        kind: ChsiVerifyErrorKind,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.detail = detail

    @property
    def code(self) -> str:
        """统一错误码口径：直接取 `kind` 的取值（`malformed_code` 等）。"""
        return self.kind.value

    @property
    def user_facing(self) -> bool:
        """这句话是不是写给用户看的。

        五类失败里，前四类的消息是给用户行动用的（改码 / 重新申请 / 稍后再试）；
        `UNPARSEABLE` 说的是"对方站点改版了"，对我们有用、对用户没用。
        """
        return self.kind is not ChsiVerifyErrorKind.UNPARSEABLE


class ChsiField(BaseModel):
    """报告里的一条字段。

    用 list 而不是 dict：报告是有阅读顺序的（姓名 → 学校 → 专业 → 学籍状态），
    顺序本身就是信息，丢掉它界面就得自己再排一遍。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="规范键，业务层用它映射画像字段")
    label: str = Field(description="报告上的原始标签，用于界面与溯源")
    value: str


class ChsiReport(BaseModel):
    """一份核验通过的在线验证报告。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    kind: ChsiReportKind = ChsiReportKind.UNKNOWN
    report_no: str = ""
    fields: list[ChsiField] = Field(default_factory=list)
    verified_at: str = Field(default="", description="核验时刻，ISO 8601")
    source_url: str = Field(default="", description="可回溯的核验地址（不含个人信息）")
    raw_excerpt: str = Field(
        default="",
        description="解析结果为空时留下的正文摘录，用于站点改版后排查",
    )

    def value_of(self, key: str) -> str:
        """按规范键取值；没有就返回空串（调用方不必写 optional 判断）。"""
        for field in self.fields:
            if field.key == key:
                return field.value
        return ""


class ChsiVerificationGateway(ABC):
    """学信网在线验证报告核验 Port。"""

    @abstractmethod
    async def verify(self, code: str) -> ChsiReport:
        """核验一串在线验证码。

        成功返回报告；失败抛 `ChsiVerifyError`，调用方按 `kind` 分流。
        实现**不得**抛出其他异常类型，否则业务层无法把失败翻成人话。
        """

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """实现自述（供装配报告与排查用）。"""


__all__ = [
    "ChsiField",
    "ChsiReport",
    "ChsiReportKind",
    "ChsiVerificationGateway",
    "ChsiVerifyError",
    "ChsiVerifyErrorKind",
]
