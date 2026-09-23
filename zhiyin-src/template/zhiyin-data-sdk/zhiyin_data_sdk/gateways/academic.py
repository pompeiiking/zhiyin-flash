"""课表与成绩单的**导入**契约（学生自己带数据进来）。

为什么是"导入"，不是"替他登录去抓"
----------------------------------
学信网有一条官方通道：用户自己申请在线验证报告，我们凭码去官方验证页核验 ——
不碰账号密码。教务系统没有这条路：中国高校的教务系统是一套套独立采购的成品软件
（正方、强智、URP、青果……），厂商没有开放接口，也没有面向第三方的授权通道。

于是只剩两条路：

1. 用户授权学号密码，我们替他进他学校的系统读一次；
2. 用户自己把课表与成绩带进来，我们负责**读懂它**。

本产品选择第 2 条。理由不是省事：

- 第 1 条要我们把用户在校内系统的密码经手一遍，那是把一个能登录他学籍系统的
  凭据拖进我们的风险面 —— 而它换来的只是"少点两下"；
- 学校系统的反爬、验证码、校内网限制都不是产品该对抗的东西；
- 第 2 条失败时用户看得见原因（粘贴的内容不对），第 1 条失败时他只看到"失败了"。

所以这一层只做一件事：**把用户带来的文本读成课表与成绩单**。
没有凭据、没有 outbound 请求、没有绕过任何东西。

支持的形态（都要能读懂，因为用户手上就这几种）
--------------------------------------------
- 教务系统课表页 / 成绩页的**整页复制**（HTML）—— 正方、强智两套主流版式；
- 从 Excel / WPS / 网页表格复制出来的**表格文本**（制表符或逗号分隔）；
- 正方接口那种 **JSON**，以及用户自己导出的"每门课一条记录"的 JSON 数组；
- 上面任意一种装在**文件里**传上来（.txt / .csv / .html / .json，编码我们认）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AcademicImportKind(str, Enum):
    """导入失败的类别。每一类都要对应**用户能做的一件事**。"""

    EMPTY = "empty"                # 什么都没贴（连提示都不用给，界面上按钮本来就该灰着）
    TOO_SHORT = "too_short"        # 贴得太短，不可能是课表/成绩单
    UNRECOGNIZED = "unrecognized"  # 读不出这是哪种版式（换一种贴法 / 用表头齐全的表格）
    NO_ROWS = "no_rows"            # 版式认得，但一条课/成绩都没读出来（多半只复制了一部分）
    NO_HEADER = "no_header"        # 表格文本缺表头，列对不上（把表头一起复制进来）


class AcademicImportError(Exception):
    """导入失败。`kind` 给业务层分流，`detail` 留给排查（不外露给用户）。"""

    def __init__(self, message: str, *, kind: AcademicImportKind, detail: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.detail = detail


class ImportFormat(BaseModel):
    """一种能吃进来的形态。界面上的"怎么导"就是它列出来的。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str = Field(description="界面上的说法，如 教务系统页面整页复制")
    howto: str = Field(default="", description="怎么拿到它 —— 这一步用户最容易卡住")


class CourseEntry(BaseModel):
    """一门课。字段取的是"排课"需要的那些，不是教务系统里所有列。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    teacher: str = ""
    weekday: int = Field(default=0, description="1=周一 … 7=周日；0 表示没读出来")
    start_period: int = Field(default=0, description="第几节开始（1 起）")
    end_period: int = Field(default=0, description="第几节结束")
    weeks: str = Field(default="", description="周次原文，如 1-16周")
    place: str = ""
    credit: str = ""
    category: str = Field(default="", description="课程性质 / 类别原文")


class GradeEntry(BaseModel):
    """一条成绩。"""

    model_config = ConfigDict(extra="forbid")

    term: str = ""
    name: str
    credit: str = ""
    score: str = Field(default="", description="成绩原文；等级制也照原样记，不换算")
    point: str = Field(default="", description="绩点原文")
    category: str = ""
    kind: str = Field(default="", description="必修 / 选修 / 任选")


class AcademicSnapshot(BaseModel):
    """一次导入的结果：这位同学这学期的课表与成绩单。"""

    model_config = ConfigDict(extra="forbid")

    school: str = Field(default="", description="学校名（用户填或从页面读到的）")
    source: str = Field(
        default="",
        description="这段数据是从哪种版式读出来的（qz / zf / table / json）—— 溯源用",
    )
    term: str = Field(default="", description="取到的是哪个学期")
    courses: list[CourseEntry] = Field(default_factory=list)
    grades: list[GradeEntry] = Field(default_factory=list)
    imported_at: str = Field(default="", description="导入时刻，ISO 8601")
    note: str = Field(
        default="",
        description="读的时候发现但不足以拒绝导入的情况（例如有课没读出时间）",
    )


class CourseImport(BaseModel):
    """一次课表解析的结果。带 `source` 是为了溯源：出问题时能立刻知道按哪种版式读的。"""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="", description="按哪种版式读出来的：qz / zf / table / json")
    term: str = Field(default="", description="从内容里读到的学期（读不到就是空）")
    courses: list[CourseEntry] = Field(default_factory=list)


class GradeImport(BaseModel):
    """一次成绩单解析的结果。"""

    model_config = ConfigDict(extra="forbid")

    source: str = ""
    grades: list[GradeEntry] = Field(default_factory=list)


class AcademicImportGateway(ABC):
    """课表与成绩单导入 Port。

    只做解析：给一段文本，还一份结构化数据。不联网、不碰凭据、不写任何东西 ——
    写入是业务层的事（见 `AcademicService`）。
    """

    @abstractmethod
    def formats(self) -> list[ImportFormat]:
        """能吃进来的形态，按推荐顺序。"""

    @abstractmethod
    def parse_courses(self, raw: str) -> CourseImport:
        """读课表。读不出来抛 `AcademicImportError`。"""

    @abstractmethod
    def parse_grades(self, raw: str) -> GradeImport:
        """读成绩单。读不出来抛 `AcademicImportError`。"""

    @abstractmethod
    def read_text(self, data: bytes, *, filename: str = "") -> str:
        """把用户**传上来的文件**读成文本（编码识别在这一层，别让调用方各自解一遍）。

        为什么算这一层的职责：解析器要的是文本，而用户手上常常是一个文件。
        "文件 → 文本"里藏着编码（GBK / 带 BOM 的 UTF-8）与二进制格式（Excel）两件
        必须处理、且处理方式必须一致的事。放在 api 或业务层，就会出现
        "粘贴能读、上传读不出"这种同一份数据的两种结果。

        读不了时抛 `AcademicImportError`，消息里要写明用户能做的事。
        """

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """实现自述（供装配报告与排查用）。"""


__all__ = [
    "AcademicImportError",
    "AcademicImportGateway",
    "AcademicImportKind",
    "AcademicSnapshot",
    "CourseEntry",
    "CourseImport",
    "GradeEntry",
    "GradeImport",
    "ImportFormat",
]
