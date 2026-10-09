"""画像服务实现。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import uuid4

from zhiyin_business.events import PROFILE_FIELD_UPDATED
from zhiyin_business.policies.collection import field_labels
from zhiyin_business.ports.blackboard import ProfileService
from zhiyin_data_sdk.repositories import ProfileRepository
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.blackboard import Profile, ProfileField, ProfileGap
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration import DomainEvent, EventBus

logger = logging.getLogger(__name__)

#: 用户手填的一个字段值最多多长（字符数）。
#
# 40 不是排版上的拍脑袋：画像里每一格都要能被**读进一句话、写进一段提示词**，
# 而"专业 / 兴趣 / 卡点"这类取值本来就是一个短语或一句话。放开长度之后，
# 用户在这里贴一整段自述进来，画像那一格会变成一个文本域，采集清单与
# 报告维度的对照关系也就断了（它们按"一格一件事"取值）。
#
# 所以线上限不住的地方由这里兜住：超长**如实拒**并说清上限，
# 而不是悄悄截断 —— 截断会让他以为自己写的后半句被记住了。
MAX_FIELD_VALUE_CHARS = 40


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
    ) -> ProfileField:
        field = ProfileField(
            key=key,
            label=label,
            value=value,
            confidence=confidence,
            source=ProfileSource(source),
            evidence=evidence or [],
            updated_at=datetime.now(timezone.utc),
        )
        # 这是**新出现**的一类信息吗？
        #
        # 为什么要在这里判：影响面的判据是"资产声明的依赖字段 ∩ 变更字段"，
        # 而依赖清单是资产**生成那一刻**记下的。一个刚出现的字段不可能在那份清单里
        # （实测：报告生成后才导入的课表，改了它，报告不会被标成"待重算"），
        # 于是"画像里多了一整类信息"这件事对已有结论完全不可见。
        # 交给下游的判据只能是"这个字段对谁都是新的"，所以得在写画像的地方算出来 ——
        # 只有这里知道画像在写之前长什么样。
        #
        # ⚠️ 必须在 upsert **之前**读：写在后面的话读到的就是刚写进去的那条，
        # `is_new` 永远是假（实测：这条判据先写在后面，整条修复静默失效）。
        try:
            known = {item.key for item in await self._profiles.list_fields(user_id)}
        except Exception:  # noqa: BLE001 - 读旧画像失败不该让这次写入失败
            logger.warning("读取既有画像失败，新字段判定按否处理", exc_info=True)
            known = None
        is_new = known is not None and key not in known
        saved = await self._profiles.upsert_field(user_id, field)
        await self._event_bus.publish(
            DomainEvent(
                event_id=f"profile-{uuid4().hex[:12]}",
                event_type=PROFILE_FIELD_UPDATED,
                occurred_at=saved.updated_at,
                payload={
                    "user_id": user_id,
                    "field_key": key,
                    "is_new": is_new,
                    "confidence": confidence,
                    "source": saved.source.value,
                },
            )
        )
        return saved

    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        await self._profiles.replace_gaps(user_id, gaps)

    async def drop_field(self, user_id: str, key: str) -> None:
        """删掉一个画像字段（撤销授权时用）。"""
        await self._profiles.delete_field(user_id, key)

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
            # `degree_level`，用户这边也只认规范键，否则同一个意思会另起一格。
            if spec.alias_of:
                continue
            labels.setdefault(spec.key, spec.label or spec.key)
        return labels

    async def correct_field(self, user_id: str, key: str, value: object) -> ProfileField:
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
        if len(text) > MAX_FIELD_VALUE_CHARS:
            raise InvalidRequest(
                f"「{label}」最多 {MAX_FIELD_VALUE_CHARS} 个字，现在有 {len(text)} 个 —— "
                "画像里一格只放一句读得完的话。"
            )

        before = next(
            (field for field in await self._profiles.list_fields(user_id, [key])), None
        )
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
        )
        try:
            await self._close_gap(user_id, key)
        except Exception:  # noqa: BLE001 - 值已经写进去了，不能因为收尾失败告诉他"没改成"
            # 与资产/缺口落库同一条口径：值写完之后的收尾失败进日志，不打断这一次写入 ——
            # 抛出去会让用户看到"没改成"，而库里其实已经是新值（那是最难查的一类错）。
            logger.warning("更正已写入，但缺口清单没跟着更新（key=%s）", key, exc_info=True)
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


__all__ = ["DefaultProfileService", "MAX_FIELD_VALUE_CHARS"]
