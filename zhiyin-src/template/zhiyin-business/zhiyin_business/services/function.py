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
from datetime import datetime, timezone
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
        self._intel_cache: dict[str, tuple[float, list[ExternalIntel]]] = {}
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
            user_id, event_types=sorted(wanted, key=lambda item: item.value), limit=200
        )
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

    async def record_track_event(self, user_id: str, event: str, payload: dict) -> None:
        await self._track_events.append_event(
            user_id,
            TrackEvent(
                id="",  # 由 Repository 生成稳定 id（进程内计数会在重启后重复）
                user_id=user_id,
                type="coach_message",
                title=event,
                detail=str(payload) if payload else "",
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
        cache_key = f"{user_id or '-'}|{topic.strip()}"
        cached = self._intel_cache.get(cache_key)
        if not refresh and cached and cached[0] > time.monotonic():
            return cached[1]
        if not allow_fetch:
            # 只读缓存：没命中就不取。见 Port 上的说明（采集 / 复盘走这条）。
            return []

        previous = cached[1] if cached else []
        items = await self._collect_intel(user_id, topic=topic, limit=limit)
        self._intel_cache[cache_key] = (time.monotonic() + self.INTEL_TTL_S, items)

        # 只在**真的有新东西**、而且**知道是谁**的时候推通知。
        # 前一条是防"每 45 秒打扰一次"；后一条是因为未登录时根本没有收件人。
        fresh = {item.id for item in items} - {item.id for item in previous}
        if fresh and user_id:
            await self._announce_intel(user_id, items)
        return items

    async def _collect_intel(
        self, user_id: Optional[str], *, topic: str, limit: int
    ) -> list[ExternalIntel]:
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

        # 主题没给就**从事画像推**。
        #
        # 这一行是"面板里那一批"和"主理引用的那一批"必须是同一批的关键：
        # 编排器喂给模型时用的也是这条规则（`intel_topic`），两处同一个主题，
        # 才会命中同一个缓存桶、取回同一批数据。
        #
        # 推不出来（没有画像字段）就**留空**：空的含义是"还不知道该查什么"，
        # 取数侧会退回平台通用公开数据 —— 比拿一句猜出来的话去搜要诚实。
        if not topic.strip():
            topic = intel_topic(rows)

        items: list[ExternalIntel] = []
        if self._data_sources is not None and (context or topic.strip()):
            result = await self._data_sources.fetch(
                DataSourceRequest(
                    source="xuezhi",
                    query=topic.strip(),
                    limit=limit,
                    context={"fields": context, "topic": topic.strip()},
                )
            )
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
                )
                for record in result.records
                if record.source_url and (record.title or record.text)
            )

        # 通用网络检索：配了搜索服务就一并取 —— 这才是"信息源很广"的落点。
        # 没配就没有这一路，界面上也不会出现"正在联网搜索"这种没发生的事。
        if self._web_search is not None and topic.strip():
            items.extend(await self._web_intel(topic.strip(), limit=limit))

        return items[: max(limit, 1) * 2]

    async def _web_intel(self, topic: str, *, limit: int) -> list[ExternalIntel]:
        """通用网络检索那一路。取不到就返回空表，不编。"""
        try:
            hits = await self._web_search.search(topic, count=min(limit, 8))
        except Exception:  # noqa: BLE001 - 一路取不到不该让整次取数失败
            logger.warning("通用网络检索失败（topic=%s）", topic, exc_info=True)
            return []
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

    async def _announce_intel(self, user_id: str, items: list[ExternalIntel]) -> None:
        """把取到的东西推成一条站内通知（前端浮窗读的就是它）。"""
        if self._notifier is None:
            return
        top = items[0]
        head = top.title or (top.text[:40] if top.text else "外部情报")
        source = top.source_name or "公开渠道"
        try:
            await self._notifier.push(
                user_id,
                title=f"给你找到 {len(items)} 条与你方向相关的公开信息",
                body=f"{head} —— 这些来自{source}，都能点回原页面核对。",
                channel=NotifyChannel.IN_APP,
                action={"kind": "intel", "label": "看看是什么"},
            )
        except Exception:  # noqa: BLE001 - 通知推不出去不该让取数失败
            logger.warning("外部情报通知推送失败（user=%s）", user_id, exc_info=True)

    def drop_intel_cache(self, user_id: str) -> None:
        """画像变了就丢掉这个人的情报缓存（下一次读会重新取）。

        缓存键是 `f"{user_id}|{topic}"`，所以**按前缀清**。
        这里原来写的是 `pop(user_id)` —— 那个键根本不存在，等于这个方法什么都没做：
        用户补了专业之后，9 分钟之内看到的仍然是按旧主题取回的那一批。
        症状很难查（"我明明填了专业，情报还是不对"），因为缓存命中本身是静默的。
        """
        prefix = f"{user_id}|"
        for key in [k for k in self._intel_cache if k.startswith(prefix)]:
            self._intel_cache.pop(key, None)

__all__ = ["DefaultFunctionService"]
