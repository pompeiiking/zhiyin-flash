"""动态资源契约。

对应：智能体、理论卡、产出契约、任务入口
均入库为动态资源，可在不发布代码的情况下修改。

第一期允许把动态资源退化为本地 YAML / JSON 常量，但模型形状必须保持一致，
并统一标记 TODO。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import (
    AgentRuntimeStatus,
    LoopStage,
)


class TheoryCard(BaseModel):
    """理论卡。智能体气泡上的理论标签点开后展示的内容。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(description="理论名，如 霍兰德 RIASEC")
    school: str = Field(default="", description="所属流派 / 出处")
    summary: str = Field(default="", description="给用户看的通俗说明")
    product_usage: str = Field(default="", description="在本产品里怎么被用")


class OutputContractSpec(BaseModel):
    """智能体产出契约。

    业务层持有 Pydantic 模型（zhiyin_business.contracts），编排层只持有本 spec
    并做通用校验，从而保证"编排层不含业务语义"（R-ORC-001）。

    **唯一键是 `(agent_id, stage)`，不是 `id`。**
    原因：一个智能体可以承担多个环节（如职业顾问同时负责 ②诊断 与 ③决策），
    契约天然是"某智能体在某环节的产出"。此前把契约 id 挂在
    `AgentDescriptor.output_contract_id` 上，是"一个智能体一个契约"的 1:1 假设，
    直接导致 `oc_decide` 成为无人引用的孤儿契约——一旦有人按说明把 JSON Schema
    填进去，③决策就会拿②诊断的契约去校验。改为一对 (agent_id, stage) 后，
    该假设不成立即无法表达，从形状上消除这个缺陷。

    `id` 保留为稳定标识（日志与溯源用），但**不得**用于查找。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="稳定标识，仅用于日志与溯源，不用于查找")
    agent_id: str = Field(description="唯一键的一部分：产出该契约的智能体")
    stage: LoopStage = Field(description="唯一键的一部分：该契约所属环节")
    model_ref: str = Field(description="业务层契约模型的全限定名")
    json_schema: dict[str, Any] = Field(
        default_factory=dict, description="通用校验用 JSON Schema"
    )

    @property
    def key(self) -> tuple[str, str]:
        """查找键。实现方与守卫统一用它，避免各自拼键。"""
        return (self.agent_id, self.stage.value)


class AgentDescriptor(BaseModel):
    """智能体注册表条目（agent_registry）。

    理论包 / 工具 / 调用场合 / 边界全部配置化，对应设计文档的能力池定义。

    注意：这里**没有** `output_contract_id`。产出契约按 `(agent_id, stage)` 查，
    由 `OutputContractSpec` 持有；智能体不再声明"我拥有哪个契约"，因为一个智能体
    可以拥有多个环节的契约，单一字段无法表达。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="稳定标识，取值见 AgentRole")
    name: str = Field(description="展示名，如 建档分析师")
    role_summary: str = Field(default="", description="一句话职责，用于显式告知")
    theory_packages: list[str] = Field(default_factory=list, description="拥有的理论卡 id")
    tools: list[str] = Field(default_factory=list, description="可用知识 / 工具")
    call_scenarios: list[str] = Field(default_factory=list, description="被调用的场合")
    not_to_do: list[str] = Field(default_factory=list, description="明确不做")
    status: AgentRuntimeStatus = AgentRuntimeStatus.ENABLED


class PolicyParamSet(BaseModel):
    """业务规则的**参数集**（动态资源）。

    业务规则本身是代码（`zhiyin_business/policies/`），但规则的**参数**
    （停滞阈值、冷却期、打扰上限、置信度阈值……）必须来自动态资源，不得写死。
    本类只承载"一个规则 code 对应一组参数"，**不解释参数含义**——含义由规则实现
    与文档约定，避免内核承载业务语义。

    `status` 用来如实表达定稿程度：`draft` 表示参数仍在业务评审中，
    实现者不得把它当成已确认口径。
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="规则 code，如 intervention")
    value: dict[str, Any] = Field(default_factory=dict, description="参数键值对")
    status: Literal["draft", "confirmed"] = Field(
        default="draft", description="draft=待业务定稿；confirmed=已定稿"
    )
    note: str = Field(default="", description="为什么是这些值 / 还缺什么")


class CacheNamespaceSpec(BaseModel):
    """一个读缓存域：TTL 多长、什么事件让它失效。

    为什么缓存参数也进动态资源：TTL 是**运行参数**，改它不该发版；
    更要紧的是"哪个事件该让哪片缓存失效"必须写在一处 ——
    散在代码里的失效调用，漏一个就是"用户改完画像、界面上还是旧的"。
    """

    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(description="命名空间，如 workspace / report / theory")
    ttl_s: int = Field(default=300, ge=0, description="存活秒数；0 表示不过期")
    invalidate_on: list[str] = Field(
        default_factory=list,
        description="让这一片失效的事件码，如 profile_field_updated / asset_version_changed",
    )
    note: str = Field(default="", description="这一片缓存放什么、为什么这么定")


class CachePolicy(BaseModel):
    """读缓存策略（动态资源 `policy_params` 里的 `cache` 一条）。"""

    model_config = ConfigDict(extra="forbid")

    default_ttl_s: int = Field(default=300, ge=0)
    namespaces: list[CacheNamespaceSpec] = Field(default_factory=list)


class ProfileFieldSpec(BaseModel):
    """画像字段词表里的一条：键 + 中文名。

    为什么要有这份词表：字段键原来是模型自由发挥的（`interest_direction` /
    `course_selection_pattern`…），而界面要给用户看中文名、采集清单与报告维度
    又都按固定键取值 —— 键一散，三件事同时坏掉。词表把"允许写哪些键"收成一份
    动态资源：改它不发版，写侧按它做门禁，界面按它取名字。

    单一来源：它就是文案包里 `profile.field.<键>` 那些条目（**一份数据两处用**）——
    名字与门禁列表分开维护，迟早会出现"词表里有、但界面上没有中文名"。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="画像字段键，如 interest")
    label: str = Field(default="", description="中文名，如「兴趣方向」")
    alias_of: str = Field(
        default="",
        description=(
            "非空表示这一条是**同义词**：模型写的这个键要归到它指向的规范键上。"
            "同义词不各占一格画像，否则同一个意思会在画像里出现三条"
        ),
    )


class TaskEntrySpec(BaseModel):
    """首页任务入口（动态资源）。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="任务 code，前端点击后回传")
    label: str = Field(description="用用户自己的话写的任务文案")
    target_stage: Optional[LoopStage] = Field(
        default=None, description="为空表示走编排器意图识别（直接开聊）"
    )
    lead_agent: Optional[str] = Field(default=None, description="该入口的默认主理")
    sort_order: int = 0


class TrackEventSpec(BaseModel):
    """埋点事件归属（动态资源）。

    决策 14：**后端派生为主 + 前端上报为辅**。`channel=backend` 的事件由后端
    行为/接口推导，不进 `POST /app/track`；`channel=frontend` 的是纯体验型事件
    （点开告知、查看报告、比较方案、进入工作台等），由前端上报。
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="事件名，事件表的唯一键")
    channel: Literal["frontend", "backend"] = Field(
        description="frontend=前端上报；backend=后端派生，不接收入站上报"
    )
    note: str = Field(default="", description="触发时机与口径说明")


class BadgeRuleSpec(BaseModel):
    """成就解锁规则（动态资源）。

    为什么它不能写在代码里：**"什么算一个成就"是产品激励口径**，不是逻辑。
    "第一次认领差距"和"第一次勾掉任务"要不要各给一枚，会随运营判断变化；
    写进 `FunctionService` 的字典里，改一次要发一次版。

    成就本身仍然**不落表**——它是由行为日志实时推导的（"只由行为日志驱动，防自嗨"）。
    这张表只管"哪条行为解锁哪个成就"，不持有任何用户数据。
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="成就标识，前端按它取徽章文案")
    trigger_events: list[str] = Field(
        default_factory=list,
        description="触发它的行为事件（取值见 BehaviorEventType）；命中任一即解锁",
    )
    sort_order: int = Field(default=0, description="展示顺序；越小越靠前")
    note: str = Field(default="", description="这枚徽章为什么这么发")


class TaskProgressSpec(BaseModel):
    """生成类 AI 任务的进度文案（动态资源）。

    这四条进度是**给用户看的话**："读你现在的处境与画像版本"比"加载中…"
    更能解释系统在做什么。文案属产品口径，所以它和别的文案一样进库，不发版。

    `code` 与 `AiTaskService` 的任务 key 对齐（`brief.today` / `dim` / `gap` …）；
    取不到时前端只会少几行进度提示，不会影响任务本身。
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="任务 key，与 AI 任务登记处对齐")
    notes: list[str] = Field(default_factory=list, description="按顺序播报的进度文案")
    sort_order: int = Field(default=0)
    note: str = Field(default="", description="口径来源")


class ChsiFieldSpec(BaseModel):
    """学信网在线验证报告的字段 → 画像键 + 展示名（动态资源）。

    两件事同时被这张表管住：

    - **写哪些字段进画像**（`key`）：多写一个学生姓名进画像就是一个隐私决定，
      它不该由一段代码顺手决定；
    - **这些字段在界面上叫什么**（`label`）：属文案，改一次不发版。

    字段顺序（`order`）也是口径：报告页按它排，跟学信网页面上的顺序一致，
    用户对照着看的时候不容易错行。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="画像字段键")
    label: str = Field(description="界面上显示的中文名")
    order: int = Field(default=0, description="展示顺序；越小越靠前")
    note: str = Field(default="", description="为什么把它写进画像 / 为什么不写")


class LayoutBlockSpec(BaseModel):
    """控制台上一个气泡的编排规则（动态资源）。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="块标识，与前端 data-block 一致")
    label: str = Field(default="", description="右菜单/叫回列表里显示的名字")
    hint: str = Field(default="", description="一句话说明这块是干什么的")
    weight: float = Field(default=1.0, gt=0.0, description="分到的空间权重")
    base: int = Field(default=100, description="基础优先级，越小越靠前")
    boost: int = Field(default=0, description="条件命中时提前多少位")
    boost_when: Optional[str] = Field(
        default=None,
        description="提前的条件名（见 zhiyin_business.policies.layout.PREDICATES）",
    )
    show_when: Optional[str] = Field(
        default=None, description="出现的条件名；为空表示总是出现"
    )
    why: str = Field(default="", description="排在这一位的原因，会显示给用户")


class LayoutPolicy(BaseModel):
    """控制台气泡的编排策略。

    为什么它必须是动态资源而不是前端常量：**"先看哪一块"本身就是产品判断**。
    用户在冲刺期最该先看到的是窗口期与行动，在探索期最该先看到的是画像缺口；
    刚核验完学籍，采集块就该让位。把它写死在组件里，这些判断就只能靠发版来改，
    而且前端根本不知道用户处在哪一步。
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str = ""
    note: str = Field(default="", description="这套编排的整体口径")
    blocks: list[LayoutBlockSpec] = Field(default_factory=list)


class StageSpec(BaseModel):
    """五个环节的展示口径（动态资源）。

    为什么它必须入库：这个名字**曾经在三个地方各写了一遍**
    （api 的 mapper、工作台服务、AI 任务的进度文案），
    改一处忘一处，前后端口径就对不上 —— 而症状是"某个页面上的环节名是旧的"，
    没人会想到去 grep 常量。放一份在库里，三处都从这里读。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="环节标识，与 LoopStage 的取值一致")
    order: int = Field(default=0, description="在管线里的位次，从 1 起")
    label: str = Field(default="", description="管线卡与轨道上的显示名")
    title: str = Field(default="", description="工作台面板标题；为空则用 label")
    asset: str = Field(default="", description="该环节产出的资产类型；空表示只推进不改资产")
    note: str = Field(default="", description="这一环节在干什么")


class CollectionRuleSpec(BaseModel):
    """一条采集规则：哪个画像字段、去哪儿取、为什么现在要它（动态资源）。

    `why` 这一列是**给用户看的**，所以写的是"这条数据挡着哪一步判断"，
    不是"这是必填项"。用户凭什么再花一次动作，全看这一列说没说清楚。

    `ask` 是"去回答"点下去之后落在输入框上方的那一句（只有 conversation 源用得到）。
    它必须在**这一层**：问题怎么写属于采集口径，写在界面上就等于"改一句话要发一次版"。
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="画像字段键")
    label: str = Field(description="中文名，界面与回执里用它")
    source: str = Field(description="chsi / conversation / academic")
    why: str = Field(default="", description="这条数据挡着哪一步判断")
    ask: str = Field(
        default="",
        description="问用户的那句（仅 conversation 源）：要求一句话答得上来",
    )
    order: int = Field(default=0, description="同档内的先后；越小的越先")


class UserSignalSpec(BaseModel):
    """一条用户信号：用户自己写下的一句话，让某个画像字段变成**前提**。

    为什么需要它
    ------------
    采集优先级原来只看两件事：还缺什么、现在走到哪一环节。两条都是**系统的视角**——
    用户看不到"我为什么先被问这个"。而用户其实早就说过话了：他写过"想冲秋招"、
    说过"家里希望我考公"、在待办里写了"下个月改完简历"。

    这条表就是把那些话接进策略：**用户自己写下的东西，优先级高于系统按阶段猜的。**
    于是回执能说出"因为你写了想冲秋招，所以我先去取你的预计毕业时间"——
    这句话里"因为你写了…"是用户的话，"所以"是策略的账。

    `why` 写的是"你这句话为什么让这条数据变成前提"，与 `CollectionRuleSpec.why`
    合成一句给用户看的话。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        default="",
        description=(
            "这一条的身份。**必须给**：同一个画像字段会被好几个词指到"
            "（秋招 / 校招 / 毕业 都指向预计毕业），入库时按身份去重，"
            "身份取 `key` 就会把它们合并成一条 —— 静默丢掉词，而且不报错。"
        ),
    )
    keyword: str = Field(description="用户话里的线索词，如 秋招 / 考研 / 考公")
    key: str = Field(description="被它顶到前面的画像字段键")
    why: str = Field(default="", description="你这句话为什么让这条数据变成前提")
    order: int = Field(default=0, description="多条命中时的先后；越小的越先")


PromptLayer = Literal[
    "core", "guide", "role", "router", "proactive", "disclosure", "task"
]


class PromptSpec(BaseModel):
    """提示词模板（动态资源）。

    为什么提示词必须入库，而不是写在装配代码里
    ------------------------------------------
    提示词在此之前**没有任何来源**：引擎的 `instructions` 参数存在但构造时是空的，
    唯一的去处就是在装配代码里写一段长字符串。那意味着每一次改口气、改禁令、
    改某一步的产出要求，都要改代码、发版、重跑回归 —— 而这恰恰是产品最需要
    高频调整的部分。

    查找键是 `code`（稳定标识），**不是**按层或按位置。原因是同一层里可以有多条
    同形态的模板（`disclosure.reason.collect` 与 `disclosure.reason.review`），
    按位置找会在插入一条时整体错位，而上层看到的只是"文案变奇怪了"。

    `agent_id` 与 `stage` 是**归属**而不是唯一键：职业顾问同时负责诊断与决策，
    两条提示词的差别只在 `stage`。取用时按 `(agent_id, stage)` 命中优先、
    只用 `agent_id` 命中兜底，取不到再回落到 `layer=role` 的通用条目。

    `params` 承载调用参数（温度 / 超时 / 重试次数）。它们与提示词同生共死：
    换一条提示词往往就要换温度，分两张表存放必然出现"提示词换了、温度没换"。
    本类**不解释参数含义**，含义由调用方与文档约定。
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="稳定标识，调用方按它取用")
    layer: PromptLayer = Field(description="所属层：总纲 / 收尾规范 / 角色 / 编排 / 主动 / 侦查 / 告知")
    content: str = Field(description="提示词正文")
    agent_id: str = Field(default="", description="归属智能体；空表示与具体智能体无关")
    stage: str = Field(default="", description="归属环节；空表示该智能体的通用条目")
    name: str = Field(default="", description="给人看的名字，运营与排查时用")
    params: dict[str, Any] = Field(
        default_factory=dict, description="调用参数（temperature / timeout_s / retries 等）"
    )
    status: Literal["enabled", "disabled"] = Field(
        default="enabled", description="enabled / disabled"
    )
    sort_order: int = Field(default=0, description="同层内的先后；越小越先")
    note: str = Field(default="", description="口径来源与定稿程度")

    @property
    def key(self) -> tuple[str, str]:
        """归属键。取用方与守卫统一用它，避免各自拼键。"""
        return (self.agent_id, self.stage)


class RoutingRuleSpec(BaseModel):
    """编排判定规则（动态资源）。

    这张表把三件原本硬编码在业务规则里的事挪出来：
    **用户说了哪些词算哪种意图、哪种意图进哪一步、哪种情形不猜而要问**。

    为什么它必须是数据而不是代码：这些词表是**产品语言**，不是逻辑。用户说
    "我投了没回音"和"我投了没人理"是同一件事，加一个词不该走一次发版；
    而"投了没回音"到底算"想验证方向"还是"卡住了"，是会随产品判断变化的取舍。
    把词表和映射写进代码，等于把产品判断冻结在发布节奏上。

    `kind` 区分规则的用途，只保留**当前真有消费者**的两种：
    - `intent`：关键词命中 → 意图（`match` + `intent`）
    - `stage`：意图 → 环节（`intent` + `stage`）

    为什么不一起把「环节 → 主理」也建成一类：那条映射已经有归属
    （智能体注册表 + 任务入口的默认主理 + 组队规则），再开一张表就是第三条事实来源，
    而建了没人读的配置比没有更危险 —— 改了它不生效，改的人还不知道。

    未命中任何规则时的行为**不在这张表里**：它是策略（"回落到当前环节交给模型"
    还是"再问一句"），属于代码。表只回答"命中了该怎样"。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="稳定标识，也是入库时的行键；不用于按位置查找")
    kind: Literal["intent", "stage"] = Field(description="规则用途：关键词到意图 / 意图到环节")
    # 排序字段与其他动态资源同名同义（越小越靠前）——不另起一个 priority，
    # 否则同一件事会有两个名字，入库时还要再翻译一次。
    sort_order: int = Field(
        default=100, description="越小越先判定；同一序号按 id 稳定排序"
    )
    match: list[str] = Field(default_factory=list, description="命中词；空表示不按词匹配")
    intent: str = Field(default="", description="命中后判定的意图（kind=intent 时输出，kind=stage 时输入）")
    stage: str = Field(default="", description="目标环节")
    status: Literal["enabled", "disabled"] = Field(
        default="enabled", description="enabled / disabled"
    )
    note: str = Field(default="", description="这条规则为什么这么定")
