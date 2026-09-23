"""DTO Mapper：业务形状 → 前端视图。

只做形状翻译：`business 读模型 / Port 返回值 → dto View`；
**不做取数**（不调服务）、**不写业务规则**（不判断该不该展示、不拼结论）；
不解析文案：文案一律来自 `copy_bundle`（动态资源），不要在这里拼中文。

`TurnResult.disclosure` 是**可空**的：只有"换主理 / 换理论 / 结论变化"时才填。
Mapper 把 None 原样透传成 `None`（前端据此决定是否渲染告知行），
**不用**空字符串或默认文案顶替——那会让"没有告知"和"告知了但是空的"无法区分。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence

if TYPE_CHECKING:  # 只用于类型标注：mapper 不 import 业务实现，只认它的读模型
    from zhiyin_business.ports.blackboard import ConversationMaterial

from zhiyin_api.dto.asset import (
    ActionPhaseView,
    ActionPlanView,
    ActionTaskView,
    AssetVersionView,
    CalendarNodeView,
    TrackEventView,
    DirectionPlanListView,
    DirectionPlanView,
    ExportResultView,
    PlanGapView,
    ReportDimensionItemView,
    ReportFullTextView,
    ReportSectionView,
    ReportTocItemView,
)
from zhiyin_api.dto.bootstrap import (
    BannerView,
    BootstrapView,
    FaqView,
    MenuView,
    PortalView,
    RouteView,
    TaskEntryView,
    TheoryCardView,
    TrustBlockView,
)
from zhiyin_api.dto.common import (
    AgentBadgeView,
    BehaviorGuideView,
    CoachNotificationView,
    DisclosureView,
    GuideOptionView,
    GuideReminderView,
    GuideTaskView,
    TheoryRefView,
)
from zhiyin_api.dto.conversation import (
    ConversationMaterialView,
    ConversationMessageView,
    ConversationTurnView,
    PipelineCardView,
    SessionListView,
    TaskSessionView,
    IntelRefView,
    RenderableView,
)
from zhiyin_api.dto.workspace import (
    AcademicCourseView,
    AcademicGradeView,
    AcademicPanelView,
    CollectionItemView,
    CollectionPanelView,
    DependencyEdgeView,
    IntelItemView,
    IntelListView,
    LayoutBlockView,
    ProfileFieldView,
    ProfileGapView,
    ProfilePanelView,
    StagePanelView,
    WorkspacePageView,
)
from zhiyin_api.dto.note import NoteView
from zhiyin_business.ports.function import ExternalIntel
from zhiyin_business.contracts.common import (
    AgentBadge,
    BehaviorGuide,
    Disclosure,
    IntelRef,
    Renderable,
    TheoryRef,
)
from zhiyin_business.ports.function import ExportResult
from zhiyin_business.ports.orchestrator import TurnResult
from zhiyin_business.ports.workspace import WorkspaceView
from zhiyin_kernel.assets import Report
from zhiyin_kernel.assets import ActionPlan, DirectionPlan
from zhiyin_kernel.assets import CalendarNode
from zhiyin_kernel.assets import TrackEvent
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.blackboard import AssetVersion, TaskSession
from zhiyin_kernel.blackboard import ConversationTurn
from zhiyin_kernel.dynamic_content import (
    BannerSpec,
    FaqSpec,
    MenuSpec,
    RouteSpec,
    TrustBlockSpec,
)
from zhiyin_kernel.enums import LoopStage
from zhiyin_kernel.identity import UserAccount
from zhiyin_kernel.registry import AgentDescriptor, TaskEntrySpec, TheoryCard

"""
环节口径来自**动态资源**（`data/registry/stages.json` → `biz_registry_item`）。

这份口径曾经在这里、在工作台服务、在 AI 任务的进度文案里**各写了一遍**，
改一处忘一处，前后端就对不上。现在只在库里有一份，启动时读进来：

    configure_stages(await registry.list_stages())   # 见 zhiyin_boot 的 lifespan

下面这份 `_FALLBACK_ORDER` **不是配置**，它只是兜底：万一动态资源没读到，
管线卡按什么顺序画。标签为空是刻意的 —— 与其显示一个可能是旧的名字，
不如显示得少一点，让缺配置这件事自己露出来。
"""
_STAGE_ORDER: list[LoopStage] = [
    LoopStage.COLLECT,
    LoopStage.DIAGNOSE,
    LoopStage.DECIDE,
    LoopStage.ACT,
    LoopStage.REVIEW,
]

def _stage_specs() -> list[Any]:
    """从**快照**取环节口径 —— 进程内唯一来源，改库后由重载统一替换。

    直接读快照而不是在本模块缓存一份：两处缓存一定会分叉，
    而分叉的表现是"重载了，但这个页面还是旧的"。
    """
    return list(dynamic_config.snapshot().stages)


def _stage_order() -> list[LoopStage]:
    order: list[LoopStage] = []
    for spec in _stage_specs():
        try:
            order.append(LoopStage(spec.id))
        except ValueError:
            continue
    return order or list(_STAGE_ORDER)


def _stage_label(stage: LoopStage) -> str:
    for spec in _stage_specs():
        if spec.id == stage.value:
            return spec.label or spec.title or ""
    # 快照为空（还没装载）时给空串，而不是猜一个可能过期的名字
    return ""


def _stage_asset(stage: LoopStage) -> str:
    for spec in _stage_specs():
        if spec.id == stage.value:
            return spec.asset or ""
    return ""


def _enabled(item) -> bool:
    return getattr(item, "status", "enabled") == "enabled"


# ---------------------------------------------------------------------------
# 启动装配（app_controller → /app/bootstrap）
# ---------------------------------------------------------------------------


def portal_view(
    *,
    copy_bundle: dict[str, str],
    task_entries: Sequence[TaskEntrySpec],
    agents: dict[str, AgentDescriptor],
    trust_blocks: Sequence[TrustBlockSpec],
    banners: Sequence[BannerSpec],
    faqs: Sequence[FaqSpec],
    feature_flags: dict[str, bool],
) -> PortalView:
    """门户内容（公开）。

    从同一份动态资源里取，但**只取门户要用的那几类**：文案、任务入口、信任块、
    横幅、FAQ、开关。不带 identity / 菜单 / 路由 —— 那些是登录后的事。

    文案只过滤 `portal.` 前缀：门户不需要知道别的页面有哪些文案，
    一次拿全量反而把"哪些文案属于这一页"这件事变模糊。
    """
    return PortalView(
        app_name=copy_bundle.get("app.name", ""),
        copy_bundle={
            code: text for code, text in copy_bundle.items() if code.startswith("portal.")
        },
        task_entries=[
            TaskEntryView(
                code=entry.code,
                label=entry.label,
                target_stage=entry.target_stage,
                lead_agent_name=agents[entry.lead_agent].name
                if entry.lead_agent in agents
                else None,
            )
            for entry in task_entries
            if _enabled(entry)
        ],
        trust_blocks=[
            TrustBlockView(
                code=block.code,
                title=block.title,
                body=block.body,
                expandable_ref=block.expandable_ref,
            )
            for block in trust_blocks
            if _enabled(block)
        ],
        banners=[
            BannerView(
                code=banner.code,
                title=banner.title,
                body=banner.body,
                action_label=banner.action_label,
                action_route=banner.action_route,
            )
            for banner in banners
            if _enabled(banner)
        ],
        faqs=[
            FaqView(code=faq.code, question=faq.question, answer=faq.answer)
            for faq in faqs
            if _enabled(faq)
        ],
        feature_flags=dict(feature_flags),
    )


def bootstrap_view(
    *,
    copy_bundle: dict[str, str],
    menus: Sequence[MenuSpec],
    routes: Sequence[RouteSpec],
    task_entries: Sequence[TaskEntrySpec],
    agents: dict[str, AgentDescriptor],
    trust_blocks: Sequence[TrustBlockSpec],
    banners: Sequence[BannerSpec],
    faqs: Sequence[FaqSpec],
    feature_flags: dict[str, bool],
    identity: Optional[UserAccount] = None,
) -> BootstrapView:
    """拼首页启动视图。

    口径：
    - `app_name` 取 `copy_bundle["app.name"]`，取不到就留空字符串——**不回落硬编码**，
      空值会让"文案包缺了"在联调时立刻可见；
    - 任务入口的 `lead_agent_name` 由 `agents[lead_agent].name` 解析，取不到时为 None
      （前端回落显示 agent_id，不静默编名字）；
    - 身份区为 `None`（游客）时 identity 留空 dict。
    """
    return BootstrapView(
        app_name=copy_bundle.get("app.name", ""),
        menus=[
            MenuView(
                key=menu.code,
                label=menu.label,
                route=menu.route,
                visible=menu.visible,
                sort_order=menu.sort_order,
            )
            for menu in menus
            if _enabled(menu)
        ],
        routes=[
            RouteView(
                path=route.path,
                page_code=route.page_code,
                require_login=route.require_login,
                sort_order=route.sort_order,
            )
            for route in routes
            if _enabled(route)
        ],
        task_entries=[
            TaskEntryView(
                code=entry.code,
                label=entry.label,
                target_stage=entry.target_stage,
                lead_agent_name=agents[entry.lead_agent].name
                if entry.lead_agent and entry.lead_agent in agents
                else None,
                sort_order=entry.sort_order,
            )
            for entry in task_entries
            if _enabled(entry)
        ],
        copy_bundle=copy_bundle,
        trust_blocks=[
            TrustBlockView(
                code=block.code,
                title=block.title,
                body=block.body,
                expandable_ref=block.expandable_ref,
            )
            for block in trust_blocks
            if _enabled(block)
        ],
        banners=[
            BannerView(
                code=banner.code,
                title=banner.title,
                body=banner.body,
                action_label=banner.action_label,
                action_route=banner.action_route,
            )
            for banner in banners
            if _enabled(banner)
        ],
        faqs=[
            FaqView(code=faq.code, question=faq.question, answer=faq.answer)
            for faq in faqs
            if _enabled(faq)
        ],
        feature_flags=feature_flags,
        identity=_identity_dict(identity),
    )


def _identity_dict(user: Optional[UserAccount]) -> dict[str, str]:
    if user is None:
        return {}
    return {"nickname": user.nickname, "role": user.role.value}


# ---------------------------------------------------------------------------
# 对话页（conversation_controller）
# ---------------------------------------------------------------------------


def task_session_view(
    session: TaskSession,
    *,
    task_name: str,
    lead_agent_name: str = "",
    progress: float = 0.0,
) -> TaskSessionView:
    """左栏会话项。`task_name` 取自动态任务入口文案，不按 agent 名排布。"""
    return TaskSessionView(
        task_id=session.id,
        task_name=task_name,
        stage=session.loop_stage,
        stage_label=_stage_label(session.loop_stage),
        lead_agent_name=lead_agent_name,
        status=session.status,
        progress=progress,
        last_active_at=session.updated_at,
    )


def session_list_view(
    sessions: Sequence[TaskSessionView], *, current_task_id: Optional[str] = None
) -> SessionListView:
    """左栏会话列表。"""
    return SessionListView(sessions=list(sessions), current_task_id=current_task_id)


def conversation_turn_view(turn: TurnResult) -> ConversationTurnView:
    """一轮回复：最短结论 + 显式告知 + 行为引导 + 管线卡。"""
    return ConversationTurnView(
        task_id=turn.task_id,
        stage=turn.stage,
        badge=agent_badge_view(turn.badge),
        messages=[
            ConversationMessageView(
                role=message.role,
                text=message.text,
                agent_id=message.agent_id,
                agent_name=turn.badge.name
                if message.agent_id and message.agent_id == turn.badge.agent_id
                else None,
                theory_refs=[theory_ref_view(ref) for ref in message.theory_refs],
                renderables=[renderable_view(item) for item in message.renderables],
                intel_refs=[intel_ref_view(ref) for ref in message.intel_refs],
                created_at=message.created_at,
            )
            for message in turn.messages
        ],
        disclosure=disclosure_view(turn.disclosure) if turn.disclosure is not None else None,
        guide=behavior_guide_view(turn.guide),
        pipeline_cards=pipeline_cards(turn.session, turn.asset_versions),
        changed_assets=[asset_version_view(version) for version in turn.asset_versions],
    )


def theory_ref_view(ref: TheoryRef) -> TheoryRefView:
    """理论引用视图。只有 id / 展示名 / 环节 —— 正文走 /app/theory-cards/{id}。"""
    return TheoryRefView(theory_id=ref.theory_id, name=ref.name, stage=ref.stage)


def agent_badge_view(badge: AgentBadge) -> AgentBadgeView:
    """主理徽章视图。"""
    return AgentBadgeView(
        agent_id=badge.agent_id,
        name=badge.name,
        role_summary=badge.role_summary,
        theory_refs=[theory_ref_view(ref) for ref in badge.theory_refs],
    )


def behavior_guide_view(guide: BehaviorGuide) -> BehaviorGuideView:
    """行为引导视图：四选一，形状逐字段搬运。"""
    return BehaviorGuideView(
        kind=guide.kind,
        text=guide.text,
        question=guide.question,
        options=[
            GuideOptionView(option_id=o.option_id, label=o.label, value=o.value)
            for o in guide.options
        ],
        task=GuideTaskView(task_id=guide.task.task_id, text=guide.task.text, due_date=guide.task.due_date)
        if guide.task is not None
        else None,
        reminder=GuideReminderView(
            title=guide.reminder.title,
            due_at=guide.reminder.due_at,
            detail=guide.reminder.detail,
        )
        if guide.reminder is not None
        else None,
    )


def disclosure_view(disclosure: Disclosure) -> DisclosureView:
    """显式告知行视图。"""
    return DisclosureView(
        kind=disclosure.kind,
        text=disclosure.text,
        theory_refs=[theory_ref_view(ref) for ref in disclosure.theory_refs],
        from_agent=disclosure.from_agent,
        to_agent=disclosure.to_agent,
    )


def pipeline_cards(
    session: TaskSession, asset_versions: Sequence[AssetVersion]
) -> list[PipelineCardView]:
    """右栏 ①-⑤ 管线卡（三态：当前产出 / 理论模型 / 评价状态）。"""
    order = _stage_order()
    current_index = order.index(session.loop_stage) if session.loop_stage in order else 0
    latest_by_type = {
        version.asset_type.value: version
        for version in asset_versions
    }
    cards: list[PipelineCardView] = []
    for index, stage in enumerate(order):
        if stage == session.loop_stage:
            status: str = "in_progress"
        elif index < current_index:
            status = "done"
        else:
            status = "empty"
        current_output = None
        asset_key = _stage_asset(stage)
        if asset_key and asset_key in latest_by_type:
            version = latest_by_type[asset_key]
            current_output = {
                "version": version.version,
                "diff_from_previous": version.diff_from_previous,
            }
        cards.append(
            PipelineCardView(
                stage=stage,
                title=_stage_label(stage),
                active=stage == session.loop_stage,
                status=status,
                current_output=current_output,
            )
        )
    return cards


# ---------------------------------------------------------------------------
# 工作台（workspace_controller）
# ---------------------------------------------------------------------------


def intel_list_view(items: list[ExternalIntel]) -> IntelListView:
    """外部情报清单 → 前端视图。取回时间取最新那一条。"""
    return IntelListView(
        items=[
            IntelItemView(
                id=item.id,
                kind=item.kind,
                kind_label=item.kind_label,
                title=item.title,
                text=item.text,
                source_url=item.source_url,
                source_name=item.source_name,
                fetched_at=item.fetched_at,
            )
            for item in items
        ],
        fetched_at=items[0].fetched_at if items else "",
    )


def workspace_page_view(view: WorkspaceView) -> WorkspacePageView:
    """工作台 ①-⑤ 聚合视图。"""
    panels = {panel.stage: panel for panel in view.panels}

    def panel_view(stage: LoopStage) -> Optional[StagePanelView]:
        panel = panels.get(stage)
        if panel is None:
            return None
        return StagePanelView(
            stage=panel.stage,
            title=panel.title,
            evaluation=panel.evaluation,
            theory_models=[theory_ref_view(ref) for ref in panel.theory_refs],
            version=panel.version,
            diff=panel.diff_from_previous,
            updated_at=panel.updated_at,
        )

    profile = view.profile
    # 字段展示名的两级来源，缺一不可：
    #   1. 字段自带的 `label` —— 字段键是模型自己起的（`interest_direction`），
    #      它的中文名只能跟着这条数据一起存下来；
    #   2. 动态资源的采集规则表 —— 标准字段（major / degree_level…）用这一份，
    #      老数据没有 label 时也靠它兜住。
    # 两级都没有才会回落到键本身：那时宁可露出英文，也不能编一个假名字。
    rules_labels = view.profile_labels or {}
    labels = {**rules_labels}
    profile_panel = ProfilePanelView(
        coverage=view.profile_coverage,
        overall_confidence=view.profile_confidence,
        fields=[
            ProfileFieldView(
                key=field.key,
                label=field.label or labels.get(field.key, ""),
                value=field.value,
                confidence=field.confidence,
                source=field.source,
                updated_at=field.updated_at,
                evidence=list(field.evidence),
            )
            for field in (profile.fields if profile else [])
        ],
        gaps=[
            ProfileGapView(
                key=gap.key,
                label=gap.label or labels.get(gap.key, ""),
                reason=gap.reason,
                suggested_next_action=gap.suggested_next_action,
            )
            for gap in (profile.gaps if profile else [])
        ],
        updated_at=profile.updated_at if profile else None,
    )
    coach_messages = [
        event.model_dump(mode="json") for event in view.track_events
    ]
    # 采集动线：业务层已经把"缺什么、去哪取、为什么"算好了，这里只搬形状。
    # api 层不再判断任何采集口径 —— 那些规则只在 policies/collection.py 一处。
    collection = view.collection
    collection_panel = CollectionPanelView(
        missing=collection.missing if collection else 0,
        by_source=dict(collection.by_source) if collection else {},
        blocked=list(collection.blocked) if collection else [],
        next_source=(
            collection.next_source().value
            if collection and collection.next_source()
            else None
        ),
        items=[
            CollectionItemView(
                key=step.key,
                label=step.label,
                source=step.source.value,
                why=step.why,
                got=step.got,
                available=step.available,
                # 「去回答」要问的那一句随清单一起下发：界面只渲染，不自己拼问题
                ask=step.ask,
            )
            for step in (collection.steps if collection else ())
        ],
    )
    return WorkspacePageView(
        profile_panel=profile_panel,
        report_panel=panel_view(LoopStage.DIAGNOSE),
        plan_panel=panel_view(LoopStage.DECIDE),
        action_panel=panel_view(LoopStage.ACT),
        review_panel=panel_view(LoopStage.REVIEW),
        coach_messages=coach_messages,
        dependencies=[
            DependencyEdgeView(
                from_asset=edge.from_asset,
                to_asset=edge.to_asset,
                via_profile_keys=edge.via_profile_keys,
            )
            for edge in view.dependencies
        ],
        collection_panel=collection_panel,
        academic_panel=academic_panel_view(view.academic),
        layout_panel=[
            LayoutBlockView(
                id=block.id,
                label=block.label,
                hint=block.hint,
                weight=block.weight,
                priority=block.priority,
                why=block.why,
            )
            for block in view.layout
        ],
    )


# ---------------------------------------------------------------------------
# 资产（asset_controller）
# ---------------------------------------------------------------------------


def asset_version_view(
    version: AssetVersion, *, previous: Optional[AssetVersion] = None
) -> AssetVersionView:
    """资产版本视图。`diff_from_previous` 优先取落库 diff；无落库 diff 且有上一版时给版本差说明。"""
    diff = version.diff_from_previous
    if diff is None and previous is not None:
        # 版本历史显示在报告页上：不写 "v1 → v2" 这种版本号缩写。
        diff = f"由第 {previous.version} 版更新而来"
    return AssetVersionView(
        asset_type=version.asset_type,
        asset_id=version.id,
        version=version.version,
        created_at=version.created_at,
        depends_on_profile_keys=version.depends_on_profile_keys,
        diff_from_previous=diff,
        # "这一版是旧的"必须能从接口看出来：否则影响面传播打了标也没人知道，
        # 界面上那份过期结论看起来和新鲜的一样。
        needs_recompute=version.needs_recompute,
    )


def note_view(note: Any) -> NoteView:
    """用户自建内容视图。

    字段口径只留这一处：`UserNote`（内核）→ `NoteView`（前端）。
    Facade 里直接 new 一个 View 会让同一条数据有两种口径，
    而"用户的原话"被翻译错一次，采集回执引用的就是一句他没写过的话。
    """
    return NoteView(
        id=note.id,
        kind=note.kind,
        text=note.text,
        done=bool(note.done),
        created_at=note.created_at,
    )


def academic_panel_view(snapshot: Any) -> Optional[AcademicPanelView]:
    """导入的课表与成绩快照 → 前端视图。

    这里用 `getattr` 而不是打类型注解：快照的形状来自 data-sdk，
    而 **api 层按依赖矩阵不许 import `zhiyin_data_sdk`**（见 test_architecture）。
    形状由业务层保证 —— 它读得出来就读得出来，读不出来就是 None。
    """
    if snapshot is None:
        return None
    return AcademicPanelView(
        school=str(getattr(snapshot, "school", "") or ""),
        source=str(getattr(snapshot, "source", "") or ""),
        term=str(getattr(snapshot, "term", "") or ""),
        imported_at=str(getattr(snapshot, "imported_at", "") or ""),
        note=str(getattr(snapshot, "note", "") or ""),
        courses=[
            AcademicCourseView(
                name=course.name,
                teacher=course.teacher,
                weekday=course.weekday,
                start_period=course.start_period,
                end_period=course.end_period,
                weeks=course.weeks,
                place=course.place,
                credit=course.credit,
                category=course.category,
            )
            for course in getattr(snapshot, "courses", []) or []
        ],
        grades=[
            AcademicGradeView(
                term=grade.term,
                name=grade.name,
                credit=grade.credit,
                score=grade.score,
                point=grade.point,
                category=grade.category,
                kind=grade.kind,
            )
            for grade in getattr(snapshot, "grades", []) or []
        ],
    )


def report_full_text_view(
    report: Report | None, *, group_labels: Optional[Mapping[str, str]] = None
) -> ReportFullTextView:
    """完整报告页正文（只读资产版本，不重新生成）。

    `report` 为 None（尚无报告资产）时返回空正文，前端渲染"报告未生成"空态。

    `group_labels` 是分组展示名（`SELF-PORTRAIT → 自我画像`），由**调用方**从
    动态资源取好传进来：Mapper 只做形状翻译、不取数（见本模块 docstring），
    而 api 层也不能自己去读动态资源（那是业务侧出口的事）。
    取不到就退回落库的分组标识 —— 宁可显示得生硬，也不在这里编一个可能过期的中文名。
    """
    if report is None:
        from datetime import datetime, timezone

        return ReportFullTextView(
            report_id="", version=0, generated_at=datetime.now(timezone.utc)
        )
    labels = dict(group_labels or {})
    toc: list[ReportTocItemView] = []
    sections: list[ReportSectionView] = []
    for group in report.dimensions:
        # `group.group` 是 Literal 字符串（不是枚举），直接取值即可。
        key = str(group.group)
        anchor = f"section-{key.lower()}"
        title = labels.get(key, key)
        toc.append(ReportTocItemView(id=anchor, title=title))
        sections.append(
            ReportSectionView(
                id=anchor,
                title=title,
                method=group.group_method,
                items=[
                    ReportDimensionItemView(
                        index=item.index,
                        name=item.name,
                        tag=item.tag,
                        conclusion=item.conclusion,
                        evidence=item.evidence,
                    )
                    for item in group.items
                ],
            )
        )
    return ReportFullTextView(
        report_id=report.id,
        version=report.version,
        generated_at=report.generated_at,
        toc=toc,
        sections=sections,
        verdict=report.verdict.model_dump(mode="json"),
        swot=report.swot.model_dump(mode="json"),
        methodologies=report.methodologies,
        sources=report.sources,
    )


def theory_card_view(card: TheoryCard | None) -> TheoryCardView | None:
    """理论卡正文。取不到卡返回 None —— 前端据此如实说"这张卡还没配"，
    而不是渲染一张只有标题的空卡（那看起来像加载失败）。"""
    if card is None:
        return None
    return TheoryCardView(
        id=card.id,
        name=card.name,
        school=card.school,
        summary=card.summary,
        product_usage=card.product_usage,
    )


def direction_plan_view(plan: DirectionPlan) -> DirectionPlanView:
    """一套方向方案。"""
    return DirectionPlanView(
        id=plan.id,
        role=plan.role,
        name=plan.name,
        target_desc=plan.target_desc,
        match_score=plan.match_score,
        gaps=[
            PlanGapView(
                requirement=gap.requirement,
                current_state=gap.current_state,
                suggestion=gap.suggestion,
            )
            for gap in plan.gaps
        ],
        fit_reason=plan.fit_reason,
        main_risk=plan.main_risk,
        selected=plan.selected,
        selected_at=plan.selected_at,
        revocable=plan.revocable,
    )


def direction_plan_list_view(plans: Sequence[DirectionPlan]) -> DirectionPlanListView:
    """三套方案 + 当前选中那一套的 id。

    `selected_id` 从同一个列表里算出来，而不是再看一次库：
    两次读之间用户可能刚改过选择，那种不一致会在界面上表现成"两套都亮着"。

    `match_score_method` 取方案资产里存下来的那一句（生成时模型给的），
    而不是写一份前端/后端的常量 —— 口径是产出的一部分，不能两处各写一遍。
    """
    items = list(plans)
    selected = next((plan.id for plan in items if plan.selected), None)
    method = next((plan.match_method for plan in items if plan.match_method), "")
    return DirectionPlanListView(
        plans=[direction_plan_view(plan) for plan in items],
        selected_id=selected,
        match_score_method=method or "三叶草契合度 × 可达性",
    )


def action_plan_view(plan: ActionPlan | None) -> ActionPlanView:
    """行动计划正文。

    `task_id` 用"阶段名:任务文本"拼（与仓储的勾选口径一致）——
    内核的 `ActionTask` 没有 id 字段，而界面必须能指认"勾的是哪一条"。
    任务文本在同一个阶段里重复的概率极低，且仓储两种实现都用同一个拼法。
    """
    if plan is None:
        return ActionPlanView(has_plan=False)

    phases: list[ActionPhaseView] = []
    first_open: ActionTaskView | None = None
    for phase in plan.phases:
        tasks: list[ActionTaskView] = []
        for task in phase.tasks:
            view = ActionTaskView(
                # 新数据有稳定 id 就用它；老数据没有 id 时回落到历史口径
                task_id=task.id or f"{phase.name}:{task.text}",
                text=task.text,
                phase=phase.name,
                due_date=task.due_date,
                done=task.done,
                done_at=task.done_at,
            )
            tasks.append(view)
            if first_open is None and not task.done:
                first_open = view
        phases.append(
            ActionPhaseView(
                name=phase.name,
                date_range=phase.date_range,
                tag=phase.tag,
                tasks=tasks,
            )
        )
    return ActionPlanView(
        has_plan=True,
        id=plan.id,
        plan_id=plan.plan_id or None,
        phases=phases,
        next_task=first_open,
        reminders_synced=plan.reminders_synced,
        exported_at=plan.exported_at,
    )


def calendar_node_view(node: CalendarNode) -> CalendarNodeView:
    """关键节点日历条目。"""
    return CalendarNodeView(
        node_id=node.node_id,
        title=node.title,
        due_at=node.due_at,
        source=node.source,
        related_task_text=node.related_task_text,
    )


def track_event_view(event: TrackEvent) -> TrackEventView:
    """跟踪时间线一条。"""
    return TrackEventView(
        id=event.id,
        type=event.type,
        title=event.title,
        detail=event.detail,
        occurred_at=event.occurred_at,
        due_at=event.due_at,
        related_task_id=event.related_task_id,
        related_stage=event.related_stage,
    )


def conversation_message_view(
    turn: ConversationTurn, *, agent_name: Optional[str] = None
) -> ConversationMessageView:
    """逐轮对话原文 → 前端气泡。

    主理展示名由调用方从注册表取好传进来（Mapper 不取数）：库里存 agent_id，
    名字是动态资源里的事实 —— 存一份名字等于把当时的叫法冻结在历史里。
    """
    return ConversationMessageView(
        role=turn.role,
        text=turn.text,
        agent_id=turn.agent_id or None,
        agent_name=agent_name,
        created_at=turn.created_at,
    )


def material_view(material: "ConversationMaterial") -> "ConversationMaterialView":
    """一份材料的回执：**只搬"它是什么"，不搬正文**。

    正文留在服务端（只在用到它的那一轮进模型输入）—— 这条分工写在这里，
    是为了让"顺手把 text 也带回去"这件事看起来就像一处不该做的改动。
    """
    return ConversationMaterialView(
        material_id=material.material_id,
        name=material.name,
        size=material.size,
        chars=material.chars,
    )


def renderable_view(item: Renderable) -> RenderableView:
    """一块可视件。`payload` 原样搬运 —— 校验发生在编排器那边（kind 注册表），
    这一层只负责把已经验过的数据摆成前端认识的样子。"""
    return RenderableView(
        kind=item.kind,
        title=item.title,
        payload=dict(item.payload),
        source_refs=[intel_ref_view(ref) for ref in item.source_refs],
    )


def intel_ref_view(ref: IntelRef) -> IntelRefView:
    """一条可点回原页面的外部情报引用。"""
    return IntelRefView(
        id=ref.id,
        title=ref.title,
        kind_label=ref.kind_label,
        source_name=ref.source_name,
        source_url=ref.source_url,
    )


def coach_notification_view(item: Mapping[str, Any]) -> CoachNotificationView:
    """通知视图：只搬运两个读侧实现都保证存在的字段（见 DTO docstring）。"""
    return CoachNotificationView(
        id=str(item.get("id", "")),
        title=str(item.get("title", "")),
        body=str(item.get("body", "")),
        channel=str(item.get("channel", "")),
        action=item.get("action"),
        related_task_id=item.get("related_task_id"),
        occurred_at=str(item["occurred_at"]) if item.get("occurred_at") else None,
    )


def export_result_view(result: ExportResult) -> ExportResultView:
    """导出结果。第一期 `available` 恒 False（占位）。"""
    return ExportResultView(
        available=result.available,
        message=result.message,
        object_key=result.object_key,
    )


__all__ = [
    "academic_panel_view",
    "action_plan_view",
    "agent_badge_view",
    "asset_version_view",
    "behavior_guide_view",
    "bootstrap_view",
    "calendar_node_view",
    "coach_notification_view",
    "conversation_message_view",
    "conversation_turn_view",
    "disclosure_view",
    "direction_plan_list_view",
    "direction_plan_view",
    "export_result_view",
    "note_view",
    "pipeline_cards",
    "portal_view",
    "report_full_text_view",
    "session_list_view",
    "task_session_view",
    "theory_card_view",
    "theory_ref_view",
    "track_event_view",
    "workspace_page_view",
]
