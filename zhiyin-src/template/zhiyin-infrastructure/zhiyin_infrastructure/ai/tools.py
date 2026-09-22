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
from typing import Any, Callable, Literal

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
    }
)


@dataclass
class ToolSpec:
    """一个可被智能体使用的工具。"""

    name: str
    description: str = ""
    source: Literal["local", "mcp"] = "local"
    handler: Callable[..., Any] | None = None
    # MCP server 连接信息（source="mcp" 时使用；连接器的落地在接入时补）
    mcp_server: dict[str, Any] = field(default_factory=dict)


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
) -> dict[str, ToolSpec]:
    """按已装配的能力组装工具目录。没装配的能力不注册（缺了会被白名单校验拦下）。

    只注册**只读**工具：查知识库、查外部事实、读画像、读行为。
    有副作用的动作（核验学籍、抓课表成绩、写日历）必须走业务侧的完整链路
    （核验 → 解析 → 写画像 → 回执），不能做成一个模型随手可调的函数 ——
    模型看不到那条链路的副作用边界，而写画像的代价是不可逆的。
    """
    catalog: dict[str, ToolSpec] = {}

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

    # 自检：注册进来的名字必须在 KNOWN_TOOL_NAMES 里。
    # 少了它，那份名单会慢慢变成一份过期文档 —— 而守卫会照着它放行。
    unlisted = sorted(set(catalog) - KNOWN_TOOL_NAMES)
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
