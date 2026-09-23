"""课表与成绩单导入的读模型（业务侧形状）。

为什么不直接把网关的模型抛给 api：导入之后业务层还做了一件事 ——
把画像摘要更新掉、并算出"这份快照值不值得展示"。结果要把这两面都带上，
否则 api 得自己拼一遍，字段口径就散成两处。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AcademicImportResult(BaseModel):
    """一次导入的结果。"""

    model_config = ConfigDict(extra="forbid")

    school: str = ""
    source: str = Field(default="", description="按哪种版式读出来的")
    term: str = ""
    courses: int = 0
    courses_scheduled: int = Field(
        default=0,
        description=(
            "课表里**读出了上课时间**（星期 + 节次）的课数。"
            "与 `courses` 分开报，是因为它们是两件事：课程进了库，但它不一定进得了课表 ——"
            "只报总数的话，用户看到的是「导入完成」，而这一周的课表还是空的。"
        ),
    )
    grades: int = 0
    imported_at: str = ""
    notes: list[str] = Field(
        default_factory=list,
        description="读的时候发现、但不足以拒绝导入的情况（例如有课没读出时间）",
    )
    wrote_profile: list[str] = Field(
        default_factory=list, description="更新了哪几条画像摘要（中文名）"
    )


__all__ = ["AcademicImportResult"]
