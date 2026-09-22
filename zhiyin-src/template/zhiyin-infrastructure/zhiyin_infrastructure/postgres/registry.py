"""PostgreSQL 动态资源 Repository。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from zhiyin_data_sdk.errors import MissingConfigError
from zhiyin_data_sdk.repositories import RegistryRepository
from zhiyin_kernel.dynamic_content import (
    BannerSpec,
    FaqSpec,
    MenuSpec,
    RouteSpec,
    TrustBlockSpec,
)
from zhiyin_kernel.enums import LoopStage
from zhiyin_kernel.registry import (
    AgentDescriptor,
    BadgeRuleSpec,
    ChsiFieldSpec,
    CollectionRuleSpec,
    LayoutPolicy,
    OutputContractSpec,
    PolicyParamSet,
    PromptSpec,
    RoutingRuleSpec,
    StageSpec,
    TaskEntrySpec,
    TaskProgressSpec,
    TheoryCard,
    TrackEventSpec,
    UserSignalSpec,
)
from zhiyin_infrastructure.postgres.database import PostgresDatabase

logger = logging.getLogger(__name__)

_FILES: dict[str, str] = {
    "agents": "agents.json",
    "theory_cards": "theory_cards.json",
    "output_contracts": "output_contracts.json",
    "task_entries": "task_entries.json",
    "policy_params": "policy_params.json",
    "menus": "menus.json",
    "routes": "routes.json",
    "copies": "copies.json",
    "banners": "banners.json",
    "trust_blocks": "trust_blocks.json",
    "faqs": "faqs.json",
    "track_events": "track_events.json",
    # 控制台气泡的编排策略：顺序与空间由它决定，不在前端写死
    "layout": "layout.json",
    # 五个环节的展示口径：曾经在三个地方各写一遍，现在只留这一份
    "stages": "stages.json",
    # 采集规则：缺什么、去哪儿取、为什么。以前硬编码在 policies/collection.py
    "collection_rules": "collection_rules.json",
    # 用户信号：用户自己写下的话里的线索词 → 哪个画像字段变成前提
    "user_signals": "user_signals.json",
    # 产品口径：成就规则 / AI 任务进度文案 / 学信网字段清单
    "badge_rules": "badge_rules.json",
    "task_progress": "task_progress.json",
    "chsi_fields": "chsi_fields.json",
}

_STATUS_FILTERED_KINDS = {
    # 前端页面内容
    "menus",
    "routes",
    "copies",
    "banners",
    "trust_blocks",
    "faqs",
}

# AI 区：提示词与编排规则的读者是引擎与编排策略，不是前端下发。
# 它们落在 `ai_prompt_template` / `ai_routing_rule` 两张表里，不并进通用表 ——
# 分区判据是"谁读它"，而通用表把形状压成 JSONB，写错字段要到读的时候才炸。
_AI_FILES: dict[str, str] = {
    "prompts": "prompts.json",
    "routing_rules": "routing_rules.json",
}

#: 每个 AI 类别落在哪张表。表名只在这里出现一次，收敛语句与计数共用它。
_AI_TABLES: dict[str, str] = {
    "prompts": "ai_prompt_template",
    "routing_rules": "ai_routing_rule",
}


class PostgresRegistryRepository(RegistryRepository):
    """动态资源从 `biz_registry_item` 读取，首次访问时用 JSON 种子导入。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase, registry_dir: str) -> None:
        self._db = database
        self._registry_dir = Path(registry_dir)
        self._seeded = False
        self._ai_seeded = False
        self._lock = asyncio.Lock()

    async def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        return _first(await self._load("agents", AgentDescriptor), "id", agent_id)

    async def raw_snapshot(self) -> dict[str, dict[str, str]]:
        """库中全部动态资源的「类别 → 稳定键 → 内容指纹」。

        给启动对账用（`zhiyin_boot.registry_bootstrap.detect_registry_drift`）：
        它只关心"库里那条与文件里那条还是不是同一份内容"，不关心形状，
        所以直接对原始 JSONB 取值做规范化哈希，不经过任何模型。
        """
        snapshot: dict[str, dict[str, str]] = {}
        rows = await self._db.fetch("SELECT kind, code, payload FROM biz_registry_item")
        for row in rows:
            items = snapshot.setdefault(row["kind"], {})
            items[str(row["code"])] = _fingerprint(_load_json(row["payload"]))

        prompt_rows = await self._db.fetch("SELECT * FROM ai_prompt_template")
        prompts = snapshot.setdefault("prompts", {})
        for row in prompt_rows:
            prompts[str(row["code"])] = _fingerprint(_prompt_payload(row))

        rule_rows = await self._db.fetch("SELECT * FROM ai_routing_rule")
        rules = snapshot.setdefault("routing_rules", {})
        for row in rule_rows:
            rules[str(row["id"])] = _fingerprint(_routing_rule_payload(row))
        return snapshot

    @staticmethod
    def seed_files() -> dict[str, str]:
        """类别 → 种子文件名。对账、文档与守卫共用这一处口径，避免各拼一份清单。"""
        return {**_FILES, **_AI_FILES}

    @staticmethod
    def fingerprint(payload: dict[str, Any]) -> str:
        """内容指纹（对账用）。与写入侧的规范化口径绑定在同一个函数里。"""
        return _fingerprint(payload)

    async def list_agents(self) -> list[AgentDescriptor]:
        return await self._load("agents", AgentDescriptor)

    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCard]:
        return _first(await self._load("theory_cards", TheoryCard), "id", theory_id)

    async def list_theory_cards(
        self, theory_ids: Optional[list[str]] = None
    ) -> list[TheoryCard]:
        cards = await self._load("theory_cards", TheoryCard)
        if not theory_ids:
            return cards
        wanted = set(theory_ids)
        return [card for card in cards if card.id in wanted]

    async def get_output_contract(
        self, agent_id: str, stage: LoopStage
    ) -> Optional[OutputContractSpec]:
        expected = stage.value if isinstance(stage, LoopStage) else str(stage)
        for item in await self._load("output_contracts", OutputContractSpec):
            if item.agent_id == agent_id and item.stage == expected:
                return item
        return None

    async def list_task_entries(self) -> list[TaskEntrySpec]:
        return await self._load("task_entries", TaskEntrySpec)

    async def get_layout_policy(self, code: str = "default") -> Optional[LayoutPolicy]:
        """控制台气泡的编排策略。缺了就返回 None —— 由调用方决定兜底。"""
        return _first(await self._load("layout", LayoutPolicy), "code", code)

    async def list_stages(self) -> list[StageSpec]:
        """五个环节的展示口径，已按 order 排序。"""
        stages = await self._load("stages", StageSpec)
        return sorted(stages, key=lambda s: s.order)

    async def list_collection_rules(self) -> list[CollectionRuleSpec]:
        """采集规则，已按 order 排序（表序本身就是重要度）。"""
        rules = await self._load("collection_rules", CollectionRuleSpec)
        return sorted(rules, key=lambda r: r.order)

    async def list_user_signals(self) -> list[UserSignalSpec]:
        """用户信号线索表，已按 order 排序。"""
        signals = await self._load("user_signals", UserSignalSpec)
        return sorted(signals, key=lambda s: s.order)

    async def list_badge_rules(self) -> list[BadgeRuleSpec]:
        """成就解锁规则，已按 sort_order 排序。"""
        rules = await self._load("badge_rules", BadgeRuleSpec)
        return sorted(rules, key=lambda r: r.sort_order)

    async def list_task_progress(self) -> list[TaskProgressSpec]:
        """AI 任务进度文案，已按 sort_order 排序。"""
        items = await self._load("task_progress", TaskProgressSpec)
        return sorted(items, key=lambda i: i.sort_order)

    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        """学信网字段清单，已按 order 排序。"""
        fields = await self._load("chsi_fields", ChsiFieldSpec)
        return sorted(fields, key=lambda f: f.order)

    async def get_policy_params(self, code: str) -> Optional[PolicyParamSet]:
        return _first(await self._load("policy_params", PolicyParamSet), "code", code)

    async def list_menus(self) -> list[MenuSpec]:
        return await self._load("menus", MenuSpec)

    async def list_routes(self) -> list[RouteSpec]:
        return await self._load("routes", RouteSpec)

    async def get_copy_bundle(self, bundle: str = "zh-CN") -> dict[str, str]:
        items = await self._load("copies", None)
        result: dict[str, str] = {}
        for item in items:
            if item.get("bundle", "zh-CN") != bundle:
                continue
            code = item.get("code") or item.get("id")
            if code:
                result[str(code)] = str(item.get("text", ""))
        return result

    async def list_banners(self) -> list[BannerSpec]:
        return await self._load("banners", BannerSpec)

    async def list_trust_blocks(self) -> list[TrustBlockSpec]:
        return await self._load("trust_blocks", TrustBlockSpec)

    async def list_faqs(self) -> list[FaqSpec]:
        return await self._load("faqs", FaqSpec)

    async def list_track_events(self) -> list[TrackEventSpec]:
        return await self._load("track_events", TrackEventSpec)

    # ---------- AI 提示词与编排规则 ----------

    async def get_prompt(self, code: str) -> Optional[PromptSpec]:
        await self._ensure_ai_seeded()
        row = await self._db.fetchrow(
            """
            SELECT code, layer, agent_id, stage, name, content, params, status, sort_order, note
            FROM ai_prompt_template
            WHERE code = $1 AND status = 'enabled'
            """,
            code,
        )
        return _to_prompt(row) if row is not None else None

    async def list_prompts(
        self,
        *,
        layer: Optional[str] = None,
        agent_id: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[PromptSpec]:
        await self._ensure_ai_seeded()
        rows = await self._db.fetch(
            """
            SELECT code, layer, agent_id, stage, name, content, params, status, sort_order, note
            FROM ai_prompt_template
            WHERE status = 'enabled'
            ORDER BY sort_order ASC, code ASC
            """
        )
        specs = [_to_prompt(row) for row in rows]
        if layer is not None:
            specs = [spec for spec in specs if spec.layer == layer]
        if agent_id is not None:
            specs = [spec for spec in specs if spec.agent_id == agent_id]
        if stage is not None:
            specs = [spec for spec in specs if spec.stage == stage]
        return specs

    async def list_routing_rules(
        self, kind: Optional[str] = None
    ) -> list[RoutingRuleSpec]:
        await self._ensure_ai_seeded()
        if kind is None:
            rows = await self._db.fetch(
                """
                SELECT id, kind, sort_order, match, intent, stage, status, note
                FROM ai_routing_rule
                WHERE status = 'enabled'
                ORDER BY sort_order ASC, id ASC
                """
            )
        else:
            rows = await self._db.fetch(
                """
                SELECT id, kind, sort_order, match, intent, stage, status, note
                FROM ai_routing_rule
                WHERE status = 'enabled' AND kind = $1
                ORDER BY sort_order ASC, id ASC
                """,
                kind,
            )
        return [_to_routing_rule(row) for row in rows]

    async def reload(self) -> None:
        """重新从 JSON 拉取一次动态资源种子。"""
        await self._ensure_seeded(force=True)
        await self._ensure_ai_seeded(force=True)

    async def resync(self) -> int:
        """以文件为准重导：先 upsert，再**删掉文件里已经没有的同类别条目**。

        与 `reload()` 的区别就是最后那一步删除，而少了它"以文件为准"只兑现一半：
        从 `data/registry/*.json` 里删掉的那一条会永远留在库、留在迁移文件里，
        继续下发给前端 —— 界面上就是一句谁都没在维护、却谁也删不掉的文案。

        删的范围严格限定在**种子文件管的类别**（`_FILES` / `_AI_FILES`），
        而且**文件缺失或读出来是空的时候不删**：那更可能是路径写错或文件被误删，
        此时清库比留着旧数据危险得多。

        返回删除的行数，供调用方在启动日志里如实报出来。
        """
        await self.reload()
        return await self._prune_stale()

    async def _prune_stale(self) -> int:
        removed = 0
        for kind, filename in _FILES.items():
            codes = _seed_keys(self._registry_dir / filename, ("code", "id", "key"))
            if not codes:
                continue
            removed += await self._delete_missing(
                "biz_registry_item", "kind", kind, "code", codes
            )
        for kind, filename in _AI_FILES.items():
            table = _AI_TABLES[kind]
            key_column = "code" if kind == "prompts" else "id"
            keys = _seed_keys(self._registry_dir / filename, (key_column,))
            if not keys:
                continue
            removed += await self._delete_missing(table, None, None, key_column, keys)
        if removed:
            logger.warning("动态资源重导：库里多出的 %d 条已按文件删除", removed)
        return removed

    async def _delete_missing(
        self,
        table: str,
        scope_column: Optional[str],
        scope_value: Optional[str],
        key_column: str,
        keys: set[str],
    ) -> int:
        where = f"{key_column} <> ALL($1::text[])"
        args: list[Any] = [sorted(keys)]
        if scope_column is not None and scope_value is not None:
            where = f"{scope_column} = $2 AND " + where
            args.append(scope_value)
        status = await self._db.execute(f"DELETE FROM {table} WHERE {where}", *args)
        # asyncpg 的 execute 返回 "DELETE <n>"，行数在末段。
        tail = str(status).rsplit(" ", 1)[-1]
        return int(tail) if tail.isdigit() else 0

    async def ensure_seeded(self) -> None:
        """补齐**尚未导入**的类别（已有的原样不动）。

        给启动阶段用。与 `reload()` 的区别是它不覆盖：
        种子只是首次导入，写进库之后以库为准 —— 否则每次启动都会把
        运营在库里改过的口径冲回 JSON 里的那一版。

        为什么要有一个显式的启动调用，而不是继续靠"第一次读"懒加载：
        懒加载会让新装的库里这些类别**一直空着**，直到有人真的读它；
        在那之前查库的人分不清"还没导"和"本来就没有配置"。
        """
        await self._ensure_seeded()
        await self._ensure_ai_seeded()

    async def _ensure_ai_seeded(self, *, force: bool = False) -> None:
        """把 AI 区的种子导进各自表里（按类别判断，已有的不覆盖）。

        与通用动态资源同一套「看这一类有没有、而不是看整库空不空」的口径，
        否则给一个已经在跑的库新增一类时永远导不进去。
        """
        if self._ai_seeded and not force:
            return
        async with self._lock:
            if self._ai_seeded and not force:
                return
            seeded_any = False
            for kind, filename in _AI_FILES.items():
                if not force:
                    existing = await self._count_ai(kind)
                    if existing > 0:
                        continue
                path = self._registry_dir / filename
                if not path.is_file():
                    # 不静默跳过：少一整类配置会让某个环节凭空变哑，
                    # 而没人会想到去查种子文件在不在。
                    raise MissingConfigError(f"缺少 AI 动态资源种子文件：{path}")
                for item in _read_items(path):
                    await self._insert_ai(kind, item)
                seeded_any = True
            self._ai_seeded = True
            if seeded_any:
                logger.info("AI 动态资源已导入：%s", "、".join(sorted(_AI_FILES)))

    async def _count_ai(self, kind: str) -> int:
        table = _AI_TABLES[kind]
        value = await self._db.fetchval(f"SELECT COUNT(*) FROM {table}")
        return int(value or 0)

    async def _insert_ai(self, kind: str, item: dict[str, Any]) -> None:
        if kind == "prompts":
            spec = PromptSpec.model_validate(item)
            await self._db.execute(
                """
                INSERT INTO ai_prompt_template
                    (code, layer, agent_id, stage, name, content, params,
                     status, sort_order, note)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10)
                ON CONFLICT (code) DO UPDATE SET
                    layer = EXCLUDED.layer,
                    agent_id = EXCLUDED.agent_id,
                    stage = EXCLUDED.stage,
                    name = EXCLUDED.name,
                    content = EXCLUDED.content,
                    params = EXCLUDED.params,
                    status = EXCLUDED.status,
                    sort_order = EXCLUDED.sort_order,
                    note = EXCLUDED.note,
                    updated_at = NOW()
                """,
                spec.code,
                spec.layer,
                spec.agent_id,
                spec.stage,
                spec.name,
                spec.content,
                json.dumps(spec.params, ensure_ascii=False),
                spec.status,
                spec.sort_order,
                spec.note,
            )
            return
        rule = RoutingRuleSpec.model_validate(item)
        await self._db.execute(
            """
            INSERT INTO ai_routing_rule
                (id, kind, sort_order, match, intent, stage, status, note)
            VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8)
            ON CONFLICT (id) DO UPDATE SET
                kind = EXCLUDED.kind,
                sort_order = EXCLUDED.sort_order,
                match = EXCLUDED.match,
                intent = EXCLUDED.intent,
                stage = EXCLUDED.stage,
                status = EXCLUDED.status,
                note = EXCLUDED.note,
                updated_at = NOW()
            """,
            rule.id,
            rule.kind,
            rule.sort_order,
            json.dumps(rule.match, ensure_ascii=False),
            rule.intent,
            rule.stage,
            rule.status,
            rule.note,
        )

    async def _load(self, kind: str, model: Any) -> list[Any]:
        await self._ensure_seeded()
        if kind in _STATUS_FILTERED_KINDS:
            rows = await self._db.fetch(
                """
                SELECT payload FROM biz_registry_item
                WHERE kind = $1 AND status = 'enabled'
                ORDER BY sort_order ASC, code ASC
                """,
                kind,
            )
        else:
            rows = await self._db.fetch(
                """
                SELECT payload FROM biz_registry_item
                WHERE kind = $1
                ORDER BY sort_order ASC, code ASC
                """,
                kind,
            )
        items = [_load_json(row["payload"]) for row in rows]
        if model is None:
            return items
        return [model.model_validate(item) for item in items]

    async def _ensure_seeded(self, *, force: bool = False) -> None:
        if self._seeded and not force:
            return
        async with self._lock:
            if self._seeded and not force:
                return
            # ⚠️ **按类别**判断有没有种，而不是看整张表空不空。
            #
            # 之前的口径是"表里一条都没有才导"，后果是：给一个已经在跑的库
            # 新增一类动态资源（比如后来的 layout），永远导不进去 ——
            # 代码里加了、测试里过了、生产上那一类永远是空的，而且不报错。
            # 迁移时最怕的就是这种"静默少一块配置"。
            for kind, filename in _FILES.items():
                if not force:
                    existing = await self._db.fetchval(
                        "SELECT COUNT(*) FROM biz_registry_item WHERE kind = $1",
                        kind,
                    )
                    if int(existing or 0) > 0:
                        continue
                if not (self._registry_dir / filename).is_file():
                    # 静默少一整类配置比报错危险得多：代码里登记了、库里是空的，
                    # 谁都不会发现，直到某天界面少一块才回头查。
                    logger.warning(
                        "动态资源种子文件缺失：%s（类别 %s 将保持为空）",
                        self._registry_dir / filename,
                        kind,
                    )
                    continue
                for index, item in enumerate(_read_items(self._registry_dir / filename)):
                    code = str(
                        item.get("code")
                        or item.get("id")
                        # 有些表天然以 `key` 为身份（采集规则、PolicyParamSet）。
                        # 不给它认这个，它就会退化成"按位置编号"——
                        # 重排一次 JSON，配置就整体错位，而上层看到的只是"值变了"。
                        or item.get("key")
                        or f"{kind}-{index}"
                    )
                    status = (
                        str(item.get("status", "enabled"))
                        if kind in _STATUS_FILTERED_KINDS
                        else "enabled"
                    )
                    await self._db.execute(
                        """
                        INSERT INTO biz_registry_item
                            (kind, code, payload, status, sort_order)
                        VALUES ($1, $2, $3::jsonb, $4, $5)
                        ON CONFLICT (kind, code) DO UPDATE SET
                            payload = EXCLUDED.payload,
                            status = EXCLUDED.status,
                            sort_order = EXCLUDED.sort_order,
                            updated_at = NOW()
                        """,
                        kind,
                        code,
                        json.dumps(item, ensure_ascii=False),
                        status,
                        int(item.get("sort_order", 0) or 0),
                    )
            self._seeded = True


def _read_items(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    return [item for item in items if isinstance(item, dict)]


def _seed_keys(path: Path, names: tuple[str, ...]) -> set[str]:
    """种子文件里这一类的稳定键集合（文件缺失或读不出条目时返回空集）。

    空集在调用方是"不动库"的意思 —— 与 `_read_items` 同一套容错口径。
    """
    return {
        str(item[name])
        for item in _read_items(path)
        for name in names
        if item.get(name)
    }


def _load_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _first(items: list[Any], field: str, expected: str) -> Optional[Any]:
    for item in items:
        if str(getattr(item, field, "")) == expected:
            return item
    return None


def _to_prompt(row: Any) -> PromptSpec:
    """把一行 `ai_prompt_template` 还原成内核形状。"""
    return PromptSpec(**_prompt_payload(row))


def _prompt_payload(row: Any) -> dict[str, Any]:
    """`ai_prompt_template` 一行 → 与 `prompts.json` 同形状的 dict。

    对账与还原共用它：两条路径一旦各写一遍字段映射，对账比的就不是
    "库里那条与文件那条是否同一份内容"，而是"两份映射是否一致"。
    """
    return {
        "code": row["code"],
        "layer": row["layer"],
        "content": row["content"],
        "agent_id": row["agent_id"] or "",
        "stage": row["stage"] or "",
        "name": row["name"] or "",
        "params": _load_json(row["params"]),
        "status": row["status"] or "enabled",
        "sort_order": int(row["sort_order"] or 0),
        "note": row["note"] or "",
    }


def _routing_rule_payload(row: Any) -> dict[str, Any]:
    """`ai_routing_rule` 一行 → 与 `routing_rules.json` 同形状的 dict。"""
    raw_match = row["match"]
    if isinstance(raw_match, str):
        raw_match = json.loads(raw_match)
    return {
        "id": row["id"],
        "kind": row["kind"],
        "sort_order": int(row["sort_order"] or 100),
        "match": [str(item) for item in (raw_match or [])],
        "intent": row["intent"] or "",
        "stage": row["stage"] or "",
        "status": row["status"] or "enabled",
        "note": row["note"] or "",
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    """内容指纹：忽略键序与 `_note` 这类纯说明字段造成的噪声。

    只对**参与运行**的字段做规范化序列化 —— 否则给文件补一句注释就会报"漂移"，
    那种噪声会让人很快学会忽略这条告警。
    """
    volatile = {"note", "_note"}
    normalized = {k: v for k, v in payload.items() if k not in volatile}
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _to_routing_rule(row: Any) -> RoutingRuleSpec:
    """把一行 `ai_routing_rule` 还原成内核形状。`match` 是 JSONB 数组。"""
    return RoutingRuleSpec(**_routing_rule_payload(row))


__all__ = ["PostgresRegistryRepository"]
