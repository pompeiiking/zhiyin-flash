"""编排器默认实现：读黑板 → 判环节 → 选主理 → 产出 → 行为引导。"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import uuid4


from zhiyin_business.contracts import STAGE_CONTRACTS
from zhiyin_business.policies.intel_labels import kind_label, source_name_of
from zhiyin_business.policies.intel_query import intel_topic
from zhiyin_business.contracts.common import (
    AgentBadge,
    BehaviorEventDraft,
    BehaviorGuide,
    ConversationMessage,
    Disclosure,
    GuideOption,
    IntelRef,
    Renderable,
    TheoryRef,
)
from zhiyin_business.policies.handoff import HandoffPolicy
from zhiyin_business.policies.renderers import validate_renderables
from zhiyin_business.policies.routing_rules import CLARIFY_PROMPT_CODE
from zhiyin_business.policies.routing import IntentPolicy, StagePolicy
from zhiyin_business.policies.teaming import LeadPolicy
from zhiyin_business.ports.blackboard import (
    AssetService,
    BehaviorService,
    BlackboardView,
    ConversationMemoryService,
    ProfileService,
)
from zhiyin_business.ports.orchestrator import (
    HandoffDecision,
    IntentType,
    LeadDecision,
    Orchestrator,
    TurnRequest,
    TurnResult,
)
from zhiyin_business.ports.registry import RegistryService
from zhiyin_business.ports.function import FunctionService
from zhiyin_data_sdk.errors import MissingConfigError
from zhiyin_data_sdk.repositories import TaskSessionRepository
from zhiyin_kernel.blackboard import AssetVersion, TaskSession
from zhiyin_kernel.assets import GapClaim
from zhiyin_kernel import dynamic_config
from zhiyin_business.policies.collection import may_override_user_edit
from zhiyin_business.services.tool_offers import TOOL_OFFERS, mentioned_tasks, proposal_at_end, task_offer
from zhiyin_business.policies.collection_gate import CollectionGate, evaluate_gate
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_kernel.enums import (
    AssetType,
    AxisAStage,
    BehaviorEventType,
    ProfileSource,
    LoopStage,
    TaskStatus,
)
from zhiyin_kernel.registry import PromptSpec
from zhiyin_orchestration import (
    AgentEngine,
    AgentRequest,
    DataSourceRequest,
    EventBus,
    ExternalDataSource,
)

def _forbids_profile_write(message: str) -> bool:
    return bool(re.search(r"(?:不要|别|无需|不必|不想).{0,8}(?:记|保存|写入|更新).{0,8}(?:画像|经历|信息|资料)", message))


def _contains_personal_disclosure(message: str) -> bool:
    if _forbids_profile_write(message):
        return False
    return bool(re.search(r"我(?:曾经|之前|现在|目前|还|也|比较|最)?(?:做过|参加过|参与过|实习过|喜欢|擅长|学过|学习过|希望|想去|计划去|就读|毕业|主修|是大[一二三四])|我的(?:专业|兴趣|经历|能力|目标|学校|年级|毕业时间)(?:是|为|叫|有)", message))


def _direct_field_updates(structured: dict[str, Any], message: str) -> dict[str, Any]:
    """Only allow updates with a nonempty evidence excerpt from this user turn."""
    updates = []
    for item in structured.get("field_updates") or []:
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence")
        if isinstance(evidence, list) and any(isinstance(e, str) and len(e.strip()) >= 3 and e.strip() in message for e in evidence):
            updates.append(item)
    return {"field_updates": updates}


def _explicit_plan_request(message: str) -> bool:
    """Only a user's affirmative request can create or replace an action plan."""
    # A later explicit prohibition must win over an earlier generation request:
    # this system stores one current plan and cannot create an isolated draft.
    # 实测漏网：**"先别改"里的"改"不在原来的否定词表**（原表只认保存/覆盖/更新/…），
    # 于是"如果把任务都改到周末…先别改，我只是问问"被当成明确改计划，静默重写了计划。
    if re.search(
        r"(?:先?别|不要|不必|无需|暂不|不能|不想|不用).{0,8}"
        r"(?:改|动|改计划|动计划|保存|覆盖|更新|修改|调整|替换|写进|写入)",
        message,
    ):
        return False
    if re.search(
        r"(?:只是问问|先问问|随便问问|先不改|先别改|先别动|先不要|先不动|别动|别改|别保存)",
        message,
    ):
        return False
    # 假设/讨论（"如果改到周末会有什么影响"）不是执行：除非同一句里已有明确执行确认。
    # "按这个方案改会怎样"里的"按这个…改"是假设动作本身，不能当成确认；只有
    # "确认保存/就按这个执行/开始改"这类明确执行才覆盖假设。
    if (
        re.search(r"(?:如果|假如|假设|要是)", message)
        and re.search(r"(?:会有什么影响|有什么影响|会怎样|怎么样|影响如何|会不会)", message)
        and not re.search(
            r"(?:确认.{0,10}(?:保存|执行|应用)|保存吧|执行吧|开始改|"
            r"就这么(?:改|定|办)|就按这个(?:保存|执行))",
            message,
        )
    ):
        return False
    # 对上一轮草案的明确确认也是执行：实测"确认按这个安排保存"原来识别不到。
    # 只认"保存/执行/应用"这类落库动作；单纯"按这个方案改"可能仍是在讨论。
    if re.search(
        r"(?:确认|就按|按这个|按刚才|按上述|按该).{0,12}"
        r"(?:安排|方案|草案|计划).{0,10}(?:保存|执行|应用)"
        r"|(?:确认|就按|按这个|按刚才).{0,8}(?:保存|执行|应用)",
        message,
    ):
        return True
    if re.search(r"(?:未|没有|没|尚未|还没|是否|有没有|会不会|怎么|如何).{0,8}(?:生成|创建|制定|保存)", message):
        return False
    pattern = r"(?:生成|制定|创建|建立|制订|重做|重新|调整|修改|改|安排|规划|给我一份|给我一个|帮我做).{0,18}(?:计划|阶段|任务|行动)|(?:计划|阶段|任务|行动).{0,12}(?:生成|制定|创建|建立|重做|调整|修改|改|安排|规划)"
    for clause in re.split(r"[，。；！？\n]", message):
        match = re.search(pattern, clause)
        if match and not re.search(r"(?:不要|不必|无需|暂不|别|不能|不想|不再|不)", clause[: match.end()]):
            return True
    return False


def _wants_view_report(message: str) -> bool:
    """用户是在"要看报告"，而不是"要生成报告"。"""
    if re.search(r"(?:不要|别|不用|先不).{0,6}(?:看|打开|查看)", message):
        return False
    return bool(
        re.search(
            r"(?:看|查看|打开|瞧瞧|给我看|看一下|点开).{0,8}(?:我的)?(?:诊断|评估)?报告"
            r"|(?:诊断|评估)?报告.{0,6}(?:在哪|看一下|打开|看看)",
            message,
        )
    )


def _wants_view_plan(message: str) -> bool:
    """用户是在"要看计划"，而不是"要生成计划"。"""
    if re.search(r"(?:不要|别|不用|先不).{0,6}(?:看|打开|查看)", message):
        return False
    return bool(
        re.search(
            r"(?:看|查看|打开|瞧瞧|给我看|看一下|点开).{0,8}(?:我的)?(?:行动|阶段)?计划"
            r"|(?:行动|阶段)?计划.{0,6}(?:在哪|看一下|打开|看看)",
            message,
        )
    )


def _explicit_report_request(message: str) -> bool:
    if re.search(r"(?:不要|不必|无需|暂不|别|不能|不想|先不|不用).{0,12}(?:诊断|报告|生成|保存|更新|修改|重算)|不(?:生成|创建|保存|更新|修改|重算|诊断)", message):
        return False
    if re.search(r"(?:未|没有|没|尚未|还没|是否|有没有|会不会|怎么|如何).{0,8}(?:生成|创建|保存)", message):
        return False
    return bool(re.search(r"(?:生成|创建|做|进行|重新生成|更新|重算|给我一份).{0,18}(?:诊断|报告)|(?:诊断报告|评估报告).{0,12}(?:生成|创建|重做|更新|重算)", message))


# The complete question is stored in the actual assistant turn, so confirmation
# survives refresh/restart and is bound to the immediate previous turn/session.
_ASSET_OFFERS = {
    "report": "目前的信息可以开始整理，要生成一份诊断报告吗？",
    "plan": "可以把接下来的行动整理成计划，要现在创建吗？",
}


_CN_ORDINAL = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "七": 6, "八": 7, "九": 8, "十": 9,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6, "8": 7, "9": 8, "10": 9,
}


def _task_operation_intent(message: str) -> bool | None:
    """用户在说"任务完成"（True）还是"恢复未完成"（False）；没提到就 None。

    深度测试实测：对话回复"第一项勾掉了"，计划页仍 0/9 —— 模型只是在说话，
    并没有调用 `workspace.task.set_done`。这里把**可判定**的完成/恢复语句
    直接执行掉，不依赖模型是否记得调用工具。
    """
    text = message or ""
    if re.search(r"(?:恢复|撤销|取消完成|取消勾选|改回|点错|标错|没做完|还没做|别标|不要标)", text):
        return False
    if re.search(r"(?:做完|完成|搞定|勾掉|划掉|写完了|投完了|弄完了|已经做|已做|已经投|已投|弄完)", text):
        return True
    return None


def _resolve_task_for_operation(plan, message: str):
    """按"完整任务名 / 第 N 项 / 已唯一完成项"定位一条任务；不唯一就返回 None。"""
    tasks = [
        task
        for phase in (plan.phases if plan else [])
        for task in phase.tasks
        if task.text
    ]
    if not tasks:
        return None
    exact = [task for task in tasks if task.text in message]
    if len(exact) == 1:
        return exact[0]
    ordinal = re.search(r"第\s*([一二三四五六七八九十\d]+)\s*(?:项|个|件|条)?", message)
    if ordinal:
        index = _CN_ORDINAL.get(ordinal.group(1))
        if index is not None and 0 <= index < len(tasks):
            return tasks[index]
    if _task_operation_intent(message) is False:
        completed = [task for task in tasks if task.done]
        if len(completed) == 1:
            return completed[0]
    return None


_STUDY_YEAR_VALUES = (
    "大一",
    "大二",
    "大三",
    "大四",
)


def _study_year_from_text(message: str) -> str | None:
    """从"我现在大三了/把学习阶段改成大三"里取出学习阶段。

    只认**本人当前状态**或**明确更正**；假设句("如果我大三")不触发，
    避免把假设写进正式档案。
    """
    text = message or ""
    if re.search(r"(?:如果|假如|假设|要是)", text):
        return None
    value = r"(大[一二三四])"
    patterns = (
        r"(?:我现在|目前|现在|已经|已|今年|刚|开学)(?:是|读|上|升|在)?[^。；\n]{0,6}?" + value,
        r"我(?:是|读|上)" + value,
        r"(?:改|调|更新|换|设置|更正)(?:成|为|到)?[^。；\n]{0,6}?" + value,
        r"(?:不是|不再是)" + value,
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _explicit_profile_correction(message: str) -> dict[str, str]:
    """可判定的本人更正/本人陈述：返回 `{画像字段键: 新值}`。

    覆盖深度测试 STU-007：对话里"把专业改成…/我的专业是…/记到项目经历里"
    既没有写工具、又会被"本人已编辑字段"保护挡住，结果回复说"记下了"而画像没变。
    这里只收**明确陈述/明确更正**，不从闲聊里猜。
    """
    corrections: dict[str, str] = {}
    text = message or ""
    if re.search(r"(?:如果|假如|假设|要是)", text):
        return corrections
    year = _study_year_from_text(text)
    if year:
        corrections["study_year"] = year

    def clean(value: str) -> str:
        value = value.strip(" \t\r\n，。；,;！？!?：:")
        value = re.sub(r"^(?:我|本人)(?:的)?", "", value).strip()
        return value

    major = re.search(
        r"(?:把|将)?(?:我的)?专业(?:改成|改为|换成|更正为|调整为|是|为)\s*"
        r"([^，。；,;！？!?]{2,40})",
        text,
    )
    if major:
        value = clean(major.group(1))
        if value:
            corrections["major"] = value

    school = re.search(
        r"(?:把|将)?(?:我的)?(?:学校|就读学校|毕业学校)(?:改成|改为|换成|更正为|是|为)\s*"
        r"([^，。；,;！？!?]{2,40})",
        text,
    )
    if school:
        value = clean(school.group(1))
        if value:
            corrections["school"] = value

    degree = re.search(
        r"(?:把|将)?(?:我的)?(?:学历|层次|学位)(?:改成|改为|换成|更正为|是|为)\s*"
        r"(本科|硕士|博士|研究生|专科|大专)",
        text,
    )
    if degree:
        corrections["degree_level"] = degree.group(1)

    # "我参加过XX竞赛，帮我记到项目经历里" / "记一下经历：XX"
    experience = re.search(
        r"(.{4,120}?)[，,；;]?\s*(?:帮我|请)?\s*(?:记到|记一下|记录一下|放到|放进|加到)"
        r"(?:我的)?(?:项目|实习|科研|竞赛)?(?:经历|实践)",
        text,
    )
    if experience:
        value = clean(experience.group(1))
        if len(value) >= 4:
            corrections["experience"] = value
    else:
        record = re.search(
            r"(?:记一下|记录一下|帮我记)(?:我的)?(?:项目|实习|科研|竞赛)?(?:经历|实践)"
            r"\s*[：:,，]\s*(.{4,200})$",
            text,
        )
        if record:
            value = clean(record.group(1))
            if value:
                corrections["experience"] = value
    return corrections


def _offer_answer(message: str) -> str | None:
    text = re.sub(r"[\s，。！？、,.!?]+", "", message)
    if re.fullmatch(r"(?:先不要|暂时不要|暂不|不要|不需要|不用|先不|算了|稍后|以后再说|再等等|等等|不了|不必)", text):
        return "decline"
    if re.fullmatch(r"(?:可以|可以的|好的|好啊|好呀|好|行的|行|没问题|当然|嗯|嗯嗯|是的|是|同意|确认|确定|开始吧|现在开始|生成吧|创建吧|请生成|请创建|要|需要|帮我生成|帮我创建)", text):
        return "accept"
    # An affirmative may also include a useful constraint. Questions and
    # reservations do not authorize a write; the original text goes to the AI.
    if (re.match(r"^\s*(?:可以|好的|好|行|同意|确认|确定)[，,。]\s*\S", message)
            and not re.search(r"[？?]|不要|不用|不想|不必|无需|先不|暂不|先别|别.{0,8}(?:做|生成|创建|保存|修改|替换)|暂缓|没想好|不确定|算了|等等|稍后|下次|以后|不急", message)):
        return "accept"
    return None


logger = logging.getLogger(__name__)

# 取数来源标识（数据，不是依赖）：换数据源只改装配层，本文件不动。
_EXTERNAL_SOURCE = "xuezhi"

# 用户可见文案一律来自动态资源，不在代码里拼。
# 这两个 code 是「换主理告知」的模板与它按环节分条的原因；澄清话术的 code
# 由规则实现持有（它同时是那条策略的一部分），这里复用同一个常量。
_LEAD_CHANGE_PROMPT = "disclosure.lead_change"
_LEAD_CHANGE_REASON_PROMPT = "disclosure.reason.{stage}"
#: 结论变化告知：画像补了新信息、这一版跟着重算过时要说的那句。
#: 它是设计里三种告知（换主理 / 换理论 / 结论变化）的第三种。
_CONCLUSION_CHANGE_PROMPT = "disclosure.conclusion_change"
#: 本人填写未被覆盖告知：他刚说的那句撞上他自己填过的格子、被挡下时说的那句。
#: 挡下是**设计如此**（见 `_apply_collect`），但挡下必须说出来 —— 不说的症状是
#: "我说了它不听"：画像一动不动、界面上一个字都没有，他只能再改一次、再被挡一次。
_FIELD_KEPT_PROMPT = "disclosure.field_kept_by_user"
# 外部事实：哪些环节**主动去取**，哪些环节**只用手上有的**。
#
# 分两档，判据是"没它会不会自己编"：
#
#   · 主动取 —— ② 诊断要有依据、③ 决策要有选项、④ 行动要有样板。
#     这三环少了外部事实，模型只能拿画像硬凑，而"硬凑的岗位要求"看起来和真的一样。
#   · 只读缓存 —— ① 采集问的是"你的情况"，⑤ 复盘问的是"这段时间的事"：
#     外部事实是加分项，不是依据来源。缓存里有就用（例如用户刚开过情报面板），
#     没有就不取，这一轮照常答。
#
# 为什么要把这条线划出来（实测数据）：采集阶段的每个回合都会去爬一遍学职平台
# —— 10 次请求、约 7 秒，而这一轮总共才 15 秒。用户等的就是这几秒，
# 站点也被白打一遍。设计文档 9.3 第 8 步写的是"只在诊断 / 决策 / 行动三个环节取"，
# 代码一度扩到五个环节，现在按文档收回来。
_EXTERNAL_FETCH_STAGES = frozenset(
    {LoopStage.DIAGNOSE, LoopStage.DECIDE, LoopStage.ACT}
)
_EXTERNAL_CACHE_ONLY_STAGES = frozenset({LoopStage.COLLECT, LoopStage.REVIEW})


@dataclass(frozen=True)
class CollectWriteResult:
    """① 采集这一轮写画像留下了什么。

    为什么要有个返回值，而不是只写日志：`_apply_collect` 现在有三类"没写进去"，
    它们的原因完全不同，混在日志里查不动 ——
    `written` 是真写进去了，`dropped_by_gate` 是键不在词表里（提示词该补同义词），
    `blocked_by_user_edit` 是他自己更正过、推断不许盖（这是**设计如此**，不是缺陷）。
    它已经有了消费方：`handle_message` 拿 `blocked_by_user_edit` 拼成一条 `Disclosure`
    说给用户听（挡下是设计如此，但**不能只留在日志里**）。同一份返回值也喂日志与守卫测试。
    """

    written: tuple[str, ...] = ()
    blocked_by_user_edit: tuple[str, ...] = ()
    dropped_by_gate: tuple[str, ...] = ()


class DefaultOrchestrator(Orchestrator):
    """职引业务编排器。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        profiles: ProfileService,
        behaviors: BehaviorService,
        memories: ConversationMemoryService,
        assets: AssetService,
        intent_policy: IntentPolicy,
        stage_policy: StagePolicy,
        lead_policy: LeadPolicy,
        handoff_policy: HandoffPolicy,
        agent_engine: AgentEngine,
        sessions: TaskSessionRepository,
        registry: RegistryService,
        event_bus: EventBus,
        functions: FunctionService | None = None,
        data_sources: ExternalDataSource | None = None,
        read_cache: Any = None,
        student_state=None,
    ) -> None:
        self._student_state = student_state
        self._profiles = profiles
        self._behaviors = behaviors
        self._memories = memories
        self._assets = assets
        self._intent_policy = intent_policy
        self._stage_policy = stage_policy
        self._lead_policy = lead_policy
        self._handoff_policy = handoff_policy
        self._agent_engine = agent_engine
        self._sessions = sessions
        self._registry = registry
        self._event_bus = event_bus
        # ④ 行动产出的关键节点要写进日历（规划师写入、教练读取）。
        # 可选：单测里可以只构造编排器本身；缺它就跳过日历登记，
        # 但**不跳过行动计划的落库** —— 计划正文与日历是两件事。
        self._functions = functions
        self._data_sources = data_sources
        # 读缓存（可缺省）：一轮对话可能改了画像、资产、行为 —— 那些都让工作台那一片作废。
        # 注入的是业务侧服务（`ReadCacheService`），这里只报"发生了什么"。
        self._cache = read_cache

    async def _fetch_external(
        self,
        *,
        user_id: str,
        message: str,
        profile_fields: Sequence[Any],
        allow_fetch: bool = True,
    ) -> dict[str, Any] | None:
        """这一轮的外部事实。

        `allow_fetch=False`（① 采集 / ⑤ 复盘）时**只读缓存、不打站点**：
        缓存里没有就如实报"这一轮没有外部事实"，而不是让用户等七八秒换一批
        他这一轮用不上的东西。理由与两档划分见 `_EXTERNAL_FETCH_STAGES`。

        两条路，优先走**功能块服务**（生产环境装配的就是它）：

        1. `functions.fetch_external_intel` —— 它自己读画像、按主题取数，
           带 900 秒缓存、按 (人, 主题) 分桶，画像变了会被事件清掉；
        2. 取数原语（`data_sources`）—— 单测里只装它一个时用这条，
           保持"取数是增强，不是硬前置"。

        为什么优先前者：面板与推送走的就是它。两边共用一次取数、一份缓存、
        一个主题口径，用户打开面板看到的那一批，和主理刚才引用的那一批
        才是同一批 —— 否则界面上会出现"两批都叫外部情报、内容却不一样"。

        **主题从画像推**（`intel_topic`），不拿用户原话当检索词：
        他说"嗯"的时候，原话里没有任何领域信息，而画像里有。
        主题为空是合法的 —— 取数侧会退回平台通用数据，而不是拿一句猜的话去查。
        """
        topic = intel_topic(profile_fields)

        if self._functions is not None:
            try:
                items = await self._functions.fetch_external_intel(
                    user_id, topic=topic, limit=8, allow_fetch=allow_fetch
                )
            except Exception:  # noqa: BLE001 - 取不到不算这一轮失败，如实报空
                logger.warning("外部情报取数失败（topic=%s），这一轮按没有处理", topic, exc_info=True)
                items = []
            return {
                "source": _EXTERNAL_SOURCE,
                "records": [item.model_dump(mode="json") for item in items],
                # 只读缓存且没命中 → 如实标注"这一轮没有"，不谎称取过又取不到。
                "degraded": not allow_fetch and not items,
                "topic": topic,
            }

        if self._data_sources is None:
            return None
        if not allow_fetch:
            # 取数原语没有缓存这一层：这一档直接不给事实，也不打站点。
            return {
                "source": _EXTERNAL_SOURCE,
                "records": [],
                "degraded": True,
                "topic": topic,
            }
        external = await self._data_sources.fetch(
            DataSourceRequest(
                source=_EXTERNAL_SOURCE,
                query=message,
                limit=8,
                context={
                    "fields": [
                        field.model_dump(mode="json") for field in profile_fields
                    ],
                    # 主题一并下发：适配器可以据此决定检索词，
                    # 不必自己再从字段里推一遍（口径只在一处）。
                    "topic": topic,
                },
            )
        )
        dumped = external.model_dump(mode="json")
        dumped["topic"] = topic
        return dumped

    async def _run_info_scout(self, external: dict[str, Any], stage: LoopStage) -> list[dict[str, Any]]:
        """Give the enabled scout its own model call, then keep only verifiable URLs.

        The raw records came from the external-data gateway. The scout can shorten and
        classify them, but cannot introduce another source: every returned source_url
        must exactly match one of those records. If the scout is unavailable or returns
        unusable output, the original linked records remain the factual fallback.
        """
        from zhiyin_business.contracts.diagnose import FactItem, ScoutOutput

        records = [row for row in external.get("records", []) if isinstance(row, dict)]
        allowed = {str(row.get("source_url") or "") for row in records}
        allowed.discard("")
        fallback = [
            FactItem(
                topic=kind_label(str(row.get("kind") or "")) or "外部事实",
                content=str(row.get("text") or row.get("title") or "")[:500],
                source=str(row.get("source_name") or source_name_of(str(row.get("source_url") or ""))),
                source_url=str(row.get("source_url") or ""),
                fetched_at=str(row.get("fetched_at") or ""),
            ).model_dump(mode="json")
            for row in records
            if row.get("source_url") and (row.get("text") or row.get("title"))
        ]
        if not fallback:
            return []
        try:
            result = await self._agent_engine.invoke(
                AgentRequest(
                    agent_id="info_scout",
                    stage=stage.value,
                    prompt_code="role.info_scout",
                    use_tools=False,
                    prompt_vars={"external_data": external},
                    output_schema=ScoutOutput.model_json_schema(),
                )
            )
            if result.valid:
                output = ScoutOutput.model_validate(result.structured)
                verified = [item.model_dump(mode="json") for item in output.facts if item.source_url in allowed]
                if verified:
                    return verified
        except Exception:  # noqa: BLE001 - 外部事实已有原始记录，侦查员失败不应中断主回答
            logger.warning("信息侦查员整理失败，保留原始可核对记录", exc_info=True)
        return fallback

    async def read_blackboard(self, user_id: str, task_id: str) -> BlackboardView:
        session = await self._sessions.get(task_id)
        asset_versions = []
        for asset_type in (AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN):
            versions = await self._assets.list_versions(user_id, asset_type)
            if versions:
                asset_versions.append(versions[-1])
        return BlackboardView(
            user_id=user_id,
            task_id=task_id,
            profile=await self._profiles.get(user_id),
            recent_behaviors=await self._behaviors.recent(user_id, limit=50),
            memories=await self._memories.list_by_user(user_id),
            asset_versions=asset_versions,
            current_stage=session.loop_stage if session else None,
        )

    async def collection_gate(self, user_id: str) -> "CollectionGate":
        """判一次"采集够了吗"（策略来自动态资源，见 `policies/collection_gate.py`）。

        门槛写成一条可数的规则，是为了让"什么时候往下走"不再由模型自由心证 ——
        真实用户遇到的就是反例：他只想聊两句，系统却一条接一条问下去。
        """
        fields = await self._profiles.get_fields(user_id)
        policy = await self._registry.get_collection_policy()
        # 采集登记表要和"来源相称"那一维一起交进去：权威字段（学信网 / 教务导入）
        # 由对话写进来时不算覆盖。不交表就只能按模块内置兜底表判，
        # 而"哪个字段该由谁出具"以库为准（与 workspace / ai_tasks 同一份读法）。
        rules = list(dynamic_config.snapshot().collection_rules) or None
        gate = evaluate_gate(fields, policy, rules=rules)
        logger.info("采集门槛：%s", gate.line)
        return gate

    # ---------- 资产创建提议（报告 / 计划）的持久化 ----------
    #
    # 提议文本原本只存在"上一条主理消息"里：用户如果先回了一句别的话，
    # 上一轮就被顶掉，提议随之消失 —— 实测清空后无论再说「可以」还是
    # 「生成报告」都得重来一次，新手会以为"它答应过却什么都没做"。
    # 这里把待确认的提议写进账号级状态，按时间过期，确认/拒绝时清掉。

    _PENDING_OFFER_KEY = "pending_asset_offer"
    _PENDING_OFFER_TTL_S = 2 * 24 * 3600

    async def _pending_asset_offer(self, user_id: str, task_id: str) -> str | None:
        if self._student_state is None:
            return None
        try:
            state = await self._student_state.get(user_id) or {}
        except Exception:  # noqa: BLE001 - 读不到就当没有，不影响本轮对话
            logger.warning("读取待确认提议失败，本轮按无提议处理", exc_info=True)
            return None
        record = state.get(self._PENDING_OFFER_KEY)
        if not isinstance(record, dict):
            return None
        kind = str(record.get("kind") or "")
        if kind not in _ASSET_OFFERS:
            return None
        # 确认必须发生在**提出提议的同一个会话**里：在另一个话题里说「可以」
        # 不构成授权（会话所有权不同，用户说的是另一件事）。
        if str(record.get("task_id") or "") != (task_id or ""):
            return None
        try:
            created_at = datetime.fromisoformat(str(record.get("at") or ""))
        except ValueError:
            return None
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - created_at).total_seconds() > self._PENDING_OFFER_TTL_S:
            return None
        return kind

    async def _set_pending_asset_offer(
        self, user_id: str, kind: str | None, *, task_id: str = ""
    ) -> None:
        if self._student_state is None:
            return

        def change(state: dict) -> dict:
            state = dict(state or {})
            if kind in _ASSET_OFFERS:
                state[self._PENDING_OFFER_KEY] = {
                    "kind": kind,
                    "task_id": task_id or "",
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                state.pop(self._PENDING_OFFER_KEY, None)
            return state

        try:
            await self._student_state.update(user_id, change)
        except Exception:  # noqa: BLE001 - 持久化失败不能打断这一轮对话
            logger.warning("保存待确认提议失败（本轮对话继续）", exc_info=True)

    async def infer_axis_a(self, user_id: str, task_id: str) -> AxisAStage:
        blackboard = await self.read_blackboard(user_id, task_id)
        profile = blackboard.profile
        fields = {field.key: field for field in (profile.fields if profile else [])}
        if "target_direction" not in fields:
            return AxisAStage.EXPLORE_SELF
        if not any(item.asset_type == AssetType.REPORT for item in blackboard.asset_versions):
            return AxisAStage.VERIFY_DIRECTION
        if any(item.asset_type == AssetType.ACTION_PLAN for item in blackboard.asset_versions):
            if any(
                behavior.event_type == BehaviorEventType.TASK_STALL
                for behavior in blackboard.recent_behaviors
            ):
                return AxisAStage.REPOSITION
            if any(
                behavior.event_type
                in {BehaviorEventType.TASK_DONE, BehaviorEventType.REVIEW}
                for behavior in blackboard.recent_behaviors
            ):
                return AxisAStage.ADAPT
            return AxisAStage.SPRINT_ACTION
        return AxisAStage.VERIFY_DIRECTION

    async def select_lead(
        self,
        user_id: str,
        task_id: str,
        axis_a: AxisAStage,
        stage: LoopStage,
        intent: IntentType,
    ) -> LeadDecision:
        blackboard = await self.read_blackboard(user_id, task_id)
        return await self._lead_policy.select(
            blackboard=blackboard,
            axis_a=axis_a,
            stage=stage,
            intent=intent,
        )

    async def handoff(
        self, user_id: str, task_id: str, to_stage: LoopStage, reason: str
    ) -> HandoffDecision:
        session = await self._sessions.get(task_id)
        if session is None:
            raise ResourceNotFound(f"任务会话不存在：{task_id}")
        _require_owner(session, user_id)
        blackboard = await self.read_blackboard(user_id, task_id)
        axis_a = await self.infer_axis_a(user_id, task_id)
        lead = await self.select_lead(
            user_id, task_id, axis_a, to_stage, IntentType.FREE_CHAT
        )
        decision = self._handoff_policy.decide(
            blackboard=blackboard,
            from_stage=session.loop_stage,
            from_agent=session.lead_agent,
            to_stage=to_stage,
            to_agent=lead.lead_agent,
            reason=reason,
        )
        if decision.disclosure is None:
            decision = decision.model_copy(
                update={
                    "disclosure": Disclosure(
                        kind="lead_change",
                        text=reason,
                        from_agent=session.lead_agent,
                        to_agent=lead.lead_agent,
                    )
                }
            )
        await self._sessions.update_stage(session.id, to_stage, lead.lead_agent)
        return decision

    async def enter_task(
        self, user_id: str, task_code: str, *, new_session: bool = False
    ) -> TaskSession:
        """进入任务：已有进行中的会话则续接，否则按任务入口建会话。

        `new_session=True` 时**不续接**：把同入口还在进行中的旧会话标记完成
        （仍留在左栏历史里可打开），再建一条新的。少了这个分支，「新建咨询」
        永远返回同一条会话 —— 用户以为开了新对话，看到的却是旧内容。

        未登记的 `task_code` **必须报错**，不能静默建一个名字等于 code 的会话：
        任务码是前端从 `/app/bootstrap` 的 `task_entries` 里取的，拼错的唯一原因
        是前端与动态资源不同步 —— 静默兜底会把这件事盖住，用户看到的是一句
        自己看不懂的「任务名」，而没有任何一处报错。

        `free_chat` 这类**已登记但没有目标环节 / 主理**的入口不受影响：
        它走下面的回落分支（环节 ①、主理由组队规则选）。
        """
        existing = await self._sessions.find_active(user_id, task_code)
        if existing is not None and not new_session:
            return existing

        entries = {entry.code: entry for entry in await self._registry.list_task_entries()}
        spec = entries.get(task_code)
        if spec is None:
            raise ResourceNotFound(
                f"未登记的任务入口：{task_code}。任务码须取自 /app/bootstrap 的 task_entries"
            )
        task_name = spec.label or task_code

        if new_session:
            # 旧会话不删除：标成已完成，历史里仍能打开；find_active 只找 active，
            # 之后同一入口的"续接"就会命中这条新会话。
            for item in await self._sessions.list_by_user(
                user_id, statuses=[TaskStatus.ACTIVE]
            ):
                if item.task_code == task_code and item.id != "":
                    await self._sessions.update_status(item.id, TaskStatus.COMPLETED)

        if spec.target_stage is not None:
            stage: LoopStage = spec.target_stage
        else:
            # 直接开聊：没有任务入口可依，回落 ① 采集（与 handle_message 兜底一致）。
            stage = LoopStage.COLLECT

        if spec.lead_agent:
            lead_agent = spec.lead_agent
        else:
            axis_a = await self.infer_axis_a(user_id, task_id="")
            lead = await self.select_lead(
                user_id, task_id="", axis_a=axis_a, stage=stage, intent=IntentType.FREE_CHAT
            )
            lead_agent = lead.lead_agent

        now = _now()
        session = await self._sessions.create(
            TaskSession(
                id=f"task-{uuid4().hex[:12]}",
                user_id=user_id,
                task_code=task_code,
                task_name=task_name,
                loop_stage=stage,
                lead_agent=lead_agent,
                status=TaskStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        return session

    async def handle_message(self, request: TurnRequest) -> TurnResult:
        from zhiyin_business.services.analysis_access import activate, load_scope

        scope = await load_scope(self._student_state, request.user_id)
        if "material" not in scope.sources and (request.attachment_text or request.attachment_name):
            error = InvalidRequest("上传材料参与分析已关闭，请移除附件后发送，或在资料偏好中开启。")
            error.user_facing = True
            raise error
        with activate(scope):
            return await self._handle_message(request)

    async def _handle_message(self, request: TurnRequest) -> TurnResult:
        session = await self._sessions.get(request.task_id)
        if session is None:
            session = await self._sessions.create(
                TaskSession(
                    id=request.task_id,
                    user_id=request.user_id,
                    task_code="free_chat",
                    task_name="直接开聊",
                    loop_stage=LoopStage.COLLECT,
                    lead_agent="profile_analyst",
                    status=TaskStatus.ACTIVE,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
        else:
            # 会话仓储只按 task_id 取（契约如此），归属校验必须在这里做。
            # 不校验的后果是：任何已登录用户只要拿到别人的 task_id，就能读到并
            # 继续推进别人的会话（IDOR）。按"不存在"处理而不是 403 ——
            # 不向调用方暴露"这个 id 确实存在"，也避免前端把它误读成登录态问题。
            _require_owner(session, request.user_id)

        # 幂等：同一条消息重发（双击发送、断网重试）直接返回上一次的答复。
        #
        # 前端每条消息都带 `client_msg_id`，而这条链路上**从来没有人读它** ——
        # 双击一次就是两条轮次 + 两次模型调用：记录里多一段重复的往返，
        # 用户白等一次，钱也白花一次。设计文档 9.3 第 1 步写的正是这一条。
        #
        # 重放的是**主理那一条原文**，不重放"下一步"引导：再推一次同一个问题，
        # 用户会以为又发生了什么（那时他自己已经答过了）。
        if request.client_msg_id:
            replay = await self._replay_reply(request, session)
            if replay is not None:
                return replay

        # 用户这句话**先落库**，再调模型。
        #
        # 轮末的 `_remember_turn` 只有走到终点才会写；而模型超时、用户点"停止"、
        # 或直接刷新页面都会让这条路径中途返回 —— 实测这三种情况下刷新后刚发
        # 的那句凭空消失，用户看到的就是"会话没保存"。先写用户这一轮，最坏
        # 结果是"有提问、暂时没有回答"，也比整句话丢掉诚实。
        try:
            if not await self._user_turn_saved(request):
                await self._memories.record_turn(
                    request.user_id,
                    request.task_id,
                    role="user",
                    text=request.message,
                    loop_stage=session.loop_stage,
                    client_msg_id=request.client_msg_id or "",
                )
        except Exception:  # noqa: BLE001 - 落库失败不能挡住这一轮对话
            logger.warning("用户这一轮先落库失败（本轮对话继续）", exc_info=True)

        # 本人明确更正画像：**系统直接改**，不等模型"记得调用工具"。
        # 深度测试实测：说"我现在已经大三了，不是大二"，回复称已改，画像仍大二；
        # 报告却按大三写，档案/对话/报告三方不一致。这里只处理可判定的学习阶段，
        # 写 user_edit（本人更正）来源，并在回复里插入一条系统说明。
        profile_correction_note = ""
        protected_profile_values: dict[str, str] = {}
        corrections = _explicit_profile_correction(request.message)
        if corrections:
            field_labels = {
                "study_year": "当前学习阶段",
                "major": "专业",
                "school": "学校",
                "degree_level": "层次",
                "experience": "经历",
            }
            changed: list[str] = []
            for key, value in corrections.items():
                # "项目经历"是累加的：本人补充一段经历，不能覆盖掉之前记过的。
                if key == "experience":
                    try:
                        existing_fields = await self._profiles.get_fields(
                            request.user_id, [key]
                        )
                    except Exception:  # noqa: BLE001
                        existing_fields = []
                    existing = (
                        str(existing_fields[0].value).strip()
                        if existing_fields and existing_fields[0].value
                        else ""
                    )
                    if existing and value not in existing:
                        value = f"{existing}；{value}"
                field = None
                try:
                    field = await self._profiles.correct_field(
                        request.user_id, key, value
                    )
                except InvalidRequest:
                    # 某些装配下词表没有把该键登记进"可更正"清单（测试/精简装配），
                    # 但本人明确说出的更正仍要落库：退回 update_field，来源仍记"本人更正"。
                    try:
                        field = await self._profiles.update_field(
                            request.user_id,
                            key,
                            value,
                            confidence=1.0,
                            source=ProfileSource.USER_EDIT.value,
                            label=field_labels.get(key, ""),
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "对话内更正画像失败：key=%s value=%s", key, value, exc_info=True
                        )
                        continue
                except Exception:  # noqa: BLE001 - 其余异常：不写，交回正常对话
                    logger.warning(
                        "对话内更正画像失败：key=%s value=%s", key, value, exc_info=True
                    )
                    continue
                changed.append(f"{field.label or field_labels.get(key, key)}：{value}")
                protected_profile_values[key] = value
            if changed:
                profile_correction_note = (
                    "已按你这次说明更新画像 —— " + "；".join(changed) + "。"
                    "其他信息保持不变。"
                )

        # Only a question produced by this server in the immediately preceding
        # assistant turn authorizes interpreting a short answer as consent.
        try:
            recent_turns = await self._memories.list_turns(request.user_id, request.task_id, limit=self._TURN_GROUP_SCAN)
        except Exception:
            logger.warning("读取确认上下文失败，本轮不自动执行提议", exc_info=True)
            recent_turns = []
        # 这一轮的用户消息刚写进逐轮原文，所以"上一条"要往回找**主理**那一轮；
        # 直接取 recent_turns[-1] 会拿到刚写的用户消息，提议/工具确认全部失效。
        previous = next(
            (turn for turn in reversed(recent_turns) if turn.role == "agent"), None
        )
        # "第一项做完了/点错了恢复"这类可判定的任务状态变更，直接执行并回读，
        # 不等模型是否记得调用 `workspace.task.set_done`：深度测试里模型回了
        # "第一项勾掉了"，计划页却仍是 0/9 —— 学生看到的完成是假的。
        direct_task = await self._direct_task_toggle(request, session)
        if direct_task is not None:
            return direct_task
        pending_offer = next((kind for kind, question in _ASSET_OFFERS.items()
                              if previous and previous.role == "agent" and previous.text.rstrip().endswith(question)), None)
        if pending_offer is None:
            # 上一轮提议被别的消息顶掉时，它仍以账号级状态保留（见 `_pending_asset_offer`）：
            # 新手很可能会先说别的，再回来点「可以」，不能让这条提议悄悄消失。
            pending_offer = await self._pending_asset_offer(request.user_id, request.task_id)
        pending_tool = proposal_at_end(previous.text) if previous and previous.role == "agent" else None
        tool_answer = _offer_answer(request.message) if pending_tool else None
        if pending_tool and re.fullmatch(r"(?:生成吧|创建吧|请生成|请创建|帮我生成|帮我创建)[。！!\s]*", request.message):
            tool_answer = None
        if (pending_tool and pending_tool not in {"task_done", "task_undo"} and tool_answer is None
                and re.fullmatch(r"(?:查吧|看吧|查一下|看一下|帮我查查|帮我看看|就按你说的|请查询)[。！!\s]*", request.message)):
            tool_answer = "accept"
        if request.option_id and pending_tool and request.option_id not in {
            f"tool.{pending_tool}.accept", f"tool.{pending_tool}.decline"
        }:
            tool_answer = None
        accepted_tool = pending_tool if tool_answer == "accept" else None
        confirmed_tool_offer = TOOL_OFFERS.get(accepted_tool) if accepted_tool else None
        if accepted_tool in {"task_done", "task_undo"}:
            prior_user = next((t.text for t in reversed(recent_turns[:-1]) if t.role == "user"), "")
            plan = await self._assets.get_action_plan(request.user_id)
            should_complete = accepted_tool == "task_done"
            matching = mentioned_tasks(plan, prior_user)
            if (len(matching) == 1 and matching[0].done != should_complete and
                    previous.text.rstrip().endswith(task_offer(matching[0].text, done=should_complete).question)):
                confirmed_tool_offer = task_offer(matching[0].text, done=should_complete)
            else:
                result = TurnResult(task_id=request.task_id, session=session, stage=session.loop_stage,
                    badge=await self._badge(session.lead_agent, []),
                    messages=[ConversationMessage(role="agent", agent_id=session.lead_agent,
                        text="任务已变化或无法唯一确认，这次没有修改。请查看现有计划后重新指定任务。")],
                    guide=BehaviorGuide(kind="question", text="", question=None))
                await self._remember_turn(request, result, loop_stage=session.loop_stage)
                return result
        offer_answer = _offer_answer(request.message) if pending_offer else None
        if request.option_id and pending_offer:
            expected = {f"asset.{pending_offer}.accept", f"asset.{pending_offer}.decline"}
            if request.option_id not in expected:
                offer_answer = None
        # 用户直接把诉求写出来（「帮我生成诊断报告」「创建行动计划」）也算确认：
        # 不该要求他先猜中"可以"两个字，才算答应了上一轮。
        if pending_offer and offer_answer is None and not request.option_id:
            if pending_offer == "report" and (
                _explicit_report_request(request.message)
                or _wants_view_report(request.message)
            ):
                offer_answer = "accept"
            elif pending_offer == "plan" and (
                _explicit_plan_request(request.message)
                or _wants_view_plan(request.message)
            ):
                offer_answer = "accept"
        accepted_offer = pending_offer if offer_answer == "accept" else None
        if pending_offer and offer_answer in {"accept", "decline"}:
            await self._set_pending_asset_offer(
                request.user_id, None, task_id=request.task_id
            )
        # Another tab may already have created an asset after the proposal.
        # Never replace it on the strength of an older offer to create one.
        already_created = False
        if accepted_offer == "plan":
            already_created = await self._assets.get_action_plan(request.user_id) is not None
        elif accepted_offer == "report":
            already_created = await self._assets.get_report(request.user_id) is not None
        if already_created:
            await self._set_pending_asset_offer(
                request.user_id, None, task_id=request.task_id
            )
            label = "行动计划" if accepted_offer == "plan" else "诊断报告"
            result = TurnResult(task_id=request.task_id, session=session, stage=session.loop_stage,
                badge=await self._badge(session.lead_agent, []),
                messages=[ConversationMessage(role="agent", agent_id=session.lead_agent,
                    text=f"已有{label}，这次没有重新生成。你可以先查看现有内容，再决定是否更新。")],
                guide=BehaviorGuide(kind="question", text="", question=None))
            await self._remember_turn(request, result, loop_stage=session.loop_stage)
            return result

        blackboard = await self.read_blackboard(request.user_id, request.task_id)
        intent_decision = await self._intent_policy.classify_with_decision(
            message=request.message,
            blackboard=blackboard,
            skip_model=bool(request.option_id or request.option_value is not None),
        )
        logger.info(
            "decision_routing intent=%s candidate=%s source=%s adopted=%s "
            "reason=%s confidence=%s probabilities=%s latency_ms=%s",
            intent_decision.intent.value,
            intent_decision.candidate,
            intent_decision.source,
            intent_decision.adopted,
            intent_decision.reason,
            intent_decision.confidence,
            intent_decision.probabilities,
            intent_decision.latency_ms,
        )
        intent = intent_decision.intent
        stage_decision = await self._stage_policy.decide(
            blackboard=blackboard, intent=intent, message=request.message
        )
        explicit_plan = _explicit_plan_request(request.message) or accepted_offer == "plan"
        explicit_report = _explicit_report_request(request.message) or accepted_offer == "report"
        # "我想看一下我的诊断报告/我的计划"：若还没有，就直接生成，而不是只回答
        # "去报告页看看"（实测第一次这样要报告没有任何产物，用户得再说一遍）。
        if not explicit_report and _wants_view_report(request.message):
            try:
                if await self._assets.get_report(request.user_id) is None:
                    explicit_report = True
            except Exception:  # noqa: BLE001
                logger.warning("读取报告状态失败（按普通查看处理）", exc_info=True)
        if not explicit_plan and _wants_view_plan(request.message):
            try:
                if await self._assets.get_action_plan(request.user_id) is None:
                    explicit_plan = True
            except Exception:  # noqa: BLE001
                logger.warning("读取计划状态失败（按普通查看处理）", exc_info=True)
        if explicit_report or (explicit_plan and (accepted_offer == "plan" or stage_decision.stage is not LoopStage.REVIEW)):
            stage_decision = stage_decision.model_copy(update={
                "stage": LoopStage.ACT if explicit_plan else LoopStage.DIAGNOSE,
                "need_clarify": False, "source": "intent",
            })
        if stage_decision.need_clarify or stage_decision.stage is None:
            question = stage_decision.clarify_question or await self._clarify_text()
            result = TurnResult(
                task_id=request.task_id,
                session=session,
                stage=session.loop_stage,
                badge=await self._badge(session.lead_agent, []),
                messages=[
                    ConversationMessage(
                        role="agent", text=question, agent_id=session.lead_agent
                    )
                ],
                guide=BehaviorGuide(
                    kind="question", text=question, question=question
                ),
            )
            # 澄清这一轮**也要落库**：它此前直接 return，既不写逐轮原文、也不记行为、
            # 也不更新会话记忆 —— 用户回头翻这条会话时，这一段是空白的，
            # 而"他说过什么、被问了什么"正好是他判断"这东西有没有在记"的依据。
            await self._remember_turn(
                request,
                result,
                loop_stage=session.loop_stage,
                answer_payload={
                    "intent": intent.value,
                    "intent_decision": intent_decision.model_dump(
                        mode="json", exclude_none=True
                    ),
                },
            )
            return result

        stage = stage_decision.stage
        # 采够了就往前走 —— 不等用户说"暗号"。
        #
        # 环节推进原来是**纯关键词**的：用户得说出"帮我分析"这类话才会离开 ①。
        # 而真实场景是"我就想先聊两句"：门槛早就过了，系统还在一条条追问，
        # 于是人在这里失去兴趣走了。现在按策略表判一次 —— 够了就进分析。
        # 门禁只顶掉"没命中意图"的那两种情况（progress / fallback）。
        #
        # 用户**明确**说"我不知道自己适合什么、有点迷茫"时（source=intent），
        # 他就是要回到"了解自己"这一步 —— 那时把他顶去诊断等于不听他说话，
        # 而且他后面补的情况一个字都进不了画像（诊断契约里没有字段更新）。
        # 实测就是这样：有人说了家里希望他求稳，画像里什么都没留下。
        if stage is LoopStage.COLLECT and (
            stage_decision.source != "intent" or stage_decision.allow_gate_advance
        ):
            gate = await self.collection_gate(request.user_id)
            if gate.ready:
                logger.info("采集门槛已过（%s），本轮直接进入诊断", gate.line)
                stage = LoopStage.DIAGNOSE
            else:
                # 门槛没到也不能让人在①无限答题：实测新手照引导答 30+ 轮仍在采集，
                # 画像只落了 6 条字段，最后是关掉页面走的。
                # 轮次到上限就带缺口进入诊断，缺口会以"待补充"继续跟着他。
                user_rounds = sum(1 for turn in recent_turns if turn.role == "user")
                if user_rounds >= self._MAX_COLLECT_ROUNDS:
                    logger.info(
                        "采集已进行 %s 轮（门槛：%s），按轮次上限带缺口进入诊断",
                        user_rounds,
                        gate.line,
                    )
                    stage = LoopStage.DIAGNOSE
        axis_a = await self.infer_axis_a(request.user_id, request.task_id)
        lead = await self.select_lead(
            request.user_id, request.task_id, axis_a, stage, intent
        )
        disclosure = None
        direction_selected = None
        if stage is LoopStage.ACT:
            directions = await self._assets.list_direction_plans(request.user_id)
            direction_selected = any(item.selected for item in directions)
        if lead.lead_agent != session.lead_agent:
            handoff = await self.handoff(
                request.user_id,
                request.task_id,
                stage,
                await self._lead_change_reason(stage, lead.lead_agent, direction_selected=direction_selected),
            )
            disclosure = handoff.disclosure
            session = await self._sessions.get(request.task_id) or session
        else:
            session = await self._sessions.update_stage(
                session.id, stage, lead.lead_agent
            )

        prompt_vars: dict[str, Any] = {
            "user_input": _user_input_with_material(request),
            "raw_user_message": request.message,
            "task_id": request.task_id,
            "intent": intent.value,
        }
        if accepted_tool:
            prior_user_text = next((t.text for t in reversed(recent_turns[:-1]) if t.role == "user"), "")
            instruction = confirmed_tool_offer.instruction
            prompt_vars["confirmed_tool_request"] = instruction
            prompt_vars["raw_user_message"] = instruction
            prompt_vars["user_input"] = f"用户已同意上一轮提议。{instruction}\n上一轮用户的问题：{prior_user_text}\n本轮补充：{request.message}"
        if accepted_offer:
            prompt_vars["confirmed_request"] = (
                "用户同意了上一轮提出的创建行动计划请求，请按现有事实创建计划。"
                if accepted_offer == "plan" else
                "用户同意了上一轮提出的生成诊断报告请求，请按现有事实生成报告。"
            )
        if profile_correction_note:
            # 系统已经写进画像：模型必须按新值回答，且不能再劝学生"去画像手动改"。
            prompt_vars["confirmed_profile_correction"] = {
                "note": profile_correction_note,
                "rule": (
                    "上一条已由系统写入正式画像（来源：本人本次说明）。"
                    "直接按新值继续分析，不要说“没写进画像”“去画像里点更正”之类的话；"
                    "其他字段保持不变。"
                ),
            }
        if stage is LoopStage.ACT and direction_selected is False:
            prompt_vars["direction_selection_status"] = "用户尚未在方向方案中正式确认方向；可以围绕本轮想法拟定计划，但不要声称方向已选定。"
        if stage is LoopStage.ACT and not explicit_plan:
            prompt_vars["plan_write_boundary"] = "本轮只回答问题，不会保存或修改行动计划；不要声称计划已创建或更新。需要修改计划时请先征求用户明确要求。"
        if stage is LoopStage.DIAGNOSE and not explicit_report:
            prompt_vars["report_write_boundary"] = "本轮只回答咨询，不会生成或保存诊断报告；不要声称报告已生成。"
        if stage is LoopStage.DIAGNOSE:
            prompt_vars["source_authority_rule"] = (
                "引用个人信息来源时，只有 existing_profile_facts 里 source=record 的项"
                "（学信网核验 / 教务导入）才能写成“学信网显示 / 教务核验”；"
                "source=user_edit 或 conversation 的只能写“本人填写 / 对话记录”。"
                "缺来源就写“尚未核验”，不得把未核验资料说成已核验。"
            )
        from zhiyin_business.services.analysis_access import current_scope
        scope = current_scope(request.user_id)
        if scope and scope.restricted:
            prompt_vars["analysis_sources"] = {
                "allowed": sorted(scope.sources),
                "note": (
                    "仅使用本轮上下文；未提供的旧摘要和推导资料已按用户设置排除，不能据此断言用户从未提供。"
                    "如果画像里明明有某一项、只是被资料范围排除，必须写“按你的资料使用范围，本次未使用该项”，"
                    "不能写成“这一项未填/没有”。"
                ),
            }
        # 共享状态中虽有画像，模型在长上下文里仍曾说“没拿到你的画像”。
        # 把已存字段提到本轮输入的显眼位置，避免把“缺岗位要求”误说成“没有画像”。
        if blackboard.profile is not None and blackboard.profile.fields:
            prompt_vars["existing_profile_facts"] = [
                {
                    "label": field.label or field.key,
                    "value": field.value,
                    "source": field.source.value,
                }
                for field in blackboard.profile.fields
            ]
        # 查询类回答必须基于真实计划/画像：深度测试里模型答"画像里只有大三"
        # 而画像页是大二、答"第一周只有一件事"而计划有 5 项 —— 都是没把库里
        # 的真实值摆到它眼前。这里把计划逐项列出来，并给一条"以事实为准"的规则。
        try:
            plan_for_facts = await self._assets.get_action_plan(request.user_id)
        except Exception:  # noqa: BLE001 - 读不到就不注入，不让这一轮失败
            plan_for_facts = None
        if plan_for_facts is not None:
            plan_facts = []
            for phase in plan_for_facts.phases:
                for task in phase.tasks:
                    plan_facts.append(
                        {
                            "phase": phase.name,
                            "task": task.text,
                            "done": task.done,
                            "status": task.status,
                            "due_date": task.due_date.isoformat()
                            if task.due_date
                            else None,
                        }
                    )
            if plan_facts:
                prompt_vars["plan_facts"] = plan_facts
        if prompt_vars.get("existing_profile_facts") or prompt_vars.get("plan_facts"):
            prompt_vars["factual_query_rule"] = (
                "如果用户问的是“我有哪些信息/还有什么没完成/计划里有什么/几项/进度”，"
                "必须以上面的 existing_profile_facts 和 plan_facts 为准逐项回答；"
                "库里没有的就说“我这边没有看到”，不要编造、不要用对话记忆替代当前档案。"
            )
        # 最近几条对话必须一并给模型（自己与他各一句）。
        #
        # 少了它，模型手上只有"这一句 + 黑板快照"：它看不到上一轮自己问了什么、用户
        # 答了什么，每一轮都像在对一个刚见面的陌生人开口 —— 接不上话，也认不出
        # "这条上一轮已经问过了"。实测症状就是"像在说梦话"：每句都像那么回事，
        # 但没有一句是在回应你。
        turn_group = await self._turn_group(
            request.user_id, request.task_id, exclude_user_text=request.message
        )
        if turn_group:
            prompt_vars["turn_group"] = turn_group
        # 这一轮如果是**点选项**而不是手打，就把那个选项的身份一并给模型。
        #
        # 只发 label 的后果实测过：用户点了「我现在还在念书」，回包又把同一个问题
        # 连同同一组选项问了一遍 —— 因为模型看到的只是一句话，它不知道那是
        # 上一轮自己给的选项之一，也就没有理由把状态往前推。带上 option_id / value
        # 之后，"用户选了什么"是可判定的，不是猜的。
        if request.option_id or request.option_value is not None:
            prompt_vars["chosen_option"] = {
                "option_id": request.option_id or "",
                "value": request.option_value,
                "label": request.message,
            }
        # 把**合法的理论卡清单**一并给模型：`theory_refs` 要填 id，
        # 而模型手上原本没有一份可选的清单，只能照名字编（实测编出过 theo_clover）。
        # 给它 id + 名字，引用才落在真实卡片上；编出来的 id 会在
        # `_known_theory_refs` 那里被剔除并留日志。
        prompt_vars["theory_cards"] = [
            {"id": card.id, "name": card.name, "school": card.school}
            for card in await self._registry.list_theory_cards()
        ]
        # 画像字段的**允许清单**（键 + 中文名）一并给模型。
        #
        # 为什么要给：字段键原来是模型自由发挥的（interest_direction /
        # course_selection_pattern / stuck_point…），而界面上要给用户看中文名、
        # 采集清单与报告维度又都按固定键取值 —— 键一散，这两件事同时坏掉。
        # 给它一份清单，它就知道该往哪条上靠；实在不属于任何一条时，
        # 契约里还留了 label 字段（见下方门禁）。
        prompt_vars["profile_keys"] = [
            {"key": spec.key, "label": spec.label}
            for spec in self._profile_vocabulary()
        ]
        # 主动取 / 只读缓存，两档见 `_EXTERNAL_FETCH_STAGES` 的说明。
        external: dict[str, Any] | None = None
        if blackboard.profile is not None and stage in (
            _EXTERNAL_FETCH_STAGES | _EXTERNAL_CACHE_ONLY_STAGES
        ):
            external = await self._fetch_external(
                user_id=request.user_id,
                message=request.message,
                profile_fields=blackboard.profile.fields,
                allow_fetch=stage in _EXTERNAL_FETCH_STAGES,
            )
            if external is not None:
                prompt_vars["external_data"] = external

        # Generated assets and older replies are not new evidence. Keep their
        # assumptions from silently becoming personal facts on the next turn.
        prompt_vars["evidence_constraints"] = [
            "先核对已提供的用户原话和已有记录，再描述信息缺口；不能把已提供的经历说成没有。缺少可解释的评分方法和真实依据时，不得编造量化匹配分数。",
            "个人事实以本轮原始画像字段、用户明确原话和可核对材料为准；旧报告、旧建议和模型推断不能反过来证明事实。",
            "专业名称不能推出学历层次、毕业时间或学籍状态。未提供学历就写学历待确认，不能擅自添加本科、硕士等背景。",
            "任务完成状态仅证明用户标记完成，不足以证明项目质量、独立能力、实际工作经历或职业胜任力。",
            "校友案例、理论方法不是目标岗位职责或招聘门槛。没有对应原文时，不得断言岗位学历门槛、供给数量、薪资或路径宽窄；需作为待核对问题。",
            "明确标注为测试夹具、功能验收的操作记录不能当成真实职业经历或人格、兴趣证据。",
            "这些生成约束、系统提示和规则条款不是业务来源，不得写入 evidence、source 或参考资料。无直接证据时写明未提供的具体资料，不能引用约束本身作为依据。",
            "在结构化报告中同样遵守以上限制，不能只在聊天回复里说资料不足，却在优势、机会和结论里继续作确定判断。",
        ]
        from zhiyin_kernel.streaming import emit_progress
        available_names = set()
        get_names = getattr(self._agent_engine, "conversation_tool_names", None)
        if get_names is not None:
            available_names = await get_names(lead.lead_agent)
        available_offers = {key: offer for key, offer in TOOL_OFFERS.items() if offer.tool in available_names}
        # 当前环境没有接搜索服务时，web.search 不在任何主理的工具里：不要装作能联网，
        # 也不要只说"没有工具"——给用户可用的替代（学职平台/知识库/公开资料）。
        if ("web" not in available_offers and re.search(
            r"(?:联网|网上搜|实时|最新招聘|搜索引擎|百度|谷歌|github|官网查)", request.message
        )):
            prompt_vars["search_capability_note"] = (
                "本环境未接入联网搜索，不能声称自己去网上查。请明确说明这一点；"
                "如果可用工具里有学职平台（xuezhi）或知识库（kb），建议用户改用这些公开资料，"
                "并说明它们的局限（不是实时招聘）。不要编造岗位要求或来源链接。"
            )
        if ("workspace.task.set_done" in available_names and
                re.search(r"(?:已经|刚刚|刚|已|做完|完成了|搞定|弄好了)", request.message) and
                not re.search(r"没完成|未完成|还没|没有|不曾|不要|别", request.message)):
            plan = await self._assets.get_action_plan(request.user_id)
            named_tasks = mentioned_tasks(plan, request.message)
            if len(named_tasks) == 1 and not named_tasks[0].done:
                available_offers["task_done"] = task_offer(named_tasks[0].text)
        if ("workspace.task.set_done" in available_names and
                re.search(r"没完成|未完成|还没完成|没有完成|误标|标错", request.message)):
            plan = await self._assets.get_action_plan(request.user_id)
            named_tasks = mentioned_tasks(plan, request.message)
            if len(named_tasks) == 1 and named_tasks[0].done:
                available_offers["task_undo"] = task_offer(named_tasks[0].text, done=False)
        prompt_vars["optional_tool_offers"] = {
            "instruction": "仅当当前问题适合、对用户确有帮助且用户没有要求只聊天时，选择一个可用能力的键放入 tool_offer；没有合适机会就填空字符串。比如讨论学业困难时可建议核对成绩，谈计划执行时可建议查看进度，需要时效信息时可建议联网核实。选择工具建议时，正文不要再提出其他问题，也不要自行承诺执行；系统会生成确认问题。",
            "choices": {key: offer.question for key, offer in available_offers.items()},
        }
        # Do not silently read or act merely because the conversation made a
        # tool relevant. Direct requests and a confirmed proposal still work.
        direct_tool_request = bool(re.search(
            r"(?:查看|查找|查询|检索|搜索|联网|读取|展示|列出|统计|给我看|帮我看|看看我的|根据我的|结合我的|"
            r"标记|勾选|取消完成|撤销完成|生成|创建|制定|画图|图表|进度卡片)", request.message))
        if re.search(r"(?:不要|不用|不必|不想|别|先不|暂不).{0,12}(?:查看|查找|查询|检索|搜索|联网|读取|展示|列出|统计|标记|勾选|生成|创建|制定|画图)", request.message):
            direct_tool_request = False
        prompt_vars["proposal_only"] = not bool(accepted_tool or accepted_offer or direct_tool_request)
        output_schema = STAGE_CONTRACTS[stage].model_json_schema()
        output_schema.setdefault("properties", {})["tool_offer"] = {
            "type": "string", "enum": [""] + list(available_offers),
            "description": "可选的下一步工具建议键；没有适合的建议时为空。",
        }
        output_schema.setdefault("required", []).append("tool_offer")
        stream_badge = await self._badge(lead.lead_agent, [])
        emit_progress({'agent': stream_badge.name, 'note': '正在整理回复'})
        result = await self._agent_engine.invoke(
            AgentRequest(
                agent_id=lead.lead_agent,
                stage=stage.value,
                blackboard=blackboard.model_dump(mode="json"),
                prompt_vars=prompt_vars,
                output_schema=output_schema,
                # Wait for writes and validation before displaying a reply
                # that might incorrectly claim a report or plan was saved.
                stream_field=None if (stage is LoopStage.DIAGNOSE and explicit_report) or (stage is LoopStage.ACT and explicit_plan) or _asks_for_chart(request.message) or (stage is not LoopStage.COLLECT and _contains_personal_disclosure(request.message)) else 'conclusion',
            )
        )

        structured = dict(result.structured or {})
        proposed_tool = structured.pop("tool_offer", None)
        if stage is LoopStage.DECIDE:
            # Current direction scores are supplied by the model, without
            # verifiable inputs or a reproducible calculation.
            for option in structured.get("plans") or []:
                if isinstance(option, dict):
                    option["match_score"] = None
        if external is not None and lead.info_scout_required:
            verified_facts = await self._run_info_scout(external, stage)
            if stage is LoopStage.DIAGNOSE:
                # Report sources are rebuilt from the scout's URL-checked facts.
                # The lead cannot promote a source label or invented link into an asset.
                structured["facts"] = verified_facts
        if stage is LoopStage.DIAGNOSE and structured:
            # The generic agent engine validates JSON Schema. Pydantic's cross-field
            # validators are deliberately outside JSON Schema, so run the business
            # contract once more before either the reply or report can consume it.
            # Otherwise a structurally valid output can still turn "not provided"
            # into a personal weakness, reach the chat, and only fail much later when
            # the report converter happens to validate it.
            from zhiyin_business.contracts.diagnose import DiagnoseOutput

            # 结论里已经写了"缺证据=能力不足"时不修：交给下面的校验器拒绝，
            # 走 fallback 回复（不展示、不落库）；只修结构性的误写。
            if not _diagnose_prose_is_unsafe(structured):
                structured = _sanitize_absence_words(_repair_diagnose_evidence(structured))
            try:
                structured = DiagnoseOutput.model_validate(structured).model_dump(
                    mode="json"
                )
            except Exception as exc:  # noqa: BLE001 - invalid model output has a safe reply
                logger.warning(
                    "诊断产出未通过证据边界校验，不展示且不落库：%s", exc
                )
                result.valid = False
                result.errors.append("诊断证据边界校验失败")
                structured = _unsafe_diagnose_fallback(structured)
        task_labels: dict[str, str] = {}
        if stage is LoopStage.REVIEW:
            plan = await self._assets.get_action_plan(request.user_id)
            task_labels = {
                task.id: task.text
                for phase in (plan.phases if plan else [])
                for task in phase.tasks
                if task.id and task.text
            }
            if structured:
                structured = _replace_task_ids_in_prose(structured, task_labels)
        # 产出不合法时必须**留痕**：契约没被满足，降级是怎么发生的要能查。
        # 之前这里直接往下走，于是"模型答了、但 JSON 少了字段"这件事
        # 在日志里一个字都没有，表现成"回复永远是同一句"。
        if not result.valid:
            logger.warning(
                "环节产出不符合契约：stage=%s agent=%s errors=%s",
                stage.value,
                lead.lead_agent,
                result.errors,
            )
        # 产出合规就**落成资产**：这一步此前完全缺失 —— 模型把 15 维诊断生成并
        # 通过契约校验之后，正文被直接丢掉，于是报告页恒空、工作台恒无版本。
        stale_before = await self._stale_asset_types(request.user_id)
        # A module data query is read-only. Stage schemas may still require an
        # asset-shaped response; do not turn that schema filler into a new plan
        # that immediately invalidates the data returned by the module tool.
        module_query = bool(result.module_attempts or result.module_results) or any(
            item.kind.startswith("module.") for item in validate_renderables(result.renderables)
        )
        # Reaching the action stage through conversation progress is not consent
        # to overwrite a saved plan. Only an explicit request can generate one.
        write_tool_attempted = "workspace.task.set_done" in result.business_tool_calls
        may_persist = (not accepted_tool and not module_query and not write_tool_attempted
                       and (not result.business_tool_calls or (stage is LoopStage.ACT and explicit_plan)
                            or (stage is LoopStage.DIAGNOSE and explicit_report))
                       and (stage is not LoopStage.ACT or explicit_plan)
                       and (stage is not LoopStage.DIAGNOSE or explicit_report))
        persisted_output = structured
        if stage is LoopStage.REVIEW and not explicit_plan and structured.get("plan_patch"):
            persisted_output = {**structured, "plan_patch": None}
        changed_assets = [] if not may_persist else await self._persist_stage_output(
            stage, request.user_id, persisted_output, valid=result.valid,
            session_id=request.task_id,
        )
        # 这一轮真的把一份"待重算"的资产重算掉了 → **必须显式告知**（结论变化），
        # 否则用户手上那份旧结论被换掉而他不知道。这是设计里三种告知中的一种，
        # 此前只有"换主理"这一种真的会发出。
        if changed_assets and stale_before & {item.asset_type for item in changed_assets}:
            notice = await self._conclusion_change_disclosure()
            if disclosure is None:
                disclosure = notice
            else:
                # 同一轮里既换了主理、又重算了一份旧结论 —— 两件事都得说，
                # 不能因为契约里只有一个位置就只说一件（实测：换主理那句把
                # "结论变了"整个盖住，用户不知道手上的旧结论已经被换掉）。
                disclosure = disclosure.model_copy(
                    update={"text": f"{disclosure.text.rstrip()} {notice.text.strip()}"}
                )
        # ① 采集的产出**不是资产，是画像本身**：这一步此前同样缺失 ——
        # 见 `_apply_collect` 的说明（模型结构化返回的字段被丢掉，画像恒空）。
        #
        # **不看 `result.valid`**：采集这一环的硬指标只有一个 —— 他说的话有没有被记下来。
        # 整份产出别处不合契约（少个字段、格式歪了）不该连累这一条：字段能解析就落库，
        # 其余的问题留在日志里。`_apply_collect` 自己会挑出能解析的部分。
        collect_data = None
        if stage is LoopStage.COLLECT and not accepted_tool and not module_query and not _forbids_profile_write(request.message):
            if not result.business_tool_calls:
                collect_data = structured
            elif _contains_personal_disclosure(request.message) and not write_tool_attempted:
                collect_data = _direct_field_updates(structured, request.message)
        elif stage is not LoopStage.COLLECT and _contains_personal_disclosure(request.message):
            # Mixed-intent turns still need to answer the requested stage. Run a
            # separate read-only collector and only accept evidence quoted from
            # this exact message; never promote old generated text into a fact.
            try:
                collected = await self._agent_engine.invoke(AgentRequest(
                    agent_id="profile_analyst", stage=LoopStage.COLLECT.value,
                    blackboard=blackboard.model_dump(mode="json"),
                    prompt_vars={"user_input": request.message, "raw_user_message": request.message,
                                 "profile_keys": prompt_vars["profile_keys"],
                                 "evidence_constraints": ["只提取用户本轮明确自述，evidence 必须逐字引用本轮原话；不要根据旧信息推断。"]},
                    output_schema=STAGE_CONTRACTS[LoopStage.COLLECT].model_json_schema(),
                    use_tools=False,
                ))
                collect_data = _direct_field_updates(collected.structured or {}, request.message)
            except Exception:
                logger.exception("混合意图画像采集失败，本轮继续原咨询流程")
        if collect_data is not None and (not result.business_tool_calls and stage is LoopStage.COLLECT or collect_data.get("field_updates")):
            write = await self._apply_collect(request.user_id, collect_data)
            if stage is not LoopStage.COLLECT and write.written and (scope is None or not scope.restricted):
                # A mixed turn only carries new field updates, not a fresh gap
                # list. Remove gaps just satisfied by these explicit facts.
                try:
                    gaps = await self._profiles.get_gaps(request.user_id)
                    remaining = [gap for gap in gaps if self._normalize_profile_key(gap.key) not in write.written]
                    if len(remaining) != len(gaps):
                        await self._profiles.replace_gaps(request.user_id, remaining)
                except Exception:
                    logger.exception("画像已写入，但已满足的缺口未能同步")
            # `_apply_collect` 的返回值在此之前**没有任何消费方**：被挡下的写入只有日志知道，
            # 而他看不到日志。这一格是他自己填的、推断改不动，那是设计如此；但"没写进去"
            # 必须当面说，并且给出口（去画像点「更正」），否则他听到的就是"我说了它不听"。
            #
            # **没有撞上时不出现**：这一轮一个字段都没被挡下时 `blocked_by_user_edit`
            # 是空元组，这里连文案都不取 —— 不能每轮都念一遍这句话，那样它就从"解释"
            # 变成了背景噪音，真正被挡的那一轮反而没人会注意。
            # 本人这一轮已经明确更正/追加画像时，系统说明条会告诉用户"改了什么"；
            # 这时再弹"没写进画像，你自己去改"就与事实相反（实测同一条回复前后矛盾）。
            if write.blocked_by_user_edit and not profile_correction_note:
                kept = await self._field_kept_disclosure(write.blocked_by_user_edit)
                if disclosure is None:
                    disclosure = kept
                else:
                    # 同一轮里既换了主理（或重算了旧结论）、又挡下一次写入：两件事都得说，
                    # 与下面「结论变化」的处理同一条口径。
                    disclosure = disclosure.model_copy(
                        update={"text": f"{disclosure.text.rstrip()} {kept.text.strip()}"}
                    )
        # 本人这一轮明确更正/追加的内容是"最终值"：采集从模型结构化输出里
        # 再写一次同一格时（尤其"记到经历里"这种追加），不能把它覆盖回旧值。
        if protected_profile_values:
            for key, value in protected_profile_values.items():
                try:
                    await self._profiles.correct_field(request.user_id, key, value)
                except InvalidRequest:
                    try:
                        await self._profiles.update_field(
                            request.user_id,
                            key,
                            value,
                            confidence=1.0,
                            source=ProfileSource.USER_EDIT.value,
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning("本人更正内容回写失败：key=%s", key, exc_info=True)
                except Exception:  # noqa: BLE001 - 回写失败保留采集结果，至少不抛给用户
                    logger.warning("本人更正内容回写失败：key=%s", key, exc_info=True)
        # tao 分支原来的写法是 `if stage is LoopStage.COLLECT and not module_query:`
        # 直接 await（不带返回值）。上面保留了 HEAD 那侧的"接出返回值、当面告知"，
        # 并把 tao 的 module_query 条件合进了 if —— 两边要的事都还在。
        badge = await self._badge(
            lead.lead_agent,
            await self._known_theory_refs(structured.get("theory_refs")),
        )
        # 主理这一轮自己产出的可视件：逐个按 kind 校验（不认识的、形状不对的丢掉留日志）。
        # 模型只挑了"看哪一类"，点位是工具从库里读的 —— 校验在 `policies/renderers.py`。
        model_renderables = validate_renderables(result.renderables)
        module_cards = [item for item in model_renderables if item.kind.startswith("module.")]
        # Only actual server-side results may describe a skill query. Model
        # stage conclusions and task guidance can claim writes that never ran.
        guide = BehaviorGuide(kind="question", text="", question=None) if module_query else _guide(
            structured.get("guide"), structured
        )
        wants_chart = _asks_for_chart(request.message) or bool(confirmed_tool_offer and confirmed_tool_offer.tool == "chart.render")
        renderables = _renderables_for_turn(
            model_renderables,
            stage,
            structured,
            message=confirmed_tool_offer.instruction if wants_chart and confirmed_tool_offer else request.message,
            profile=await self._profiles.get(request.user_id) if wants_chart and accepted_tool != "chart_plan" else None,
        )
        reply_text = (
            _chart_reply_text(renderables)
            if wants_chart
            else _user_facing_text(structured, guide, result.raw_text, valid=result.valid)
        )
        if stage is LoopStage.REVIEW:
            reply_text = _replace_task_ids_in_prose(reply_text, task_labels)
        if result.business_read_receipts and not result.valid and not result.business_tool_receipts:
            reply_text = "\n\n".join(str(item.get("text") or "") for item in result.business_read_receipts)
            guide = BehaviorGuide(kind="question", text="", question=None)
        if (not result.business_tool_receipts
                and re.search(r"标记.{0,8}完成|取消完成|撤销完成|勾选", request.message)
                and not re.search(r"不要|不必|无需|暂不|别", request.message)):
            reply_text = "这次没有确认任务已更改，请写出完整任务名称后重试。"
            guide = BehaviorGuide(kind="question", text="", question=None)
        if result.business_tool_receipts:
            receipt = next((item for item in reversed(result.business_tool_receipts) if item.get("executed")), result.business_tool_receipts[-1])
            if receipt.get("executed"):
                state = "完成" if receipt.get("done") else "未完成"
                reply_text = f"已将「{receipt.get('task', '该任务')}」标记为{state}。"
            else:
                reply_text = "没有更改任务：" + str(receipt.get("reason") or "操作未完成，请重试。")
            guide = BehaviorGuide(kind="question", text="", question=None)
        if accepted_tool:
            offer = confirmed_tool_offer
            if offer.tool == "workspace.read":
                succeeded = any(r.get("area") == offer.area for r in result.business_read_receipts)
            elif offer.tool == "workspace.task.set_done":
                succeeded = any(r.get("executed") for r in result.business_tool_receipts)
            elif offer.tool == "chart.render":
                succeeded = any(r.kind == "bars_chart" for r in model_renderables)
            elif offer.tool in {"action_progress.read", "plan_progress_skill.read"}:
                succeeded = any(r.get("module_id") == offer.tool.split(".")[0] for r in result.module_results)
            else:
                succeeded = offer.tool in result.tool_calls
            if not succeeded and not result.business_tool_receipts:
                reply_text = "这次未能确认所需工具已成功调用，请稍后重试。"
                guide = BehaviorGuide(kind="question", text="", question=None)
        requested_asset = (AssetType.ACTION_PLAN if stage is LoopStage.ACT and explicit_plan else
                           AssetType.REPORT if stage is LoopStage.DIAGNOSE and explicit_report else None)
        if requested_asset and not module_query and not write_tool_attempted:
            label = "行动计划" if requested_asset is AssetType.ACTION_PLAN else "诊断报告"
            if any(item.asset_type == requested_asset for item in changed_assets):
                reply_text = f"{reply_text.rstrip()}\n\n{label}已生成，可以到对应页面查看。".strip()
            else:
                # The model may have written “已生成” before validation or a
                # failed database write; only the server can confirm success.
                # 措辞要可执行：这句话实测出现时，用户唯一的感受是"它又失败了"；
                # 要告诉他下一步能做什么，并明确已有内容没有被改。
                reply_text = (
                    f"这次没有成功生成{label}（模型没有给出可用内容，已自动重试）。"
                    f"已有内容没有被修改。你可以再说一次「生成{label}」，"
                    f"或先补充一条具体信息（比如一份岗位要求、一段经历）再试。"
                )
                guide = BehaviorGuide(kind="question", text="", question=None)

        # Do not repeatedly ask after a postponement. A fresh explicit request
        # remains available at any time. Limit the cooldown to this conversation.
        recent_offer_kinds = {kind for kind, question in _ASSET_OFFERS.items()
                              if any(t.role == "agent" and t.text.rstrip().endswith(question)
                                     for t in recent_turns[-12:])}
        user_context = " ".join([request.message] + [t.text for t in recent_turns[-8:] if t.role == "user"])
        has_plan_context = bool(direction_selected or re.search(
            r"实习|求职|升学|考研|考公|考编|就业|岗位|职业|方向|项目|简历|作品集|面试|考试|技能|编程|课程", user_context))
        offer_kind = None
        if (result.valid and not module_query and not write_tool_attempted and not requested_asset
                and not pending_offer and not pending_tool and not _asks_for_chart(request.message)
                and not re.search(r"(?:先|想|只|继续|再).{0,4}聊|(?:先|继续|再).{0,4}(?:了解|谈谈)", request.message)
                and not re.search(r"(?:不要|暂不|先不|不想|无需|不必|别).{0,12}(?:报告|诊断|计划|生成|创建)", request.message)):
            if (stage in (LoopStage.COLLECT, LoopStage.DIAGNOSE) and "report" not in recent_offer_kinds
                    and await self._assets.get_report(request.user_id) is None
                    and (await self.collection_gate(request.user_id)).ready):
                offer_kind = "report"
            elif (stage is LoopStage.ACT and intent is IntentType.HOW_TO_ACT
                    and "plan" not in recent_offer_kinds
                    and has_plan_context
                    and await self._assets.get_action_plan(request.user_id) is None):
                offer_kind = "plan"
        if offer_kind:
            reply_text = f"{reply_text.rstrip()}\n\n{_ASSET_OFFERS[offer_kind]}".strip()
            guide = BehaviorGuide(kind="options", text="", options=[
                GuideOption(option_id=f"asset.{offer_kind}.accept", label="可以", value="accept"),
                GuideOption(option_id=f"asset.{offer_kind}.decline", label="先不要", value="decline"),
            ])
            # 提议写进账号级状态：用户下一句说别的也不会把它顶掉，
            # 之后再说「可以」或「生成报告」仍然算数（见 `_pending_asset_offer`）。
            await self._set_pending_asset_offer(
                request.user_id, offer_kind, task_id=request.task_id
            )
        recent_tool_offers = {proposal_at_end(t.text) for t in recent_turns[-12:] if t.role == "agent"}
        # An unambiguous statement about an existing task deserves the matching
        # status question even when the model selected a more generic read.
        if "task_done" in available_offers:
            proposed_tool = "task_done"
        elif "task_undo" in available_offers:
            proposed_tool = "task_undo"
        if (not offer_kind and result.valid and isinstance(proposed_tool, str) and proposed_tool in available_offers
                and proposed_tool not in recent_tool_offers and not pending_tool and not pending_offer
                and not accepted_tool and not requested_asset and not write_tool_attempted and not module_query
                and not result.business_tool_calls and not result.tool_calls
                and not re.search(r"(?:先|想|只|继续|再).{0,4}聊|不要|暂不|先不|不想|无需|不必", request.message)):
            if proposed_tool in {"task_done", "task_undo"}:
                # Only the confirmed write receipt may claim that status changed.
                reply_text = "我找到了你提到的任务。"
            reply_text = f"{reply_text.rstrip()}\n\n{available_offers[proposed_tool].question}".strip()
            guide = BehaviorGuide(kind="options", text="", options=[
                GuideOption(option_id=f"tool.{proposed_tool}.accept", label="可以", value="accept"),
                GuideOption(option_id=f"tool.{proposed_tool}.decline", label="先不要", value="decline"),
            ])
        # 系统已经明确写进画像时，模型仍可能复述旧的"我没写进画像/你自己去改"
        # 兜底提示（它看不到我们刚写库这件事）—— 两句同时出现会互相打脸。
        # 清掉这类与事实相反的句子，系统说明条单独负责"改了什么"。
        if profile_correction_note:
            reply_text = "".join(
                part
                for part in re.split(r"(?<=[。！？\n])", reply_text)
                if not re.search(
                    r"(?:没写进画像|没有写进画像|去画像里点|自己改一次|"
                    r"我不该拿推断|手填字段.{0,6}不能改)",
                    part,
                )
            ).strip() or reply_text
        # 假成功语兜底：模型说了"已保存/已勾掉/记下了"，但这一轮**没有任何真实写入**
        # （没调写工具、没有资产变化、也没有我们刚做的画像更正）——必须当场澄清。
        # 深度测试里 AGT-06/08/22 都出现过"安排我认/目标先记下/进度卡挂上了"而页面没变。
        if (
            not write_tool_attempted
            and not changed_assets
            and not result.business_tool_calls
            and not profile_correction_note
            # 查询句（"有哪些/多少/进度/怎么样了"）不是写请求，别给它加"没写入"的说明。
            and not re.search(
                r"(?:有哪些|哪些|什么|多少|几[项个条]|进度|怎么样了|如何|是否|吗[？?]?$)",
                request.message,
            )
            and re.search(
                r"(?:已把|已经|已(?:经)?(?:保存|添加|创建|更新|修改|标记|记录|安排|生成|设好|完成)"
                r"|勾掉了|记下了|挂上了|安排我认|已设好)",
                reply_text,
            )
            and re.search(
                r"(?:任务|计划|待办|目标|复盘|提醒|偏好|设置|画像|成绩|课表|方向|这条|这一项)"
                r".{0,10}(?:完成|做完|勾掉|恢复|加|新增|创建|保存|改|调整|记录|删除)"
                r"|(?:帮我|请|给我).{0,12}(?:完成|做完|勾掉|恢复|加|新增|创建|保存|改|调整|记录|删除)",
                request.message,
            )
        ):
            reply_text = (
                reply_text.rstrip()
                + "\n\n（说明：这一轮没有真正写入业务数据。如果你刚才是在要求修改，"
                "请以对应页面为准，或明确再说一次要改哪一项。）"
            )
        # 画像查询与正式档案不一致时，以档案为准补一句（模型曾答"画像里只有大三"
        # 而页面显示大二；这类矛盾会直接进报告结论）。
        if re.search(r"(?:画像|学习阶段|年级|个人信息)", request.message) and blackboard.profile:
            study_year = next(
                (
                    str(field.value)
                    for field in blackboard.profile.fields
                    if field.key == "study_year" and field.value
                ),
                "",
            )
            if study_year and re.search(
                r"(?:大一|大二|大三|大四)", reply_text
            ) and study_year not in reply_text:
                reply_text = (
                    reply_text.rstrip()
                    + f"\n\n（以画像页为准：你的当前学习阶段是「{study_year}」。）"
                )
        messages = [
            ConversationMessage(
                role="agent",
                text=_module_query_text(module_cards, result.module_results, result.module_attempts)
                if module_query
                else reply_text,
                agent_id=lead.lead_agent,
                theory_refs=badge.theory_refs,
                # 可视件与情报引用都来自**这一轮的实测数据**：可视件由服务端按 kind 填，
                # 引用用这一轮真的取回的外部事实 —— 不是让模型自己编。
                #
                # 两种来源，同一个形状：主理自己调的（它调 `chart.render` 时，
                # 点位是工具从库里读出来的 —— 模型只挑了"画哪一类"，碰不到数值）；
                # 它没点，就补上这一环节默认那张（仍然是实测分值）。
                renderables=model_renderables if module_query else renderables,
                intel_refs=_intel_refs(prompt_vars.get("external_data")),
            )
        ]
        if profile_correction_note:
            # 用系统条把"真的改了什么"显式说给学生，避免模型的回复与档案再次不一致。
            messages.insert(
                0,
                ConversationMessage(
                    role="system", text=profile_correction_note, agent_id=""
                ),
            )
        await self._remember_turn(
            request,
            TurnResult(
                task_id=request.task_id,
                session=session,
                stage=stage,
                badge=badge,
                messages=messages,
                guide=guide,
            ),
            loop_stage=stage,
            answer_payload={
                "stage": stage.value,
                "intent": intent.value,
                "intent_decision": intent_decision.model_dump(
                    mode="json", exclude_none=True
                ),
                # 点选项与手打要分得开：复盘"用户是怎么答的"时，
                # "点了哪个选项"是行为本身的一部分，丢了就只剩一句文字。
                **({"option_id": request.option_id} if request.option_id else {}),
            },
        )
        # 这一轮可能改了画像（① 采集）、资产（②③④ 产出）或会话状态 —— 工作台那一片失效。
        # 只报"发生了什么"：哪片缓存受影响由动态资源里的策略决定。
        if self._cache is not None:
            for event in ("profile_field_updated", "asset_version_changed", "session_changed"):
                await self._cache.invalidate_for_event(event)
        await self._log_stage_events(
            stage,
            request,
            valid=result.valid,
        )
        return TurnResult(
            task_id=request.task_id,
            session=session,
            stage=stage,
            badge=badge,
            messages=messages,
            disclosure=disclosure,
            guide=guide,
            asset_versions=changed_assets,
        )

    async def _replay_reply(
        self, request: TurnRequest, session: TaskSession
    ) -> Optional[TurnResult]:
        """这条消息是不是答过了？答过就把上次那条原文再给一次。

        只回**主理那一句**，不带 guide：重复的"下一步"会让人以为又发生了什么。
        读不到（老数据没有这个键、或收藏层没接）就返回 None，照常走这一轮 ——
        幂等是省一次调用，不是拦下用户的话。
        """
        try:
            reply = await self._memories.find_reply(
                request.user_id, request.client_msg_id or ""
            )
        except Exception:  # noqa: BLE001 - 幂等查询失败不该拦下这一轮
            logger.warning(
                "幂等查询失败（client_msg_id=%s），按新消息处理",
                request.client_msg_id,
                exc_info=True,
            )
            return None
        if reply is None or not reply.text.strip():
            return None
        logger.info("重复消息（client_msg_id=%s），返回上一次的答复", request.client_msg_id)
        return TurnResult(
            task_id=request.task_id,
            session=session,
            stage=session.loop_stage,
            badge=await self._badge(reply.agent_id or session.lead_agent, []),
            messages=[
                ConversationMessage(
                    role="agent", text=reply.text, agent_id=reply.agent_id or None,
                    renderables=validate_renderables(reply.renderables),
                )
            ],
            guide=BehaviorGuide(kind="question", text="", question=None),
        )

    async def _direct_task_toggle(
        self, request: TurnRequest, session: TaskSession
    ) -> "TurnResult | None":
        """用户明确说"第 N 项做完了/恢复"时直接改任务状态（不经模型）。

        只在**能唯一定位任务**时执行；定位不到就交回模型追问，绝不猜。
        返回 None 表示这一轮不接管。
        """
        intent = _task_operation_intent(request.message)
        if intent is None:
            return None
        try:
            plan = await self._assets.get_action_plan(request.user_id)
        except Exception:  # noqa: BLE001 - 读不到计划就交回正常对话
            logger.warning("读取行动计划失败，任务完成语句交回模型", exc_info=True)
            return None
        if plan is None:
            return None
        task = _resolve_task_for_operation(plan, request.message)
        if task is None or not task.id:
            return None
        if bool(task.done) == intent:
            text = (
                f"「{task.text}」已经是完成状态了，这次没有重复修改。"
                if intent
                else f"「{task.text}」现在是未完成状态，不需要再恢复。"
            )
        else:
            try:
                await self._assets.mark_action_task_done(
                    request.user_id, task.id, done=intent
                )
            except Exception:  # noqa: BLE001 - 写失败必须如实说，不能假装成功
                logger.warning("对话内任务状态更新失败：task_id=%s", task.id, exc_info=True)
                text = "这次没能改动任务状态（系统暂时没有保存成功），已保留你的原计划。请稍后在计划页重试。"
            else:
                if intent:
                    try:
                        await self._behaviors.log(
                            request.user_id,
                            BehaviorEventDraft(
                                event_type=BehaviorEventType.TASK_DONE,
                                payload={"task_id": task.id, "source": "conversation"},
                            ),
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning("任务完成行为日志写入失败（任务已更新）", exc_info=True)
                plan = await self._assets.get_action_plan(request.user_id)
                tasks = [
                    item
                    for phase in (plan.phases if plan else [])
                    for item in phase.tasks
                ]
                total = len(tasks)
                done_count = sum(1 for item in tasks if item.done)
                text = (
                    f"已把「{task.text}」标记为完成（计划现在 {done_count}/{total} 项完成）。"
                    if intent
                    else f"已把「{task.text}」恢复为未完成（计划现在 {done_count}/{total} 项完成）。"
                )
        result = TurnResult(
            task_id=request.task_id,
            session=session,
            stage=session.loop_stage,
            badge=await self._badge(session.lead_agent, []),
            messages=[
                ConversationMessage(
                    role="agent", text=text, agent_id=session.lead_agent
                )
            ],
            guide=BehaviorGuide(kind="question", text="", question=None),
        )
        await self._remember_turn(request, result, loop_stage=session.loop_stage)
        return result

    async def _user_turn_saved(self, request: TurnRequest) -> bool:
        """这一轮用户消息是否已经写进逐轮原文（开头先写、轮末不重复写）。"""
        try:
            turns = await self._memories.list_turns(
                request.user_id, request.task_id, limit=5
            )
        except Exception:  # noqa: BLE001 - 读不到就当没写过，宁可重复也别丢
            return False
        for turn in reversed(turns):
            if turn.role != "user":
                continue
            if request.client_msg_id:
                # 带幂等键时按 key 认；纯文本比对会在"连发两句一样的话"时误吞。
                if (
                    turn.client_msg_id == request.client_msg_id
                    and turn.text == request.message
                ):
                    return True
                continue
            if turn.text == request.message:
                return True
        return False

    async def _remember_turn(
        self,
        request: TurnRequest,
        result: TurnResult,
        *,
        loop_stage: LoopStage,
        answer_payload: dict[str, Any] | None = None,
    ) -> None:
        """把这一轮记进三本账：会话摘要、逐轮原文、行为日志。

        三条都**不影响回包**：任何一条写不进去都只记日志，让用户这一轮已经说完的话
        不至于白说（与本文件其它落库口径一致）。

        摘要写的是**人话**（他那一句 + 主理那一句），不再是模型的产出 JSON。
        原来那是 `result.raw_text`（一整坨 JSON），实测 12 轮就长到 24.9KB，
        每一轮都随黑板塞回模型：既是白花的 token，也会让模型把五轮前的旧结论
        当成当前的。摘要的用处是"接着上次聊"，那就该是对话本身。
        """
        lead_agent = result.badge.agent_id if result.badge else ""
        spoken = " ".join(
            _single_line(message.text) for message in result.messages if message.text
        )
        try:
            await self._memories.upsert(
                request.user_id,
                request.task_id,
                loop_stage=loop_stage,
                lead_agent=lead_agent,
                summary_delta=f"他：{_single_line(request.message, limit=60)}\n"
                f"主理：{_single_line(spoken, limit=120)}\n",
            )
        except Exception:  # noqa: BLE001
            logger.exception("会话摘要落库失败：task_id=%s", request.task_id)

        # 逐轮原文也要留一份：摘要给模型续接用，原文给"会话列表点进去看历史"
        # 与复盘取证用。少了它，"回到旧会话"只能是空屏。
        try:
            # 用户这一轮在 `_handle_message` 开头已经先写过（防"停止/刷新丢消息"），
            # 这里只补主理那一条；再写一次就是同一条消息在历史里出现两遍。
            if not await self._user_turn_saved(request):
                await self._memories.record_turn(
                    request.user_id,
                    request.task_id,
                    role="user",
                    text=request.message,
                    loop_stage=loop_stage,
                    client_msg_id=request.client_msg_id or "",
                )
            for message in result.messages:
                await self._memories.record_turn(
                    request.user_id,
                    request.task_id,
                    role=message.role,
                    text=message.text,
                    loop_stage=loop_stage,
                    agent_id=message.agent_id or "",
                    # 主理那一轮也带上幂等键：下一次重复消息靠它认出"这条答过了"。
                    client_msg_id=request.client_msg_id or "",
                    renderables=[item.model_dump(mode="json") for item in message.renderables],
                )
        except Exception:  # noqa: BLE001 - 原文落库失败不该让这一轮白答
            logger.exception("对话原文落库失败：task_id=%s", request.task_id)

        # 行为日志：每答一轮就是一次动作。停滞检测、环节推进、复盘时间线都读它。
        try:
            await self._behaviors.log(
                request.user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.ANSWER, payload=dict(answer_payload or {})
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception("行为日志落库失败：task_id=%s", request.task_id)

    async def _log_stage_events(
        self, stage: LoopStage, request: TurnRequest, *, valid: bool
    ) -> None:
        """把"这一步真的发生了什么"记进行为日志。

        为什么必须记：行为日志是**唯一的事实来源** —— 停滞干预靠它判断"他最近有没有动作"，
        环节推进靠它判断"能不能往下走"，复盘时间线靠它说清"这段时间发生过什么"。
        少记一条，链条上就有一处永远读不到东西，而且不报错。

        这里补的三条此前**都没有生产者**（枚举、干预白名单、轴A 判定里都写着它们，
        而全仓没有一处写）：

        · ② 认领差距：用户在诊断环节点了一个选项，就是认领了那一条差距 ——
          这正是设计里 ②→③ 的衔接点（见 `Report.gap_claims` 与 `GapClaim`）；
        · ⑤ 完成复盘：复盘环节产出了合规结论，才算走过一次复盘；
        · ④ 任务停滞：由停滞 Worker 记（不在这里，见 `workers/active_event.py`）。
        """
        if stage is LoopStage.DIAGNOSE and request.option_id and not request.option_id.startswith("asset."):
            await self._behaviors.log(
                request.user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.GAP_CLAIM,
                    payload={
                        "stage": stage.value,
                        "gap_id": request.option_id,
                        # 原话一起留：报告与复盘要能显示"他认领的是哪一条"，
                        # 只存一个 id 的话，界面上只剩一串没人看得懂的标识。
                        "label": request.message,
                    },
                ),
            )
        if stage is LoopStage.REVIEW and valid:
            await self._behaviors.log(
                request.user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.REVIEW,
                    payload={"stage": stage.value},
                ),
            )

    async def _persist_stage_output(
        self,
        stage: LoopStage,
        user_id: str,
        structured: dict[str, Any],
        *,
        valid: bool,
        session_id: str | None = None,
    ) -> list[AssetVersion]:
        """把合规的环节产出落成资产正文，返回本轮变化的资产版本。

        三条口径：

        1. **只落合规产出**。契约没过就不存 —— 存一份缺字段的报告比不存更坏：
        报告页会把它当成"完整报告"展示给用户，而它连 SWOT 都不齐。
        2. **落库失败不打断对话**。资产写不进去是服务端的事，用户这一轮的话已经答完了；
        这里记日志并继续，让错误出现在日志里而不是用户的屏幕上。
        3. **①采集 / ⑤复盘不产资产**：采集改的是画像（ProfileService 已在写），
        复盘产的是跟踪事件（走 FunctionService），都不该在这里顺手造一个空资产。
        """
        if not valid or not structured:
            return []

        # ⑤ 复盘本身不产资产（它产的是跟踪事件），但它**可以改计划**：
        # 复盘里说"周六删掉"，就得真的从行动计划里删掉（实测 ZY-05：
        # 话改了、资产没改，用户第二天看到的还是旧计划）。
        if stage is LoopStage.REVIEW:
            await self._apply_review_plan_patch(user_id, structured)
            await self._complete_round(session_id)
            return []

        converters = {
            LoopStage.DIAGNOSE: self._save_report,
            LoopStage.DECIDE: self._save_direction_plans,
            LoopStage.ACT: self._save_action_plan,
        }
        saver = converters.get(stage)
        if saver is None:
            return []

        try:
            return await saver(user_id, structured)
        except Exception:  # noqa: BLE001 - 落库失败不能让用户这一轮白说
            logger.exception("环节产出落库失败：stage=%s", stage.value)
            return []

    async def _apply_collect(
        self, user_id: str, structured: dict[str, Any]
    ) -> CollectWriteResult:
        """把 ① 采集这一轮的字段与缺口落进画像。

        为什么必须有这一步
        ------------------
        采集环节的产出**不是资产**，它就是画像本身：模型把
        "兴趣 = 结构设计、把握 0.8、来源 对话" 结构化地返回了，
        此前这里没有任何落库路径 —— 读完就丢。后果是三重的，而且都不报错：

          · 画像面板恒空（用户回答了一堆，界面上还是"进入对话完成首次建档"）；
          · 采集清单恒说"还缺 6 条"（缺口从没被更新过）；
          · ② 诊断照样能凭对话记忆生成 15 维报告（看起来一切正常），
            但那份报告**没有画像依据**，`depends_on_profile_keys` 是空的，
            于是"画像一变就重算受影响资产"这条影响面传播也一并失效。

        落库失败不打断这一轮：用户的话已经答完了，错误进日志即可（与资产落库同一条口径）。

        **但"用户亲手写的"那条值不许被推断覆盖**（见下方字段门禁之后的第二道判定）。
        他在画像里点「更正」把专业改成自己要的那句，下一轮对话里模型再产出一条
        `major` 就把他的话盖掉了 —— 他刚纠正过的东西又变回去，而界面上没有一处
        告诉他发生了什么。挡掉之后保留的是他自己写的那条值（`user_edit`），
        权威记录（`record`：学信网核验 / 教务导入）仍然覆盖得动 —— 它是出具方，
        比自述更权威。他本人也随时能再「更正」一次，这条路没被堵死
        （写 `user_edit` 的是 `DefaultProfileService.correct_field`，不经过这里）。

        返回值见 `CollectWriteResult`：`blocked_by_user_edit` 由 `handle_message` 拼成
        一条用户可见的 `Disclosure`（他刚说的那句撞上自己填过的格子时**必须当面说**，
        并告诉他去哪儿改）。被挡下的写入同时也留一条 `WARNING` 日志，给查库的人看。
        """
        from zhiyin_business.contracts.collect import CollectOutput, FieldUpdate

        try:
            output = CollectOutput.model_validate(structured)
        except Exception:  # noqa: BLE001
            # 整份不合契约时，**仍然把能解析的字段捞出来**。
            #
            # 这是这一环唯一的硬指标：他说的话有没有被记下来。因为缺了别的字段
            # （比如没写 conclusion、少了一个数组）就把这一轮的画像更新整段丢掉，
            # 代价是用户白说一遍、采集清单还挂着"还差 N 条" —— 而那正是他刚答过的。
            salvaged: list[Any] = []
            for item in structured.get("field_updates") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    salvaged.append(FieldUpdate.model_validate(item))
                except Exception:  # noqa: BLE001 - 这一条解析不了就跳过这一条
                    continue
            if not salvaged:
                logger.warning("① 采集产出里没有可解析的字段，本轮不写画像")
                return CollectWriteResult()
            logger.warning(
                "① 采集产出不合契约，仍从里面救回 %d 条字段更新", len(salvaged)
            )
            output = CollectOutput(field_updates=salvaged)

        allowed = self._allowed_profile_keys()
        # 画像里现有的每一条（键 → 整条字段）：判"这一格是不是他亲手写的"要看**来源**，
        # 而来源只长在那条旧值上。读一次，这一轮所有字段共用。
        current = await self._current_fields(user_id)
        dropped: list[str] = []
        written: list[str] = []
        blocked_by_user_edit: list[str] = []
        for update in output.field_updates:
            if update.source in {ProfileSource.RECORD, ProfileSource.USER_EDIT}:
                update = update.model_copy(update={"source": ProfileSource.CONVERSATION})
            key = self._normalize_profile_key(update.key)
            # **字段门禁**：画像只有一份固定词表（动态资源的采集规则）。
            # 不在表里的键一律不写 —— 放进去的代价不是"多一条记录"，
            # 而是界面上多一条没人认识、也没有中文名的东西，
            # 采集清单与报告维度又都对不上它，整份画像从此不可分析。
            if allowed and key not in allowed:
                dropped.append(update.key)
                continue
            # **第二道门禁：他亲手写的那条值不许被推断覆盖**（见方法说明与
            # `policies/collection.py::may_override_user_edit`）。判在写之前，
            # 因为 `update_field` 是整行替换：写进去就找不回原值了。
            if not may_override_user_edit(current.get(key), update.source):
                blocked_by_user_edit.append(key)
                continue
            try:
                await self._profiles.update_field(
                    user_id,
                    key,
                    update.value,
                    confidence=update.confidence,
                    source=update.source.value,
                    # 名字跟着字段一起落库：字段键是模型自己起的（interest_direction
                    # 这种），界面没有中文名就只剩一串英文。
                    label=update.label,
                    evidence=list(update.evidence),
                )
            except Exception:  # noqa: BLE001 - 同资产：一条写不进去不该断整轮
                logger.exception("画像字段落库失败：key=%s", update.key)
                continue
            written.append(key)

        # 画像更新本身也是一次**动作**：干预判定要能看见"他刚补了信息"，
        # 否则一个只补画像、不勾任务的人会被判成"好几天没动"。
        # 这条事件类型一直躺在干预白名单里，此前没有任何生产者（实测库里 0 行）。
        #
        # 被挡下的那几条**不算一次更新**：库里没有新值，却报一条"画像字段更新"，
        # 会让影响面传播去重算一份没变的画像（而它的由头正是这次"更新"）。
        for key in written:
            await self._behaviors.log(
                user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.PROFILE_FIELD_UPDATED,
                    payload={"field_key": key, "stage": LoopStage.COLLECT.value},
                ),
            )

        if blocked_by_user_edit:
            # 不静默，但也不当故障：这是设计如此。日志里要说清"被挡的是什么、
            # 原值是谁写的、他要改该走哪条路" —— 否则下一个人看到"画像没更新"，
            # 只能从头查一遍（实测这类问题查起来很费时间）。
            logger.warning(
                "画像写入被「本人填写」挡下：%s —— 这些格子是他自己更正过的，"
                "对话推断不许覆盖它；要改仍由他本人点「更正」改（POST profile/fields/{key}）",
                sorted(set(blocked_by_user_edit)),
            )

        if dropped:
            # 不静默：被门禁挡掉的键要能被发现（多半是提示词需要补一条同义词）
            logger.warning(
                "画像字段门禁挡下不在词表里的键：%s（当前词表 %d 条）",
                sorted(set(dropped)),
                len(allowed),
            )

        # **画像真的变了**才作废那份"外部情报"（它是按画像取的）。
        # 不丢的话，新用户先取过一次空的，补完画像之后十几分钟里界面还是空；
        # 但**每轮都丢**的代价更大：采集阶段每轮都会重爬一遍外部站点（实测 10 次请求、
        # 约 7 秒），而多数轮次一个字段都没改 —— 用户为此白等，站点也被白打。
        if written and self._functions is not None:
            self._functions.drop_intel_cache(user_id)

        if output.remaining_gaps:
            # 缺口与字段走**同一套**归一与词表：它们指的是同一批东西
            # （"还差专业"和"专业已拿到"必须对得上）。只归一字段不归缺口的话，
            # 界面上就会出现"字段叫「学历层次」、缺口叫 education_stage"这种自相矛盾。
            labels = {spec.key: spec.label for spec in self._profile_vocabulary()}
            normalized: list[Any] = []
            for gap in output.remaining_gaps:
                key = self._normalize_profile_key(gap.key)
                if allowed and key not in allowed:
                    continue
                normalized.append(
                    gap.model_copy(
                        update={"key": key, "label": gap.label or labels.get(key, "")}
                    )
                )
            blocked = [
                self._normalize_profile_key(gap.key)
                for gap in output.remaining_gaps
                if allowed and self._normalize_profile_key(gap.key) not in allowed
            ]
            if blocked:
                logger.warning("画像缺口门禁挡下不在词表里的键：%s", sorted(set(blocked)))
            if not normalized:
                # 本轮缺口全被门禁挡下（多半是模型自己发明了键）：
                # **保留上一份清单**，不要用空表覆盖 —— 空表和"没有缺口"
                # 在界面上是同一句话，而那会与采集清单里的"还差 N 条"自相矛盾。
                logger.warning("本轮缺口全部不在词表里，保留上一份清单")
            else:
                try:
                    await self._profiles.replace_gaps(user_id, normalized)
                except Exception:  # noqa: BLE001
                    logger.exception("画像缺口落库失败")

        return CollectWriteResult(
            written=tuple(written),
            blocked_by_user_edit=tuple(sorted(set(blocked_by_user_edit))),
            dropped_by_gate=tuple(sorted(set(dropped))),
        )

    async def _current_fields(self, user_id: str) -> dict[str, Any]:
        """画像里现在已有的字段（键 → 整条），用来判"这一格是不是他亲手写的"。

        为什么允许多读一次：判据（来源）只长在旧值上，不读旧值就只能盲写，
        而 `update_field` 是整行替换 —— 盲写的代价是他自己更正过的值被盖掉。

        读不到就返回空表（＝这一轮不挡）：**读旧画像失败不该让用户刚说的话
        全部写不进去**，这与 `DefaultProfileService.update_field` 里 `is_new`
        的降级是同一条口径（那里也把读失败当"未知"，照样写）。
        代价是这一次可能盖掉一条本人填写的值，但那要求读路径先坏掉 ——
        比起"他说了话画像一动不动"，这是更小、也更可查的一种失败。
        """
        try:
            return {field.key: field for field in await self._profiles.get_fields(user_id)}
        except Exception:  # noqa: BLE001
            logger.warning("读取既有画像失败，本轮不做「本人填写」保护", exc_info=True)
            return {}

    def _allowed_profile_keys(self) -> set[str]:
        """画像允许的字段键（动态资源里的画像字段词表；读不到时返回空集＝不拦）。

        读不到就不拦：把"配置没装载"变成"用户说的话被丢掉"，比多几条字段坏得多。
        """
        return {
            spec.key for spec in self._profile_vocabulary() if not spec.alias_of
        }

    def _normalize_profile_key(self, key: str) -> str:
        """把模型写的同义词归到规范键上（`grade` → `study_year`）。

        不做这一步的后果，实测是这样的：同一个意思在不同轮次被写成
        `internship` / `internship_experience` / `experience` 三条，
        画像里三格都占着，而采集清单还在说"实习经历没拿到"。
        """
        raw = (key or "").strip()
        for spec in dynamic_config.snapshot().profile_fields:
            if spec.alias_of and spec.key == raw:
                return spec.alias_of
        return raw

    @staticmethod
    def _profile_vocabulary() -> tuple[Any, ...]:
        """画像字段词表（键 + 中文名），来自装载好的动态配置快照。

        与界面显示名**同一份**：文案包里的 `profile.field.<键>`。
        """
        return dynamic_config.snapshot().profile_fields

    async def _asset_dependencies(self, user_id: str) -> list[str]:
        """这份资产依赖哪些画像字段。

        取当前画像的**全部字段键**：诊断/决策/行动都是拿整份画像得出的结论，
        声称"只依赖其中三个"会让影响面传播漏掉该重算的资产。
        将来若真的按字段片段生成，这里改成从产出里取证据链即可。
        """
        profile = await self._profiles.get(user_id)
        return [field.key for field in (profile.fields if profile else [])]

    async def _save_report(self, user_id: str, structured: dict[str, Any]) -> list[AssetVersion]:
        from zhiyin_business.contracts.diagnose import DiagnoseOutput
        from zhiyin_business.services.asset_content import report_from_diagnose

        # 兜底再修一次：这条路径也可能被别的调用方直接使用（不只对话主链路）。
        if not _diagnose_prose_is_unsafe(structured):
            structured = _sanitize_absence_words(_repair_diagnose_evidence(structured))
        output = DiagnoseOutput.model_validate(structured)
        report = report_from_diagnose(output, user_id=user_id)
        # 认领是**用户行为**，不该被重算冲掉：报告里的 gap_claims 是从行为日志
        # 还原出来的快照，而不是模型这一轮的输出。事实来源只有一个（行为日志），
        # 报告只是把"他已经认领了哪几条"摆回正文里给他看得见。
        claims = await self._claimed_gaps(user_id)
        if claims:
            report = report.model_copy(update={"gap_claims": claims})
        version = await self._assets.save_report(
            user_id,
            report,
            depends_on_profile_keys=await self._asset_dependencies(user_id),
            diff_from_previous="② 诊断产出：15 维与 SWOT",
        )
        return [version]

    async def _claimed_gaps(self, user_id: str) -> list[GapClaim]:
        """用户认领过的差距（事实来源是行为日志，见 `_log_stage_events`）。

        读不到就返回空表：认领记录丢了不该让这一轮报告生成失败，
        更不该编一条出来（报告的每一格都要能追回一条真实记录）。
        """
        try:
            behaviors = await self._behaviors.recent(user_id, limit=50)
        except Exception:  # noqa: BLE001
            logger.warning("读取认领记录失败，报告里的差距认领按空处理", exc_info=True)
            return []
        claims: list[GapClaim] = []
        seen: set[str] = set()
        for event in behaviors:
            if event.event_type is not BehaviorEventType.GAP_CLAIM:
                continue
            gap_id = str(event.payload.get("gap_id") or "").strip()
            if not gap_id or gap_id in seen:
                continue
            seen.add(gap_id)
            claims.append(
                GapClaim(
                    gap_id=gap_id,
                    label=str(event.payload.get("label") or ""),
                    claimed_at=event.occurred_at,
                )
            )
        return claims

    async def _save_direction_plans(
        self, user_id: str, structured: dict[str, Any]
    ) -> list[AssetVersion]:
        from zhiyin_business.contracts.decide import DecideOutput
        from zhiyin_business.services.asset_content import direction_plans_from_decide

        output = DecideOutput.model_validate(structured)
        if not output.plans:
            # 一套方案都没有的"决策"不是决策：语义上应当回落到澄清追问，
            # 这里不落库（落一个空方案组会让工作台显示"已有方案"）。
            logger.warning("③ 决策产出里没有方案，未落库（应回落到澄清追问）")
            return []
        plans = direction_plans_from_decide(output, user_id=user_id)
        version = await self._assets.save_direction_plans(
            user_id,
            plans,
            depends_on_profile_keys=await self._asset_dependencies(user_id),
            diff_from_previous=f"③ 决策产出：{len(plans)} 套方向方案",
        )
        return [version]

    async def _apply_review_plan_patch(
        self, user_id: str, structured: dict[str, Any]
    ) -> None:
        """把复盘给出的结构化调整真正落到行动计划上（实测 ZY-05）。

        只在复盘明确给出 `plan_patch` 且确实命中时才写：
        没给、或给了但对不上任何一条任务，就什么都不做 —— 宁可不动，
        也不要凭空造一次"已按复盘调整"的假象。
        落库失败只记日志：用户这一轮的话已经答完了。

        仅此一处会以「⑤ 复盘校准」为差异说明升版；单纯的"做完了"不升版。
        """
        from zhiyin_business.contracts.review import ReviewOutput
        from zhiyin_business.services.plan_patch import apply_plan_patch

        try:
            output = ReviewOutput.model_validate(structured)
        except Exception:
            logger.warning("复盘产出无法按契约解析，跳过计划调整", exc_info=True)
            return
        if output.plan_patch is None:
            return
        plan = await self._assets.get_action_plan(user_id)
        if plan is None:
            logger.info("复盘要求调整计划，但当前没有行动计划，未落库")
            return

        from zhiyin_business.contracts.student import Preferences

        state = await self._student_state.get(user_id) if self._student_state is not None else {}
        preferences = Preferences.model_validate(state.get("preferences", {}))
        updated, summary = apply_plan_patch(plan, output.plan_patch, timezone_name=preferences.timezone)
        if not summary:
            logger.info("复盘给出的计划调整没有命中任何任务，未落库")
            return
        try:
            await self._assets.save_action_plan(
                user_id,
                updated,
                diff_from_previous="⑤ 复盘校准：" + "；".join(summary[:3]),
            )
        except Exception:
            logger.warning("复盘的计划调整没落库", exc_info=True)
            return
        logger.info("复盘校准已落到计划：%s", "；".join(summary))

    async def _complete_round(self, session_id: str | None) -> None:
        """复盘走完 → 给这一轮一个明确的结束边界（实测 ZY-12）。

        原本：五阶段都走完了，页面上仍写着"⑤ 复盘校准 进行中"，系统继续生成微任务，
        用户得自己判断什么时候可以停。

        状态本来就存在（`TaskStatus.COMPLETED` 与 `update_status`），
        缺的只是"复盘完成时把它标上"。标记的是**这一轮**的结束：
        长期陪伴仍然有效，用户随时能开新的一段，所以页面上说的是"本轮完成"。
        """
        if not session_id:
            return
        try:
            await self._sessions.update_status(session_id, TaskStatus.COMPLETED)
        except Exception:
            logger.warning("复盘完成，但会话状态没更新", exc_info=True)

    async def _save_action_plan(
        self, user_id: str, structured: dict[str, Any]
    ) -> list[AssetVersion]:
        from zhiyin_business.contracts.act import ActOutput
        from zhiyin_business.services.asset_content import action_plan_from_act

        output = ActOutput.model_validate(structured)
        if output.need_recheck_direction:
            # 拆不动就回 ②，不要硬拆 —— 这一条是产出契约里写明的前置判断。
            logger.info("④ 行动产出要求回 ② 复核方向，未落库")
            return []
        plan, nodes = action_plan_from_act(output, user_id=user_id)
        # 关键节点日历：规划师写入、教练读取。先写日历再存计划 ——
        # 顺序反过来的话，`reminders_synced=True` 会在日历还没写进去时就落库。
        if self._functions is not None and nodes:
            for node in nodes:
                await self._functions.write_calendar_node(user_id, node)
            plan = plan.model_copy(update={"reminders_synced": True})
        version = await self._assets.save_action_plan(
            user_id,
            plan,
            depends_on_profile_keys=await self._asset_dependencies(user_id),
            diff_from_previous="④ 行动产出：阶段与任务",
        )
        return [version]

    async def _badge(self, agent_id: str, theory_refs: list[TheoryRef]) -> AgentBadge:
        descriptor = await self._registry.get_agent(agent_id)
        return AgentBadge(
            agent_id=agent_id,
            name=descriptor.name if descriptor else agent_id,
            role_summary=descriptor.role_summary if descriptor else "",
            theory_refs=theory_refs,
        )

    async def _known_theory_refs(self, raw: Any) -> list[TheoryRef]:
        """只保留**真实存在**的理论卡引用。

        为什么要在边界上筛：`theory_refs` 是模型给的。模型手里没有一份"合法 id 清单"，
        于是会照名字编一个（实测拿到过 `theo_clover`，而真卡 id 是 `clover`）。
        前端拿到这种 id 会**如实去请求** `GET /app/theory-cards/theo_clover` → 404，
        用户点开是一张打不开的卡 —— 而它本来就不该出现在界面上。

        筛掉不等于装作没发生：进日志（WARNING），这样"模型在编 id"这件事看得见，
        可以顺着去补提示词或给模型一份清单，而不是静默吞掉。
        """
        refs = _theory_refs(raw)
        if not refs:
            return []
        known = {card.id for card in await self._registry.list_theory_cards()}
        kept: list[TheoryRef] = []
        for ref in refs:
            if ref.theory_id in known:
                kept.append(ref)
            else:
                logger.warning(
                    "理论卡引用不存在，已从徽章里剔除：id=%s（模型可能编了 id）",
                    ref.theory_id,
                )
        return kept

    # ------------------------------------------------------------------
    # 对话回灌：上一轮说了什么
    # ------------------------------------------------------------------

    #: 回灌几轮。规格是"最近三条对话（自己与他各一句）"，一条对话两轮，
    #: 取 6 条正好是三次来回；再多只会把这一轮真正要看的东西挤下去。
    _TURN_GROUP_SIZE = 6
    #: 仓储取最近的若干条并按时间正序返回，上限与会话历史使用相同量级。
    _TURN_GROUP_SCAN = 200
    #: ① 采集最多问几轮用户回答。到上限后带缺口进入诊断 —— 门槛是"尽量采到"，
    #: 不是"采不到就不许往下走"：产品口径是宁可带着不完整画像进入下一环。
    _MAX_COLLECT_ROUNDS = 8
    #: 每行上限。原文里可能有几百字的附件正文（用户传一份简历就是一整篇）。
    _TURN_LINE_MAX = 30

    async def _turn_group(
        self, user_id: str, task_id: str, *, exclude_user_text: str = ""
    ) -> list[str]:
        """最近几条对话的短行（`他：…` / `职业顾问：…`）。

        取**逐轮原文**（`biz_conversation_turn`），不是累积摘要：摘要里塞的是历次
        产出的 JSON 原文，越到后面越像一坨内部数据，模型读不出"刚才聊到哪"。

        取不到就返回空表 —— 这一轮照常走完，只是"接不上话"这件事会如实留在
        这一轮里，而不是拿一份编出来的对话顶上。

        `exclude_user_text`：这一轮的用户消息在 `_handle_message` 开头已先落库，
        它本身会作为 `user_input` 单独进提示词；再从历史里带一遍就是同一句话说两次，
        还会让"第一轮不该有历史对话"这类口径失真。
        """
        try:
            turns = await self._memories.list_turns(
                user_id, task_id, limit=self._TURN_GROUP_SCAN
            )
        except Exception:  # noqa: BLE001 - 回灌失败不该吃掉用户这一轮的话
            logger.warning("读取逐轮原文失败：task_id=%s", task_id, exc_info=True)
            return []
        lines: list[str] = []
        visible = list(turns[-self._TURN_GROUP_SIZE :])
        if exclude_user_text:
            # 只去掉"这一轮"用户消息（最近一条同文），历史里同文的更早消息保留。
            for index in range(len(visible) - 1, -1, -1):
                if visible[index].role == "user" and visible[index].text == exclude_user_text:
                    visible.pop(index)
                    break
        for turn in visible:
            text = _single_line(turn.text, limit=self._TURN_LINE_MAX)
            if not text:
                continue
            who = "他" if turn.role == "user" else await self._spoken_name(turn.agent_id)
            lines.append(f"{who}：{text}")
        return lines

    async def _spoken_name(self, agent_id: str) -> str:
        """agent_id → 用户称呼；取不到就用「主理」顶上。

        与 `_display_name` 不同，这里**不抛**：回灌的是历史，一句称呼缺了，
        不该让用户这一轮已经说完的话白说。
        """
        if not agent_id:
            return "主理"
        descriptor = await self._registry.get_agent(agent_id)
        name = descriptor.name if descriptor else ""
        return name or "主理"

    async def _stale_asset_types(self, user_id: str) -> set[AssetType]:
        """哪些资产的当前版本是"画像变过、还没重算"的。

        读的是三本正文资产的最新版本标记（见 `AssetVersion.needs_recompute`）。
        读不到不算这一轮失败：标记只用来决定"要不要补一句告知"，
        所以异常按"没有待重算的资产"处理并留日志。
        """
        stale: set[AssetType] = set()
        for asset_type in (
            AssetType.REPORT,
            AssetType.DIRECTION_PLAN,
            AssetType.ACTION_PLAN,
        ):
            try:
                latest = await self._assets.get_latest_version(user_id, asset_type)
            except Exception:  # noqa: BLE001
                logger.warning("读取资产待重算标记失败：%s", asset_type.value, exc_info=True)
                continue
            if latest is not None and latest.needs_recompute:
                stale.add(asset_type)
        return stale

    async def _conclusion_change_disclosure(self) -> Disclosure:
        """结论变化告知。文案取自动态资源，缺配置直接抛（不用字面量顶上）。"""
        prompt = await self._required_prompt(_CONCLUSION_CHANGE_PROMPT)
        return Disclosure(kind="conclusion_change", text=prompt.content.strip())

    async def _field_kept_disclosure(self, keys: Sequence[str]) -> Disclosure:
        """本人填写未被覆盖告知：被挡下的是哪几格、为什么、他要改该去哪儿改。

        字段名走画像词表（`_profile_vocabulary`，与界面同一份中文名），**不念英文键**：
        `major` 对用户毫无意义，"专业"才是他在画像里看到的那个词。
        这个词表读不到（配置没装载）时退回键本身 —— 宁可难看，也不能因为他这一格
        没名字就整句话不说（不说的代价正是这次要修的那个现象）。

        `kind` 用既有的 `conclusion_change`：对外它属于同一类"这一轮有件事你得知道"，
        前端只渲染 `text`（见 `web/src/stores/session.ts`）。新开一个枚举取值要同时改
        业务契约、API 视图、OpenAPI 快照与前端类型，收益只是内部标签更贴切 ——
        这轮不做，留在这里说明为什么。
        """
        labels = {spec.key: spec.label for spec in self._profile_vocabulary()}
        names = "、".join(labels.get(key, "") or key for key in keys)
        prompt = await self._required_prompt(_FIELD_KEPT_PROMPT)
        # 占位符对不上会在这里抛 KeyError：那是配置错，不是运行故障，不该被吞掉
        # （与 `_lead_change_reason` 同一条口径）。
        return Disclosure(kind="conclusion_change", text=prompt.content.format(fields=names))

    # ------------------------------------------------------------------
    # 用户可见文案：取自动态资源，代码里不再拼句子
    #
    # 这两段以前都是**写在代码里的字符串**，而且拼接时把内部概念直接带给了用户：
    #   · 换主理的理由写成「进入 collect 环节，改由 career_advisor 主理」——
    #     环节枚举与智能体标识对用户毫无意义，还会让人以为系统漏了翻译；
    #   · 澄清追问写成一句字面量，改一次口径要发一次版。
    # 现在两个占位符都来自数据：接手人的**用户称呼**与该环节的**用户说法**。
    #
    # 三处都**不做兜底**：配置缺了就抛。兜底句看着稳妥，代价是把"少了一条配置"
    # 变成"这一轮回答得有点怪"，等有人察觉时已经不知道该查哪一天。
    # ------------------------------------------------------------------

    async def _clarify_text(self) -> str:
        """全新会话的澄清追问。配置缺失直接抛，不用字面量顶上。"""
        prompt = await self._registry.get_prompt(CLARIFY_PROMPT_CODE)
        if prompt is None or not prompt.content.strip():
            raise MissingConfigError(f"缺少澄清话术配置：{CLARIFY_PROMPT_CODE}")
        return prompt.content.strip()

    async def _lead_change_reason(self, stage: LoopStage, to_agent: str, *, direction_selected: bool | None = None) -> str:
        """换主理时对用户说的那句话：谁接手 + 为什么。"""
        reason_code = _LEAD_CHANGE_REASON_PROMPT.format(stage=stage.value)
        template = await self._required_prompt(_LEAD_CHANGE_PROMPT)
        reason = await self._required_prompt(reason_code)
        to_name = await self._display_name(to_agent)
        # 占位符对不上会在这里抛 KeyError：那是配置错，不是运行故障，不该被吞掉。
        reason_text = "先把当前想法整理成步骤，方向仍可调整。" if stage is LoopStage.ACT and direction_selected is False else reason.content
        return template.content.format(to_name=to_name, reason=reason_text)

    async def _display_name(self, agent_id: str) -> str:
        """agent_id → 用户称呼。取不到就抛：把标识念给用户听等于没配。"""
        descriptor = await self._registry.get_agent(agent_id)
        if descriptor is None or not descriptor.name:
            raise MissingConfigError(f"智能体展示名缺失：{agent_id}")
        return descriptor.name

    async def _required_prompt(self, code: str) -> PromptSpec:
        prompt = await self._registry.get_prompt(code)
        if prompt is None:
            raise MissingConfigError(f"缺少提示词配置：{code}")
        return prompt


def _guide(raw: Any, structured: dict[str, Any] | None = None) -> BehaviorGuide:
    """本轮该对用户说的那句话。

    这里曾经用一句**写死的**文案兜底（"你愿意先说说现在最卡的那一步吗？"）。
    后果很严重：模型明明答了，只是它的 JSON 少了 `guide` 字段（契约里
    `guide` 是必填，模型经常漏），于是每个回合、无论用户说什么，
    界面上都是同一句话 —— 用起来就像接了个假模型。

    所以兜底的顺序改成"尽量用**模型自己写的内容**"：
      1. 模型给了合法 guide → 直接用；
      2. 没给，但它给了 `remaining_gaps[].suggested_next_action`
         —— 那本来就是模型写的"下一步该问什么"，直接拿它当追问；
      3. 都没有 → 才用系统兜底句，而且措辞要像是系统在说话，不是主理在说话。
    """
    if isinstance(raw, dict):
        try:
            return BehaviorGuide.model_validate(raw)
        except Exception:
            pass

    for gap in (structured or {}).get("remaining_gaps") or []:
        if not isinstance(gap, dict):
            continue
        action = str(gap.get("suggested_next_action") or "").strip()
        if action:
            return BehaviorGuide(kind="question", text=action, question=action)

    return BehaviorGuide(
        kind="question",
        text="这一轮我没能按格式产出内容。你再说一句，我重新试。",
        question="这一轮我没能按格式产出内容。你再说一句，我重新试。",
    )


def _theory_refs(raw: Any) -> list[TheoryRef]:
    if not isinstance(raw, list):
        return []
    refs: list[TheoryRef] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                refs.append(TheoryRef.model_validate(item))
            except Exception:
                continue
    return refs


def _renderables_for_turn(
    from_model: Sequence[Renderable],
    stage: Any,
    structured: dict[str, Any],
    *,
    message: str = "",
    profile: Any = None,
) -> list[Renderable]:
    """这一轮要摆给用户看的可视件：主理自己点的那张，或者这一环节默认那张。

    **只有一种形状**（`Renderable`），前端按 `kind` 分发渲染。
    以前这里另有一条"柱状图专用字段 `chart`"的兼容通道 —— 前端当时只认它。
    现在前端按 kind 走，那条通道就删了：少了"同一张图有两个字段"的歧义
    （改一处漏一处，就会出现"图没变、别处变了"这种说不清的现象）。

    默认那张只从**实测分值**里取点：
      · ② 诊断 —— 画像各维的把握度（"你现在哪一块最薄"一眼能看出来）；
      · ③ 决策 —— 三套方案的匹配度（"三套差多少"比三行字清楚）。
    取不到就不补：宁可没有图，也不要拿编出来的数字画一张。
    """
    kept = _without_uninformative_full_scale_bars(
        validate_renderables([item.model_dump(mode="json") for item in from_model])
    )
    # 否定意图优先于关键词命中，也优先于模型已经调用过的画图工具。
    # 否则“不要生成图表”既会命中“生成图表”，模型误调工具后还会把图原样带出去。
    if _forbids_chart(message):
        return [item for item in kept if item.kind != "bars_chart"]
    if not _asks_for_chart(message):
        return [item for item in kept if item.kind != "bars_chart"]
    if any(item.kind == "bars_chart" for item in kept):
        return kept
    if _asks_for_chart(message):
        fields = list(getattr(profile, "fields", []) or [])
        points = [
            {
                "label": str(field.label or field.key)[:12],
                "value": field.confidence,
            }
            for field in fields
            if field.confidence is not None and (field.label or field.key)
        ]
        if len(points) >= 2:
            kept.extend(
                _without_uninformative_full_scale_bars(validate_renderables(
                    [{
                        "kind": "bars_chart",
                        "title": "这几项你现在各有多少把握",
                        "payload": {"unit": "%", "points": points[:8]},
                    }]
                ))
            )
            if any(item.kind == "bars_chart" for item in kept):
                return kept
        # 用户明确要图时，没有可比较的数据就如实说画不出来；不要再拿当前环节的
        # 默认图替代，否则看起来像回答了请求，实际比较的是另一组东西。
        return kept
    # Do not attach a stage-default chart to unrelated questions. In
    # particular, model-generated direction scores are not verified metrics.
    return kept


def _without_uninformative_full_scale_bars(items: list[Renderable]) -> list[Renderable]:
    """去掉三项以上全部为 100% 的柱状图。

    画像里的 ``confidence=1`` 对本人更正字段表示“这句话确由本人确认”，并不等于
    兴趣、能力或经历已经被客观验证到 100%。把一长串这样的值画成满格条既没有
    比较信息，也容易被理解成确定性结论；保留原始字段，但不把它伪装成有区分度的图。
    """
    result: list[Renderable] = []
    for item in items:
        points = item.payload.get("points") if item.kind == "bars_chart" else None
        values = [point.get("value") for point in points or [] if isinstance(point, dict)]
        if len(values) >= 3:
            try:
                if all(abs(float(value) - 1.0) < 1e-9 for value in values):
                    continue
            except (TypeError, ValueError):
                pass
        result.append(item)
    return result


def _forbids_chart(message: str) -> bool:
    text = message.strip()
    return bool(re.search(
        r"(?:不要|不想|不需要|无需|不用|别|禁止|避免).{0,8}(?:图表|柱状图|可视化|画图)",
        text,
    ))


def _asks_for_chart(message: str) -> bool:
    text = message.strip()
    if _forbids_chart(text):
        return False
    return any(word in text for word in (
        "画个图", "画张图", "画一个图", "画图", "给我一张图",
        "生成图表", "做个图表", "做张图表", "看图表", "看看图表",
        "展示图表", "用图表", "画柱状图", "看柱状图",
        "可视化一下", "做个可视化", "给我可视化", "看看可视化",
    ))


def _chart_reply_text(renderables: list[Renderable]) -> str:
    """明确要图时用已核验图点生成回话，避免模型文字否认已存事实。"""
    labels = list(dict.fromkeys(
        str(point.get("label") or "").strip()
        for chart in renderables
        for point in (chart.payload.get("points") or [])
        if isinstance(point, dict) and str(point.get("label") or "").strip()
    ))
    if not labels:
        return "目前没有足够的可比较数据生成图表；补充或核对记录后可以再看。"
    shown = "、".join(labels[:4])
    suffix = f"等 {len(labels)} 项" if len(labels) > 4 else ""
    return f"图表已生成，展示已存记录中的{shown}{suffix}。这张图只呈现这些记录，不代表职业匹配结论。"


def _default_bars(stage: Any, structured: dict[str, Any]) -> Optional[Renderable]:
    """这一环节顺手给的那张柱状图（点全部来自库里已存的分值）。

    **超出 0–1 的分值一律不画**（调用方过 `validate_renderables`，见
    `test_default_chart_rejects_model_score_outside_ratio_range`）：宁可没有图，
    也不要把一个量纲不明的数字画成图 —— 前端拿到 7400 会当比值再乘 100，
    用户读到的是"740000 分"加三根一样长的柱子（issue 证据截图 3/4/6）。
    契约本身在 `contracts/decide.py`：`match_score: ge=0.0, le=1.0`。
    """
    try:
        if stage is LoopStage.DECIDE:
            points = [
                {
                    "label": str(plan.get("name") or f"方案{i + 1}")[:12],
                    "value": float(plan["match_score"]),
                }
                for i, plan in enumerate(structured.get("plans") or [])
                if isinstance(plan, dict)
                and isinstance(plan.get("match_score"), (int, float))
            ]
            if len(points) >= 2:
                # 标题是**用户要读的**：不写"三套方案"这种内部说法（实测用户看不懂
                # "三条路""三套方案"指的是什么），写他一看就懂的那件事。
                return Renderable(
                    kind="bars_chart",
                    title="各方向和你手上的东西合不合",
                    payload={"unit": "分", "points": points},
                )
        if stage is LoopStage.DIAGNOSE:
            points = [
                {
                    "label": str(item.get("name") or item.get("dimension") or "")[:12],
                    "value": float(item.get("score") or item.get("value") or 0.0),
                }
                for item in (structured.get("gaps") or structured.get("dimensions") or [])
                if isinstance(item, dict)
            ]
            points = [point for point in points if point["label"]]
            if len(points) >= 3:
                return Renderable(
                    kind="bars_chart",
                    title="这几项你现在各有多少把握",
                    payload={"unit": "分", "points": points[:8]},
                )
    except Exception:  # noqa: BLE001 - 画不出图不该影响这一轮回复
        logger.warning("这一轮没能构造默认可视件，跳过", exc_info=True)
    return None


def _intel_refs(external: Any) -> list[IntelRef]:
    """这一轮真的取回的外部事实，做成可点回原页面的引用。

    `external` 是 `DataSourceResult.model_dump()` 之后的样子（见 prompt_vars）。
    没有取到就是空表 —— 不编来源。
    """
    records = (external or {}).get("records") if isinstance(external, dict) else None
    refs: list[IntelRef] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        url = str(record.get("source_url") or "")
        if not url:
            continue
        refs.append(
            IntelRef(
                id=str(record.get("id") or ""),
                title=str(record.get("title") or "")[:60],
                kind_label=kind_label(str(record.get("kind") or "")),
                source_name=source_name_of(url),
                source_url=url,
            )
        )
    return refs[:4]


def _replace_task_ids_in_prose(value: Any, task_labels: dict[str, str]) -> Any:
    """复盘正文用任务文字称呼已登记任务，保留结构中的机器 ID。"""
    if isinstance(value, dict):
        return {
            key: item if key in {"id", "task_id", "option_id", "achievements_unlocked", "plan_patch"}
            else _replace_task_ids_in_prose(item, task_labels)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_task_ids_in_prose(item, task_labels) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    for task_id, label in sorted(task_labels.items(), key=lambda pair: len(pair[0]), reverse=True):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(task_id)}(?![A-Za-z0-9_])"
        text = re.sub(pattern, lambda _match, label=label: f"「{label}」", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]+(?=「)", "", text)
    return re.sub(r"(?<=」)[ \t]+(?=[\u4e00-\u9fff])", "", text)


def _single_line(text: str, *, limit: int = 0) -> str:
    """把一段原文压成一行：换行与连续空白折成单空格，超长（limit>0）截断。

    回灌给模型的对话必须是短行：用户传一份简历进来，原文就是几百上千字，
    照抄进去会把这一轮真正要看的东西挤出上下文。
    """
    collapsed = " ".join((text or "").split())
    if limit and len(collapsed) > limit:
        return collapsed[:limit] + "…"
    return collapsed


def _prose_of(raw_text: str) -> str:
    """从模型原文里取出"它其实在对人说"的那句话。

    产出不合契约时有两种情况，必须分开对待：
      · 模型根本没答（空、或只有一句报错）→ 只能用系统兜底句；
      · 模型答得好好的，只是没套进 JSON（这是最常见的）→ **把它说的话给用户**。
        以前两种情况都掉进系统兜底句，于是用户连问三次都看到同一句
        "我没能按格式产出" —— 明明台上那个人说得挺清楚。
    """
    text = (raw_text or "").strip()
    if len(text) < 12:
        return ""
    if text.startswith("{") or text.startswith("["):
        # 是 JSON 而不是人话：不值得整段丢给用户
        return ""
    if text.startswith("```"):
        return ""
    return text[:600] + ("…" if len(text) > 600 else "")


def _module_query_text(
    cards: list[Renderable], results: list[dict[str, Any]], attempts: list[str]
) -> str:
    """Present verified read results, never a model's fabricated stage writes."""
    parts: list[str] = []
    card_ids = {card.kind.removeprefix("module.") for card in cards}
    if cards:
        parts.append("已读取「" + "、".join(card.title for card in cards) + "」，结果见下方卡片。")
    completed = Counter(str(item.get("module_id") or "") for item in results)
    described: set[str] = set()
    for item in results:
        module_id = str(item.get("module_id") or "")
        if module_id in card_ids or module_id in described:
            continue
        described.add(module_id)
        result = item.get("result")
        data = result.get("data") if isinstance(result, dict) else None
        summary = data.get("summary") if isinstance(data, dict) else None
        title = str(item.get("title") or module_id or "已授权")
        parts.append(_single_line(summary) if isinstance(summary, str) and summary.strip()
                     else f"已完成「{title}」技能查询。")
    if not parts:
        return "本次技能查询未完成，请确认模块启用状态和调用权限后重试。"
    if any(count > completed[module_id] for module_id, count in Counter(attempts).items()):
        parts.append("本次技能查询未完成，请确认模块启用状态和调用权限后重试。")
    return " ".join(parts)


def _user_facing_text(
    structured: dict[str, Any], guide: Any, raw_text: str, *, valid: bool = True
) -> str:
    """最短结论进对话流：结论字段 → （产出不合契约时）模型原话 → 行为引导文案。

    五个环节的契约里都有 `conclusion`，它就是"这一轮对他说的一句话结论"。

    顺序不能反：`guide.text` 写的是「为什么现在问这个」（给人看清下一步的由头），
    它**不是**结论。以前没有 conclusion 时这里落到 guide.text，用户读到的每一句
    都是"我为什么要问你"——话都对，但没有一句是在回他。

    原始 JSON 属于长内容，只允许截断兜底，绝不整段给用户。
    """
    for key in ("conclusion", "summary", "headline"):
        value = structured.get(key)
        if isinstance(value, str) and value.strip():
            # 结论可能被模型写成两三行；对话里它得是一行，否则气泡会散开。
            return _single_line(value)
    if not valid:
        prose = _prose_of(raw_text)
        if prose:
            return prose
    text = getattr(guide, "text", "")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raw = (raw_text or "").strip()
    return raw[:200] + ("…" if len(raw) > 200 else "") or "本轮已按当前环节完成分析。"


def _unsafe_diagnose_fallback(structured: dict[str, Any]) -> dict[str, Any]:
    """Keep verified sources while withholding an evidence-unsafe diagnosis.

    This value is intentionally not a report-shaped substitute. ``result.valid`` is
    set to false by the caller, so it cannot be persisted as a complete report. It is
    only the short, deterministic reply shown for this turn; using the model's raw
    prose here would reintroduce the claim that just failed the evidence boundary.
    """
    facts = structured.get("facts")
    return {
        "conclusion": (
            "现有资料还不足以判断这些能力强弱。"
            "我先把缺少的原始材料保留为待核对，不把它当成你的短板。"
        ),
        "facts": facts if isinstance(facts, list) else [],
        "theory_refs": [],
        "gaps": [],
        "dimensions": [],
        "guide": None,
    }


def _diagnose_prose_is_unsafe(structured: dict[str, Any]) -> bool:
    """结论/判断正文里是否已经把"缺证据"直接说成了"能力不足"。

    修补只负责**可判定的结构性误写**（把维度标签、SWOT 弱项、差距现状从
    "未提供"改回"待验证"）。如果模型已经在结论里写了"未提供作品，所以你的
    项目能力不足"，那就不是修补能救的：洗掉"未提供"只会留下一句更危险的
    "所以你的项目能力不足"。这种情况仍整份走 fallback（不展示、不落库）。
    """
    from zhiyin_business.contracts.diagnose import ABSENCE_PHRASES, NEGATIVE_TAGS

    verdict = structured.get("verdict") if isinstance(structured.get("verdict"), dict) else {}
    prose = " ".join(
        str(part or "")
        for part in (
            structured.get("conclusion"),
            verdict.get("title"),
            verdict.get("summary"),
        )
    )
    return any(word in prose for word in ABSENCE_PHRASES) and any(
        word in prose for word in NEGATIVE_TAGS
    )


def _repair_diagnose_evidence(structured: dict[str, Any]) -> dict[str, Any]:
    """把"资料没提供被写成短板"就地修成"待验证"，再交给契约校验。

    真实模型反复这么写；直接拒绝的后果是用户点了「可以」只收到一句
    "没有成功生成诊断报告"，重试还是同一句 —— 实测连试 3 轮全部失败。
    这里只修**可判定的三类**（判据与 `DiagnoseOutput` 的校验器共用同一份常量）：
    - 维度标签是短板/弱项、证据却是"未提供/未见" → 标签改「待验证」；
    - SWOT 弱项里出现"未提供" → 从弱项移除（没看到的不能当弱点）；
    - 差距的现状写"未提供" → 改成「现有材料未覆盖这一项，先按待核对处理」。
    修完仍不合契约的，照旧走 fallback（不落库、不假装生成成功）。
    """
    from zhiyin_business.contracts.diagnose import ABSENCE_PHRASES, NEGATIVE_TAGS

    def has_absence(value: Any) -> bool:
        return any(word in str(value or "") for word in ABSENCE_PHRASES)

    for group in structured.get("dimensions") or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            if any(word in str(item.get("tag") or "") for word in NEGATIVE_TAGS) and has_absence(
                item.get("evidence")
            ):
                item["tag"] = "待验证"
    swot = structured.get("swot")
    if isinstance(swot, dict) and isinstance(swot.get("weakness"), list):
        swot["weakness"] = [item for item in swot["weakness"] if not has_absence(item)]
    for gap in structured.get("gaps") or []:
        if isinstance(gap, dict) and has_absence(gap.get("current_state")):
            # 保留"待核对"这一层事实，但把触发校验的缺证表达换掉：
            # 只做过滤仍有漏网的组合（实测报告仍偶发因这句被拒）。
            gap["current_state"] = "现有材料未覆盖这一项，先按待核对处理"
    return structured


def _sanitize_absence_words(value: Any) -> Any:
    """把文本里残留的"未提供/未见"等缺证表达换成中性说法。

    校验器的判据是**字符串里出现这些词**；修补阶段若只做过滤，嵌套字段里
    偶尔还会漏。落库前再扫一遍，比让用户看到"没有成功生成报告"要好。
    """
    from zhiyin_business.contracts.diagnose import ABSENCE_PHRASES

    if isinstance(value, str):
        for phrase in ABSENCE_PHRASES:
            if phrase in value:
                value = value.replace(phrase, "待核对")
        return value
    if isinstance(value, list):
        return [_sanitize_absence_words(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_absence_words(item) for key, item in value.items()}
    return value


def _user_input_with_material(request: TurnRequest) -> str:
    """模型看到的用户输入：他说的话 + 这一轮带上来的材料正文。

    **只有模型输入这一条路会拼上正文**：`request.message` 才是落库、也是显示的那一句
    （"我传了一份材料：简历.txt"）。正文进对话流正是用户抱怨过的那件事 ——
    一份简历几百段铺在气泡里，他要读的是主理的回话，不是自己刚交上去的东西。
    """
    text = (request.attachment_text or "").strip()
    if not text:
        return request.message
    label = request.attachment_name or "用户上传的材料"
    head = request.message.strip() or f"我传了一份材料：{label}"
    return f"{head}\n\n【用户上传的材料：{label}】\n{text}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner(session: TaskSession, user_id: str) -> None:
    """任务会话的归属校验。

    为什么必须有：`TaskSessionRepository.get(session_id)` 的签名里**没有** user_id
    （它要服务"按 id 取会话"的通用场景），所以越权只能在使用侧拦。少了这一步，
    任何已登录用户只要知道别人的 `task_id`，就能读到并继续推进别人的会话。

    抛 `ResourceNotFound` 而不是 `AccessDenied`：不向调用方确认"这个 id 存在"，
    同时避免前端把它当成登录态失效而弹出登录框。
    """
    if session.user_id != user_id:
        raise ResourceNotFound(f"任务会话不存在：{session.id}")


__all__ = ["DefaultOrchestrator"]
