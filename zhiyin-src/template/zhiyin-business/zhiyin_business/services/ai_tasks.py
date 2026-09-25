"""九项页面 AI 任务服务。

前端触发任务后，这里组装真实画像、行为与资产上下文，调用 Agno 模型产出，
按 `contracts/ai_tasks.py` 校验并以 SSE 下发进度及终帧。结果与依据绑定，
缓存按输入事件失效；学信网和学业导入属于独立的数据链路，不由模型编造回执。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta, timezone
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel

from zhiyin_business.contracts.ai_tasks import (
    AiMeta,
    AiResultEnvelope,
    BindResult,
    BindStep,
    BriefToday,
    Citation,
    DayAdvice,
    DimensionReading,
    GapClarify,
    MatchResult,
    ProfileLift,
    PortraitAnalysis,
    ReportSummary,
    TimetablePlan,
    TodoSuggestions,
)
from zhiyin_business.ports.blackboard import (
    AssetService,
    BehaviorService,
    ProfileService,
)
from zhiyin_business.policies.collection import filled_by, plan_collection
from zhiyin_data_sdk.gateways.chsi import (
    ChsiVerificationGateway,
    ChsiVerifyError,
    ChsiVerifyErrorKind,
)
from zhiyin_data_sdk.errors import MissingConfigError
from zhiyin_data_sdk.repositories import AiTaskResultRepository
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.blackboard import Profile
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.errors import ResourceNotFound
from zhiyin_orchestration import AgentEngine, AgentRequest

_log = logging.getLogger(__name__)

# 任务 key → （主理智能体、提示词条目、产出契约）。展示名不再硬编码：
# 交给注册表把 agent_id 翻成用户称呼，改称呼不发版。
_TASK_SPECS: dict[str, tuple[str, str, type[BaseModel], bool]] = {
    "brief.today": ("career_advisor", "task.brief.today", BriefToday, False),
    "dim": ("career_advisor", "task.dim", DimensionReading, False),
    # 「对你的分析」：整份画像合起来的一段判断（画像页第一屏）。归职业顾问，
    # 不归画像分析员 —— 后者的角色提示词里写死"不下结论、不给建议"。
    "portrait.analysis": ("career_advisor", "task.portrait.analysis", PortraitAnalysis, False),
    # 按天的一条建议：日历里点开某一天时生成。归职业顾问 —— 它同样是"下判断"。
    "day.advice": ("career_advisor", "task.day.advice", DayAdvice, False),
    "gap": ("profile_analyst", "task.gap", GapClarify, False),
    "report.summary": ("career_advisor", "task.report.summary", ReportSummary, False),
    "plan.timetable": ("path_planner", "task.plan.timetable", TimetablePlan, False),
    "plan.todos": ("career_advisor", "task.plan.todos", TodoSuggestions, False),
    # 方向匹配要自己去取职业要求，所以它是唯一挂工具的生成类任务
    "match.careers": ("career_advisor", "task.match.careers", MatchResult, True),
    # bind.chsi / bind.academic 不在这张表里：它们是数据链路（核验 → 解析 → 写画像 → 回执），
    # 回执里的每一步都必须与真实结果逐项一致，交给模型生成只会引入不一致。
}

# 任务 key → 谁在替你做这件事（展示名从注册表取，这里只放 agent_id）
_TASK_OWNER: dict[str, str] = {
    "bind.chsi": "info_scout",
    "bind.academic": "info_scout",
}

# 每条产出**依据的是哪些事实**，以及事实一变谁不能再用（任务 key → 事件码）。
#
# 为什么必须写下来：产出是**按 key 存的**（`ai_task_result` 表），而 key 里
# 只有"哪一件事"，没有"依据是什么版本的" —— 依据变了而 key 没变，那份旧产出
# 就会被当成最新的用，一直错下去（缓存跨重启，也没有 TTL）。
# 所以每一条要在这里说清"我依赖什么"，作废按它执行。
#
# 事件码与读缓存用的是**同一套**（`data/registry/policy_params.json` 的 cache 一条）：
# "发生了什么"全站只有一套说法，缓存不该各记各的。
#
# 刻意**不写全量作废**（任何事件都清空该用户所有产出）：每一条清掉，下次打开
# 就是一次真实的模型调用（花钱、花时间），而绝大多数产出与这次变化无关。
_TASK_INPUTS: dict[str, tuple[str, ...]] = {
    # 今日简报：画像 + 最近的行动 + 他自己写下的话
    "brief.today": (
        "profile_field_updated",
        "asset_state_changed",
        "note_changed",
    ),
    # 维度解读：只讲一条画像字段
    "dim": ("profile_field_updated",),
    # 对你的分析：整份画像 + 缺口 + 他写过的话
    "portrait.analysis": ("profile_field_updated", "note_changed"),
    # 这一天怎么用：那天的课 + 那天到期的节点 + 手里还没做完的任务 + 画像
    "day.advice": (
        "profile_field_updated",
        "academic_changed",
        "asset_state_changed",
        "asset_version_changed",
    ),
    # 缺口追问：问的就是那一条缺口（画像与缺口同源）
    "gap": ("profile_field_updated",),
    # 报告小结：报告正文 + 画像
    "report.summary": ("asset_version_changed", "profile_field_updated"),
    # 空档课表：导入的课表 + 行动计划的时段
    "plan.timetable": (
        "academic_changed",
        "asset_version_changed",
        "asset_state_changed",
    ),
    # 待办建议：缺口优先级 + 最近的行动 + 他写下的话
    "plan.todos": (
        "profile_field_updated",
        "asset_state_changed",
        "note_changed",
    ),
    # 职业匹配：画像（外网那一半每次现取，不进缓存键）
    "match.careers": ("profile_field_updated",),
}

# 画像来源 → 给模型看的说法。模型要引用来源，但读不懂 `behavior_inference` 这种键。
_SOURCE_TEXT: dict[str, str] = {
    "conversation": "对话",
    "record": "客观档案",
    "assessment": "测评",
    "behavior_inference": "行为推断",
    "resume": "简历",
    "mentor": "导师建议",
}


def _source_text(source: Any) -> str:
    value = getattr(source, "value", source)
    return _SOURCE_TEXT.get(str(value), str(value))


def _value_text(value: Any) -> str:
    """字段值读给模型听。

    画像里的值不只是字符串：兴趣、约束、成绩这些本来就是**多项**。
    直接把它们塞进提示词，模型看到的是 `['混凝土结构设计 88 分', '结构力学 84 分']`
    —— 方括号和引号是 Python 的表示法，不是他要读的东西，而且很容易被照抄进产出里，
    最后出现在用户眼前。所以先摊平成"、` 连起来的短句。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "、".join(f"{k}：{_value_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return "、".join(part for part in (_value_text(v) for v in value) if part)
    return str(value)


def _place_text(course: Any) -> str:
    """课程的"在哪儿、谁上" —— 有就写，没有就不写，不留一个空的括号。"""
    place = str(getattr(course, "place", "") or "").strip()
    teacher = str(getattr(course, "teacher", "") or "").strip()
    if place and teacher:
        return f"{place} · {teacher}"
    return place or teacher


def _period_text(course: Any) -> str:
    """课程的节次：`第 3-4 节`。没读出节次的就不写，不留一个"第 0-0 节"。"""
    start = int(getattr(course, "start_period", 0) or 0)
    end = int(getattr(course, "end_period", 0) or 0) or start
    if start <= 0:
        return "时间没读出来"
    return f"第 {start}-{end} 节" if end > start else f"第 {start} 节"

"""
这里原来有三份**假数据**：五项能力、两条职业方向的需求矩阵、三门演示课程。

它们的问题不是"不够真实"，而是**看起来像真的**：课程表上有老师、有教室、有学分，
匹配结果里有一位小数的契合度。用户没有任何办法分辨这些是编的 ——
而真正没接上的那两件事（课程与成绩、学职网的职业条目）就这么被盖住了。

所以全部删掉。课表与匹配现在只有一条路：**说清缺什么**，不猜。
"""


"""
**有副作用的采集任务不许命中缓存。**

任务缓存的口径本来是"同样的输入给同样的产出，没必要重算"——那对
生成类任务（简报 / 维度解读 / 报告结论）是对的。但采集不是生成：

    用户点"核验学籍"，他要的是**真的去取一次、真的写进画像**。

命中缓存意味着这次什么都没做，界面上却照样显示"已核验、补上了 8 条" ——
这是一条比"没反应"更坏的失败：它让人以为数据已经进去了。
（这个 bug 是实跑时抓到的：清空画像后重新核验，回执说补了 8 条，库里 0 条。）
"""
_SIDE_EFFECTING_HEADS: frozenset[str] = frozenset({"bind"})

"""
在线验证报告里哪些字段写进画像。

只写"学业档案"这一档：学校、院系、专业、层次、学制、学习形式、入学与预计毕业、
学籍状态、学号、姓名。**不写身份证号**——报告里那一条本身是脱敏的，
而我们也没有任何业务需要用到它；少存一条敏感信息，就少一份泄露风险。

**不写在线验证码本身。** 那串码等于这份报告的一把钥匙（谁拿到谁就能读），
它的用途只在"核验这一次"。要再核验，让用户重新给一串新的码即可 ——
这也正好符合"报告有有效期"这件事。
"""
class AiTaskService:
    """九项页面 AI 任务的执行与缓存。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        profiles: ProfileService,
        behaviors: BehaviorService,
        assets: AssetService,
        chsi: Optional[ChsiVerificationGateway] = None,
        registry: Any = None,
        notes: Any = None,
        academic_records: Any = None,
        functions: Any = None,
        engine: Optional[AgentEngine] = None,
        results: Optional[AiTaskResultRepository] = None,
    ) -> None:
        self._profiles = profiles
        self._behaviors = behaviors
        self._assets = assets
        # 学信网核验网关：装配报告里独立占一个能力位。
        # 允许为空（本地跑没有外网时），但为空时 bind 任务必须**明确报错**，
        # 而不是退回一份看着像样的假学籍。
        self._chsi = chsi
        # 他自己写下的东西（自建待办 / 写下的目标）：采集优先级要引用他的原话
        self._notes = notes
        # 学生自己导入的课表与成绩（快照）：空档要**从真实课表**里数出来
        self._academic_records = academic_records
        # 关键节点日历（规划师写、这里读）："这一天有什么到期" 从这儿来。
        # 允许为空 —— 为空时那一天就只按课表和任务说，不假装有节点。
        self._functions = functions
        # 动态资源读侧：采集规则在库里（`data/registry/collection_rules.json`）
        self._registry = registry
        # 智能体引擎：生成类任务的**唯一**内容来源。为空时那些任务直接报错，
        # 不再退回"拼一段看起来像样的文案"——本项目已经删干净那种做法了。
        self._engine = engine
        self._rules_cache: list[Any] | None = None
        # 产出缓存走 Repository（Postgres 模式下是 `ai_task_result` 表）：
        # 它是**资产级内容**，不是临时缓存 —— 重启一次就让模型重算一遍说不过去，
        # 多实例各存一份也会让同一个用户刷新两次拿到两份不同的生成。
        # 允许为空（单测里可以只构造服务本身），为空时退化为不缓存。
        self._results = results

    async def invalidate(self, user_id: str, prefix: str = "") -> int:
        """作废该用户某个前缀下的全部产出，返回作废条数。

        语义是"用户补了信息，旧产出不能再当最新的用" —— 所以这是**删库**，不是清内存。
        """
        if self._results is None:
            return 0
        return await self._results.delete_prefix(user_id, prefix)

    async def invalidate_for_event(self, user_id: str, event: str) -> int:
        """按"发生了什么"作废受影响的产出，返回作废条数。

        映射就是 `_TASK_INPUTS`：谁依据的事实里有这一条，谁的产出就不能再当最新的用。
        没命中任何一个前缀时**什么都不做**（返回 0）—— 这是常态，
        比如一路只是发消息、没改任何事实。

        为什么要按事件而不是"谁想清就自己清"：调用点（API 层、编排器、Worker）
        只该知道"发生了什么"，"这一下影响到哪些产出"是这里的知识 ——
        和读缓存的口径一致（那边把映射放在动态资源里，这边在服务内，
        因为任务 key 本身就是代码常量）。
        """
        if self._results is None:
            return 0
        prefixes = [
            prefix for prefix, events in _TASK_INPUTS.items() if event in events
        ]
        removed = 0
        for prefix in prefixes:
            # 一个前缀就够：仓储按 `LIKE '前缀%'` 删，无参数的键（`brief.today`）
            # 与带参数的键（`dim.兴趣` / `day.advice.2026-09-23|480`）都被它罩住。
            removed += await self.invalidate(user_id, prefix)
        return removed

    def _collection_rules(self):
        """采集规则（动态配置快照）。为空时返回 None，由策略层退回内置表。

        读快照而不是读库：配置在启动时装一次，改库之后由
        `POST /app/config/reload` 统一替换 —— 见 kernel.dynamic_config。
        """
        return list(dynamic_config.snapshot().collection_rules) or None

    def _user_signals(self):
        """用户信号线索表（同一份快照）。没有它，回执就永远说不出"因为你写了…"。"""
        return list(dynamic_config.snapshot().user_signals) or None

    def _available_sources(self) -> tuple[str, ...]:
        """现在真的取得动数据的源头。

        `academic`（课表与成绩）现在是**用户自己导入**：不需要接入任何外部系统，
        所以它永远可用 —— 而它一旦可用，"课程表 / 成绩单"就从
        "暂时补不了"变成"导入一次就有"。
        """
        return ("chsi", "conversation", "academic")

    async def _note_texts(self, user_id: str) -> list[str]:
        """他自己写过的话。读不到就当没有 —— 绝不编一句他没用过的话。"""
        if self._notes is None:
            return []
        try:
            return await self._notes.texts(user_id)
        except Exception:
            _log.exception("读取用户自建内容失败：采集回执按没有额外理由处理")
            return []

    # ---------- 生成类任务：一律走智能体引擎 ----------

    async def _generate(
        self,
        user_id: str,
        key: str,
        *,
        context_text: str,
        citations: list[Citation],
        rationale: str,
    ) -> AiResultEnvelope:
        """把一个生成类任务交给智能体引擎：提示词与产出契约从动态资源取。

        两条口径：

        - **没有引擎就报错**，不退回拼字符串。拼出来的那段话看起来完全正常，
          用户没有任何办法分辨它背后没有模型 —— 那正是这一轮要清掉的东西。
        - **产出不符合契约也算失败**。契约校验在这里是硬门槛：结构不对说明
          提示词或模型出了问题，宁可让用户看到一次失败，也不要放一份半成品过去。
        """
        spec = _TASK_SPECS.get(key)
        if spec is None:
            raise ResourceNotFound(f"未登记的生成类任务：{key}")
        if self._engine is None:
            raise MissingConfigError(f"智能体引擎未装配，{key} 无法生成内容")
        agent_id, prompt_code, contract, uses_tools = spec
        result = await self._engine.invoke(
            AgentRequest(
                agent_id=agent_id,
                prompt_code=prompt_code,
                blackboard={"user_id": user_id, "task_id": f"ai-task-{key}"},
                prompt_vars={"context_text": context_text},
                output_schema=contract.model_json_schema(),
                use_tools=uses_tools,
            )
        )
        if not result.valid:
            raise MissingConfigError(
                f"{key} 的产出不符合契约：{result.errors[:3]}"
            )
        data = contract.model_validate(result.structured)
        if key == "plan.todos":
            # 模型按对象输出（见 TodoSuggestions 的说明），对外下发的是数组
            data = data.items
        return self._envelope(
            data, citations, await self._display_name(agent_id), rationale
        )

    async def _display_name(self, agent_id: str) -> str:
        """agent_id → 用户称呼。取不到就抛：把标识念给用户听等于没配。"""
        descriptor = await self._registry.get_agent(agent_id) if self._registry else None
        if descriptor is None or not descriptor.name:
            raise MissingConfigError(f"智能体展示名缺失：{agent_id}")
        return descriptor.name

    @staticmethod
    def _context(*blocks: tuple[str, list[str]]) -> str:
        """把上下文渲染成短行文本。

        为什么不是 JSON：模型读一坨 JSON 时，字段的来源与时间会退化成噪声；
        短行文本里"来源""把握"是自然语言，模型更容易引用它们而不是忽略。
        空块直接不出现 —— 不写"（无）"，那会让模型以为那里本该有东西。
        """
        lines: list[str] = []
        for title, rows in blocks:
            present = [row for row in rows if row]
            if not present:
                continue
            lines.append(f"【{title}】")
            lines.extend(f"- {row}" for row in present)
        return "\n".join(lines)

    @staticmethod
    def _profile_lines(profile: Optional[Profile]) -> list[str]:
        if profile is None:
            return []
        return [
            f"{f.key}：{_value_text(f.value)}（来源：{_source_text(f.source)}，把握：{f.confidence:.2f}，"
            f"更新于 {f.updated_at.strftime('%m-%d')}）"
            for f in profile.fields
        ]

    @staticmethod
    def _gap_lines(profile: Optional[Profile]) -> list[str]:
        if profile is None:
            return []
        return [
            f"{gap.key}：{gap.reason}（下一步可以问：{gap.suggested_next_action}）"
            for gap in profile.gaps
        ]

    async def stream(self, user_id: str, key: str, arg: str = "") -> AsyncIterator[dict]:
        """执行一个 AI 任务：yield 进度帧，最后 yield {"result": ...} 终帧。"""
        started = time.perf_counter()
        head = key.split(".")[0]
        cache_key = f"{key}.{arg}" if arg else key
        cacheable = head not in _SIDE_EFFECTING_HEADS

        if cacheable:
            cached = await self._load_cached(user_id, cache_key)
            if cached is not None:
                yield {"result": cached}
                return

        notes = await self._progress_notes(key, head)
        for i, note in enumerate(notes):
            yield {"pct": round((i + 1) / (len(notes) + 1), 3), "note": note}
            await asyncio.sleep(0.05)

        try:
            envelope = await self._produce(user_id, head, arg, key=key)
        except ChsiVerifyError as exc:
            # 学信网核验失败是"用户能自己修"的一类失败（码写错了、报告过期了），
            # 所以不吞、也不 500：把类别和原因原样送到前端，让用户看见并重试。
            # 这里只带 kind，具体错误码由 api 层翻译（业务层不许认识 api 的错误码）。
            yield {"error": {"kind": exc.kind.value, "message": str(exc)}}
            return
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        envelope.meta.ms = elapsed_ms
        envelope.meta.at = ""
        if cacheable:
            await self._store_cached(user_id, cache_key, envelope)
        yield {"result": envelope}

    async def _progress_notes(self, key: str, head: str) -> list[str]:
        """按 key 取进度文案。

        文案在动态资源（`data/registry/task_progress.json`），由 RegistryService 读。
        取法：先按完整 key（`report.summary`）找，再按 head（`dim` / `gap`）找 ——
        维度解读与缺口追问是**一族任务共一段文案**，它们的 key 带参数后缀。
        取不到就返回空列表：少几行进度提示，不影响任务本身。
        """
        if self._registry is None:
            return []
        try:
            specs = await self._registry.list_task_progress()
        except Exception:  # noqa: BLE001 - 文案读不到不该让任务失败
            _log.warning("AI 任务进度文案读取失败，本次不带进度提示", exc_info=True)
            return []
        by_code = {spec.code: list(spec.notes) for spec in specs}
        return by_code.get(key) or by_code.get(head) or []

    async def _chsi_field_specs(self) -> dict[str, Any]:
        """学信网字段清单（key → 规格）。读不到就返回空 —— 那时**一个字段都不写进画像**。

        返回空而不是"放行所有字段"：白名单读不到时放行，等于把隐私决定交给了
        "配置文件在不在"，而配置缺失是运维问题，不该变成隐私问题。
        """
        if self._registry is None:
            return {}
        try:
            specs = await self._registry.list_chsi_fields()
        except Exception:  # noqa: BLE001
            _log.warning("学信网字段清单读取失败，本次不写入任何字段", exc_info=True)
            return {}
        return {spec.key: spec for spec in specs}

    async def _load_cached(self, user_id: str, cache_key: str) -> Optional[AiResultEnvelope]:
        """读缓存。命中时把 `cached` 标记点亮 —— 用户要能看出"这是算过的"。"""
        if self._results is None:
            return None
        payload = await self._results.get(user_id, cache_key)
        if payload is None:
            return None
        try:
            envelope = AiResultEnvelope.model_validate(payload)
        except Exception:  # noqa: BLE001
            # 存坏的一条（老版本形状）不该让这个任务永久失败：当作没缓存，重算一次。
            _log.warning("AI 任务缓存形状不兼容，已忽略：key=%s", cache_key)
            return None
        return envelope.model_copy(
            update={"meta": envelope.meta.model_copy(update={"cached": True})}
        )

    async def _store_cached(
        self, user_id: str, cache_key: str, envelope: AiResultEnvelope
    ) -> None:
        """写缓存。写失败只记日志：缓存是优化，不该让用户这一轮拿不到结果。"""
        if self._results is None:
            return
        try:
            await self._results.put(user_id, cache_key, envelope.model_dump(mode="json"))
        except Exception:  # noqa: BLE001
            _log.exception("AI 任务产出写入失败（本次结果仍会返回）：key=%s", cache_key)

    # ------------------------------------------------------------------

    async def _produce(self, user_id: str, head: str, arg: str, *, key: str) -> AiResultEnvelope:
        profile = await self._profiles.get(user_id)
        spec = _TASK_SPECS.get(key)
        owner = _TASK_OWNER.get(key) or (spec[0] if spec else "career_advisor")
        by = await self._display_name(owner)
        builder = {
            "brief": self._brief,
            "dim": self._dimension,
            "portrait": self._portrait,
            "day": self._day_advice,
            "gap": self._clarify,
            "report": self._report_summary,
            "bind": self._bind_chsi,
            "plan": self._plan,
            "match": self._match,
        }.get(head)
        if builder is None:
            raise ResourceNotFound(f"未登记的 AI 任务：{head}")
        if head == "plan":
            # plan.timetable / plan.todos 共用一个 builder，按完整 key 分流
            arg = "todos" if key == "plan.todos" else ""
        return await builder(user_id, profile, arg, by=by)

    def _envelope(self, data, citations: list[Citation], by: str, rationale: str) -> AiResultEnvelope:
        return AiResultEnvelope(
            data=data,
            citations=citations,
            meta=AiMeta(by=by, at="", ms=0, cached=False),
            rationale=rationale,
        )

    # ---------- 各任务 ----------

    async def _brief(self, user_id: str, profile: Optional[Profile], arg: str, *, by: str) -> AiResultEnvelope:
        recent = await self._behaviors.recent(user_id, limit=5)
        notes = await self._note_texts(user_id)
        citations = [
            Citation(
                source="你的画像",
                detail=f"{len(profile.fields) if profile else 0} 个字段 · "
                f"{len(profile.gaps) if profile else 0} 条缺口",
                confidence=0.8,
            )
        ]
        if recent:
            citations.append(
                Citation(
                    source="行为日志",
                    detail=f"最近一次行为：{recent[0].event_type.value}",
                    confidence=0.9,
                    at=recent[0].occurred_at.strftime("%m-%d"),
                )
            )
        context = self._context(
            ("我已经知道的", self._profile_lines(profile)),
            ("还缺的", self._gap_lines(profile)),
            (
                "他最近做过的事",
                [f"{b.occurred_at.strftime('%m-%d')} {b.event_type.value}" for b in recent],
            ),
            ("他自己写下的", notes),
        )
        return await self._generate(
            user_id,
            "brief.today",
            context_text=context,
            citations=citations,
            rationale="今天的事 = 画像里最卡方向的那条缺口 + 最近变过的字段。",
        )

    async def _portrait(
        self, user_id: str, profile: Optional[Profile], arg: str, *, by: str
    ) -> AiResultEnvelope:
        """「对你的分析」：把整份画像收成一段整体判断。

        与「维度解读」的分工：解读是**一条**字段的注解（这条是什么、凭什么），
        这里是**合起来**说他现在是个什么处境 —— 手里有什么、方向有多确定、
        卡在哪、下一步先动哪一件。所以它读全部字段 + 缺口 + 他自己写过的话。

        没有字段就不生成：一份空画像能"分析"出来的只有空白，让模型去写
        只会得到一段像模像样但没有任何依据的话 —— 那是本仓最不能有的东西。
        """
        fields = list(profile.fields) if profile else []
        if not fields:
            raise ResourceNotFound("画像还是空的，没有可分析的内容")
        gaps = list(profile.gaps) if profile else []
        notes = await self._note_texts(user_id)

        # 依据：一条总账 + 按把握从高到低最实的几条字段。
        # 为什么按把握排：分析里最硬的那几句就是从这里来的，点开抽屉时
        # 用户先看到的应该是"他真的有据"的那几条。
        ranked = sorted(fields, key=lambda f: f.confidence, reverse=True)
        citations = [
            Citation(
                source="你的画像",
                detail=f"{len(fields)} 条记录 · {len(gaps)} 条还缺",
                confidence=0.8,
            )
        ]
        citations += [
            Citation(
                source=f"画像 · {f.label or f.key}",
                detail=f"{_value_text(f.value)}（{_source_text(f.source)}，把握 {f.confidence:.2f}）",
                confidence=f.confidence,
                at=f.updated_at.strftime("%Y-%m-%d"),
            )
            for f in ranked[:6]
        ]
        if gaps:
            citations.append(
                Citation(
                    source="画像缺口",
                    detail="、".join(gap.label or gap.key for gap in gaps[:6]),
                    confidence=0.9,
                )
            )

        context = self._context(
            ("我已经知道的", self._profile_lines(profile)),
            ("还缺的", self._gap_lines(profile)),
            ("他自己写下的", notes),
        )
        return await self._generate(
            user_id,
            "portrait.analysis",
            context_text=context,
            citations=citations,
            rationale="对你的分析 = 把画像里已有的每条记录合起来，说他现在处在哪一步。",
        )

    async def _day_advice(
        self, user_id: str, profile: Optional[Profile], day: str, *, by: str
    ) -> AiResultEnvelope:
        """「这一天的建议」：把这一天的事实收成一句"今天怎么过"。

        事实从三处读，都是真的读，不是让模型回忆：
          · 课表 —— 学生自己导入的快照里，星期几对得上的那些课；
          · 关键节点 —— 规划师写进日历、到期日正好是这一天的那些；
          · 行动任务 —— 到期日不晚于这一天的、还没勾掉的。
        缺哪一处就少说哪一处：没有课表就不提课，不编一句"你今天有课"。
        """
        """
        `arg` 的形状是 `2026-09-25|480`：日期 + 客户端时区（分钟，东为正）。

        为什么要带时区：库里存的是 UTC，而"那一天"是**用户手表上的那一天** ——
        晚上 23:00 的事在 UTC 里已经是第二天了。不带这个偏移，
        傍晚以后的事会被算到前一天，界面（按本地日分组的）与这里的建议就对不上。
        """
        raw_day, _, raw_tz = (day or "").partition("|")
        try:
            target = date.fromisoformat(raw_day)
        except (TypeError, ValueError) as exc:
            raise ResourceNotFound(f"看不懂这个日期：{raw_day}") from exc
        try:
            # 现实存在的时区偏移在 ±14 小时以内；超出的当作没给，而不是照着算
            offset_minutes = int(raw_tz) if raw_tz else 0
        except ValueError:
            offset_minutes = 0
        if not -840 <= offset_minutes <= 840:
            offset_minutes = 0
        local = timezone(timedelta(minutes=offset_minutes))

        def local_day(value: Any) -> Optional[date]:
            """某个时刻在**用户那边**是哪一天。"""
            if value is None:
                return None
            return value.astimezone(local).date()

        weekday = target.isoweekday()  # 1=周一 … 7=周日

        courses: list[Any] = []
        if self._academic_records is not None:
            try:
                snapshot = await self._academic_records.get(user_id)
                # 快照里的课是 `CourseEntry`：星期几叫 weekday、节次叫 start_period/end_period
                # （和内核里那个给界面看的 Course 不是同一个形状，别串了）
                courses = [
                    c
                    for c in (getattr(snapshot, "courses", []) or [])
                    if getattr(c, "weekday", 0) == weekday
                ]
            except Exception:  # noqa: BLE001
                _log.exception("读课表失败：这一天按没有课处理")

        nodes: list[Any] = []
        if self._functions is not None:
            try:
                nodes = [
                    n
                    for n in await self._functions.list_calendar_nodes(user_id)
                    if local_day(getattr(n, "due_at", None)) == target
                ]
            except Exception:  # noqa: BLE001
                _log.exception("读关键节点失败：这一天按没有节点处理")

        due: list[str] = []
        try:
            action_plan = await self._assets.get_action_plan(user_id)
            for phase in getattr(action_plan, "phases", []) or []:
                for task in phase.tasks:
                    if task.done or task.due_date is None:
                        continue
                    if (local_day(task.due_date) or date(1970, 1, 1)) <= target:
                        due.append(f"{task.text}（{phase.name}，应完成于 {task.due_date:%m-%d}）")
        except Exception:  # noqa: BLE001
            _log.exception("读行动计划失败：这一天按没有到期任务处理")

        citations = [
            Citation(
                source="这一天",
                detail=f"{raw_day} 周{'一二三四五六日'[weekday - 1]}",
                confidence=1.0,
            )
        ]
        citations += [
            Citation(
                source="课表",
                detail=f"{_period_text(c)} {c.name}（{_place_text(c)}）",
                confidence=0.95,
                origin="academic",
            )
            for c in courses
        ]
        citations += [
            Citation(
                source="关键节点",
                detail=str(getattr(n, "title", "")),
                confidence=0.9,
                at=day,
            )
            for n in nodes
        ]
        if due:
            citations.append(
                Citation(source="行动计划", detail="；".join(due[:3]), confidence=0.9)
            )

        context = self._context(
            ("这一天", [f"{raw_day}（周{'一二三四五六日'[weekday - 1]}）"]),
            (
                "这一天有课",
                [f"{_period_text(c)}：{c.name}（{_place_text(c)}）" for c in courses],
            ),
            ("到期日正好是这一天的事", [str(getattr(n, "title", "")) for n in nodes]),
            ("到期了还没做完的事", due),
            ("我已经知道的", self._profile_lines(profile)),
            ("还缺的", self._gap_lines(profile)),
        )
        return await self._generate(
            user_id,
            "day.advice",
            context_text=context,
            citations=citations,
            rationale="这一天怎么过 = 那天有的课 + 那天到期的事 + 他手里还差什么，排成能直接做的顺序。",
        )

    async def _dimension(self, user_id: str, profile: Optional[Profile], dim_id: str, *, by: str) -> AiResultEnvelope:
        fields = {f.key: f for f in (profile.fields if profile else [])}
        field = fields.get(dim_id)
        if field is None:
            raise ResourceNotFound(f"画像中没有维度：{dim_id}")
        score = field.confidence
        citations = [
            Citation(
                source=f"画像 · {dim_id}",
                detail=ev,
                confidence=score,
                at=field.updated_at.strftime("%Y-%m-%d"),
            )
            for ev in field.evidence[:5]
        ] or [
            Citation(
                source=f"画像 · {dim_id}",
                detail=f"来源 {_source_text(field.source)}",
                confidence=score,
            )
        ]
        context = self._context(
            (
                "这一条维度",
                [
                    f"字段：{dim_id}",
                    f"值：{_value_text(field.value)}",
                    f"把握程度：{score:.2f}",
                    "决策线：0.60（低于它只能给备选建议）",
                    f"来源：{_source_text(field.source)}",
                    f"更新于：{field.updated_at.strftime('%Y-%m-%d')}",
                ],
            ),
            ("支撑它的证据", [str(ev) for ev in field.evidence]),
        )
        return await self._generate(
            user_id,
            "dim",
            context_text=context,
            citations=citations,
            rationale="维度解读只整理证据，不新增判断 —— 判断在诊断环节。",
        )

    async def _clarify(self, user_id: str, profile: Optional[Profile], gap_key: str, *, by: str) -> AiResultEnvelope:
        gaps = {g.key: g for g in (profile.gaps if profile else [])}
        gap = gaps.get(gap_key)
        if gap is None:
            raise ResourceNotFound(f"画像中没有缺口：{gap_key}")
        citations = [Citation(source="画像缺口", detail=f"{gap.key}：{gap.reason}", confidence=0.9)]
        context = self._context(
            (
                "要问的那一条缺口",
                [
                    f"字段：{gap.key}",
                    f"为什么算缺口：{gap.reason}",
                    f"建议的采集动作：{gap.suggested_next_action}",
                ],
            ),
            ("我已经知道的（不要再问）", self._profile_lines(profile)),
        )
        return await self._generate(
            user_id,
            "gap",
            context_text=context,
            citations=citations,
            rationale="缺口追问是采集环节的收尾动作：回答即写入画像。",
        )

    async def _report_summary(self, user_id: str, profile: Optional[Profile], arg: str, *, by: str) -> AiResultEnvelope:
        report = await self._assets.get_report(user_id)
        citations: list[Citation] = []
        blocks: list[tuple[str, list[str]]] = []
        if report is not None:
            citations.append(
                Citation(
                    source=f"诊断报告 v{report.version}",
                    detail=report.verdict.title,
                    confidence=0.85,
                    at=report.generated_at.strftime("%Y-%m-%d"),
                )
            )
            blocks.append(("诊断结论", [report.verdict.title, report.verdict.summary]))
            blocks.append(("优劣势", list(report.swot.strength) + list(report.swot.weakness)))
            blocks.append(("主要风险", list(report.swot.risk)))
        else:
            citations.append(
                Citation(
                    source="画像状态",
                    detail=f"缺口 {len(profile.gaps) if profile else 0} 条",
                    confidence=0.9,
                )
            )
        blocks.append(("我已经知道的", self._profile_lines(profile)))
        blocks.append(("还缺的", self._gap_lines(profile)))
        return await self._generate(
            user_id,
            "report.summary",
            context_text=self._context(*blocks),
            citations=citations,
            rationale="没有诊断就不编结论：报告还没生成时，这一段的任务是说清还差什么。",
        )

    async def _bind_chsi(self, user_id: str, profile: Optional[Profile], arg: str, *, by: str) -> AiResultEnvelope:
        """学信网绑定：核验在线验证码 → 读报告 → 写画像。

        这是**真数据**：`arg` 是用户在学信档案申请到的在线验证码，
        我们拿它去学信网官方验证页核验，读回报告里的学籍字段，
        再逐条写进画像（来源标记为 `record`，置信度满分——它是权威机构出的记录，
        不是我们推断的）。

        覆盖边界要说清楚：学信网**没有**课程表与成绩单。
        这一步就只补学籍这一类；课程与成绩由学生自己从教务系统导出后导入
        （见 `/app/academic/import`），不在这里编。
        """
        if self._chsi is None:
            raise ChsiVerifyError(
                "学信网核验网关未装配，暂时无法核验。",
                kind=ChsiVerifyErrorKind.UNREACHABLE,
                detail="container.chsi is None",
            )

        report = await self._chsi.verify(arg)
        existing = {
            field.key: field
            for field in await self._profiles.get_fields(user_id)
        }

        # 采集策略的前后对照：这一趟是**为画像的缺口**去取的，
        # 所以回执必须说清楚"补上了哪几条本来缺的" ——
        # 用户看到的不是"取了 11 条字段"，而是"还差的东西少了 4 条"。
        rules = self._collection_rules()
        signals = self._user_signals()
        notes = await self._note_texts(user_id)
        sources = self._available_sources()
        plan_before = plan_collection(
            profile, rules=rules, notes=notes, signals=signals, available_sources=sources
        )

        written: list[ProfileLift] = []
        detail_bits: list[str] = []
        # 学信网字段的"写哪些 / 叫什么 / 什么顺序"在动态资源（`chsi_fields.json`）：
        # 多写一个字段进画像是一个**隐私决定**，不该由代码顺手决定。
        chsi_specs = await self._chsi_field_specs()
        for item in report.fields:
            spec = chsi_specs.get(item.key)
            if spec is None:
                # 不在清单里的字段**不进画像**（比如学信网报告里可能多出的项）。
                # 这是刻意的白名单，不是遗漏。
                continue
            before = existing[item.key].confidence if item.key in existing else 0.0
            await self._profiles.update_field(
                user_id,
                item.key,
                item.value,
                # 权威机构出具的在籍记录：不猜、不打折。
                confidence=1.0,
                source=ProfileSource.RECORD.value,
                evidence=[report.source_url],
            )
            written.append(
                ProfileLift(
                    dim=spec.label or item.key,
                    **{"from": round(before, 2), "to": 1.0},
                    because=f"学信网{report.kind.value}在线验证报告 · {item.label}",
                )
            )
            detail_bits.append(f"{spec.label or item.key} {item.value}")

        verified_note = " · ".join(detail_bits[:4]) or "报告已核验"
        report_note = f"报告编号 {report.report_no}" if report.report_no else "报告已核验"

        # 闭环的后半句：取回来之后，还差的东西变了多少。
        # 这一句必须来自**重新读一次画像**，不能用刚才写进去的条数自己推算 ——
        # 报告里有几条本来就不在采集清单里（比如姓名），推算会把它们算成"补上的缺口"。
        refreshed = await self._profiles.get(user_id)
        plan_after = plan_collection(
            refreshed, rules=rules, notes=notes, signals=signals, available_sources=sources
        )
        filled = filled_by(plan_before, plan_after)
        closed_loop = (
            f"补上了 {len(filled)} 条原本缺的：{' / '.join(filled)}。"
            f"采集清单从 {plan_before.missing} 条降到 {plan_after.missing} 条。"
            if filled
            else "这份报告里的字段画像已经有了，所以还差的东西没变。"
        )
        steps = [
            BindStep(
                id="s1",
                label="核验报告",
                detail=f"学信网已确认这份{report.kind.value}报告有效 · {report_note}",
                got=len(report.fields),
                source="学信网 · 在线验证",
            ),
            BindStep(
                id="s2",
                label=report.kind.value,
                detail=verified_note,
                got=len(written),
                source=f"学信网 · {report.kind.value}信息",
            ),
            # 这一步是"动态采集"的可视化：取之前缺什么、取完之后还缺什么
            BindStep(
                id="s3",
                label="补上的缺口",
                detail=closed_loop,
                got=len(filled),
                source="采集策略 · 画像对照",
            ),
            BindStep(
                id="s4",
                label="写入画像",
                detail=f"写入 {len(written)} 条画像字段，来源标记为「客观档案」",
                got=len(written),
                source="画像 · 增量更新",
            ),
            # 这一步 got=0 是刻意的：学信网确实不提供课程与成绩，
            # 与其演一门课的假数据，不如把"这里还没有源头"摆出来。
            BindStep(
                id="s5",
                label="课程与成绩",
                detail="学信网不提供课程表与成绩单 —— 这一块从教务系统导出后自己导入。",
                got=0,
                source="学信网 · 无此数据",
            ),
        ]
        citations = [
            Citation(
                source=f"学信网 · {report.kind.value}在线验证报告",
                detail=f"核验于 {report.verified_at[:16].replace('T', ' ')}（UTC）"
                + (f"，报告编号 {report.report_no}" if report.report_no else ""),
                confidence=1.0,
                origin="chsi",
            ),
            Citation(
                source="核验方式",
                detail="由用户提供在线验证码，经学信网官方验证页核验；"
                "不索取、不保存用户的学信网账号密码，也不留存那串验证码。",
                confidence=1.0,
                origin="chsi",
            ),
        ]
        return self._envelope(
            BindResult(steps=steps, courses=[], lifted=written),
            citations,
            by,
            f"共核验 {len(report.fields)} 个报告字段，写入 {len(written)} 条画像字段；"
            "学信网是权威事实源，这些字段置信度记为 1.0。课程与成绩不在其覆盖范围内。",
        )

    async def _plan(self, user_id: str, profile: Optional[Profile], arg: str, *, by: str) -> AiResultEnvelope:
        if arg == "todos" or arg == "suggestions":
            recent = await self._behaviors.recent(user_id, limit=5)
            notes = await self._note_texts(user_id)
            citations = [
                Citation(
                    source="你的画像",
                    detail=f"{len(profile.gaps) if profile else 0} 条缺口待补",
                    confidence=0.85,
                )
            ]
            context = self._context(
                ("还缺的（按这个排优先级）", self._gap_lines(profile)),
                ("我已经知道的", self._profile_lines(profile)),
                (
                    "他最近做过的事",
                    [f"{b.occurred_at.strftime('%m-%d')} {b.event_type.value}" for b in recent],
                ),
                ("他自己写下的", notes),
            )
            return await self._generate(
                user_id,
                "plan.todos",
                context_text=context,
                citations=citations,
                rationale="排序按「现在做最省力」：先补挡住后面几步的那一条，并给到具体时段。",
            )

        # plan.timetable
        #
        # 课表从哪来：**学生自己从教务系统导出后导入**（见 /app/academic/import）。
        # 学信网不提供课程表与成绩单，这一点过去写在注释里、界面上却含糊，
        # 于是"先绑学信网导课程"这句错话把用户指去了找不到东西的地方。
        #
        # 所以这里读一次真实快照：有课表就算空档，没有就如实说"还没导入"。
        snapshot = None
        if self._academic_records is not None:
            try:
                snapshot = await self._academic_records.get(user_id)
            except Exception:
                _log.exception("读取导入的课表失败：这一段按没有课表处理")
                snapshot = None

        courses = list(getattr(snapshot, "courses", []) or [])
        if not courses:
            citations = [
                Citation(
                    source="课表",
                    detail="还没有导入课程数据",
                    confidence=1.0,
                    origin="academic",
                )
            ]
            context = self._context(
                ("课表", ["还没有导入任何课程"]),
                ("还缺的", self._gap_lines(profile)),
            )
            envelope = await self._generate(
                user_id,
                "plan.timetable",
                context_text=context,
                citations=citations,
                rationale="没有课程时间就算不出空档；这一段缺的是数据，不是算法。",
            )
            # 空档是算出来的事实：没有课表就是没有空档，不许模型补一个。
            envelope.data = TimetablePlan(
                headline=envelope.data.headline, windows=[], moves=envelope.data.moves
            )
            return envelope

        windows = _free_windows(courses)
        citations = [
            Citation(
                source="你导入的课表",
                detail=f"{len(courses)} 门课 · {getattr(snapshot, 'term', '') or '本学期'}",
                confidence=1.0,
                origin="academic",
            )
        ]
        context = self._context(
            (
                "可投入的空档（原样引用，不要增删）",
                [f"{w['day']} {w['slot']}（{w['why']}）" for w in windows],
            ),
            ("还缺的", self._gap_lines(profile)),
            ("已经知道的", self._profile_lines(profile)),
        )
        envelope = await self._generate(
            user_id,
            "plan.timetable",
            context_text=context,
            citations=citations,
            rationale="空档从导入的课表里数出来；模型只负责说这段时间适合放什么。",
        )
        # 空档是**算出来的事实**，用它强制覆盖模型的输出：模型可以改措辞，
        # 不能改时间。一处对不上，用户照着排的事就落在上课时间上。
        envelope.data = TimetablePlan(
            headline=envelope.data.headline,
            windows=windows,
            moves=envelope.data.moves,
        )
        return envelope

    async def _match(self, user_id: str, profile: Optional[Profile], arg: str, *, by: str) -> AiResultEnvelope:
        """方向匹配：拿**外部职业要求**比**他实际具备什么**。

        这里原来有一份手写的需求矩阵（都是编的数），后来改成"只说明缺什么"。
        现在两头都有真来源了：职业要求由这个任务**自己调工具**从学职平台取，
        课程与成绩从导入的快照里读。所以它真的可以给出匹配 —— 前提是输入齐。

        输入不齐时仍然不给分：硬约束写在提示词里，模型只被允许在数据上做比较。
        """
        snapshot = None
        if self._academic_records is not None:
            try:
                snapshot = await self._academic_records.get(user_id)
            except Exception:
                _log.exception("读取导入的课表与成绩失败：匹配按没有成绩处理")
                snapshot = None
        grades = list(getattr(snapshot, "grades", []) or [])
        courses = list(getattr(snapshot, "courses", []) or [])

        citations = [
            Citation(
                source="职业能力要求",
                detail="由这次匹配自己从学职平台取（见工具调用记录）",
                confidence=1.0,
                origin="xuezhi",
            ),
            Citation(
                source="你的课程与成绩",
                detail=(
                    f"已导入：{len(grades)} 门成绩"
                    if grades
                    else "未导入：数据在教务系统，导出后导入即可"
                ),
                confidence=1.0,
                origin="academic",
            ),
        ]
        context = self._context(
            ("我已经知道的", self._profile_lines(profile)),
            (
                "他修过的课",
                [
                    f"{getattr(c, 'name', '')}（{getattr(c, 'credit', '')} 学分）"
                    for c in courses
                ],
            ),
            (
                "他的成绩",
                [
                    f"{getattr(g, 'name', '')}：{getattr(g, 'score', '')}"
                    for g in grades
                ],
            ),
        )
        return await self._generate(
            user_id,
            "match.careers",
            context_text=context,
            citations=citations,
            rationale=(
                "匹配 = 外部职业要求 × 他的实际能力。职业要求由本任务自己取；"
                "任何一项输入缺失就不给分 —— 编出来的契合度会被当成依据用。"
            ),
        )


"""节次 → 钟点。不同学校作息不同，所以只给一个**通用**区间，用于读起来像人话。"""
_PERIOD_CLOCK: tuple[str, ...] = (
    "08:00–08:45", "08:55–09:40", "10:00–10:45", "10:55–11:40",
    "13:30–14:15", "14:25–15:10", "15:30–16:15", "16:25–17:10",
    "18:30–19:15", "19:25–20:10", "20:20–21:05", "21:15–22:00",
)
_WEEKDAY_LABEL: tuple[str, ...] = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _free_windows(courses) -> list[dict]:
    """从**导入的课表**里数出空档。

    口径写在这里，因为它要能被解释：把一周按"上午 / 下午 / 晚上"切成三段
    （1-4 节、5-8 节、9-12 节），某一段里有 ≥2 节没课就算一段可投入窗口。
    只空一节的段不算 —— 一格放不下任何需要连续时间的事，列出来只是凑数。
    """
    busy: set[tuple[int, int]] = set()
    for course in courses:
        if course.weekday < 1 or course.weekday > 7:
            continue
        start = max(1, course.start_period)
        end = max(start, course.end_period or start)
        for period in range(start, end + 1):
            busy.add((course.weekday, period))

    windows: list[dict] = []
    for day in range(1, 8):
        for first, label in ((1, "上午"), (5, "下午"), (9, "晚上")):
            free = [p for p in range(first, first + 4) if (day, p) not in busy]
            if len(free) < 2:
                continue
            windows.append(
                {
                    "day": _WEEKDAY_LABEL[day - 1],
                    "slot": f"{label} {_PERIOD_CLOCK[free[0] - 1]}–{_PERIOD_CLOCK[free[-1] - 1]}",
                    "why": f"{label}连着 {len(free)} 节没课，是一整块时间",
                }
            )
    return windows


__all__ = ["AiTaskService"]
