"""功能块服务实现。

第一期形态：报告全文 P0（只读资产版本）、日历 P0 登记、
成就 P0 只由行为日志驱动、导出占位、导师占位、演示只读。

两条口径的落点：
- 报告全文**只读资产版本**（`AssetService.get_report`），不重新生成；
- 成就**只由行为日志驱动**：`list_achievements` 每次从行为日志实时推导，
  不做登录 / 浏览型徽章（防自嗨）。

日历 / 体验型事件时间线第一期用进程内存储承载（P0 登记形态），
切表时把 `_*_store` 换成对应 Repository 即可，方法签名不变。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from zhiyin_business.ports.blackboard import AssetService, BehaviorService
from zhiyin_business.ports.function import ExternalIntel, ExportResult, FunctionService
from zhiyin_business.ports.blackboard import ProfileService
from zhiyin_business.policies.intel_labels import kind_label, source_name_of
from zhiyin_business.policies.intel_query import intel_topic
from zhiyin_data_sdk.gateways.datasource import (
    DataSourceGateway,
    DataSourceRequest,
)
from zhiyin_data_sdk.gateways.messaging import NotifyGateway
from zhiyin_kernel.enums import NotifyChannel
from zhiyin_data_sdk.gateways.storage import ObjectStoreGateway
from zhiyin_data_sdk.repositories import (
    CalendarNodeRepository,
    NotificationRepository,
    TrackEventRepository,
)
from zhiyin_business.ports.registry import RegistryService
from zhiyin_kernel.assets import Achievement, CalendarNode, TrackEvent
from zhiyin_kernel.enums import BehaviorEventType

logger = logging.getLogger(__name__)


class DefaultFunctionService(FunctionService):
    """功能块服务默认实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        assets: AssetService,
        behaviors: BehaviorService,
        object_store: ObjectStoreGateway,
        calendar: CalendarNodeRepository,
        track_events: TrackEventRepository,
        notifications: NotificationRepository,
        registry: RegistryService | None = None,
        profiles: ProfileService | None = None,
        data_sources: DataSourceGateway | None = None,
        notifier: NotifyGateway | None = None,
        web_search: Any = None,
    ) -> None:
        self._assets = assets
        self._behaviors = behaviors
        self._object_store = object_store
        # 三类数据都走 Repository：它们都是**用户可见的核心数据**，
        # 不是缓存。放在进程内存里的代价是"重启即丢 + 多实例各存一份"。
        self._calendar = calendar
        self._track_events = track_events
        self._notifications = notifications
        # 「外部情报」那条链路的三件依赖：读画像（决定去查什么）、
        # 取公开数据（学职网）、把结果推成一条通知（让它自己冒出来）。
        self._profiles = profiles
        self._data_sources = data_sources
        self._notifier = notifier
        #: 通用网络检索（可配）。配了它，情报就**不只**来自学职平台 ——
        #: 用户要的"信息源很广"在实现上就是"多一个来源接进来"，而不是把
        #: 结果编得更像样。
        self._web_search = web_search
        self._intel_cache: dict[tuple[str | None, str, str, int], tuple[float, list[ExternalIntel]]] = {}
        #: 上一次取数的**结果状态**：`ok / empty / failed`。
        #:
        #: 为什么必须分开记：面板上"0 条"有两种完全不同的意思 ——
        #: "确实没有匹配的公开资料"和"这次检索/上游失败了"。前者该安心，
        #: 后者该给他一个重试。只回一个空数组，界面只能猜。
        self._intel_status: dict[tuple[str | None, str, str], dict[str, Any]] = {}
        #: 站内提醒去重：同一批情报在 12 小时内只推一次。
        #: 此前每次取数都推一条同标题提醒，实测同一个用户攒出 3 条一字不差的
        #: 「给你找到 5 条与你方向相关的公开信息」，提醒页完全无法区分。
        self._last_intel_announce: dict[str, tuple[float, str]] = {}
        # 成就解锁规则来自动态资源（经 RegistryService 这个业务侧出口读）。
        # 缺读侧时**不发放任何成就**，而不是退回一张内置表：
        # 内置表会让"库里改了规则但没生效"看起来像正常 —— 那正是要避免的静默回落。
        self._registry = registry

    async def get_report_full_text(self, user_id: str, version: int | None = None) -> dict:
        report = await self._assets.get_report(user_id, version)
        return {"report": report}

    async def export_asset(
        self, user_id: str, asset_type: str, fmt: Literal["pdf", "docx"]
    ) -> ExportResult:
        return ExportResult(asset_type=asset_type, format=fmt)

    async def list_calendar_nodes(self, user_id: str) -> list[CalendarNode]:
        return await self._calendar.list_nodes(user_id)

    async def write_calendar_node(self, user_id: str, node: CalendarNode) -> CalendarNode:
        return await self._calendar.upsert_node(user_id, node)

    async def delete_calendar_node(self, user_id: str, node_id: str) -> int:
        return await self._calendar.delete_node(user_id, node_id)

    async def list_achievements(self, user_id: str) -> list[Achievement]:
        rules = await self._registry.list_badge_rules() if self._registry is not None else []
        if not rules:
            return []
        # 规则里的 trigger_events 是事件名（字符串），比对时统一成 value 口径，
        # 免得"规则写的是 answer，代码里比的是 BehaviorEventType.ANSWER"这类错位。
        # 认不出的事件名**跳过该触发项并记日志**：一条配错的规则不该让完成记录整页打不开。
        triggers: dict[str, set[BehaviorEventType]] = {}
        wanted: set[BehaviorEventType] = set()
        for rule in rules:
            matched: set[BehaviorEventType] = set()
            for name in rule.trigger_events:
                try:
                    matched.add(BehaviorEventType(name))
                except ValueError:
                    logger.warning(
                        "完成记录规则 %s 引用了不存在的行为事件：%s（已跳过该触发项）",
                        rule.code,
                        name,
                    )
            triggers[rule.code] = matched
            wanted |= matched

        # 一次读够：判断"做到了没"和"什么时候做到的"读的是同一份日志。
        #
        # 为什么不再写 `unlocked_at=now`：那等于每次打开都告诉用户"你刚刚拿到这枚"，
        # 而事实是他可能三周前就做到了 —— 完成记录的可信度全在这种细节上。
        # 只读最近 200 条（限定在这几类触发行为上）：一个用户在这几类行为里积到
        # 200 条以上还不重复，现实中不会出现；真到了那天，该换成仓储层的"首次发生时间"。
        events = await self._behaviors.recent(
            user_id, event_types=sorted(wanted | {BehaviorEventType.TASK_REOPENED}, key=lambda item: item.value), limit=200
        )
        reopened = {}
        for event in events:
            if event.event_type == BehaviorEventType.TASK_REOPENED:
                key = event.payload.get("task_id")
                reopened[key] = max(reopened.get(key, event.occurred_at), event.occurred_at)
        events = [event for event in events if event.event_type != BehaviorEventType.TASK_REOPENED and not (
            event.event_type == BehaviorEventType.TASK_DONE and event.payload.get("task_id") in reopened
            and event.occurred_at <= reopened[event.payload.get("task_id")])]
        first_at: dict[BehaviorEventType, datetime] = {}
        for event in events:
            current = first_at.get(event.event_type)
            if current is None or event.occurred_at < current:
                first_at[event.event_type] = event.occurred_at

        badges: list[Achievement] = []
        for rule in rules:
            times = [first_at[item] for item in triggers[rule.code] if item in first_at]
            unlocked_at = min(times) if times else None
            badges.append(
                Achievement(
                    id=f"ach-{user_id}-{rule.code}",
                    user_id=user_id,
                    badge_key=rule.code,
                    unlocked=unlocked_at is not None,
                    unlocked_at=unlocked_at,
                )
            )
        return badges

    async def list_track_events(self, user_id: str) -> list[TrackEvent]:
        return await self._track_events.list_events(user_id)

    async def record_track_event(
        self, user_id: str, event: str, payload: dict, *, title: str = ""
    ) -> None:
        """落一条时间线记录。

        `title` 由 Facade 从登记表取（人话名字），`detail` 一律留空：
        这条时间线回答的是"这段时间发生过什么"，而一条体验型事件的 payload 是给系统看的
        （`{'has_review': True}`）—— 写进去只会让用户读到 Python 字典的 repr
        （不是 JSON，连引号都是单的）。`event` 仍然参与本方法（供日志/排查），
        但它不再是给用户看的标题。
        """
        logger.debug("埋点落时间线：%s（%s）", event, title or "未登记")
        await self._track_events.append_event(
            user_id,
            TrackEvent(
                id="",  # 由 Repository 生成稳定 id（进程内计数会在重启后重复）
                user_id=user_id,
                type="coach_message",
                title=title or "一条操作记录",
                detail="",
                occurred_at=datetime.now(timezone.utc),
            ),
        )

    async def list_pending_notifications(self, user_id: str) -> list[dict]:
        """取该用户未读的教练通知。

        来源是 `orc_notification` —— 与 `NotifyGateway.push` 的写侧**同一张表**。
        此前读侧是本地进程队列，于是"通知写进库了、前端什么都读不到"：
        写侧和读侧各自活在自己的世界里，而它们本该是同一份数据。
        """
        return await self._notifications.list_pending(user_id)

    async def mark_notification_read(self, user_id: str, message_id: str) -> int:
        """把一条通知标成已读（浮窗关掉时回执）。

        不回执的后果：读侧按"未读"出队，用户关掉的浮窗下次进页面还会再来一遍。
        """
        return await self._notifications.mark_read(user_id, message_id)

    # ---------- 外部情报（学职网自动采集 → 反馈给用户） ----------

    #: 情报缓存：同一个人 15 分钟内不重复打外部站点。
    #: 键是 user_id —— 情报跟着他的专业与方向走，这两个变了会由事件失效。
    INTEL_TTL_S = 900

    async def fetch_external_intel(
        self,
        user_id: Optional[str] = None,
        *,
        topic: str = "",
        limit: int = 12,
        refresh: bool = False,
        allow_fetch: bool = True,
    ) -> list[ExternalIntel]:
        """去公开渠道取回外部情报。**不要求登录**。

        两个入口共用它：
          · 给了 `user_id` → 按这个人的专业与方向取（个性化）；
          · 没给（未登录 / 公开页）→ 按 `topic` 取，没有 topic 就取平台通用公开数据。

        登录在这里只影响**收窄范围**，不影响"能不能取" ——
        情报是爬公开数据的，信息源非常广，不可能每个网站都登一次。

        缓存是进程内的短缓存（15 分钟）：这条链路会打外部站点，
        每开一次界面就打一遍既不礼貌也没必要。
        """
        # 缓存键带上"当前方向方案 id"：用户选/换方向后必须拿新结果，
        # 不能因为 topic 为空就命中上一个方向的旧缓存（15 分钟）。
        direction_name, direction_id = await self._direction_basis(user_id)
        status_key = (user_id, topic.strip(), direction_id or "")
        cache_key = (*status_key, limit)
        cached = self._intel_cache.get(cache_key)
        if not refresh and cached and cached[0] > time.monotonic():
            return cached[1]
        if not allow_fetch:
            # 只读缓存：没命中就不取。见 Port 上的说明（采集 / 复盘走这条）。
            return []

        previous = cached[1] if cached else []
        failure = ""
        try:
            items, failure = await self._collect_intel(user_id, topic=topic, limit=limit)
        except Exception:  # noqa: BLE001 - 上游整体失败不该把面板打成 500
            logger.warning("外部情报取数失败（user=%s, topic=%s）", user_id, topic, exc_info=True)
            failure = "检索服务这次没有响应"
            items = []
        self._intel_cache[cache_key] = (time.monotonic() + self.INTEL_TTL_S, items)
        await self._record_intel_status(user_id, status_key, topic=topic, items=items, failure=failure)

        # 只在**真的有新东西**、而且**知道是谁**的时候推通知。
        # 前一条是防"每 45 秒打扰一次"；后一条是因为未登录时根本没有收件人。
        fresh = {item.id for item in items} - {item.id for item in previous}
        if fresh and user_id:
            await self._announce_intel(user_id, items)
        return items

    async def _record_intel_status(
        self,
        user_id: Optional[str],
        cache_key: tuple[str | None, str, str],
        *,
        topic: str,
        items: list[ExternalIntel],
        failure: str = "",
    ) -> None:
        """把这次取数归成三类之一，附一句用户能行动的话。

        - `ok`：取到了条目；
        - `empty`：链路正常，但确实没有匹配资料（"换个关键词/先补专业"就是可行动的话）；
        - `failed`：上游/检索失败（"稍后重试"才是可行动的话）。
        """
        major = await self.profile_major(user_id) if user_id else ""
        if items:
            status, message = "ok", f"已取到 {len(items)} 条公开资料。"
            if failure:
                message += "部分来源暂时不可用，可稍后重试。"
        elif failure:
            status, message = (
                "failed",
                f"{failure}，这次没有取到资料 —— 可以稍后重试。",
            )
        else:
            status, message = "empty", "没有找到匹配的公开资料，可以换个关键词或先补充专业信息后再试。"
        self._intel_status[cache_key] = {
            "status": status,
            "degraded": bool(failure),
            "message": message,
            "items": len(items),
            "topic": topic,
            "major": major,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    async def intel_fetch_status(self, user_id: Optional[str] = None, *, topic: str = "") -> dict[str, Any]:
        """最近一次外部情报取数的状态（供 API/前端显示"重试"而不是把失败当 0 条）。

        返回 `status`（ok/empty/failed/unknown）、`message`（给学生的下一步）、
        `major`（画像里已记录的专业，供"专业起点"判断）以及条数/时间。
        """
        _, direction_id = await self._direction_basis(user_id)
        cache_key = (user_id, topic.strip(), direction_id or "")
        known = self._intel_status.get(cache_key)
        if known is not None:
            return dict(known)
        major = await self.profile_major(user_id) if user_id else ""
        return {
            "status": "unknown",
            "message": "还没有取过外部资料。",
            "items": 0,
            "topic": topic,
            "major": major,
            "fetched_at": "",
        }

    async def profile_major(self, user_id: Optional[str]) -> str:
        """画像里**已记录的专业**（"专业起点"的唯一依据）。

        为什么单独给一个方法：前端原来只看取回的情报里有没有 `speciality` 条目，
        上游一旦失败/为空就显示"专业信息待补充" —— 可画像里明明有专业。
        专业是否已记录，不该由"这次取数成不成功"决定。
        """
        if not user_id or self._profiles is None:
            return ""
        try:
            rows = await self._profiles.get_fields(user_id)
        except Exception:  # noqa: BLE001 - 读不到就当没有，不让面板因此报错
            logger.warning("读取画像字段失败：专业起点按未知处理", exc_info=True)
            return ""
        return intel_topic(rows)

    async def _direction_basis(self, user_id: Optional[str]) -> tuple[str, str]:
        """当前方向方案（已选优先、否则主攻）作为探索依据；没有就返回空。

        职业探索此前只读画像（major/target_direction），完全不知道
        `direction_plan` 里用户已经选/已经生成的方向 —— 于是方向页说"后端开发"，
        探索页却按专业返回"游戏开发/移动端"，看起来像两个功能各说各的。
        """
        if not user_id or self._assets is None:
            return "", ""
        try:
            plans = await self._assets.list_direction_plans(user_id)
        except Exception:  # noqa: BLE001 - 方向读不到不应让探索整页失败
            logger.warning("读取方向方案失败：探索退回画像依据", exc_info=True)
            return "", ""
        if not plans:
            return "", ""
        selected = next((plan for plan in plans if plan.selected), None)
        main = next(
            (
                plan
                for plan in plans
                if str(getattr(plan.role, "value", plan.role)) == "main"
            ),
            None,
        )
        plan = selected or main
        return (plan.name, plan.id) if plan else ("", "")

    async def intel_basis(self, user_id: Optional[str]) -> tuple[str, str]:
        """探索依据：`("后端开发工程师", "direction")` 或 `("软件工程", "profile")`。

        空串是合法结果：既没有方向也没有专业，界面应引导补资料，而不是假装
        已经按某个方向探索过。
        """
        direction_name, _ = await self._direction_basis(user_id)
        if direction_name:
            return direction_name, "direction"
        major = await self.profile_major(user_id)
        return (major, "profile") if major else ("", "")

    async def _collect_intel(
        self, user_id: Optional[str], *, topic: str, limit: int
    ) -> tuple[list[ExternalIntel], str]:
        context: list[dict[str, Any]] = []
        rows: list[Any] = []
        if user_id and self._profiles is not None:
            # 用 `get_fields` 而不是 `get`：情报只关心**有哪些字段**。
            # 读整份 Profile 会多一次聚合，而且画像行与字段行不一致时（迁移、
            # 手工补数之后偶发）会静默拿到空表 —— 表现就是"明明有画像却说没有相关情报"。
            rows = await self._profiles.get_fields(user_id)
            context = [
                {"key": f.key, "value": f.value, "confidence": f.confidence}
                for f in rows
            ]

        # 方向方案是比画像 major 更近的一层依据：把它作为 target_direction
        # 交给学职取数（取数侧会按 job_terms 查职业），这样探索页的结果才会
        # 跟方向页正在考虑/已选的方向对得上。
        direction_name, _ = await self._direction_basis(user_id)
        if direction_name:
            context.append(
                {"key": "target_direction", "value": direction_name, "confidence": 1.0}
            )

        # 主题没给就**从事画像/方向推**。
        #
        # 这一行是"面板里那一批"和"主理引用的那一批"必须是同一批的关键：
        # 编排器喂给模型时用的也是这条规则（`intel_topic`），两处同一个主题，
        # 才会命中同一个缓存桶、取回同一批数据。
        #
        # 推不出来（没有画像字段）就**留空**：空的含义是"还不知道该查什么"，
        # 取数侧会退回平台通用公开数据 —— 比拿一句猜出来的话去搜要诚实。
        if not topic.strip():
            topic = direction_name or intel_topic(rows)

        items: list[ExternalIntel] = []
        failure = ""
        if self._data_sources is not None and (context or topic.strip()):
            try:
                result = await self._data_sources.fetch(
                    DataSourceRequest(
                        source="xuezhi",
                        query=topic.strip(),
                        limit=limit,
                        context={"fields": context, "topic": topic.strip()},
                    )
                )
            except Exception:  # noqa: BLE001 - 学职平台一路失败，仍可保留网络检索那一路
                logger.warning("学职平台取数失败（topic=%s）", topic, exc_info=True)
                failure = "检索服务这次没有响应"
                result = None
            if result is not None:
                if result.degraded or result.errors:
                    failure = "部分检索来源暂时不可用"
                items.extend(
                    ExternalIntel(
                        id=record.id,
                        kind=record.kind,
                        kind_label=kind_label(record.kind),
                        title=record.title,
                        text=record.text,
                        source_url=record.source_url,
                        source_name=source_name_of(record.source_url, source=result.source),
                        fetched_at=record.fetched_at,
                        relation=str(record.metadata.get("relation") or ""),
                    )
                    for record in result.records
                    if record.source_url and (record.title or record.text)
                )

        # 通用网络检索：配了搜索服务就一并取 —— 这才是"信息源很广"的落点。
        # 没配就没有这一路，界面上也不会出现"正在联网搜索"这种没发生的事。
        if self._web_search is not None and topic.strip():
            try:
                items.extend(await self._web_intel(topic.strip(), limit=limit))
            except Exception:  # noqa: BLE001 - 保留其他来源已取得的结果
                logger.warning("通用网络检索失败（topic=%s）", topic, exc_info=True)
                failure = "部分检索来源暂时不可用"

        return items[: max(limit, 1) * 2], failure

    async def _web_intel(self, topic: str, *, limit: int) -> list[ExternalIntel]:
        """通用网络检索；异常由调用方记录为降级，保留其他来源结果。"""
        hits = await self._web_search.search(topic, count=min(limit, 8))
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return [
            ExternalIntel(
                id=f"web:{abs(hash(hit.url)) % 10**12}",
                kind="web",
                kind_label=kind_label("web"),
                title=hit.title,
                text=hit.snippet,
                source_url=hit.url,
                source_name=source_name_of(hit.url, source="web"),
                fetched_at=stamp,
            )
            for hit in hits
            if hit.url
        ]

    #: 同一批情报的提醒冷却时间（秒）。12 小时内内容没变就不再推。
    INTEL_ANNOUNCE_COOLDOWN_S = 12 * 3600

    async def _announce_intel(self, user_id: str, items: list[ExternalIntel]) -> None:
        """把取到的东西推成一条站内通知（前端浮窗读的就是它）。"""
        if self._notifier is None:
            return
        fingerprint = "|".join(sorted(item.id or item.title or "" for item in items))
        last = self._last_intel_announce.get(user_id)
        if last and last[1] == fingerprint and time.monotonic() < last[0]:
            logger.info("情报内容与上次相同，12 小时内不重复推送（user=%s）", user_id)
            return
        top = items[0]
        head = top.title or (top.text[:40] if top.text else "外部情报")
        source = top.source_name or "公开渠道"
        basis, _ = await self.intel_basis(user_id)
        scope = f"与你关注的「{basis}」相关" if basis else "与你当前资料相关"
        title = f"给你找到 {len(items)} 条{scope}的公开信息"
        # 进程内冷却重启即失效；再查一次最近通知，重启后也不会把同一批
        # 情报重复推给用户（通知历史本身就是去重账本）。
        if await self._recent_intel_announced(user_id, title, head):
            logger.info("情报内容与最近通知相同，12 小时内不重复推送（user=%s）", user_id)
            return
        try:
            await self._notifier.push(
                user_id,
                title=title,
                body=f"{head} —— 这些来自{source}，都能点回原页面核对。",
                channel=NotifyChannel.IN_APP,
                action={"kind": "intel", "label": "看看是什么"},
            )
            self._last_intel_announce[user_id] = (
                time.monotonic() + self.INTEL_ANNOUNCE_COOLDOWN_S,
                fingerprint,
            )
        except Exception:  # noqa: BLE001 - 通知推不出去不该让取数失败
            logger.warning("外部情报通知推送失败（user=%s）", user_id, exc_info=True)

    async def _recent_intel_announced(self, user_id: str, title: str, head: str) -> bool:
        """从通知历史判断同一批情报是否已在冷却期内推过。"""
        if self._notifications is None:
            return False
        try:
            history = await self._notifications.list_all(user_id)
        except Exception:  # noqa: BLE001 - 历史读不到就退回进程内冷却
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.INTEL_ANNOUNCE_COOLDOWN_S)
        for note in history[:30]:
            if str(note.get("title") or "") != title:
                continue
            if head not in str(note.get("body") or ""):
                continue
            stamp = note.get("occurred_at") or note.get("created_at")
            try:
                when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff:
                return True
        return False

    def drop_intel_cache(self, user_id: str) -> None:
        """画像变了就丢掉这个人的情报缓存（下一次读会重新取）。

        结构化键按账号精确匹配，同时清理旧状态，避免账号分隔符碰撞或残留旧画像依据。
        """
        for key in [k for k in self._intel_cache if k[0] == user_id]:
            self._intel_cache.pop(key, None)
        for key in [k for k in self._intel_status if k[0] == user_id]:
            self._intel_status.pop(key, None)

__all__ = ["DefaultFunctionService"]
