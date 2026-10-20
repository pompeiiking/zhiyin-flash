"""画像服务实现。"""

from __future__ import annotations

from zhiyin_business.services.unit_of_work import atomic_repository

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import uuid4

from zhiyin_business.events import PROFILE_FIELD_UPDATED
from zhiyin_business.policies.collection import field_labels
from zhiyin_business.ports.blackboard import ProfileService
from zhiyin_data_sdk.repositories import ProfileRepository
from zhiyin_kernel import dynamic_config
from zhiyin_kernel import profile_taxonomy
from zhiyin_kernel.blackboard import (
    Profile,
    ProfileClue,
    ProfileField,
    ProfileFieldRevision,
    ProfileGap,
)
from zhiyin_kernel.enums import (
    ProfileClueStatus,
    ProfileEntryStatus,
    ProfileSource,
    ProfileVerification,
)
from zhiyin_kernel.errors import DuplicateResource, InvalidRequest, ResourceNotFound
from zhiyin_orchestration import DomainEvent, EventBus

logger = logging.getLogger(__name__)

#: 两个标签页改同一格时的冲突文案。
#:
#: 为什么不用仓储层原话：那句话说"这项画像已更新"，指的是整份画像；
#: 而用户此刻改的是**一个字段**，界面上也只有那一格 —— 按字段说、并告诉他下一步
#: 做什么（核对最新值再保存），比"画像已更新"更容易对上他自己看到的东西。
PROFILE_FIELD_CONFLICT_MESSAGE = "这个字段已在其他页面更新，请核对最新值后再保存"

#: 兼容常量：短事实（专业 / 学校 / 年级）仍按 40 字，但**不再是所有记录的统一上限**。
#:
#: 《个人画像设计-2026-10-20》第 4 节：不继续用统一的 40 字短字符串承载所有记录。
#: 各内容类别分别限制条数、文本长度、结构深度与来源大小 —— 具体口径在
#: `zhiyin_kernel.profile_taxonomy`（键优先、类别兜底），这里只保留这个常量给
#: 既有调用方与测试引用，避免它们被迫跟着改一遍。
MAX_FIELD_VALUE_CHARS = 40

#: 线索失效原因：给用户看的一句话，说明「这条理解为啥不算数了」。
#: 设计第 7 节：用户更正/删除后，相关理解要标记待核对，不能继续当结论用。
PROFILE_CLUE_INVALIDATED_BY_CORRECTION = "本人更正了这条理解所依据的画像信息"
PROFILE_CLUE_INVALIDATED_BY_DELETION = "本人删除了这条理解所依据的画像信息"
PROFILE_CLUE_DENIED_REASON = "本人否认了这条理解"


class DefaultProfileService(ProfileService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, profiles: ProfileRepository, event_bus: EventBus) -> None:
        self._profiles = profiles
        self._event_bus = event_bus

    async def get(self, user_id: str) -> Optional[Profile]:
        return await self._profiles.get(user_id)

    async def get_fields(
        self, user_id: str, keys: Optional[Sequence[str]] = None
    ) -> list[ProfileField]:
        return await self._profiles.list_fields(user_id, keys)

    async def get_gaps(self, user_id: str) -> list[ProfileGap]:
        return await self._profiles.list_gaps(user_id)

    # ---------- 待验证线索（《个人画像设计-2026-10-20》第 3.2、7、9 节） ----------

    async def get_clues(self, user_id: str) -> list[ProfileClue]:
        """读取待验证线索。

        与 `get_fields` 分开是因为它们回答的是两个问题：字段答"他提供了什么"，
        线索答"系统理解为可能怎样" —— 后者必须能单独展示、单独否认。
        """
        return await self._profiles.list_clues(user_id)

    async def replace_session_clues(
        self, user_id: str, session_id: str, clues: list[ProfileClue]
    ) -> list[ProfileClue]:
        """按会话整体替换线索，返回落库后的那一批。

        同一 session 是**整体替换**，不是追加：重复跑一次分析不该让同一句理解
        出现两次 —— 那看起来像「被反复验证过」，而设计第 3.2 节明确禁止用重复
        次数把推测变成结论。

        标识由服务端定：只有「本来就属于这个会话」的 id 才会被沿用（否认、重排
        这类操作要靠它定位）；外面带进来的 id 一律重新生成，避免一条线索被另一次
        写入顶掉或跨账号串用。
        """
        if not user_id:
            raise InvalidRequest("缺少账号，无法写线索。")
        current = await self._profiles.list_clues(user_id)
        existing = {item.id: item for item in current if item.session_id == session_id}
        now = datetime.now(timezone.utc)
        used: set[str] = set()
        stored: list[ProfileClue] = []
        for clue in clues:
            clue_id = clue.id if clue.id in existing else f"clue_{uuid4().hex[:12]}"
            while clue_id in used:
                clue_id = f"clue_{uuid4().hex[:12]}"
            used.add(clue_id)
            stored.append(
                clue.model_copy(
                    update={
                        "id": clue_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "created_at": existing[clue_id].created_at
                        if clue_id in existing
                        else clue.created_at,
                        "updated_at": now,
                    }
                )
            )
        await self._profiles.replace_session_clues(user_id, session_id, stored)
        return stored

    async def deny_clue(self, user_id: str, clue_id: str) -> ProfileClue:
        """用户否认一条「系统理解」（设计第 9 节）。

        否认不等于删除字段：字段是他说过的事实，线索是系统的推测 —— 他否认的是
        后者。失效的线索保留在原位（带原因），这样同类理解不会被悄悄重新提出，
        界面上也能如实说「你否认过这条」。

        `user_id` 必须参与定位：只按 clue_id 查会让任何知道 id 的人都能否认
        别人的画像（验收 P23 的账号隔离）。
        """
        target_id = (clue_id or "").strip()
        if not target_id:
            raise InvalidRequest("缺少要否认的那条理解。")
        clues = await self._profiles.list_clues(user_id)
        target = next((item for item in clues if item.id == target_id), None)
        if target is None:
            raise ResourceNotFound("这条理解已经不在了，刷新后再看。")
        if target.status is ProfileClueStatus.INVALID:
            # 幂等：重复否认不报错，也不改写第一次的原因。
            return target
        denied = target.model_copy(
            update={
                "status": ProfileClueStatus.INVALID,
                "invalidated_reason": PROFILE_CLUE_DENIED_REASON,
            }
        )
        session_clues = [
            denied if item.id == target.id else item
            for item in clues
            if item.session_id == target.session_id
        ]
        saved = await self.replace_session_clues(user_id, target.session_id, session_clues)
        return next(item for item in saved if item.id == target.id)

    async def _invalidate_clues_for(
        self, user_id: str, keys: list[str], reason: str
    ) -> None:
        """依据这些字段的线索标记失效；失败只记日志，不阻断主写入。

        为什么不能抛：字段已经写进去了（或删掉了），此时报错只会让用户看到
        「没改成」而库里其实已经是新状态 —— 那是最难查的一类错。线索收尾失败
        进日志，下一次依赖变化的重新分析仍会把它带出来。
        """
        try:
            await self._profiles.invalidate_clues(user_id, list(keys), reason)
        except Exception:  # noqa: BLE001 - 收尾失败不影响主写入
            logger.warning(
                "画像已写入，但相关待验证线索没失效（user=%s keys=%s）",
                user_id,
                keys,
                exc_info=True,
            )

    @atomic_repository("_profiles")
    async def update_field(
        self,
        user_id: str,
        key: str,
        value: object,
        *,
        confidence: float,
        source: str,
        label: str = "",
        evidence: Optional[list[str]] = None,
        expected_updated_at: datetime | None = None,
        check_version: bool = False,
        attributes: dict[str, object] | None = None,
        verification: str | None = None,
        origin_ref: str = "",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        event_at: datetime | None = None,
        status: str | None = None,
    ) -> ProfileField:
        """写入一条画像记录（所有来源共用的唯一写入口）。

        写入方只提供「键、整理后的内容、来源与依据」；类别、取值形状、核实状态
        与有效范围由服务端按受控词表校验后固化 —— 模型不能自己声明一个类别或
        一个 `allowed=true` 绕过权限。

        第 4 节的语义契约在这里落地：
        - 类别来自键的受控映射（`profile_taxonomy.entry_type_of`），不采信调用方自报；
        - 不同类型的取值形状与上限不同（兴趣可以是多条，经历正文可长）；
        - 三者分开：何时知道（`updated_at`）、何时发生（`event_at`）、何时仍适用
          （`valid_from` / `valid_to`）；未知时间不补成当前时间；
        - 同一条记录每次写入版本 +1，供并发更新与「我看到的是哪一版」使用。
        """
        source_value = ProfileSource(source)
        entry_type = profile_taxonomy.entry_type_of(key)
        normalized = profile_taxonomy.normalize_value(key, value, entry_type)
        normalized_attributes = profile_taxonomy.normalize_attributes(entry_type, attributes)
        profile_taxonomy.validate_window(valid_from, valid_to)
        try:
            verification_value = (
                ProfileVerification(verification)
                if verification
                else profile_taxonomy.verification_for(source_value)
            )
        except ValueError as exc:
            raise InvalidRequest("核实状态无效。") from exc
        try:
            status_value = ProfileEntryStatus(status) if status else ProfileEntryStatus.ACTIVE
        except ValueError as exc:
            raise InvalidRequest("记录状态无效。") from exc

        # 这是**新出现**的一类信息吗？
        #
        # 为什么要在这里判：影响面的判据是"资产声明的依赖字段 ∩ 变更字段"，
        # 而依赖清单是资产**生成那一刻**记下的。一个刚出现的字段不可能在那份清单里
        # （实测：报告生成后才导入的课表，改了它，报告不会被标成"待重算"），
        # 于是"画像里多了一整类信息"这件事对已有结论完全不可见。
        # 交给下游的判据只能是"这个字段对谁都是新的"，所以得在写画像的地方算出来 ——
        # 只有这里知道画像在写之前长什么样。
        try:
            existing = await self._profiles.list_fields(user_id)
        except Exception:  # noqa: BLE001 - 读旧画像失败不该让这次写入失败
            logger.warning("读取既有画像失败，新字段判定按否处理", exc_info=True)
            existing = []
        known = {item.key for item in existing}
        is_new = not existing or key not in known
        before = next((item for item in existing if item.key == key), None)
        field = ProfileField(
            key=key,
            label=label,
            value=normalized,
            confidence=confidence,
            source=source_value,
            evidence=evidence or [],
            updated_at=datetime.now(timezone.utc),
            entry_type=entry_type,
            attributes=normalized_attributes,
            verification=verification_value,
            status=status_value,
            origin_ref=origin_ref.strip()[:2000],
            valid_from=valid_from,
            valid_to=valid_to,
            event_at=event_at,
            entry_version=(before.entry_version if before else 1)
            + (1 if before else 0),
            superseded_by=before.superseded_by if before else "",
        )
        saved = await self._profiles.upsert_field(user_id, field, expected_updated_at=expected_updated_at, check_version=True) if check_version else await self._profiles.upsert_field(user_id, field)
        if before is not None and (
            before.value != normalized or dict(before.attributes or {}) != normalized_attributes
        ):
            # 旧值进历史（设计第 7 节）：当前值仍是一行一键的兼容投影，
            # 历史只追加，不参与用途读取。
            await self._append_history(
                user_id, before, status=ProfileEntryStatus.SUPERSEDED,
                replaced_at=saved.updated_at, reason="被后续版本替代",
            )
        await self._event_bus.publish(
            DomainEvent(
                event_id=f"profile-{uuid4().hex[:12]}",
                event_type=PROFILE_FIELD_UPDATED,
                occurred_at=saved.updated_at,
                payload={
                    "user_id": user_id,
                    "field_key": key,
                    "entry_type": entry_type.value,
                    "is_new": is_new,
                    "confidence": confidence,
                    "source": saved.source.value,
                    "verification": verification_value.value,
                    "status": status_value.value,
                },
            )
        )
        return saved

    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        await self._profiles.replace_gaps(user_id, gaps)

    @atomic_repository("_profiles")
    async def drop_field(self, user_id: str, key: str, *, expected_updated_at: datetime | None = None, check_version: bool = False) -> None:
        """删掉一个画像字段（撤销授权时用）。

        删完把依据这一格的待验证线索一起标记失效（设计第 7 节）：依据没了，
        建立在其上的理解不能继续当有效结论展示。
        """
        before = next((item for item in await self._profiles.list_fields(user_id, [key])), None)
        if check_version:
            await self._profiles.delete_field(user_id, key, expected_updated_at=expected_updated_at, check_version=True)
        else:
            await self._profiles.delete_field(user_id, key)
        if before is not None:
            await self._append_history(
                user_id, before, status=ProfileEntryStatus.WITHDRAWN,
                replaced_at=datetime.now(timezone.utc), reason="本人删除了这条画像信息",
            )
        await self._event_bus.publish(DomainEvent(event_id=f"profile-{uuid4().hex[:12]}",
            event_type=PROFILE_FIELD_UPDATED, occurred_at=datetime.now(timezone.utc),
            payload={"user_id": user_id, "field_key": key, "deleted": True, "is_new": False}))
        await self._invalidate_clues_for(user_id, [key], PROFILE_CLUE_INVALIDATED_BY_DELETION)

    # ---------- 历史版本与冲突裁定（设计第 4、7 节） ----------

    async def _append_history(
        self,
        user_id: str,
        before: ProfileField,
        *,
        status: ProfileEntryStatus,
        replaced_at: datetime,
        reason: str,
    ) -> None:
        """把一版旧记录追加进历史；历史是旁路，写失败只记日志，不阻断主写入。"""
        revision = ProfileFieldRevision(
            id="",
            user_id=user_id,
            key=before.key,
            label=before.label,
            value=before.value,
            attributes=dict(before.attributes or {}),
            confidence=before.confidence,
            source=before.source,
            verification=before.verification,
            status=status,
            evidence=list(before.evidence),
            origin_ref=before.origin_ref,
            valid_from=before.valid_from,
            valid_to=before.valid_to,
            event_at=before.event_at,
            entry_version=before.entry_version,
            created_at=before.updated_at,
            replaced_at=replaced_at,
            change_reason=reason,
        )
        try:
            await self._profiles.append_revision(user_id, revision)
        except Exception:  # noqa: BLE001 - 历史写失败不该让当前值写不进去
            logger.warning("画像历史版本写入失败（user=%s key=%s）", user_id, before.key, exc_info=True)

    async def list_revisions(
        self, user_id: str, key: str | None = None, *, status: list[str] | None = None
    ) -> list[ProfileFieldRevision]:
        """读取历史版本；冲突提案用 `status=["conflict"]` 单独取。"""
        return await self._profiles.list_revisions(user_id, key, status=status)

    async def list_conflicts(self, user_id: str) -> list[ProfileFieldRevision]:
        """当前等待用户裁定的冲突提案（不参与用途读取）。"""
        return await self._profiles.list_revisions(user_id, status=["conflict"])

    @atomic_repository("_profiles")
    async def record_conflict(
        self,
        user_id: str,
        key: str,
        value: object,
        *,
        confidence: float = 0.8,
        source: str = ProfileSource.CONVERSATION.value,
        label: str = "",
        evidence: Optional[list[str]] = None,
        attributes: dict[str, object] | None = None,
        origin_ref: str = "",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        event_at: datetime | None = None,
    ) -> ProfileFieldRevision:
        """把「与当前记录不一致的新说法」追加为冲突提案，**不覆盖当前值**。

        设计第 7 节：不能明确区分修正与冲突时并存标记，只有影响当前服务时才澄清。
        当前值继续作为兼容投影供旧 API 读取；冲突提案单独等待用户裁定。
        """
        entry_type = profile_taxonomy.entry_type_of(key)
        normalized = profile_taxonomy.normalize_value(key, value, entry_type)
        normalized_attributes = profile_taxonomy.normalize_attributes(entry_type, attributes)
        profile_taxonomy.validate_window(valid_from, valid_to)
        source_value = ProfileSource(source)
        current = next((item for item in await self._profiles.list_fields(user_id, [key])), None)
        revision = ProfileFieldRevision(
            id="",
            user_id=user_id,
            key=key,
            label=label or (current.label if current else ""),
            value=normalized,
            attributes=normalized_attributes,
            confidence=confidence,
            source=source_value,
            verification=profile_taxonomy.verification_for(source_value),
            status=ProfileEntryStatus.CONFLICT,
            evidence=evidence or [],
            origin_ref=origin_ref.strip()[:2000],
            valid_from=valid_from,
            valid_to=valid_to,
            event_at=event_at,
            entry_version=(current.entry_version if current else 1) + (1 if current else 0),
            created_at=datetime.now(timezone.utc),
            replaced_at=None,
            change_reason="与当前记录不一致，等待核对",
        )
        return await self._profiles.append_revision(user_id, revision)

    @atomic_repository("_profiles")
    async def resolve_conflict(
        self, user_id: str, revision_id: str, *, choice: str
    ) -> ProfileFieldRevision:
        """用户裁定一条冲突：`revision`=以新说法为准，`current`=保留当前记录。"""
        if choice not in {"revision", "current"}:
            raise InvalidRequest("请选择以哪一版为准。")
        conflicts = await self._profiles.list_revisions(user_id, status=["conflict"])
        target = next((item for item in conflicts if item.id == revision_id), None)
        if target is None:
            raise ResourceNotFound("这条待核对的说法已经不在了，刷新后再看。")
        if choice == "revision":
            await self.update_field(
                user_id,
                target.key,
                target.value,
                confidence=target.confidence,
                source=ProfileSource.USER_EDIT.value,
                label=target.label,
                evidence=list(target.evidence),
                attributes=dict(target.attributes),
                verification=ProfileVerification.USER_CONFIRMED.value,
                origin_ref=target.origin_ref,
                valid_from=target.valid_from,
                valid_to=target.valid_to,
                event_at=target.event_at,
            )
            status, reason = ProfileEntryStatus.SUPERSEDED, "本人选择以此版本为准"
            await self._invalidate_clues_for(user_id, [target.key], PROFILE_CLUE_INVALIDATED_BY_CORRECTION)
        else:
            status, reason = ProfileEntryStatus.WITHDRAWN, "本人选择保留当前记录"
        await self._profiles.update_revision_status(
            user_id,
            target.id,
            status=status.value,
            replaced_at=datetime.now(timezone.utc),
            change_reason=reason,
        )
        return target.model_copy(
            update={"status": status, "replaced_at": datetime.now(timezone.utc), "change_reason": reason}
        )

    def _registered_fields(self) -> dict[str, str]:
        """登记过的画像字段：键 → 中文名。

        两份登记表合起来看，因为它们各自漏一半：
          · 采集规则表（`collection_rules.json`）说"这一条从哪来、为什么现在要它"，
            内置兜底表让它在配置没装载时也非空；
          · 画像字段词表（文案包里的 `profile.field.*`，与写侧门禁同一份）多认了
            学信网带回来的姓名 / 院系这类字段 —— 它们不在采集动线里，但确实是
            画像里的一格，用户改它不该被拒。

        **不做专业名合法性校验**：专业名有几百个（含每年新增、学校自定义的方向名），
        任何白名单都会把真专业挡在外面 —— 那正是这个 issue 要修的那类错。
        这里只回答"画像里有没有这一格"。
        """
        labels = field_labels(list(dynamic_config.snapshot().collection_rules) or None)
        for spec in dynamic_config.snapshot().profile_fields:
            # 同义词（alias_of）不是画像里的格子：模型写的 `grade` 会归到
            # `study_year`，用户这边也只认规范键，否则同一个意思会另起一格。
            if spec.alias_of:
                continue
            labels.setdefault(spec.key, spec.label or spec.key)
        return labels

    @atomic_repository("_profiles")
    async def correct_field(self, user_id: str, key: str, value: object, *, expected_updated_at: datetime | None = None, check_version: bool = False) -> ProfileField:
        """用户本人更正一个画像字段（issue #26 第三条）。

        为什么这条路径必须存在
        ----------------------
        此前画像只有"系统去记"的写路径（采集 / 学信网 / 教务导入）。用户发现记错了
        —— 他说的是"计算机大类"，系统却把它当成"计算机科学与技术"记了下来 ——
        界面上只能看、一个字也改不了。他能做的只有再跟对话说一遍，而那句话又进了
        同一台推断机，出来的仍然是一条替他挑好的具体专业。于是那条错值永远留在画像里，
        后面每一份报告、每一个方向推荐都按它算。

        所以这里补的是**他自己写的**那一条：来源记成 `user_edit`，
        界面上说「本人填写」，而不是混进"对话 / 学信网"里没人分得出来。
        """
        key = (key or "").strip()
        labels = self._registered_fields()
        if key not in labels:
            # 不在登记表里的键不写：画像里多一格没人认识的东西，采集清单与报告维度
            # 都对不上它（口径见 ProfileService.correct_field 与 orchestrator 的字段门禁）。
            #
            # 键本身不进用户可见的那句话（那是内部标识），进日志 —— 见 api 层的
            # `_USER_MESSAGE` 口径：界面上只出现用户能行动的话。
            logger.warning("用户更正画像字段被拒：键 %s 不在登记表里", key)
            raise InvalidRequest(
                "画像里没有这一格，改不了 —— 只有登记过的字段能改。"
            )

        label = labels.get(key, key)
        text = "" if value is None else str(value).strip()
        if not text:
            # 空值单独拒，而不是当成"清空这一格"：清空是另一件事（撤销一条记录），
            # 混进来的后果是用户以为自己在改值，实际把一条依据删掉了。
            raise InvalidRequest(f"「{label}」不能是空的 —— 写一句你认可的说法再提交。")
        limit = profile_taxonomy.value_limit(key)
        if len(text) > limit:
            raise InvalidRequest(
                f"「{label}」最多 {limit} 个字，现在有 {len(text)} 个 —— "
                "画像里一格只放一句读得完的话。"
            )
        if key == "study_year" and text not in {"大一", "大二", "大三", "大四"}:
            raise InvalidRequest(
                "当前只支持大一到大四的学习阶段；如果你是其他年级，请先按当前本科阶段选择，"
                "具体说明可以写进「个人情况」或对话里。"
            )
        if key == "degree_level" and text in {"研究生", "硕士", "博士"}:
            raise InvalidRequest(
                "当前只支持本科阶段（大一到大四）；研究生/硕士/博士暂不写入层次字段。"
            )

        before = next(
            (field for field in await self._profiles.list_fields(user_id, [key])), None
        )
        # 两个标签页改同一格：只要调用方带了"我看到的是哪一版"（updated_at），
        # 就必须按版本写 —— 不能提示"已保存"却把另一页的值留在那里。
        # 原来默认 check_version=False，于是没显式要校验的调用方会静默覆盖；
        # 这里改成"带了期望版本就校验"，比让每个调用方各自记得传更可靠。
        enforce_version = check_version or expected_updated_at is not None
        try:
            saved = await self.update_field(
                user_id,
                key,
                text,
                # 把握度给 1.0，不是"抬高他"：这条不是推出来的，是他自己写的。
                # 采集口径里把握低于 0.45 会被算成"还没拿到"（见 policies/collection_gate），
                # 于是沿用旧把握度会让刚改对的那条继续挂在缺口里 —— 他明明刚说完。
                confidence=1.0,
                source=ProfileSource.USER_EDIT.value,
                # 中文名优先沿用这一格原来的：模型起的名字（"专业方向"）比规则表的
                # 通用名更贴他当时那句话，而 upsert 是整行替换，不带上就丢了。
                label=(before.label if before else "") or label,
                # 旧证据撑的是**旧值**，留着会让"这条凭什么"指回一个已经不成立的说法。
                # 更正之后的出处就是他本人，这一点由 source 负责说明。
                evidence=[],
                # 更正后的记录是「本人确认」，而不是任何未经核验的分数：
                # 核实状态与来源分开表达（第 3.1、4 节）。
                verification=ProfileVerification.USER_CONFIRMED.value,
                # 旧属性描述的是旧值（例如兴趣的“喜欢/不喜欢”），不能跟着新值留着。
                attributes={},
                expected_updated_at=expected_updated_at,
                check_version=enforce_version,
            )
        except DuplicateResource as exc:
            # 冲突要能被他读懂、且指出下一步；同时**不能**回"已保存"。
            raise DuplicateResource(PROFILE_FIELD_CONFLICT_MESSAGE) from exc
        if saved.value != profile_taxonomy.normalize_value(key, text):
            # 写路径返回了别的值（例如调用方漏传版本导致覆盖、或仓储幂等分支返回旧值）：
            # 与其让界面显示"已保存"而库里不是他写的内容，不如如实说冲突。
            raise DuplicateResource(PROFILE_FIELD_CONFLICT_MESSAGE)
        try:
            await self._close_gap(user_id, key)
        except Exception:  # noqa: BLE001 - 值已经写进去了，不能因为收尾失败告诉他"没改成"
            # 与资产/缺口落库同一条口径：值写完之后的收尾失败进日志，不打断这一次写入 ——
            # 抛出去会让用户看到"没改成"，而库里其实已经是新值（那是最难查的一类错）。
            logger.warning("更正已写入，但缺口清单没跟着更新（key=%s）", key, exc_info=True)
        # 更正之后，依据这一格的「系统理解」不再成立（设计第 7 节：相关理解标记待核对）。
        await self._invalidate_clues_for(
            user_id, [key], PROFILE_CLUE_INVALIDATED_BY_CORRECTION
        )
        return saved

    async def _close_gap(self, user_id: str, key: str) -> None:
        """把这一条从缺口清单里拿掉。

        不改的话症状很具体：用户改完值、刷新，那一行还挂着「没定」——
        因为界面的"没定"读的是缺口清单，不是字段本身。他刚亲手写下这一格，
        系统还在说"这条还没定"，这是最不该出现的一句自相矛盾。
        """
        gaps = await self._profiles.list_gaps(user_id)
        kept = [gap for gap in gaps if gap.key != key]
        if len(kept) != len(gaps):
            await self._profiles.replace_gaps(user_id, kept)

    async def overall_confidence(self, user_id: str) -> float:
        fields = await self._profiles.list_fields(user_id)
        if not fields:
            return 0.0
        return sum(field.confidence for field in fields) / len(fields)


__all__ = [
    "DefaultProfileService",
    "MAX_FIELD_VALUE_CHARS",
    "PROFILE_CLUE_DENIED_REASON",
    "PROFILE_CLUE_INVALIDATED_BY_CORRECTION",
    "PROFILE_CLUE_INVALIDATED_BY_DELETION",
    "PROFILE_FIELD_CONFLICT_MESSAGE",
]
