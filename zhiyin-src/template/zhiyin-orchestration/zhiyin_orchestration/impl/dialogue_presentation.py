"""Model-selected identity in the same response as streamed public text."""
import asyncio
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhiyin_kernel.assets import PlanGap
from zhiyin_kernel.enums import DIALOGUE_ROLE_FOCUS
from zhiyin_kernel.streaming import emit_progress
from zhiyin_kernel.privacy import redact_sensitive
from .stream_text import partial_root_string

Role = Literal['profile_analyst', 'career_advisor', 'path_planner', 'companion_coach']


class DirectionDraft(BaseModel):
    """本轮生成的一套方向方案（服务端补 id 并保存草稿）。

    为什么放在回复 JSON 里、而不是只依赖模型调用 workspace.action：
    实测模型会把三套方向完整写进正文，却没有调用保存操作 —— 对话里有方案、
    方案页始终为空。正文和结构化字段走同一次输出，服务端拿到后确定性落草稿，
    不再把"页面有没有内容"交给模型记不记得调工具。
    """
    model_config = ConfigDict(extra='ignore')
    role: Literal['main', 'parallel', 'fallback']
    name: str = Field(min_length=1, max_length=60)
    target_desc: str = Field(default='', max_length=1000)
    fit_reason: str = Field(default='', max_length=2000)
    main_risk: str = Field(default='', max_length=1000)
    gaps: list[PlanGap] = Field(default_factory=list, max_length=8)


class PlanTaskDraft(BaseModel):
    model_config = ConfigDict(extra='ignore')
    text: str = Field(min_length=1, max_length=300)
    due_date: datetime | None = None
    scheduled_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)


class PlanPhaseDraft(BaseModel):
    model_config = ConfigDict(extra='ignore')
    name: str = Field(min_length=1, max_length=80)
    date_range: str = Field(default='', max_length=80)
    tasks: list[PlanTaskDraft] = Field(default_factory=list, max_length=20)


class ActionPlanDraft(BaseModel):
    model_config = ConfigDict(extra='ignore')
    phases: list[PlanPhaseDraft] = Field(default_factory=list, max_length=8)


class DialogueReply(BaseModel):
    # Unrecognized transport annotations never reach the public text or authority.
    model_config = ConfigDict(extra='ignore')
    role_id: Role
    focus: Literal['collect', 'diagnose', 'decide', 'act', 'review']
    collaborators: list[Literal['profile_analyst', 'career_advisor', 'path_planner', 'companion_coach', 'info_scout']] = Field(default_factory=list, max_length=4)
    answer: str = Field(min_length=1)
    # 放在 answer 之后：流式解析先拿到正文，结构化资产在结尾一起到。
    directions: list[DirectionDraft] = Field(default_factory=list, max_length=6)
    plan: ActionPlanDraft | None = None

    @model_validator(mode='after')
    def matching_focus(self):
        if self.focus not in DIALOGUE_ROLE_FOCUS[self.role_id]:
            raise ValueError('主理与工作重点不匹配')
        if not self.answer.strip():
            raise ValueError('回复正文不能为空')
        return self


def enabled(value):
    return str(getattr(value, 'value', value)) == 'enabled'


async def load_professionals(registry):
    async def load(role_id):
        role, prompt = await asyncio.gather(registry.get_agent(role_id), registry.get_prompt('conversation.role.' + role_id))
        return (role_id, (role, prompt)) if role and prompt and enabled(role.status) and enabled(prompt.status) else None
    rows = await asyncio.gather(*(load(role_id) for role_id in DIALOGUE_ROLE_FOCUS))
    return dict(row for row in rows if row)


def presentation_instructions(professionals):
    roles = [{"id": key, "name": role.name, "focus": sorted(DIALOGUE_ROLE_FOCUS[key]),
              "responsibility": role.role_summary, "boundaries": role.not_to_do, "instructions": prompt.content}
             for key, (role, prompt) in professionals.items()]
    return (
        '内部回复传输协议：最终回复必须是一个 JSON 对象，字段依次为 role_id、focus、collaborators、answer。'
        '格式样例（只示范封装，主理及正文必须按当前真实任务选择）：'
        '{"role_id":"path_planner","focus":"act","collaborators":[],"answer":"先做一个能完成的小步骤。"}。'
        '先判断本轮用户实际需要的工作，再选主理；不得因为上一轮是谁或未调用工具就沿用默认身份。'
        '梳理本人经历与偏好选 profile_analyst/collect；分析差距选 career_advisor/diagnose；'
        '比较取舍与选择选 career_advisor/decide；拆分步骤、安排时间与完成标准选 path_planner/act；'
        '执行卡点、反馈、复盘选 companion_coach/review。只提供建议、不保存数据时也要选正确主理。'
        '这些是语义任务说明，不是按字词匹配；引述、否定、历史话题不覆盖当前真实意图。'
        '普通闲聊与事实问答可保留当前主理及重点，不强行推进流程。只有下列已启用角色可以选择。'
        'info_scout 只作协作事实查证，列入 collaborators，不可成为最终主理或独立工作阶段。'
        '专业职责在本轮已加载；无需为选择主理再次调用use_specialist，仅在需要详细方法卡时按需加载。'
        '协作角色按实际参与填写，不为凑齐五个角色而调用。加载协作方法不会接管主理。'
        'answer 是直接给用户的自然正文，继续遵守简洁、引导和权限规则；不包含身份字段、JSON封装或私有推理。'
        '系统会剥离外层 JSON，只把 answer 实时展示；先前不输出JSON的要求适用于 answer 正文。'
        '顶部 focus 和 record_exploration.mode 是两种字段；后者只能是 explore/answer/act/paused，复盘不要填 review。'
        '本轮若完整给出方向方案（主攻/平行/保底），必须同时填写顶层 directions：每项含 role（main/parallel/fallback）、'
        'name、target_desc、fit_reason、main_risk，gaps 可选（requirement/current_state/suggestion）。'
        '本轮若完整给出行动计划（阶段与可执行任务），必须同时填写顶层 plan：phases 每项含 name、date_range、'
        'tasks（text 必填，due_date/scheduled_at 可选）。这两项是正文交付物的一部分，不能只写在正文里。'
        '服务端会按 directions / plan 自动保存（首次生成时作为当前版本；已有版本时只存草稿，不替换正式版本），'
        '因此不要再为同一份内容调用 workspace.action 保存；'
        '只有用户明确要求保存、启用或修改已有资产时才调用对应工具。没有完整生成时，directions 留空数组、plan 留 null。'
        '\n已加载的真实专业职责：' + json.dumps(roles, ensure_ascii=False)
    )


def history_content(item):
    content = redact_sensitive(item['content'])
    if item['role'] != 'assistant':
        return content
    # Consistent transport examples prevent plain stored answers from teaching
    # the model to abandon JSON on the second turn. Keep stored history natural.
    role, focus = item.get('agent_id'), item.get('focus')
    if role in DIALOGUE_ROLE_FOCUS and focus in DIALOGUE_ROLE_FOCUS[role]:
        value = {'role_id': role, 'focus': focus, 'collaborators': [], 'answer': content}
    else:
        # Old/system/interrupted messages have no verified role+focus pair.
        value = {'historical': True, 'answer': content}
    return json.dumps(value, ensure_ascii=False)


def select_presentation(state, professionals, role_id, focus):
    if role_id not in professionals or role_id == 'info_scout' or focus not in DIALOGUE_ROLE_FOCUS[role_id]:
        raise ValueError('本轮主理不可用或工作重点不匹配')
    state['lead'], state['stage'] = role_id, focus
    if role_id not in state['roles']:
        state['roles'].append(role_id)
    if state.get('selected') != (role_id, focus):
        state['selected'] = (role_id, focus)
        emit_progress({'type': 'role.selected', 'agent': role_id, 'stage': focus, 'note': '正在分析你的问题'})


def stream_public_reply(raw, state, professionals):
    role_id = partial_root_string(raw, 'role_id', complete_only=True)
    focus = partial_root_string(raw, 'focus', complete_only=True)
    if not role_id or not focus:
        return ''
    if role_id not in professionals or role_id == 'info_scout' or focus not in DIALOGUE_ROLE_FOCUS.get(role_id, set()):
        return ''
    select_presentation(state, professionals, role_id, focus)
    return partial_root_string(raw, 'answer')


def finish_public_reply(raw, state, professionals):
    reply = DialogueReply.model_validate_json(raw)
    if any(role not in professionals for role in reply.collaborators):
        raise ValueError('协作角色不可用')
    select_presentation(state, professionals, reply.role_id, reply.focus)
    for role in reply.collaborators:
        if role not in state['roles']:
            state['roles'].append(role)
    # 结构化交付物随最终回复一起交给业务层；由业务层在同一个动作边界里
    # 保存草稿，不依赖模型是否记得调用保存工具。
    assets = {}
    if reply.directions:
        assets['directions'] = [item.model_dump(mode='json', exclude_none=True) for item in reply.directions]
    if reply.plan and any(phase.tasks for phase in reply.plan.phases):
        assets['plan'] = reply.plan.model_dump(mode='json', exclude_none=True)
    if assets:
        state['reply_assets'] = assets
    else:
        state.pop('reply_assets', None)
    return reply.answer
