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


class UserRole(str, Enum):
    """身份角色。"""

    GUEST = "guest"
    STUDENT = "student"
    MENTOR = "mentor"
    ADMIN = "admin"


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

    TASK_TOO_BIG = "task_too_big"          # 任务太大
    LOW_MOTIVATION = "low_motivation"      # 动机不足
    DIRECTION_DOUBT = "direction_doubt"    # 方向动摇


class NotifyChannel(str, Enum):
    """通知通道。第一期只有本地通道。"""

    IN_APP = "in_app"      # 应用内消息
    LOCAL_LOG = "local_log"  # 本地日志
