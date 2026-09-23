"""AI 工具 / MCP 注册表（AI 面向切面的"工具维护"切面，见设计文档第六章 6.5）。

分层口径：
- **基础设施层**持有工具的**实现与登记**：本地工具（学职网取数、学信网拉取、
  黑板读写、日历）与外部 MCP server 的连接信息都在这里注册；
- **编排层**在组装智能体时从注册表取工具、包成 agno Toolkit/工具列表——
  它只认识名字，不认识实现；
- **业务层**声明"某个智能体允许用哪些工具"（agents.json 的 `tools` 字段，
  已有口径），实现侧不得自作主张扩大权限（如信息侦查员只给只读工具）。

第一期：注册 / 查询 / 权限过滤三件事。MCP 连接器的落地
（stdio / SSE 子进程管理）在接入第一个真实 MCP server 时再补——
先建登记处，避免将来工具散落各层无人盘点。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Sequence

from agno.run import RunContext

from zhiyin_kernel.errors import ResourceNotFound

# 全站可注册的工具名清单（唯一口径）。
#
# 为什么要有这份常量：`agents.json` 的 `tools` 是**业务侧声明的白名单**，
# 而工具目录是这里按装配情况注册出来的。两者一旦对不上，引擎会在**运行时**
# 抛 `MissingConfigError` —— 症状是"对话直接 500"，而根因只是配置里写了一个
# 早已改名的工具。声明一份名单，「白名单 ⊆ 名单」就能在 CI 里机械判定。
#
# 它必须与 `build_tool_catalog` 真正注册的名字一致，由函数末尾的自检保证。
KNOWN_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "kb.search",
        "xuezhi.search",
        "web.search",
        "profile.read",
        "behavior.recent",
        "plan.read",
        "chart.render",
    }
)

#: 本轮可视件的**回传盒子**在 `run_context.dependencies` 里的键名。
#: 与编排层 `agno_engine.CHART_BOX_KEY` 是同一个约定，但两边各写一遍 ——
#: 依赖守卫不许编排层 import 基础设施层的实现，而这个键名是它们之间的约定。
CHART_BOX_KEY = "renderables"

#: 能画的图**只有这几种**，每一种的点都由服务端自己从库里读出来。
#:
#: 这是"防止假数据"的关键：工具的参数只有 `kind`（一个枚举），**没有任何位置**
#: 能让模型传数值进来。它决定"画哪一类"，数字由服务端读真实数据算出来。
#: 想加一种图，就在 `_chart_points` 里加一个分支，并在下面登记它的说明。
_CHART_KINDS: dict[str, str] = {
    "profile_confidence": "他现在每一项情况的把握度（来自画像里每条的真实把握度）",
    "direction_match": "已经存下来的几套方向各自的匹配度（来自方案资产的真实分值）",
    "plan_progress": "行动计划每个阶段做完了多少（来自已存计划里的勾选状态）",
}

_DEFAULT_CHART_TITLES: dict[str, str] = {
    "profile_confidence": "这几项你现在各有多少把握",
    "direction_match": "各方向和你手上的东西合不合",
    "plan_progress": "每个阶段做完了多少",
}
_CHART_UNITS: dict[str, str] = {
    "profile_confidence": "%",
    "direction_match": "分",
    "plan_progress": "%",
}


async def _chart_points(
    kind: str,
    run_context: RunContext,
    profile_reader: Callable[..., Any] | None,
    plan_reader: Callable[..., Any] | None,
) -> list[dict[str, Any]] | None:
    """按类别从**库里**读出点位。读不到就返回 None（调用方负责如实说画不出来）。

    三种图各自读一份真实数据，全部来自服务端：
      · 画像把握度 ← 画像里每条字段自带的 confidence；
      · 方向匹配度 ← 已落库的方案资产（match_score）；
      · 计划进度   ← 已落库的行动计划里每个阶段的勾选状态。
    **没有一个数字来自模型的自由发挥**，这是这张图能被信任的全部理由。
    """
    user_id = run_context.user_id or ""
    if kind == "profile_confidence":
        if profile_reader is None:
            return None
        data = await _read(profile_reader, user_id)
        fields = list(getattr(data, "fields", []) or []) if not isinstance(data, dict) else list(
            data.get("fields", []) or []
        )
        points = []
        for item in fields:
            label = getattr(item, "label", "") or (
                item.get("label") if isinstance(item, dict) else ""
            )
            key = getattr(item, "key", "") or (item.get("key") if isinstance(item, dict) else "")
            confidence = getattr(item, "confidence", None)
            if confidence is None and isinstance(item, dict):
                confidence = item.get("confidence")
            if confidence is None:
                continue
            points.append(
                {
                    "label": str(label or key)[:12],
                    "value": round(float(confidence) * 100),
                }
            )
        return points or None
    if plan_reader is None:
        return None
    data = await _read(plan_reader, user_id)
    if not isinstance(data, dict):
        return None
    if kind == "direction_match":
        directions = list(data.get("directions") or [])
        points = []
        for plan in directions:
            name = getattr(plan, "name", "") or (
                plan.get("name") if isinstance(plan, dict) else ""
            )
            score = getattr(plan, "match_score", None)
            if score is None and isinstance(plan, dict):
                score = plan.get("match_score")
            if score is None:
                continue
            points.append({"label": str(name)[:12], "value": round(float(score) * 100)})
        return points or None
    action = data.get("plan")
    phases = list(getattr(action, "phases", []) or []) if action is not None else []
    points = []
    for phase in phases:
        tasks = list(getattr(phase, "tasks", []) or [])
        if not tasks:
            continue
        done = sum(1 for task in tasks if getattr(task, "done", False))
        points.append(
            {
                "label": str(getattr(phase, "name", "") or "阶段")[:12],
                "value": round(done * 100 / len(tasks)),
            }
        )
    return points or None


@dataclass
class ToolSpec:
    """一个可被智能体使用的工具。"""

    name: str
    description: str = ""
    source: Literal["local", "mcp"] = "local"
    handler: Callable[..., Any] | None = None
    # MCP server 连接信息（source="mcp" 时使用；连接器的落地在接入时补）
    mcp_server: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolModule:
    """**产品自己做好的一个功能模块**：一份后端能力 + 前端一整套渲染。

    一个模块要交的是"模型能调的那几个工具"，而模块自己产出的可视件（图 / 时间线 /
    对比矩阵…）要按三件事落地：

    1. 后端取数：模块自己的逻辑（读库、走数据源都行，但**只能是只读**）；
    2. 注册可视件：`zhiyin_business.policies.renderers.register_renderer` —— 给它
       kind 名与校验函数，服务端就认这件东西，并且由它把关数据形状；
    3. 前端组件：按 kind 分发（前端拿到的就是 `{kind, title, payload}`）。

    模块**不决定谁能用它**：挂在哪个智能体上仍写在 `agents.json` 的白名单里。
    这样"能力是谁做的"与"这个角色该有什么能力"两件事分开，各自可审。

    工具名请带模块前缀（`timetable.heatmap` 这种），避免与内置能力重名 ——
    重名会在装配时报错，而不是悄悄顶掉一个再让你去查为什么行为变了。
    """

    name: str
    tools: Sequence[ToolSpec]


class ToolRegistry:
    """工具登记处：注册、查询、按白名单过滤。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        if not replace and spec.name in self._tools:
            raise ValueError(f"工具已注册：{spec.name}（replace=True 可覆盖）")
        self._tools[spec.name] = spec

    def register_mcp_server(self, name: str, server: dict[str, Any]) -> None:
        """登记一个 MCP server（命令行 / URL 连接信息），工具名前缀为 `mcp:<server>:`。"""
        self.register(
            ToolSpec(
                name=f"mcp:{name}",
                description=f"MCP server {name}（{server.get('transport', 'stdio')}）",
                source="mcp",
                mcp_server=server,
            ),
            replace=True,
        )

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ResourceNotFound(f"工具未注册：{name}")
        return self._tools[name]

    def list(self, *, allowed: set[str] | None = None, source: str | None = None) -> list[ToolSpec]:
        """列出工具；`allowed` 是业务侧白名单（如 agents.json 的 tools 字段）。"""
        tools = self._tools.values()
        if allowed is not None:
            tools = [t for t in tools if t.name in allowed]
        if source is not None:
            tools = [t for t in tools if t.source == source]
        return sorted(tools, key=lambda t: t.name)

    def __len__(self) -> int:
        return len(self._tools)


# ---------------------------------------------------------------------------
# 真实工具：把已有的能力包成智能体能调的函数
#
# 三条约定（与 agno 2.x 对齐，不要改）：
#
# 1. 第一个参数写成 `run_context: RunContext`，框架会注入当前这次运行的上下文。
#    它会自动从**给模型看的参数表里排除**，所以工具不该、也不能让模型传 `user_id`
#    —— 让模型自己报用户是谁，等于把越权入口摆在它面前。
# 2. 返回值一律是**给模型看的文本**，不是内部对象。工具的任务是把数据变成能读的话，
#    不是把数据结构甩给模型让它猜。
# 3. 取不到就**如实说取不到**，并且明说不要编。工具层编造事实，后面没有任何一步能发现。
# ---------------------------------------------------------------------------


def _profile_fields(profile: Any) -> list[dict[str, Any]]:
    """从画像里取出"键 + 值"的字段快照，供数据源挑检索词用。读不到就是空。"""
    if profile is None:
        return []
    fields = profile.get("fields") if isinstance(profile, dict) else getattr(profile, "fields", None)
    snapshot: list[dict[str, Any]] = []
    for item in list(fields or []):
        if isinstance(item, dict):
            key, value = item.get("key"), item.get("value")
        else:
            key, value = getattr(item, "key", None), getattr(item, "value", None)
        if key:
            snapshot.append({"key": str(key), "value": value})
    return snapshot


def build_tool_catalog(
    *,
    search: Any = None,
    external_data: Any = None,
    web_search: Any = None,
    profile_reader: Callable[[str], Any] | None = None,
    behavior_reader: Callable[[str, int], Any] | None = None,
    plan_reader: Callable[[str], Any] | None = None,
    modules: Sequence[ToolModule] = (),
) -> dict[str, ToolSpec]:
    """按已装配的能力组装工具目录。没装配的能力不注册（缺了会被白名单校验拦下）。

    只注册**只读**工具：查知识库、查外部事实、读画像、读行为。
    有副作用的动作（核验学籍、抓课表成绩、写日历）必须走业务侧的完整链路
    （核验 → 解析 → 写画像 → 回执），不能做成一个模型随手可调的函数 ——
    模型看不到那条链路的副作用边界，而写画像的代价是不可逆的。

    `modules` 是**产品自己做好的功能模块**（后端取数 + 前端一整套渲染 = 一个可视件）。
    模块把自己的工具交进来，装配层只管挂上；哪个角色能用它，仍然写在
    `agents.json` 的白名单里（模块不自己决定谁能用）。见 `ToolModule` 的说明。
    """
    catalog: dict[str, ToolSpec] = {}

    # 产品模块先挂（内置工具之后挂，同名时内置优先 —— 模块不该悄悄顶掉基础能力）。
    for module in modules:
        for spec in module.tools:
            if spec.name in KNOWN_TOOL_NAMES:
                raise ValueError(
                    f"模块 {module.name} 想注册的工具名 {spec.name} 与内置工具重名。"
                    "模块的工具名要能看出是哪一家的（加前缀），否则两边会互相顶掉。"
                )
            catalog[spec.name] = spec

    if web_search is not None:

        async def web_search_tool(run_context: RunContext, query: str) -> str:
            """在公开网络上检索一条**当前**的事实（政策、公告、岗位动态…）。

            知识库与学职平台覆盖不到的、时效性强的东西用这一条；
            取回来的每条都带链接，引用时把链接一起给用户。

            Args:
                query: 检索词，写具体一点，例如"2026 秋招 结构设计 设计院 招聘 时间"
            """
            try:
                hits = await web_search.search(query)
            except Exception as exc:  # noqa: BLE001 - 搜索失败要如实说，不编
                return f"这次联网检索失败了（{exc.__class__.__name__}）。不要凭印象补，直接说这次没查到。"
            if not hits:
                return "网上没有搜到相关结果。这种情况不要凭印象补，直接说没查到。"
            return "\n".join(
                f"- {hit.title} —— {hit.snippet}\n  {hit.url}" for hit in hits
            )

        catalog["web.search"] = ToolSpec(
            name="web.search",
            description="在公开网络上检索时效性事实（政策 / 公告 / 岗位动态），返回带链接的条目",
            handler=web_search_tool,
        )

    if search is not None:

        async def kb_search(run_context: RunContext, query: str, top_k: int = 5) -> str:
            """检索方法论与职业知识库，用来支撑判断的依据。

            Args:
                query: 检索词，写具体一点，例如"结构设计岗 能力要求"或"执行意图 拆任务"
                top_k: 返回几条，默认 5
            """
            hits = await search.hybrid(query, top_k=top_k)
            if not hits:
                return "知识库里没有找到相关条目。这种情况不要凭印象补，直接说没查到。"
            lines = [
                f"- {str(hit.content).strip()[:400]}"
                for hit in hits
                if str(getattr(hit, "content", "")).strip()
            ]
            return "\n".join(lines) or "知识库里没有找到相关条目。"

        catalog["kb.search"] = ToolSpec(
            name="kb.search",
            description="检索方法论与职业知识库，取回可用于支撑判断的片段",
            handler=kb_search,
        )

    if external_data is not None:

        async def xuezhi_search(run_context: RunContext, query: str, limit: int = 5) -> str:
            """查学职平台的公开数据：专业介绍、对应职业、职业要求、公开案例。

            Args:
                query: 想查什么，例如"土木工程 对口职业"或"结构设计 岗位要求"
                limit: 最多取几条，默认 5
            """
            profile: Any = None
            if profile_reader is not None:
                profile = await _read(profile_reader, run_context.user_id)
            from zhiyin_data_sdk.gateways.datasource import DataSourceRequest

            result = await external_data.fetch(
                DataSourceRequest(
                    source="xuezhi",
                    query=query,
                    limit=max(1, min(int(limit), 20)),
                    context={"fields": _profile_fields(profile)},
                )
            )
            records = list(getattr(result, "records", []) or [])
            if not records:
                errors = "；".join(str(e) for e in (getattr(result, "errors", []) or []))
                return (
                    f"这次没取到学职平台的数据（{errors or '没有命中'}）。"
                    "不要用相似数据替代，直接说没取到。"
                )
            parts: list[str] = []
            for record in records:
                title = str(getattr(record, "title", "") or "").strip()
                text = str(getattr(record, "text", "") or "").strip()
                origin = str(getattr(record, "source_url", "") or "").strip()
                fetched = str(getattr(record, "fetched_at", "") or "").strip()
                parts.append(
                    f"- {title}：{text[:500]}（来源：{origin or '学职平台'}，取数时间：{fetched or '未知'}）"
                )
            if getattr(result, "degraded", False):
                parts.append("（这次只取到一部分，用它的时候要说明不完整。）")
            return "\n".join(parts)

        catalog["xuezhi.search"] = ToolSpec(
            name="xuezhi.search",
            description="查学职平台的公开数据：专业、对口职业、职业要求与公开案例",
            handler=xuezhi_search,
        )

    if profile_reader is not None:

        async def profile_read(run_context: RunContext) -> str:
            """读当前用户的画像：已知哪些字段、把握多大、还缺什么。"""
            data = await _read(profile_reader, run_context.user_id)
            return _describe_profile(data)

        catalog["profile.read"] = ToolSpec(
            name="profile.read",
            description="读当前用户的画像字段与缺口",
            handler=profile_read,
        )

    if behavior_reader is not None:

        async def behavior_recent(run_context: RunContext, limit: int = 10) -> str:
            """读当前用户最近做过的事（勾掉任务、改主意、复盘等）。

            Args:
                limit: 读最近几条，默认 10
            """
            rows = await _read(behavior_reader, run_context.user_id, max(1, min(int(limit), 50)))
            if not rows:
                return "这个用户还没有任何行为记录。"
            return "\n".join(_describe_behavior(row) for row in rows)

        catalog["behavior.recent"] = ToolSpec(
            name="behavior.recent",
            description="读当前用户最近的行为记录",
            handler=behavior_recent,
        )

    if plan_reader is not None:

        async def plan_read(run_context: RunContext) -> str:
            """读当前用户的行动计划与关键节点：分几个阶段、有哪些任务、哪些做完了、什么时候截止。

            排计划的人要靠它知道"上一版排了什么、他做到哪了"，才不会重复排、也不会
            把已经勾掉的事再安排一遍；陪你推进的人靠它判断"停在哪一步"。
            """
            data = await _read(plan_reader, run_context.user_id)
            return _describe_plan(data)

        catalog["plan.read"] = ToolSpec(
            name="plan.read",
            description="读当前用户的行动计划、任务完成情况与关键节点截止时间",
            handler=plan_read,
        )

    if profile_reader is not None or plan_reader is not None:

        async def chart_render(
            run_context: RunContext, kind: str, title: str = ""
        ) -> str:
            """给他画一张图，挂在这一轮的回复上。

            **数字不是你填的**：你只挑"画哪一类"，点位由系统从库里读真实数据算出来。
            所以你不用、也不能在回复里报这些数字 —— 图就在他眼前。
            画完用一句话告诉他这张图在说什么就够了。

            Args:
                kind: 只能取这几个之一 —— profile_confidence（他各项情况的把握度）、
                    direction_match（几套方向各自的匹配度）、plan_progress（各阶段做完了多少）
                title: 图上方给他看的一句话（不填就用默认标题）
            """
            wanted = (kind or "").strip()
            if wanted not in _CHART_KINDS:
                return (
                    f"没有「{kind}」这一类图。能画的只有："
                    + "；".join(f"{name}（{desc}）" for name, desc in _CHART_KINDS.items())
                )
            points = await _chart_points(wanted, run_context, profile_reader, plan_reader)
            if points is None:
                return f"这一类图现在画不出来：{_CHART_KINDS[wanted]}还缺数据。别硬画，也别编数字。"
            if len(points) < 2:
                return "只有一项，画成图看不出什么，直接用话说给他听更清楚。"
            spec = {
                "kind": "bars_chart",
                "title": (title or "").strip()[:30] or _DEFAULT_CHART_TITLES[wanted],
                "payload": {"unit": _CHART_UNITS[wanted], "points": points},
            }
            # 放进这一次运行的**回传盒子**：跑完由引擎取走，交给编排器校验后挂到消息上。
            # 盒子不在（比如某个调用方没接）也不报错 —— 可视件是加分项。
            dependencies = getattr(run_context, "dependencies", None)
            if isinstance(dependencies, dict):
                box = dependencies.setdefault(CHART_BOX_KEY, [])
                if isinstance(box, list):
                    box.append(spec)
            listed = "、".join(f"{item['label']} {item['value']:g}{_CHART_UNITS[wanted]}" for item in points)
            return f"图已经挂上了（{spec['title']}）：{listed}。用一句话跟他讲这张图在说什么。"

        catalog["chart.render"] = ToolSpec(
            name="chart.render",
            description=(
                "给他画一张图挂在这一轮的回复上。只能挑图的类别"
                "（" + "、".join(_CHART_KINDS) + "），数字由系统读真实数据生成"
            ),
            handler=chart_render,
        )

    # 自检：注册进来的名字必须在 KNOWN_TOOL_NAMES 里。
    # 少了它，那份名单会慢慢变成一份过期文档 —— 而守卫会照着它放行。
    #
    # **模块带来的工具不查这份名单**：名字是模块自己的（`timetable.heatmap` 这种），
    # 它先由 `ToolModule` 声明、再在装配时进目录，最后按 `agents.json` 的白名单决定
    # 谁能用 —— 那是另一条校验路径。硬塞进内置名单反而会让"哪个是内置能力、
    # 哪个是产品模块"分不清。
    module_names = {spec.name for module in modules for spec in module.tools}
    unlisted = sorted(set(catalog) - KNOWN_TOOL_NAMES - module_names)
    if unlisted:
        raise ValueError(
            f"工具目录注册了未登记的工具名：{unlisted}。"
            "请同步 zhiyin_infrastructure.ai.tools.KNOWN_TOOL_NAMES"
            "（agents.json 的白名单校验也以它为准）"
        )
    return catalog


async def _read(reader: Callable[..., Any], *args: Any) -> Any:
    """读侧回调可能是同步的（内存实现）也可能是异步的（数据库实现），两种都认。"""
    value = reader(*args)
    if hasattr(value, "__await__"):
        return await value
    return value


def _describe_profile(data: Any) -> str:
    """把画像整理成给模型看的几行字。空就如实说空。"""
    if isinstance(data, str):
        return data
    fields = list(getattr(data, "fields", []) or []) if not isinstance(data, dict) else list(
        data.get("fields", []) or []
    )
    gaps = list(getattr(data, "gaps", []) or []) if not isinstance(data, dict) else list(
        data.get("gaps", []) or []
    )
    if not fields and not gaps:
        return "这个用户还没有画像内容。先问出一个能答的问题，不要假装已经知道。"
    lines = ["已知："]
    for item in fields:
        key = getattr(item, "key", None) or (item.get("key") if isinstance(item, dict) else "")
        value = getattr(item, "value", None) if not isinstance(item, dict) else item.get("value")
        confidence = getattr(item, "confidence", 0.0) if not isinstance(item, dict) else item.get("confidence", 0.0)
        source = getattr(item, "source", "") if not isinstance(item, dict) else item.get("source", "")
        source = getattr(source, "value", source)
        lines.append(f"- {key}：{value}（来源：{source}，把握：{float(confidence or 0):.2f}）")
    if gaps:
        lines.append("还缺：")
        for gap in gaps:
            key = getattr(gap, "key", "") if not isinstance(gap, dict) else gap.get("key", "")
            reason = getattr(gap, "reason", "") if not isinstance(gap, dict) else gap.get("reason", "")
            lines.append(f"- {key}：{reason}")
    return "\n".join(lines)


def _describe_plan(data: Any) -> str:
    """行动计划 + 关键节点 → 给模型看的几行字。没有就如实说没有。"""
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return "还没读到计划内容。"
    plan = data.get("plan")
    nodes = list(data.get("nodes") or [])
    lines: list[str] = []
    phases = list(getattr(plan, "phases", []) or []) if plan is not None else []
    if phases:
        lines.append("现在这一版计划：")
        for phase in phases:
            name = getattr(phase, "name", "") or ""
            window = getattr(phase, "date_range", "") or ""
            lines.append(f"- 阶段 {name}（{window}）")
            for task in getattr(phase, "tasks", []) or []:
                mark = "已做" if getattr(task, "done", False) else "没做"
                text = getattr(task, "text", "") or ""
                lines.append(f"  · [{mark}] {text}")
    else:
        lines.append("还没有行动计划 —— 这一轮如果要给任务，就是第一版。")
    if nodes:
        lines.append("关键节点：")
        for node in nodes:
            title = getattr(node, "title", "") or (node.get("title") if isinstance(node, dict) else "")
            due = getattr(node, "due_at", None) if not isinstance(node, dict) else node.get("due_at")
            lines.append(f"- {title}（截止：{due or '未写'}）")
    return "\n".join(lines)


def _describe_behavior(row: Any) -> str:
    """一条行为记录 → 一行字。"""
    if isinstance(row, str):
        return f"- {row}"
    event = getattr(row, "event_type", "") if not isinstance(row, dict) else row.get("event_type", "")
    event = getattr(event, "value", event)
    moment = getattr(row, "occurred_at", None) if not isinstance(row, dict) else row.get("occurred_at")
    when = moment.strftime("%m-%d %H:%M") if hasattr(moment, "strftime") else str(moment or "")
    return f"- {when} {event}"


__all__ = ["ToolRegistry", "ToolSpec", "build_tool_catalog"]
