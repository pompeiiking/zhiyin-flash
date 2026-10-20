"""枚举契约。

取值口径以设计文档为准。
本模块只定义取值，不定义业务规则。
"""

from __future__ import annotations

from enum import Enum


class LoopStage(str, Enum):
    """轴 B · 服务微循环五环节。"""

    COLLECT = "collect"      # ① 采集建模
    DIAGNOSE = "diagnose"    # ② 诊断匹配
    DECIDE = "decide"        # ③ 决策
    ACT = "act"              # ④ 行动
    REVIEW = "review"        # ⑤ 复盘校准


class AxisAStage(str, Enum):
    """轴 A · 用户职业发展进程（隐性，后台推断，前台不让用户选）。

    五段全量口径：
    探索自我 → 验证定向 → 冲刺行动 → 适应 → 再定位。
    它改变"同一环节被服务的深度与口气"，不新增页面层级。
    """

    EXPLORE_SELF = "explore_self"          # 探索自我
    VERIFY_DIRECTION = "verify_direction"  # 验证定向
    SPRINT_ACTION = "sprint_action"        # 冲刺行动
    ADAPT = "adapt"                        # 适应
    REPOSITION = "reposition"              # 再定位


class PathFocus(str, Enum):
    """任务会话的路径焦点（决策 3 = C：轴 A 单轨 + 会话可带焦点标记）。

    一个用户全局只有一个轴 A 阶段；混合路径（就业 / 考研 / 留学并行）时，
    由会话携带本焦点标记，让主理选择与工作台按"当前关注哪条路"取数。
    """

    EMPLOYMENT = "employment"        # 就业
    POSTGRADUATE = "postgraduate"    # 考研
    STUDY_ABROAD = "study_abroad"    # 留学


class AgentRole(str, Enum):
    """五个智能体的稳定标识。

    展示名、理论包、边界由 agent_registry（动态资源）维护，不硬编码。
    """

    PROFILE_ANALYST = "profile_analyst"      # 建档分析师
    CAREER_ADVISOR = "career_advisor"        # 职业顾问
    PATH_PLANNER = "path_planner"            # 路径规划师
    COMPANION_COACH = "companion_coach"      # 陪伴教练
    INFO_SCOUT = "info_scout"                # 信息侦查员


class AgentRuntimeStatus(str, Enum):
    """智能体在第一期的运行态。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


class AssetType(str, Enum):
    """资产类型。影响面传播的最小单位。"""

    REPORT = "report"                  # 15 维诊断报告
    DIRECTION_PLAN = "direction_plan"  # 主攻/平行/保底方向方案
    ACTION_PLAN = "action_plan"        # 行动计划


class BehaviorEventType(str, Enum):
    """行为日志事件类型（对应埋点事件表）。"""

    ANSWER = "answer"                                  # 作答
    GAP_CLAIM = "gap_claim"                            # 认领差距
    DECISION_SELECT = "decision_select"                # 做出选择
    DECISION_RESELECT = "decision_reselect"            # 修改选择
    TASK_DONE = "task_done"                            # 勾掉任务
    TASK_REOPENED = "task_reopened"                    # 撤销完成（追加修正事件）
    TASK_STALL = "task_stall"                          # 任务停滞
    PROFILE_FIELD_UPDATED = "profile_field_updated"    # 画像字段更新
    REVIEW = "review"                                  # 完成复盘
    ASSET_VERSION_CHANGED = "asset_version_changed"    # 资产版本变化


class ProfileSource(str, Enum):
    """画像字段来源。"""

    RESUME = "resume"                          # 简历
    CONVERSATION = "conversation"              # 对话
    ASSESSMENT = "assessment"                  # 测评
    BEHAVIOR_INFERENCE = "behavior_inference"  # 行为推断
    MENTOR = "mentor"                          # 导师建议
    RECORD = "record"                          # 客观档案（学信网等权威机构出具的记录）
    # 用户本人更正（他自己在画像里改的值）。
    #
    # 为什么它必须是一个**独立取值**而不是复用"对话"：这两个来源在界面上说的是
    # 两句不同的话（"系统从你说的话里记的" / "你自己写的"）。复用 conversation
    # 的后果是：他亲手改过的那一条看起来仍然像系统推断的，下一次再看到还是不敢信；
    # 也再没有一处能回答"这条到底是谁定的"。
    USER_EDIT = "user_edit"


class ProfileEntryType(str, Enum):
    """画像条目的内容类别（《个人画像设计-2026-10-20》第 2 节）。

    类别是**组织视角**，不是一个条目只能有一个去处：一份经历可以同时支撑
    兴趣与能力分析（通过引用关联），但原始经历只有一个出处。因此每一次写入
    都必须落到一个明确类别上，消费方不再猜字段键字符串的含义。

    受控词表：类别由服务端按字段键推导（见 `profile_taxonomy.entry_type_of`），
    模型不能自由生成，也不参与权限判断。
    """

    LEARNING_BACKGROUND = "learning_background"  # 学习背景（学校/专业/年级/学历/课程成绩）
    INTEREST = "interest"                        # 兴趣与偏好（多条、可不确定、可变化）
    EXPERIENCE = "experience"                    # 经历（项目/实践/实习中的行动与结果）
    ABILITY = "ability"                          # 能力与技能（接触/自评/成果）
    CAREER_FOCUS = "career_focus"                # 职业关注（了解/考虑/已选）
    VALUES = "values"                            # 价值取向
    CONDITION = "condition"                      # 现实条件（时间/地点/经济/家庭）
    SUPPLEMENT = "supplement"                    # 补充信息（有来源、暂无法归类）


class ProfileEntryStatus(str, Enum):
    """画像条目状态（第 4、7 节）。

    不统一执行「最新值覆盖旧值」：修正、冲突、过期、撤回是四种不同的变化，
    混成一个状态后，界面上就分不清「他改过」和「两条资料对不上」。
    """

    ACTIVE = "active"          # 当前有效
    CORRECTED = "corrected"    # 用户明确更正过
    CONFLICT = "conflict"      # 两条来源对不上，尚未裁定
    EXPIRED = "expired"        # 超出适用范围/时间
    WITHDRAWN = "withdrawn"    # 用户撤回（不再作为事实使用）
    SUPERSEDED = "superseded"  # 历史版本：已被后续版本替代（只出现在版本记录里）


class ProfileVerification(str, Enum):
    """核实状态：与「来源」分开表达（第 3.1、4 节）。

    `ProfileSource` 回答「这条从哪儿来」，核实状态回答「它被确认到什么程度」——
    用一个分数混合这两件事，用户看到的就只是一个说不清含义的百分比。
    """

    SELF_REPORTED = "self_reported"  # 本人自述（有原话支持，不需要外部验证）
    USER_CONFIRMED = "user_confirmed"  # 本人手动确认/更正
    RECORD = "record"                # 资料记录（教务/学信网等）
    VERIFIED = "verified"            # 外部核验通过
    PENDING = "pending"              # 待核实


class ProfilePurpose(str, Enum):
    """按用途读取（第 8 节）：业务方读服务端生成的用途视图。

    任何业务都不能再自行扫描整份画像、把任意字符串拼成查询词；允许哪些类别
    进入哪个用途，由服务端规则计算。
    """

    MAJOR_RETRIEVAL = "major_retrieval"              # 专业相关职业检索
    CAREER_RETRIEVAL = "career_retrieval"            # 职业/方向检索
    DIRECTION_RECOMMENDATION = "direction_recommendation"  # 方向推荐与比较
    PLANNING = "planning"                            # 制定计划
    CONVERSATION = "conversation"                    # 普通交流


class ProfileClueStatus(str, Enum):
    """待验证线索的状态（《个人画像设计-2026-10-20》第 3.2、7 节）。

    线索是「AI 对信息的有限理解」，与事实字段分开存：必须关联依据、标明适用范围，
    不进入事实字段，也不能靠反复引用把自己变成稳定结论。

    · `PROPOSED`：待验证（默认）。依据变化、用户否认或用途不再需要时失效；
    · `INVALID`：已失效。依据被更正/撤回/删除，或用户明确否认这条理解；
    · `CONFIRMED`：已确认。留给后续「用户认可/重新分析后成立」的链路 ——
      当前没有任何自动确认路径，重复出现不等于确认。

    状态是服务端算的，不由模型自报。
    """

    PROPOSED = "proposed"
    INVALID = "invalid"
    CONFIRMED = "confirmed"


class UserRole(str, Enum):
    """身份角色。"""

    GUEST = "guest"
    STUDENT = "student"
    MENTOR = "mentor"
    ADMIN = "admin"
    DEVELOPER = "developer"


class TaskStatus(str, Enum):
    """任务会话状态。"""

    ACTIVE = "active"        # 进行中
    PAUSED = "paused"        # 已中断，可续接
    COMPLETED = "completed"  # 已完成


class PlanRole(str, Enum):
    """方向方案角色。"""

    MAIN = "main"          # 主攻
    PARALLEL = "parallel"  # 平行
    FALLBACK = "fallback"  # 保底


class ReviewAttribution(str, Enum):
    """复盘归因判别结果。"""

    UNKNOWN = "unknown"                    # 证据不足，暂不归因
    TASK_TOO_BIG = "task_too_big"          # 任务太大
    LOW_MOTIVATION = "low_motivation"      # 动机不足
    DIRECTION_DOUBT = "direction_doubt"    # 方向动摇


class NotifyChannel(str, Enum):
    """通知通道。第一期只有本地通道。"""

    IN_APP = "in_app"      # 应用内消息
    LOCAL_LOG = "local_log"  # 本地日志


# Professional focus is advisory: neither workflow completion nor write authority.
DIALOGUE_ROLE_FOCUS = {
    "profile_analyst": {"collect"}, "career_advisor": {"diagnose", "decide"},
    "path_planner": {"act"}, "companion_coach": {"review"}, "info_scout": set(),
}
