"""画布上"哪些块、什么顺序" —— issue #22/#25 的三条不变式。

用户报的是"卡片过多、布局杂乱、找不到重点"，以及"这块收不起来"。
对应的实现分三处：块名单（`lib/blocks.ts`）、画布的核心区上限与可见性
（`ConsoleView.vue`）、以及管理入口与持久化（`stores/session.ts` + `BlocksOverlay.vue`）。
这三处任何一处单独改动都会让症状复活，所以一起钉。
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1]
WEB = TEMPLATE / "zhiyin-web" / "src"
BLOCKS = WEB / "lib" / "blocks.ts"
CONSOLE = WEB / "views" / "ConsoleView.vue"
SESSION = WEB / "stores" / "session.ts"
PANEL = WEB / "components" / "console" / "BlocksOverlay.vue"
APP = WEB / "App.vue"


def test_every_block_has_a_human_label() -> None:
    """名单里每一块都要有中文名。

    漏一个的后果很具体：画布上照常有它，而「全部组件」里显示成 `timetable` 这种
    id —— 用户不知道那是什么，也就不会去收它。
    """
    source = BLOCKS.read_text(encoding="utf-8")
    order = re.search(r"BLOCK_ORDER: string\[\] = \[(.*?)\]", source, re.S)
    labels = re.search(r"BLOCK_LABELS: Record<string, string> = \{(.*?)\n\}", source, re.S)
    assert order and labels, "lib/blocks.ts 的名单或名字表解析不出来 —— 守卫会空跑"
    ids = re.findall(r"'([a-z_]+)'", order.group(1))
    named = re.findall(r"^\s*([a-z_]+):", labels.group(1), re.M)
    assert ids, "BLOCK_ORDER 里没解析到 id"
    missing = [i for i in ids if i not in named]
    assert not missing, f"这些块没有中文名（会以英文 id 出现在「全部组件」里）：{missing}"


def test_the_block_list_has_one_source_of_truth() -> None:
    """块名单只有一份：画布与「全部组件」面板都从 `lib/blocks` 读。

    各写一份的下场是"面板里少一块"或"同一个块两处叫不同名字"——
    两种都不会报错，只会安静地画错。
    """
    console = CONSOLE.read_text(encoding="utf-8")
    assert "from '@/lib/blocks'" in console, "画布没有从 lib/blocks 读名单"
    assert "const BLOCK_ORDER" not in console, "画布里又长出了一份 BLOCK_ORDER"
    assert "const BLOCK_LABELS" not in console, "画布里又长出了一份 BLOCK_LABELS"
    panel = PANEL.read_text(encoding="utf-8")
    assert "from '@/lib/blocks'" in panel, "「全部组件」面板没有从 lib/blocks 读名单"


def test_canvas_caps_the_default_set() -> None:
    """没被用户管过时只铺核心区 —— 这是 #22/#25"卡片过多"的直接解药。

    两件事都要在：
      · 上限作用在 **`visible`（渲染）** 这一层，不能只挡分格 ——
        只挡分格的话那块照样画出来、只是掉进 `tileStyle` 的兜底格位
        （真机验证时正是这个症状：一屏 9 块，第 9 块没有格位）；
      · 上限**只在用户动手之前**生效：他刚排好的布局不该被一句规则改掉。
    """
    console = CONSOLE.read_text(encoding="utf-8")
    assert "CORE_COUNT" in console, "核心区上限被删了（一屏又会铺满十几块）"
    caps = console[console.index("const capsAway") :][:700]
    assert "shown.slice(CORE_COUNT)" in caps, "上限没有作用在候选清单上"
    assert "session.blocksHidden.length > 0 || session.blocksOrder.length > 0" in caps, (
        "上限的生效条件变了：它必须在用户没自己收过/排过时才生效"
    )
    visible = console[console.index("const visible = (id: string)") :][:260]
    assert "capsAway.value.has(id)" in visible, (
        "上限没有挡在渲染这一层（visible）—— 那块会画出来但没有格位"
    )


def test_every_block_render_goes_through_visible() -> None:
    """模板里每一块的 `v-if` 都要经过 `visible()`。

    课表与匹配这两块的 `v-if` 曾经直接写数据条件（`showTimetable` / `session.chsiBound`），
    于是"收起"和核心区上限对它们完全无效：用户收不掉它，它还会以兜底格位画出来。
    """
    console = CONSOLE.read_text(encoding="utf-8")
    for block, cond in (("timetable", "showTimetable"), ("match", "session.chsiBound")):
        assert f"{cond} && visible('{block}')" in console, (
            f"{block} 的 v-if 没有经过 visible()：收起与核心区上限对它无效"
        )


def test_hidden_and_order_persist_locally() -> None:
    """收起与排序要**记住**（刷新、重开浏览器还在）。

    只存在内存里的版本用户已经受够了：拖完一刷新回原样，等于白拖；
    "收起"过一会儿自己回来，用户只会以为没生效。
    """
    source = SESSION.read_text(encoding="utf-8")
    assert "'zhiyin_blocks_hidden'" in source and "'zhiyin_blocks_order'" in source
    assert "localStorage.setItem(key, JSON.stringify(value))" in source
    for action in ("hideBlockForGood(", "showBlock(", "showAllBlocks(", "setBlocksOrder("):
        assert action in source, f"缺少动作 {action}"
    # 读坏了不能白屏：取不到就当空
    assert "return []" in source


def test_the_management_entry_reaches_every_block() -> None:
    """管理入口要能到每一块，而且**不是**只藏在右键菜单里。

    以前只有右键菜单（`叫出「X」`），而没有人会去右键空白处 —— 等于没有入口。
    """
    assert "overlay === 'blocks'" in APP.read_text(encoding="utf-8"), "「全部组件」面板没挂上"
    console = CONSOLE.read_text(encoding="utf-8")
    assert "session.openOverlay('blocks')" in console, "画布上没有打开「全部组件」的入口"
    assert "全部组件" in console, "入口没有可见的文字（只在右键菜单里等于没有）"
    panel = PANEL.read_text(encoding="utf-8")
    assert "hideBlockForGood" in panel and "showBlock" in panel and "setBlocksOrder" in panel
