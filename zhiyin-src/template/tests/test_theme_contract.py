"""外观系统守卫：多条轴，各自的契约、各自的边界。

为什么单独一个文件
------------------
外观是**纯 CSS 覆盖**：它不出现在任何组件的 import 里，也没有编译器看着。
一条轴出问题，症状几乎都是"不报错、只是看着不对"：

1. **漏档**：某条轴的文件少写了一条令牌，那一处在那一档下还是上一档的样子；
2. **越界**：组件风格去写颜色、交互轴去改字号 —— 各自都"能生效"，
   于是七条轴互相顶掉，谁也说不清最后是什么样；
3. **没接线**：文件写了、菜单里没有，或者 `@import` 漏了 —— 点了没反应；
4. **对比度塌了**：手挑的颜色很容易让"说明文字"掉到 3:1 一带；
5. **换肤长出新的写死色值**：写死一处，那一处在别的配色上就永远不对。

**这个文件只做机械可判的事**：解析 `lib/theme.ts` 的 AXES 表与各轴目录里的文件，
逐条比对。它不判断颜色好不好看 —— 那需要人看。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = TEMPLATE_ROOT / "zhiyin-web"
SRC = WEB_ROOT / "src"
STYLES = SRC / "styles"
TOKENS_CSS = STYLES / "tokens.css"
MOTION_CSS = STYLES / "motion.css"
BASE_CSS = STYLES / "base.css"
THEME_TS = SRC / "lib" / "theme.ts"
INDEX_HTML = WEB_ROOT / "index.html"

#: `styles/<目录>/index.css` 里那一行 @import 用的是相对本目录的路径
AXIS_DIRS = {
    "theme": "themes",
    "ui": "ui",
    "feedback": "feedback",
    "type": "type",
    "shape": "shape",
    "skeleton": "skeleton",
    "font": "font",
}

#: 轴在 base.css 里的加载顺序 —— 顺序即胜负（特异性全是 0,1,1），
#: 所以这张表就是"谁压得住谁"的书面约定，改了它要同时改 base.css 与 DESIGN.md。
#: 字体排最后：组件轴的 roomy / mono 也写过 --font-*，用户在"字体"上做的选择应当压过它。
AXIS_IMPORT_ORDER = ("theme", "ui", "feedback", "type", "shape", "skeleton", "font")

#: 只有配色轴有"必须覆盖的契约"（61 条颜色与材质令牌）。
#: 表面 3、文字 4、描边 4、填充 3、强调 6、语义 3、彩铅笔 7 对、玻璃 4、投影 6、
#: 底料 3、遮罩 1、图表 2、手绘辅线 5、光标 3。
THEME_CONTRACT: tuple[str, ...] = (
    "--c-plaster", "--c-paper", "--c-sand-1",
    "--c-ink", "--ink-2", "--ink-3", "--ink-4",
    "--line-1", "--line-2", "--line-3", "--line-4",
    "--fill-subtle", "--fill-hover", "--fill-press",
    "--g-10", "--g-100", "--g-110", "--g-120", "--accent-ink", "--accent-glow",
    "--o-80", "--b-80", "--p-80",
    "--mk-green", "--mk-green-soft", "--mk-purple", "--mk-purple-soft",
    "--mk-orange", "--mk-orange-soft", "--mk-pink", "--mk-pink-soft",
    "--mk-blue", "--mk-blue-soft", "--mk-teal", "--mk-teal-soft",
    "--mk-yellow", "--mk-yellow-soft",
    "--glass-1", "--glass-2", "--glass-solid-1", "--glass-solid-2",
    "--e-1", "--e-2", "--e-3", "--e-4", "--inner-hi", "--accent-shadow",
    "--bg-veil", "--grain-opacity", "--grain-blend",
    "--scrim",
    "--chart-area", "--chart-area-strong",
    "--sketch-halo", "--sketch-ink", "--sketch-ink-2", "--sketch-ink-3", "--sketch-ink-4",
    "--cursor-arrow", "--cursor-dot", "--cursor-pen",
)

#: 组件风格**只许**声明这三类令牌：形（圆角/描边/影）、密度（间距与字号）、字（字体）。
UI_SHAPE_TOKENS = frozenset(
    {
        "--bw", "--card-border",
        "--r-xs", "--r-sm", "--r-md", "--r-lg", "--r-pill",
        "--r-sketch-sm", "--r-sketch-md", "--r-sketch-lg",
        "--e-1", "--e-2", "--e-3", "--e-4", "--inner-hi",
        # 画布网格的缝：块的"外距"。它和 --s*（卡内距）是两套账，
        # 而"紧凑/舒展"要真的改版面，就必须能同时动这两套。
        "--canvas-gap",
    }
)
UI_TYPE_TOKENS = frozenset(
    {
        "--font-sans", "--font-cjk", "--font-display", "--font-mono",
        "--font-editorial", "--font-hand",
        "--t-h1", "--t-h2", "--t-h3", "--t-h4",
        "--t-body", "--t-sm", "--t-xs", "--t-label",
        "--lh-tight", "--lh-snug", "--lh-body", "--track-h",
    }
)
UI_SPACE_TOKENS = frozenset(f"--s{i}" for i in range(1, 11))
UI_ALLOWED_TOKENS = UI_SHAPE_TOKENS | UI_TYPE_TOKENS | UI_SPACE_TOKENS

#: 字体轴的预算：全站字体的唯一出口（base.css 里 body / h1-h4 / .mono / .editorial 各吃一个）。
#: 它和组件轴都动 --font-*（roomy 用 Fraunces、mono 用等宽），两条轴重叠时**字体轴说了算** ——
#: 加载顺序在 AXIS_IMPORT_ORDER 里钉着（字体排在组件之后）。
FONT_FACE_TOKENS = frozenset(
    {
        "--font-sans", "--font-cjk", "--font-cjk-serif",
        "--font-display", "--font-mono", "--font-editorial",
        "--font-hand", "--font-var",
    }
)

#: 每条轴**允许声明**的自定义属性。空集 = 这一层只许写规则、一个属性都不许声明。
#: 这是七条轴不互相顶掉的全部机制：配色管色、组件管形/密度/字、四条轴只写规则，
#: 字体轴只写字族。
AXIS_DECLARATIONS: dict[str, frozenset[str]] = {
    "ui": UI_ALLOWED_TOKENS,
    "feedback": frozenset(),
    "type": frozenset(),
    "shape": frozenset(),
    "skeleton": frozenset(),
    "font": FONT_FACE_TOKENS,
}

#: 对比度口径：正文与"真的当文字用"的令牌对纸面 ≥4.5:1。
#: `--warn` 与 `--mk-yellow` 按默认皮肤自己的现状取 4.4（它们是 4.42 / 4.46）。
CONTRAST_MIN = 4.5
CONTRAST_MIN_LEGACY = 4.4
LEGACY_LOW = {"--warn", "--mk-yellow"}

#: 参与对比度检查的（前景, 背景）对，都是**真的当文字用**的令牌。
CONTRAST_PAIRS: tuple[tuple[str, str], ...] = (
    ("--ink-1", "--n-1"),
    ("--ink-2", "--n-1"),
    ("--ink-3", "--n-1"),
    ("--warn", "--n-1"),
    ("--fact", "--n-1"),
    ("--violet", "--n-1"),
    ("--mk-green", "--n-1"),
    ("--mk-purple", "--n-1"),
    ("--mk-orange", "--n-1"),
    ("--mk-pink", "--n-1"),
    ("--mk-blue", "--n-1"),
    ("--mk-teal", "--n-1"),
    ("--mk-yellow", "--n-1"),
    ("--accent", "--n-1"),
    ("--accent-ink", "--accent"),
    ("--accent", "--accent-soft"),
    ("--mk-green", "--accent-soft"),
    ("--mk-purple", "--mk-purple-soft"),
)

#: 允许直接写颜色字面量的文件：令牌表与各条轴的目录。
#: 轴目录放行是因为它们要写**影**（`rgba(0, 0, 0, 0.18)` 这种黑）与调色板定义 ——
#: 影是"形"不是"色"，黑在浅底暗底上都成立。
#: 口子由下面 `test_axis_literals_are_shadows_only` 收紧：只有黑白灰能写。
_MASK_LITERALS = {"#000", "#fff", "#000000", "#ffffff"}

#: 非配色轴里允许出现的颜色字面量：只有影的黑白灰。
_SHADOW_TINT = re.compile(
    r"^(?:#(?:0{3,8}|f{3,8})|rgba?\(\s*(?:0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\b)"
)

#: 上游原件：默认值保持与上游一致，调用方显式传色，所以不参与"不许写死色值"那条。
LITERAL_EXEMPT_FILES = {
    "components/vendor/vuebits/ClickSpark.vue": "vue-bits 原件：默认值保持与上游一致，调用方（门户）显式传色",
    "components/vendor/vuebits/MagnetLines.vue": "vue-bits 原件：默认值保持与上游一致，调用方（InkField）显式传色",
}

_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)")
_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
#: `@keyframes 名字 { … }` 整块 —— 它没有选择器，里面是 from/to/百分比
_KEYFRAMES = re.compile(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\}\s*)*[^{}]*\}")
_STYLE_BLOCK = re.compile(r"<style[^>]*>([\s\S]*?)</style>")
_ROOT_BLOCK = re.compile(r":root\s*\{([^}]*)\}", re.S)
_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
_OPTION_ID = re.compile(r"\{\s*id:\s*'([a-z0-9-]+)'")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block_after(text: str, start: int) -> str:
    """从 `start`（指向 `{`）取到配对的 `}`。"""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    raise AssertionError("CSS 花括号没有配对")


def _declarations(block: str) -> dict[str, str]:
    block = _COMMENT.sub(" ", block)
    return {name: value.strip() for name, value in _DECL.findall(block)}


def _root_tokens(path: Path) -> dict[str, str]:
    text = _COMMENT.sub(" ", _read(path))
    match = _ROOT_BLOCK.search(text)
    assert match, f"{path.name} 里没有解析到 :root 块 —— 守卫会变成空跑"
    return _declarations(match.group(1))


def _root_selector(axis: str) -> re.Pattern[str]:
    """某一层"根块"的选择器：`html[data-<轴>="<档>"] {`（紧跟花括号，不含后代组合符）。"""
    return re.compile(rf"""html\[data-{axis}=["']([a-z0-9-]+)["']\]\s*\{{""")


# --------------------------------------------------------------------------
# 0. 解析注册表（lib/theme.ts 的 AXES）
# --------------------------------------------------------------------------


def _array_block(text: str, const_name: str) -> str:
    """取出 `export const <名>… = [ … ]` 那一段（按方括号配对）。"""
    at = text.index(f"const {const_name}")
    # 从"= "之后找方括号：`const AXES: Axis[] = [` 里类型那对空括号在前，
    # 直接找第一个 '[' 会取到类型，返回一个空数组。
    start = text.index("[", text.index("=", at))
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"{const_name} 的数组没有闭合")


def _axis_entries() -> dict[str, str]:
    """`{轴 id: 它在 AXES 里的那段原文}` —— 需要看某条轴写了什么（例如 swatch）时用它。

    解析的是我自己写的、格式稳定的 AXES 表；解析不出东西就报错 ——
    守卫退回空集比报错更坏（它会"看起来在跑、其实什么都没比"）。
    """
    block = _array_block(_read(THEME_TS), "AXES")
    starts = [m.start() for m in re.finditer(r"\{\s*\n\s*id: '[a-z0-9-]+',", block)]
    assert len(starts) >= len(AXIS_IMPORT_ORDER), (
        f"AXES 里只解析到 {len(starts)} 条轴 —— 守卫会变成空跑"
    )

    entries: dict[str, str] = {}
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(block)
        entry = block[start:end]
        match = re.search(r"id: '([a-z0-9-]+)'", entry)
        assert match, "AXES 里有一条没有 id"
        entries[match.group(1)] = entry
    return entries


def _axes() -> dict[str, list[str]]:
    """`{轴 id: [档 id, …]}`，顺序即注册表顺序（第 0 项是默认档）。"""
    axes: dict[str, list[str]] = {}
    for axis_id, entry in _axis_entries().items():
        options_at = entry.index("options: [")
        options = _OPTION_ID.findall(entry[options_at:])
        assert len(options) >= 2, f"轴 {axis_id} 的 options 少于两档"
        axes[axis_id] = options

    assert set(axes) == set(AXIS_IMPORT_ORDER), (
        f"AXES 里的轴与 base.css 的加载顺序对不上：\n"
        f"  注册表：{sorted(axes)}\n  预期：{sorted(AXIS_IMPORT_ORDER)}"
    )
    return axes


def _axis_files(axis: str) -> dict[str, Path]:
    directory = STYLES / AXIS_DIRS[axis]
    return {p.stem: p for p in sorted(directory.glob("*.css")) if p.name != "index.css"}


def _axis_index_imports(axis: str) -> set[str]:
    return set(
        re.findall(
            r"""@import\s+["']\./([a-z0-9-]+)\.css["']""",
            _read(STYLES / AXIS_DIRS[axis] / "index.css"),
        )
    )


def _axis_tokens(path: Path, axis: str) -> dict[str, str]:
    """取一个档位文件的根块声明；顺带守住"选择器 id 必须等于文件名"。

    四种轴（交互/排版/形状/骨架）是**纯规则**、一个自定义属性都不声明 ——
    它们的档位文件里不该有根块，这里返回空字典，让"越界声明"那条测试自然成立。
    """
    text = _COMMENT.sub(" ", _read(path))
    selectors = list(_root_selector(axis).finditer(text))
    if not selectors:
        budget = AXIS_DECLARATIONS.get(axis)
        assert budget == frozenset(), (
            f"{path.name} 里没有解析到 html[data-{axis}] 根块 —— "
            f"轴 {axis} 要覆盖令牌，必须有一个根块（否则它什么都没声明）"
        )
        return {}

    ids = {match.group(1) for match in selectors}
    assert len(selectors) == 1, (
        f"{path.name} 里有 {len(selectors)} 个 html[data-{axis}] 选择器：一档只该有一个根块，两个块会互相盖"
    )
    assert ids == {path.stem}, (
        f"{path.name} 的选择器是 data-{axis}=\"{sorted(ids)[0]}\"，与文件名对不上 —— "
        f"应当写成 html[data-{axis}=\"{path.stem}\"]，否则这个文件永远不会生效"
    )
    return _declarations(_block_after(text, selectors[0].end() - 1))


def _all_axis_options() -> list[tuple[str, str]]:
    return [(axis, option) for axis, options in _axes().items() for option in options[1:]]


# --------------------------------------------------------------------------
# 1. 接线：注册表 ↔ 文件 ↔ @import ↔ 首屏脚本 ↔ 加载顺序
# --------------------------------------------------------------------------


@pytest.mark.parametrize("axis", AXIS_IMPORT_ORDER)
def test_axis_is_wired(axis: str) -> None:
    """一条轴要"能选、能生效"，必须在五处同时存在：注册表、文件、@import、首屏、加载顺序。

    漏一处的症状分别是：菜单里没有（选了没得选）、点了没反应（样式没加载）、
    首屏闪一下（属性到挂载才写）、以及"被别的轴盖掉"（顺序不对）。
    这五处分散在五个文件里，只有机械比对才靠得住。
    """
    options = _axes()[axis]
    default, others = options[0], options[1:]
    files = _axis_files(axis)
    imported = _axis_index_imports(axis)

    assert set(files) == set(others), (
        f"{AXIS_DIRS[axis]}/ 里的文件与 AXES 里的档对不上：\n"
        f"  只有文件：{sorted(set(files) - set(others))}\n  只有注册项：{sorted(set(others) - set(files))}"
    )
    assert imported == set(others), (
        f"{AXIS_DIRS[axis]}/index.css 的 @import 与文件对不上：\n"
        f"  没被 import：{sorted(set(files) - imported)}\n  import 了不存在的东西：{sorted(imported - set(files))}"
    )
    assert default not in files, (
        f"轴 {axis} 的默认档 {default} 不该有文件 —— 默认值就是 tokens.css / base.css 里今天的样子，"
        "多一份文件就多一份「默认到底在哪」的歧义"
    )

    # 首屏脚本里那张 AX 表必须与注册表一致（不一致只是"某条轴首屏闪一下"，无声无息）
    match = re.search(r"var AX = (\{[^}]*\})", _read(INDEX_HTML))
    assert match, "index.html 里没解析到首屏那张 AX 表 —— 守卫会变成空跑"
    inline = json_loads_relaxed(match.group(1))
    assert inline == {a: _axes()[a][0] for a in AXIS_IMPORT_ORDER}, (
        "index.html 的首屏 AX 表与 lib/theme.ts 的 AXES 对不上：\n"
        f"  首屏：{inline}\n  注册表：{ {a: _axes()[a][0] for a in AXIS_IMPORT_ORDER} }"
    )

    # base.css 的加载顺序 = 书面约定（顺序即胜负）
    base = _read(BASE_CSS)
    positions = []
    for name in AXIS_IMPORT_ORDER:
        needle = f'./{AXIS_DIRS[name]}/index.css'
        assert needle in base, f"base.css 里没有 import {needle}"
        positions.append(base.index(needle))
    assert positions == sorted(positions), (
        "base.css 里各轴的加载顺序不对：顺序即胜负（特异性全是 0,1,1），"
        f"约定顺序是 {list(AXIS_IMPORT_ORDER)}"
    )


def json_loads_relaxed(raw: str) -> dict[str, str]:
    """把首屏脚本里那张表解析出来（它是 JSON，键值都是双引号）。"""
    import json

    return json.loads(raw)


# --------------------------------------------------------------------------
# 2. 各条轴的契约与边界
# --------------------------------------------------------------------------


@pytest.mark.parametrize("axis,option", _all_axis_options(), ids=lambda v: str(v))
def test_axis_declares_only_its_own_tokens(axis: str, option: str) -> None:
    """每条轴只许声明自己那一类令牌 —— 这是七条轴不互相顶掉的全部机制。

    越界的后果不是"难看"，而是**两条轴开始抢同一个变量**：交互轴写了一个颜色，
    换配色时那一处就不跟了；组件轴写了字体，排版轴的字号就白设了。
    症状永远是"某一处没跟着变"，而且没有任何报错。
    """
    path = _axis_files(axis)[option]
    declared = _axis_tokens(path, axis)
    known = set(_root_tokens(TOKENS_CSS)) | set(_root_tokens(MOTION_CSS))

    if axis == "theme":
        missing = sorted(set(THEME_CONTRACT) - set(declared))
        assert not missing, (
            f"{path.name} 少了这些令牌：\n  " + "\n  ".join(missing)
            + "\n这一档配色下，用到它们的地方会继续用上一套的值。"
        )
    else:
        budget = AXIS_DECLARATIONS[axis]
        over = sorted(set(declared) - budget)
        assert not over, (
            f"{path.name} 声明了本条轴预算之外的令牌：{over}\n"
            f"  轴 {axis} 只允许声明：{sorted(budget) or '（一个都不许）'}"
        )

    unknown = sorted(set(declared) - known)
    assert not unknown, (
        f"{path.name} 声明了 tokens.css / motion.css 里没有的令牌：{unknown}。"
        "多半是拼错了名字（拼错等于没写：CSS 变量不会报错，只会静默失效）。"
    )


@pytest.mark.parametrize("axis,option", _all_axis_options(), ids=lambda v: str(v))
def test_axis_styles_nothing_outside_its_own_attribute(axis: str, option: str) -> None:
    """每条轴的文件里，规则的选择器都必须挂在它自己的属性下。

    这条守的是**默认外观不被别人改**：轴文件是全局样式表，一条漏了前缀的
    `.btn { … }` 会同时改掉默认档与其它所有档 —— 而"其它档长什么样"是它们各自的事。
    """
    path = _axis_files(axis)[option]
    text = _COMMENT.sub(" ", _read(path))
    # 先摘掉 @keyframes 整块：它不是选择器，里面的 from / to 也不是（骨架轴的入场动画在这）。
    text = _KEYFRAMES.sub(" ", text)
    # 再揭开 @media 外壳：悬停必须 gate 在"真的能悬停"的设备上（触屏第一次点按会套上并留住 hover），
    # 所以合法的轴文件多了一层 `@media (hover: hover) and (pointer: fine) { … }`。
    # 不揭开它，外壳会被当成一条"没挂轴属性"的规则 —— 而里面那条恰恰是最该被检查的。
    text = re.sub(r"@media[^{]*\{", " ", text)
    prefix = f'html[data-{axis}="'
    offenders = [
        match.group(1).strip().splitlines()[-1].strip()[:80]
        for match in re.finditer(r"([^{}]+)\{", text)
        if not match.group(1).strip().splitlines()[-1].strip().startswith(prefix)
    ]
    assert not offenders, (
        f"{path.name} 里有不挂在 【{prefix}…】 下的规则：\n  " + "\n  ".join(offenders)
        + "\n轴文件是全局样式，漏了前缀会同时改掉默认档与其它档。"
    )


def _classes_used_in_components() -> set[str]:
    """`.vue` 里真实出现过的类名：模板的 `class="…"` + 组件自己的 `<style>` 里定义过的。

    只看 `.vue`（不看样式表）：因为要拦的正是"只在全局样式表里存在、从没挂到元素上"
    的那种类 —— 拿样式表自己当证据，这条守卫就永远通过。
    """
    names: set[str] = set()
    for path in SRC.rglob("*.vue"):
        text = _read(path)
        for attr in re.findall(r'class="([^"]*)"', text):
            names |= {token for token in re.split(r"\s+", attr) if token}
        for block in _STYLE_BLOCK.findall(text):
            names |= set(re.findall(r"\.([a-zA-Z][\w-]*)", block))
    assert names, "没有从 .vue 里解析到任何类名 —— 守卫会变成空跑"
    return names


@pytest.mark.parametrize("axis,option", _all_axis_options(), ids=lambda v: str(v))
def test_axis_selectors_name_parts_that_exist(axis: str, option: str) -> None:
    """轴文件里点名的类，必须真的挂在某个元素上。

    这条守的是**"点了没反应"**——2026-10-08 就是这么发现 `.surface` 是一个幽灵零件的：
    base.css 与四条轴都在给它写规则，而模板里从来没有 `class="surface"`。
    于是那些规则一条都不生效，而且**什么都不报**：样式表照常加载、构建照常通过、
    面板照常高亮，只有界面纹丝不动。同一批里还有 `.float-card`、`.overlay`、`.chat`。

    机械判据只有一条：这个名字在 `.vue` 里出现过吗。出现过 = 有元素挂它（或者组件
    自己定义了它）；没出现过 = 这条规则是死的。改动名不报错的坑，只能这样拦。
    """
    path = _axis_files(axis)[option]
    text = _KEYFRAMES.sub(" ", _COMMENT.sub(" ", _read(path)))
    used = _classes_used_in_components()
    dead: list[str] = []
    for selector in re.findall(r"([^{}]+)\{", text):
        for cls in re.findall(r"\.([a-zA-Z][\w-]*)", selector):
            if cls not in used:
                dead.append(f"{cls}（选择器：{' '.join(selector.split())[:64]}）")
    assert not dead, (
        f"{path.name} 点名的这些类在 .vue 里不存在：\n  " + "\n  ".join(sorted(set(dead)))
        + "\n这类规则永远不会生效（构建通过、面板能点、界面不动）。"
        "要么把这个类挂到元素上，要么改点真实存在的零件。"
    )


#: 布局属性：轴文件是"叠在组件之上的全局样式"，写这些等于改别人的骨架
_LAYOUT_PROPS = ("position", "display", "inset", "top", "right", "bottom", "left", "z-index", "float")


def _rules(text: str) -> list[tuple[str, str]]:
    """把样式表拆成 (选择器, 声明块)。先摘掉 @keyframes（它没有选择器）。

    再**揭开 `@media` 外壳**：`@media (hover: hover) and (pointer: fine) { … }` 里的规则
    仍然要按同一把尺子量。这是 2026-10-08 手机端整改时补的 —— 悬停必须 gate 在
    "真的能悬停"的设备上（触屏第一次点按会套上并留住 hover），所以轴文件里合法的
    写法多了一层外壳；不揭开它，外壳会被当成选择器、里面那条规则反而漏检。
    """
    text = _KEYFRAMES.sub(" ", text)
    text = re.sub(r"@media[^{]*\{", " ", text)
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text)
    ]


@pytest.mark.parametrize("axis,option", _all_axis_options(), ids=lambda v: str(v))
def test_axis_files_do_not_reposition_components(axis: str, option: str) -> None:
    """轴文件不许在**真实元素**上写布局属性（伪元素不受限）。

    这一条是踩出来的（2026-10-08）：折角那档为了给 `::after` 定位，在 `.surface` / `.sheet`
    上写了 `position: relative`。而 `html[data-shape="dogear"] .sheet`（0,2,1）压得过外观台
    自己的 `.look[data-v-…]`（0,2,0）—— 面板的 `position: fixed` 被改成了普通流，
    面板掉进文档流，用户点「外观台」再也打不开。

    轴文件是**叠在组件之上的全局样式**：它看得见 `.sheet`，但不知道那个 `.sheet` 是浮层、
    是下拉、还是文档流里的一张纸。改布局就一定会踩到某一个。需要视觉元素时：
    用背景图（折角现在就是这么画的），或者用宿主本来就有的定位
    （`.surface` / `.sheet` 在 base.css 里已经是 `position: relative`）。
    """
    path = _axis_files(axis)[option]
    problems: list[str] = []
    for selector, body in _rules(_COMMENT.sub(" ", _read(path))):
        if "::before" in selector or "::after" in selector or ":before" in selector:
            continue  # 伪元素只影响自己画出来的那一层，不算改骨架
        for name in re.findall(r"(?:^|;)\s*([a-z-]+)\s*:", body):
            if name in _LAYOUT_PROPS:
                problems.append(f"{selector[:50]} → {name}")
    assert not problems, (
        f"{path.name} 在真实元素上写了布局属性：\n  " + "\n  ".join(problems)
        + "\n轴文件改别人的定位/布局会静默改坏别的组件（浮层、下拉都会被推进文档流）。"
        "需要视觉元素请用背景图，或依赖宿主已有的定位。"
    )


@pytest.mark.parametrize("axis,option", _all_axis_options(), ids=lambda v: str(v))
def test_axis_literals_are_shadows_only(axis: str, option: str) -> None:
    """非配色轴唯一允许写死的颜色是**影的黑白**。

    配色轴可以写色值（它就是调色板）；其余六条轴只许写规则，
    需要颜色时引用令牌 —— 一旦写死一个 `#ff0000`，那一处就与配色轴脱钩了。
    影是例外：`rgba(0, 0, 0, 0.2)` 这种黑在浅底暗底上都成立，它表达的是"形"。
    """
    if axis == "theme":
        pytest.skip("配色轴就是调色板，色值写在这里是它的职责")
    path = _axis_files(axis)[option]
    offenders: list[str] = []
    for lineno, line in enumerate(_COMMENT.sub(" ", _read(path)).splitlines(), start=1):
        for literal in _COLOR.findall(line):
            if not _SHADOW_TINT.match(literal):
                offenders.append(f"{path.name}:{lineno}: {literal}")
    assert not offenders, (
        "非配色轴里出现了「影」以外的颜色字面量（色归配色轴管）：\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------
# 3. 配色轴的对比度
# --------------------------------------------------------------------------


def _parse_color(value: str) -> tuple[int, int, int, float]:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
        return red, green, blue, alpha
    match = re.match(r"rgba?\(([^)]+)\)", value)
    assert match, f"看不懂的颜色：{value}"
    parts = [p for p in re.split(r"[,\s/]+", match.group(1)) if p]
    red, green, blue = (int(float(p)) for p in parts[:3])
    alpha = float(parts[3]) if len(parts) > 3 else 1.0
    return red, green, blue, alpha


def _on_top(
    fg: tuple[int, int, int, float], bg: tuple[int, int, int, float]
) -> tuple[int, int, int, float]:
    alpha = fg[3] + bg[3] * (1 - fg[3])
    if alpha == 0:
        return 0, 0, 0, 0
    return tuple(
        round((fg[i] * fg[3] + bg[i] * bg[3] * (1 - fg[3])) / alpha) for i in range(3)
    ) + (alpha,)


def _luminance(color: tuple[int, int, int, float]) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color[0]) + 0.7152 * channel(color[1]) + 0.0722 * channel(color[2])


def _contrast(fg: str, bg: str) -> float:
    background = _parse_color(bg)
    foreground = _on_top(_parse_color(fg), background)
    hi, lo = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _resolved(axis_option: str | None) -> dict[str, str]:
    """把 :root 与某一档配色的声明合成一张表；`None` 就是默认配色。"""
    merged = dict(_root_tokens(TOKENS_CSS))
    if axis_option is not None:
        merged.update(_axis_tokens(_axis_files("theme")[axis_option], "theme"))
    return merged


def _color_of(table: dict[str, str], name: str) -> str:
    """顺着别名链取到一个字面量颜色（`--n-1` → `--c-paper` 这种）。"""
    seen: set[str] = set()
    while True:
        assert name in table, f"{name} 没有定义"
        value = table[name]
        alias = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", value.strip())
        if not alias:
            return value.strip()
        name = alias.group(1)
        assert name not in seen, f"令牌别名成环：{name}"
        seen.add(name)


@pytest.mark.parametrize("option", [None, *_axes()["theme"][1:]])
def test_text_stays_readable(option: str | None) -> None:
    """每一档配色里，"真的当文字用"的那些令牌都要守住对比度。

    这不是审美判断，是"深色配色上说明文字会不会糊掉"的最低线。
    默认配色（None）一起查：它是基准，也是"守卫没有比现状更松"的证明。
    """
    table = _resolved(option)
    label = option or _axes()["theme"][0]
    failures: list[str] = []

    for fg, bg in CONTRAST_PAIRS:
        ratio = _contrast(_color_of(table, fg), _color_of(table, bg))
        need = CONTRAST_MIN_LEGACY if fg in LEGACY_LOW else CONTRAST_MIN
        if ratio < need:
            failures.append(f"{fg} 对 {bg}：{ratio:.2f}:1（要 ≥{need}:1）")

    assert not failures, f"配色 {label} 的对比度不达标：\n  " + "\n  ".join(failures)


# --------------------------------------------------------------------------
# 4. 令牌值本身写坏了也要拦
# --------------------------------------------------------------------------

_HEX = re.compile(r"#[0-9a-fA-F]+")
_RGB_FN = re.compile(r"rgba?\(")


def _value_shape_problems(declared: dict[str, str]) -> list[str]:
    """值写坏了 CSS 会静默忽略（那一处退回默认或 initial）。

    三条机械可判的：括号配平、颜色对颜色、`#` 后位数只许 3/4/6/8。
    """
    roots = _root_tokens(TOKENS_CSS)
    problems: list[str] = []
    for name, value in declared.items():
        if value.count("(") != value.count(")"):
            problems.append(f"{name}: 括号不配平 —— {value[:60]}")
        default = roots.get(name, "")
        is_color = bool(_HEX.match(default) or _RGB_FN.match(default))
        if is_color and not (_HEX.match(value) or _RGB_FN.match(value)):
            problems.append(f"{name}: 默认是颜色，这里却不是 —— {value[:60]}")
        for literal in _HEX.findall(value):
            if len(literal) - 1 not in (3, 4, 6, 8):
                problems.append(f"{name}: 十六进制颜色位数不对 —— {literal}")
    return problems


@pytest.mark.parametrize("axis,option", _all_axis_options(), ids=lambda v: str(v))
def test_axis_values_are_well_formed(axis: str, option: str) -> None:
    """档位文件里写坏的值不会报错，只会静默失效。"""
    path = _axis_files(axis)[option]
    problems = _value_shape_problems(_axis_tokens(path, axis))
    assert not problems, f"{path.name} 里有写坏的值：\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------
# 5. 组件样式里不许再长出新的写死色值
# --------------------------------------------------------------------------


def _is_palette(path: Path) -> bool:
    """允许直接写颜色字面量的文件：令牌表与七条轴的目录。"""
    return path == TOKENS_CSS or path.parent.name in set(AXIS_DIRS.values())


def _style_sources() -> list[tuple[Path, str]]:
    """样式来源：所有 .css（调色板除外）+ 每个 .vue 的 <style> 块。

    只看样式：组件里的颜色字面量出现在 script/template 时，要么是掩码（与主题无关），
    要么是"从令牌读、读不到时的兜底值"（那正是我们想要的写法），都不该被误伤。
    """
    sources: list[tuple[Path, str]] = []
    for path in sorted(SRC.rglob("*")):
        if path.suffix == ".css":
            if _is_palette(path):
                continue
            sources.append((path, _COMMENT.sub(" ", _read(path))))
        elif path.suffix == ".vue":
            for block in _STYLE_BLOCK.findall(_read(path)):
                sources.append((path, _COMMENT.sub(" ", block)))
    assert sources, "没找到任何样式来源 —— 守卫会变成空跑"
    return sources


def test_styles_carry_no_raw_colors() -> None:
    """除各条轴的目录外，组件样式里不许出现颜色字面量。

    写死一处的代价不是"这一处不好看"，而是**它在别的配色上永远不对**：
    换到暗色配色时，那一块要么是白斑，要么比周围脏一点，而且没有任何报错。
    所以这条要一直钉着 —— 新加样式时顺手用令牌，比事后满仓找色值便宜得多。
    """
    hits: list[str] = []
    for path, text in _style_sources():
        rel = path.relative_to(SRC).as_posix()
        if rel in LITERAL_EXEMPT_FILES:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            literals = _COLOR.findall(line)
            # 掩码里的黑/白只看 alpha，与配色无关 —— 但只豁免这两种字面量，
            # 不是"这一行有 mask 就整行免检"（那样 mask 旁边新写的色值会被一起放过）
            if "mask" in line.lower() and all(lit in _MASK_LITERALS for lit in literals):
                continue
            for literal in literals:
                hits.append(f"{rel}:{lineno}: {literal} —— {line.strip()[:90]}")

    assert not hits, (
        "样式里出现了颜色字面量（请改用令牌，或把新令牌加进 tokens.css 与各条轴）：\n  "
        + "\n  ".join(hits[:20])
        + ("\n  …" if len(hits) > 20 else "")
    )


# --------------------------------------------------------------------------
# 6. 外观台：配得出来（每一格都有预览）与够得着（每页都有入口）
# --------------------------------------------------------------------------

LOOK_PANEL = SRC / "components" / "theme" / "LookPanel.vue"
LOOK_TRIGGER = SRC / "components" / "theme" / "LookTrigger.vue"
APP_VUE = SRC / "App.vue"

#: 「外观台」三个字必须出现在这三页上 —— 少一页，那一页就配不了外观
PAGES_WITH_TRIGGER = ("views/ConsoleView.vue", "views/ReportView.vue", "views/PortalView.vue")


def _panel_glyph_keys() -> set[str]:
    match = re.search(
        r"const GLYPHS: Record<string, Glyph\[\]> = \{(.*?)\n\}", _read(LOOK_PANEL), re.S
    )
    assert match, "LookPanel.vue 里没解析到 GLYPHS 表 —— 守卫会变成空跑"
    return set(re.findall(r"'([a-z]+:[a-z0-9-]+)':", match.group(1)))


def test_panel_has_a_preview_for_every_option() -> None:
    """矩阵里每一格都要有一张小图。

    少一张的症状是**那一格空着**：面板照常打开、也点得动，只是那颗格子看着像坏了 ——
    没有任何报错。配色行走三格色卡、组件行走 CSS 画的形，其余五条轴走 GLYPHS 路径表。
    """
    axes = _axes()
    # 默认档也要预览：矩阵把**每一档**都画出来（默认档只是没有文件，不是没有格子）
    # 配色走色卡、组件走 CSS 画的形、字体走真字，这三条轴不查 GLYPHS 路径表。
    need = {
        f"{axis}:{o}"
        for axis, options in axes.items()
        if axis not in ("theme", "ui", "font")
        for o in options
    }
    have = _panel_glyph_keys()
    missing = sorted(need - have)
    assert not missing, f"面板里缺这些档的小图：{missing}（那些格子会是空的）"
    stale = sorted(k for k in have - need if k.split(":")[0] not in ("theme", "ui", "font"))
    assert not stale, f"面板里有指向不存在档位的小图：{stale}"

    # 字体轴：面板里那张 FACES 表必须与本轴的档一一对应（缺一条预览就是空字）
    faces = re.search(r"const FACES: Record<string, string> = \{(.*?)\n\}", _read(LOOK_PANEL), re.S)
    assert faces, "LookPanel.vue 里没解析到 FACES 表 —— 字体那一行会没有预览"
    face_keys = set(re.findall(r"(?:^|\n)\s*'?([a-z-]+)'?\s*:", faces.group(1)))
    assert face_keys == set(axes["font"]), (
        "面板 FACES 表与字体轴的档对不上（缺的档在矩阵里显示不出字面）：\n"
        f"  面板：{sorted(face_keys)}\n  注册表：{sorted(axes['font'])}"
    )

    ui_options = axes["ui"]
    panel = _read(LOOK_PANEL)
    miss_shape = [o for o in ui_options if f".g--{o}" not in panel]
    assert not miss_shape, f"面板里缺组件的形预览类：{miss_shape}"

    theme_entry = _axis_entries()["theme"]
    assert theme_entry.count("swatch:") == len(axes["theme"]), (
        "配色每一档都要给三格色卡（swatch）—— 缺一档，矩阵里那一格就是空的"
    )


#: `--ink-4` 在四套配色里实测只有 2.50–3.14:1 —— 它是一条"装饰线的浓淡"，
#: tokens.css 自己写着"只做装饰，不承载信息"。这张白名单把允许用它当文字色的地方**冻住**：
#: 只留纯装饰零件（抓手、箭头、空槽占位）。新增一处就失败，因为它的症状是
#: "某段小字在某一套配色下看不清"，而没有任何报错。
#: （2026-10-08 按 Assessment B 的实测改了 11 处承载信息的用法，见 commit 说明。）
_INK4_DECORATIVE = {
    "Bubble.vue": {".bubble__grip"},
    "MarketBubble.vue": {".chain__arrow"},
    "PortraitBubble.vue": {".slots__d"},
    "PortraitOverlay.vue": {".mrow__go"},
    "PortraitFieldList.vue": {".row__go"},
}

_INK4_AS_TEXT = re.compile(r"color:\s*var\(--ink-4\)|color:\s*var\([a-z0-9-]+,\s*var\(--ink-4\)\)")


def _enclosing_selector(text: str, pos: int) -> str:
    """取某条声明所属的选择器（往回收缩到上一个 } 或 { 之后）。"""
    brace = text.rfind("{", 0, pos)
    if brace == -1:
        return "?"
    start = max(text.rfind("}", 0, brace), text.rfind("{", 0, brace - 1))
    return " ".join(text[start + 1 : brace].split())


def test_ink4_stays_decorative() -> None:
    """装饰色不许承载信息。

    `--ink-4` 是这套体系里最淡的一档（实测 2.50–3.14:1）。它画分隔线、箭头、空槽占位是对的；
    一旦拿去写"日期数字 / 面包屑 / 字段名 / 图表标题"这种要读的字，就是一条静默的无障碍欠账 ——
    四套配色里没有一套能让它达标，而页面不会有任何报错。
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.vue")):
        allowed = _INK4_DECORATIVE.get(path.name, set())
        for block in _STYLE_BLOCK.findall(_read(path)):
            text = _COMMENT.sub(" ", block)
            for match in _INK4_AS_TEXT.finditer(text):
                selector = _enclosing_selector(text, match.start())
                if selector not in allowed:
                    offenders.append(f"{path.name}: {selector}")

    assert not offenders, (
        "这些地方把装饰色 --ink-4 当成文字色用了（它只有 2.5–3.1:1）：\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\n改用 --ink-3（四套配色都 ≥5.6:1）。若确实是纯装饰（箭头/抓手/占位），"
        "把它加进 _INK4_DECORATIVE 并写清理由。"
    )


def test_look_panel_is_mounted_and_reachable_from_every_page() -> None:
    """面板要挂着，入口要三页都在，而且面板必须挂到 body 上。

    三条都是"配不出来"的成因，而且都不报错：
      · 面板没挂 → 点三个字什么都没发生；
      · 某页没入口 → 那一页配不了（门户与报告恰恰是最常拿给人看的两页）；
      · 没 Teleport → 控制台那条 chrome 会整块滑动（带 transform），面板会被裁掉一角。
    """
    assert "<LookPanel" in _read(APP_VUE), "App.vue 没有挂外观台的面板 —— 三页都开不出来"
    assert 'Teleport to="body"' in _read(LOOK_PANEL), (
        "面板必须 Teleport 到 body：控制台左上角那条 chrome 会整块滑动（带 transform），"
        "留在里面会被裁掉一角。"
    )
    missing = [rel for rel in PAGES_WITH_TRIGGER if "<LookTrigger" not in _read(SRC / rel)]
    assert not missing, f"这些页面没有「外观台」入口：{missing}（那一页就配不了外观）"


def test_trigger_is_excluded_from_the_outside_click_guard() -> None:
    """面板"点外面就关"要排掉触发按钮 —— 靠的是两边都写同一个类名 `.look-trigger`。

    改一边不改另一边，症状是**点那三个字没反应**：pointerdown 判定成"点在面板外面"，
    紧接着把刚打开的面板关掉 —— 看起来完全没开。跨文件的同一个字符串，只能这样钉住。
    """
    trigger, panel = _read(LOOK_TRIGGER), _read(LOOK_PANEL)
    assert "look-trigger" in trigger, "LookTrigger.vue 的按钮上没有 look-trigger 类"
    assert "closest('.look-trigger')" in panel, (
        "LookPanel 的「点击外部就关」判定里没有排掉 `.look-trigger` —— "
        "点那三个字会变成「开了又立刻关上」"
    )


_GROUP_ENTRY = re.compile(r"\{\s*name:\s*'([^']+)',\s*axes:\s*\[([^\]]*)\]\s*\}")


def test_axis_groups_cover_every_axis_in_order() -> None:
    """分组表必须**恰好覆盖每条轴一次**，且每条轴在组内的先后跟随注册表。

    这条比它看起来重要：面板按它分段，一旦有轴没被收进任何一组，那一行会从外观台上
    整条消失（用户会以为这个能力没了）；列了两次则会出现两行同一条轴 —— 两种情况
    都不报错，只是安静地画错。

    **不要求摊平后与 AXES 顺序一致**：分组本来就会重排（"形状"并进"形与密度"、
    "字体"并进"字号字体"），那是分组的意义。要钉的是覆盖与组内次序。
    """
    block = _array_block(_read(THEME_TS), "AXIS_GROUPS")
    listed = _GROUP_ENTRY.findall(block)
    assert listed, "AXIS_GROUPS 没解析出来 —— 守卫会空跑"
    groups = [
        (name, [axis.strip().strip("'") for axis in axes.split(",") if axis.strip()])
        for name, axes in listed
    ]
    flat = [axis for _, axes in groups for axis in axes]
    assert sorted(flat) == sorted(_axes()), (
        "分组表与 AXES 覆盖不上（少列或重复）：\n"
        f"  分组表：{sorted(flat)}\n  注册表：{sorted(_axes())}"
    )
    assert len(set(flat)) == len(flat), f"有轴被列进多个分组：{flat}"
    names = [name for name, _ in groups]
    assert len(set(names)) == len(names), f"分组重名：{names}"
    # 组内先后跟随注册表：主次由 AXES 决定，不由分组的写法决定
    order = {axis: index for index, axis in enumerate(_axes())}
    for name, axes in groups:
        assert axes == sorted(axes, key=lambda axis: order[axis]), (
            f"「{name}」组内的轴与注册表顺序不一致：{axes}"
        )
