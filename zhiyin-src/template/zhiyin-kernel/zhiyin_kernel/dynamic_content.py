"""前端动态内容契约（菜单 / 路由 / 文案 / 横幅 / 信任块 / FAQ）。

为什么这些形状在**内核**而不是 `zhiyin_api`：
它们是跨层共用的数据形状——数据访问契约（`RegistryRepository`）要返回它们、
基础设施层要读出它们、业务读侧服务要转手给 BFF。若定义在 api 层，
SDK 与基础设施就要反向依赖 api，依赖倒置立刻失效。

对应「前端动态内容表」13 张里的 7 张
（`app_menu` / `app_route` / `app_task_entry` / `app_copy` / `app_banner` /
`app_trust_block` / `app_faq`）。

以下 4 张**故意不建形状**，因为第一期没有消费者：
`app_page` / `app_page_section` / `app_component` / `app_component_prop`
（"页面结构可配置化"——第一期前端是真实 Vue 组件而不是配置渲染），
以及 `app_task_option`（任务入口内的选项组）。
等出现真实消费者时再补形状与 JSON，避免出现"看起来能配、实际没人读"的空契约。

第一期由本地 JSON 承载（`data/registry/*.json`），第二期切动态资源表时形状不变。
`effective_at` / `expire_at` 这类生效窗口字段留给第二期：第一期没有按时间生效的需求，
先建字段等于让实现者维护一个永远为空的列。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ContentStatus = Literal["enabled", "disabled"]


class ContentSpec(BaseModel):
    """动态内容公共字段（统一配置模式）。

    所有前端动态内容都带 `code` / `status` / `sort_order`：运营侧靠 code 定位、
    靠 status 上下线、靠 sort_order 排序，三者不齐就没法"改配置不发版"。
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="稳定标识，运营与前端按它定位")
    status: ContentStatus = Field(default="enabled", description="enabled / disabled")
    sort_order: int = Field(default=0, description="越小越靠前")


class MenuSpec(ContentSpec):
    """顶层导航菜单。

    只允许「首页 / 核心对话页 / 智能工作台」三条主线；功能块不进主线导航。
    """

    label: str
    route: str = Field(description="前端路由 path，必须能在 routes 里找到")
    visible: bool = True


class RouteSpec(ContentSpec):
    """前端路由（页面锚点口径）。"""

    path: str
    page_code: str = Field(description="页面锚点，如 screen-home / screen-conv")
    require_login: bool = False


class CopySpec(ContentSpec):
    """单条文案。前端不得硬编码展示文案（R-API-001）。"""

    text: str
    bundle: str = Field(default="zh-CN", description="文案包 / 多语言标识")
    note: str = Field(default="", description="文案来源或待定稿说明")


class BannerSpec(ContentSpec):
    """横幅 / 运营位（可配置上下线与排序）。"""

    title: str
    body: str = ""
    action_label: str = Field(default="", description="行动按钮文案，空表示无按钮")
    action_route: str = Field(default="", description="行动按钮跳转的前端路由")


class TrustBlockSpec(ContentSpec):
    """信任背书块。

    口径：只讲一条主线「你做的每步都基于职业咨询的成熟方法」，不堆数字炫技。
    `expandable_ref` 指向可点开的方法论示例（脱敏演示数据）。
    """

    title: str
    body: str = ""
    expandable_ref: str = Field(
        default="", description="可展开内容的引用键，空表示纯文本块"
    )


class FaqSpec(ContentSpec):
    """常见问题。"""

    question: str
    answer: str


__all__ = [
    "BannerSpec",
    "ContentSpec",
    "ContentStatus",
    "CopySpec",
    "FaqSpec",
    "MenuSpec",
    "RouteSpec",
    "TrustBlockSpec",
]
