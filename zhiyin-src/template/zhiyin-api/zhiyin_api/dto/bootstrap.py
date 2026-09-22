"""启动装配类 DTO（R-API-001）。

/app/bootstrap 一次返回菜单、路由、任务入口、文案与功能开关，
让前端启动只请求一次即可渲染首页——因此任务文案与功能开关变更不需要前端发版。

**这里不放任何默认文案。** 本文件是形状定义，不是文案仓库：应用名、定位语、
信任区、演示标注一律来自动态资源（`data/registry/copies.json` 等），
由 `zhiyin_api/dto/mappers.py` 填进来。此前 `app_name` / `trust_copy` 带默认字符串，
等于在代码里留了一份"影子文案"，改了 JSON 也不会生效。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import LoopStage


class TaskEntryView(BaseModel):
    """首页任务入口。文案必须用"用户自己的话"。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    target_stage: Optional[LoopStage] = Field(
        default=None, description="为空表示走「直接开聊」，由编排器判定入口"
    )
    lead_agent_name: Optional[str] = Field(default=None, description="开场主理展示名")
    sort_order: int = 0


class MenuView(BaseModel):
    """顶层导航项。仅"首页 / 核心对话页 / 智能工作台"三条主线。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    route: str
    visible: bool = True
    sort_order: int = 0


class RouteView(BaseModel):
    """前端路由。"""

    model_config = ConfigDict(extra="forbid")

    path: str
    page_code: str = Field(description="页面锚点口径，如 screen-home / screen-conv")
    require_login: bool = False
    sort_order: int = 0


class BannerView(BaseModel):
    """横幅 / 运营位（可上下线、可排序）。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    body: str = ""
    action_label: str = ""
    action_route: str = ""


class TrustBlockView(BaseModel):
    """信任背书块。只讲一条主线，可点开方法论示例。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    body: str = ""
    expandable_ref: str = Field(default="", description="可展开内容的引用键，空为纯文本")


class FaqView(BaseModel):
    """常见问题。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    question: str
    answer: str


class PortalView(BaseModel):
    """门户内容（**公开**：不需要登录）。

    为什么单独一个视图而不是复用 BootstrapView：那一份带着"我是谁"（identity）、
    菜单、路由、个人任务入口 —— 那些是登录后的事。门户只回答"这是什么、凭什么信"，
    内容全是产品自己的话（文案包 + 信任块 + 横幅 + FAQ + 功能开关），
    所以它可以、也应该在没有身份的情况下返回。

    此前门户文案写死在前端（`data/portal.ts`）—— 那是本仓底线之一"文案不进代码"
    的最后一处例外：改一句主张要发一次前端版本。
    """

    model_config = ConfigDict(extra="forbid")

    app_name: str = ""
    copy_bundle: dict[str, str] = Field(
        default_factory=dict, description="文案包（含全部 portal.* 键）"
    )
    task_entries: list[TaskEntryView] = Field(
        default_factory=list, description="任务入口：门户上展示的'能做什么'"
    )
    trust_blocks: list[TrustBlockView] = Field(default_factory=list)
    banners: list[BannerView] = Field(default_factory=list)
    faqs: list[FaqView] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class BootstrapView(BaseModel):
    """启动装配视图。"""

    model_config = ConfigDict(extra="forbid")

    app_name: str = Field(
        default="", description="应用名，取自动态文案 app.name；为空表示文案包缺失"
    )
    menus: list[MenuView] = Field(default_factory=list)
    routes: list[RouteView] = Field(default_factory=list)
    task_entries: list[TaskEntryView] = Field(default_factory=list)
    copy_bundle: dict[str, str] = Field(
        default_factory=dict,
        description="文案包（key → text），前端按 key 取用，不从后端解析自然语言",
    )
    trust_blocks: list[TrustBlockView] = Field(
        default_factory=list, description="信任区：第一条为主线，其余为可展开示例"
    )
    banners: list[BannerView] = Field(default_factory=list, description="横幅 / 运营位")
    faqs: list[FaqView] = Field(default_factory=list, description="常见问题")
    feature_flags: dict[str, bool] = Field(
        default_factory=dict, description="功能开关：导出/导师/演示等"
    )
    identity: dict[str, str] = Field(
        default_factory=dict, description="当前身份：role / nickname / avatar"
    )


class TheoryCardView(BaseModel):
    """理论卡正文。前端点开理论标签时展示的内容。

    四个字段都来自动态资源 `data/registry/theory_cards.json`——
    这里只做搬运，不生成、不改写。`summary` 是给用户看的通俗说明，
    `product_usage` 说清"这条理论在本产品里怎么被用"（可解释性的落点）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="理论卡 id，与 TheoryRef.theory_id 对应")
    name: str
    school: str = Field(default="", description="所属流派 / 出处")
    summary: str = Field(default="", description="给用户看的通俗说明")
    product_usage: str = Field(default="", description="在本产品里怎么被用")
