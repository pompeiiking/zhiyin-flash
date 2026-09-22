"""文案包守卫：`data/registry/copies.json` 里的每一条都得有人读。

为什么值得单独一条守卫
----------------------
文案包是动态资源，改一句不发版 —— 代价是它**只增不减**。
实测：这份文件里 129 条有 116 条从没有任何代码读过，而且都是上一版外壳
留下的词（"微循环管线""① 画像状态"）。它们不会报错、不会出现在界面上，
只会在下一个人想改文案时先看到一堆"像是真的"的旧句子 ——
那正是这个仓最该避免的一种污染：**看起来能用，其实没人用**。

所以口径是：**先接线，再登记**。这条守卫挡住两个方向：

1. 包里有、没人读 → 删掉，或在消费方接上；
2. 前端按 key 取用、包里没有 → 那一处文案在界面上会是空白
   （门户页刻意不放过兜底文案，"缺了要立刻可见"）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
COPIES = TEMPLATE_ROOT / "data" / "registry" / "copies.json"
PORTAL_VIEW = TEMPLATE_ROOT / "zhiyin-web" / "src" / "views" / "PortalView.vue"
PORTRAIT_VIEW = TEMPLATE_ROOT / "zhiyin-web" / "src" / "components" / "console" / "PortraitOverlay.vue"

#: 消费方所在位置。前端读门户文案、后端拼通知与分组名，两边都要算进来。
CONSUMERS: tuple[Path, ...] = (
    TEMPLATE_ROOT / "zhiyin-web" / "src",
    TEMPLATE_ROOT / "zhiyin-api",
    TEMPLATE_ROOT / "zhiyin-business",
    TEMPLATE_ROOT / "zhiyin-boot",
)

#: 门户地图八站的文案是**拼出来的**（`portal.stop.<id>.<字段>`），看不到字面量。
#: 这里认 PortalView 里那条规则本身：规则在，八站文案就有人读。
_STOP_KEY_RULE = re.compile(r"portal\\\.stop\\\.")

#: 画像字段的中文对照同样是**拼出来的**（`profile.field.<字段键>`）：字段键是模型
#: 生成的（`interest_direction` 这种），写不成字面量。认那条拼接规则本身。
_PROFILE_LABEL_RULE = re.compile(r"profile\.field\.\$\{")

#: 画像字段的同义词表（`profile.alias.<模型写的键>` → 规范键）同理：键来自模型，
#: 一组一组地写出来不现实。认 `dynamic_config` 里按前缀挑词表的那条规则。
_PROFILE_ALIAS_RULE = re.compile(r"PROFILE_ALIAS_PREFIX")
TEMPLATE_DYNAMIC_CONFIG = (
    TEMPLATE_ROOT / "zhiyin-business" / "zhiyin_business" / "services" / "dynamic_config.py"
)


def _codes() -> list[str]:
    return [item["code"] for item in json.loads(COPIES.read_text(encoding="utf-8"))["items"]]


def _consumer_sources() -> dict[Path, str]:
    sources: dict[Path, str] = {}
    for root in CONSUMERS:
        for path in root.rglob("*"):
            if path.suffix in {".ts", ".vue", ".py"}:
                sources[path] = path.read_text(encoding="utf-8")
    assert sources, "没有扫到任何消费方源码 —— 守卫会变成空跑"
    return sources


def test_every_copy_entry_is_read_by_someone() -> None:
    sources = _consumer_sources()
    portal_has_stop_rule = bool(_STOP_KEY_RULE.search(PORTAL_VIEW.read_text(encoding="utf-8")))
    assert portal_has_stop_rule, (
        "PortalView 里没有找到拼接 `portal.stop.<id>.<字段>` 的那条规则 —— "
        "八站文案会被判成没人读。规则改名了就把本守卫一起改。"
    )

    dead: list[str] = []
    for code in _codes():
        if code.startswith("portal.stop.") and portal_has_stop_rule:
            continue
        if code.startswith("profile.field.") and _profile_label_rule():
            continue
        if code.startswith("profile.alias.") and _alias_rule():
            continue
        if any(f"'{code}'" in text or f'"{code}"' in text for text in sources.values()):
            continue
        dead.append(code)

    assert not dead, (
        "这些文案没有任何代码读过（界面上不会出现，只会在下次改文案时误导人）：\n  "
        + "\n  ".join(dead)
        + "\n处理方式：接上消费方，或从 data/registry/copies.json 里删掉。"
    )


def _profile_label_rule() -> bool:
    """画像字段的对照表有没有人在按规则读（规则改名了这条守卫要一起改）。"""
    has_rule = bool(_PROFILE_LABEL_RULE.search(PORTRAIT_VIEW.read_text(encoding="utf-8")))
    assert has_rule, (
        "PortraitOverlay 里没有找到拼接 `profile.field.<字段键>` 的那条规则 —— "
        "字段的中文对照会被判成没人读。规则改名了就把本守卫一起改。"
    )
    return has_rule


def _alias_rule() -> bool:
    """同义词表有没有人在按前缀读（前缀改名了这条守卫要一起改）。"""
    has_rule = bool(
        _PROFILE_ALIAS_RULE.search(TEMPLATE_DYNAMIC_CONFIG.read_text(encoding="utf-8"))
    )
    assert has_rule, (
        "dynamic_config 里没有找到 `PROFILE_ALIAS_PREFIX` —— "
        "画像字段的同义词表会被判成没人读。前缀改名了就把本守卫一起改。"
    )
    return has_rule


def test_portal_keys_the_frontend_reads_exist_in_the_bundle() -> None:
    """门户页按 key 取的每一条都必须在包里 —— 缺了那一处就是空白。"""
    text = PORTAL_VIEW.read_text(encoding="utf-8")
    wanted = set(re.findall(r"text\(\s*'([a-z0-9_.]+)'", text))
    assert wanted, "没解析到 PortalView 的文案 key —— 守卫会变成空跑"

    missing = sorted(wanted - set(_codes()))
    assert not missing, (
        f"门户页读了这些 key，但 data/registry/copies.json 里没有：{missing}。"
        "门户页刻意不留兜底文案 —— 两份主张是它最不该有的东西，缺 key 就等于缺文案。"
    )
