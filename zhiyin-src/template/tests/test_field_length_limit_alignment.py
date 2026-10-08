"""画像字段值长度上限的前后端守卫（跨语言常量，只有断言能钉住）。

现象
----
真正拒超长的是后端 `DefaultProfileService.MAX_FIELD_VALUE_CHARS = 40`
（`services/profile.py`，用户更正走它）。前端 `PortraitFieldList.vue` 里另写了
一个 `const MAX_CHARS = 40`，只用来显示输入框旁边那个"30/40"的计数。
两个数字之间没有任何编译期联系 —— 改一边，另一边不会报错，症状全落在用户身上：

    · 前端写 30、后端还是 40：他打到 41 个字才被拒，而计数早在 30 就变红了，
      "还能打"和"会被拒"两句话同时出现在一屏里；
    · 前端写 40、后端放宽到 60：他明明还能写，界面却提前拦住（那是"静默截断"
      的软版本，同样让他以为自己写的后半句被记住了）。

这条守卫把两个数字钉在一起：后端 import 常量，前端源码里正则解析字面量。
**只加测试，不改前端文件**（前端由 Lead 在改，动它会撞车）——
所以这里对前端的要求只有一个：那个数字得是一个**可解析的字面量**，
也就是现在这句 `const MAX_CHARS = 40`。将来它若改成"从接口读"或"拼出来的"，
守卫会红，那时的最小改法是留一行字面量常量（`const MAX_CHARS = <数字>`）
作为声明，其余地方引用它。

前端的注释里写明了它与后端的对应关系（`PortraitFieldList.vue` 里
「与后端 DefaultProfileService.MAX_FIELD_VALUE_CHARS 对齐（40）」）——
注释能解释为什么，但拦不住漂移；拦得住的是下面这条断言。
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_FIELD_LIST = (
    TEMPLATE_ROOT / "zhiyin-web" / "src" / "components" / "portrait" / "PortraitFieldList.vue"
)

#: 前端那处常量的声明形状（`const MAX_CHARS = 40`）。
#: 只认这一种写法：数字必须是字面量，才可能被解析出来与后端比。
#: 它同时是给下一个人的**契约**：改这行的时候别把它变成算出来的值。
_FRONTEND_MAX_CHARS = re.compile(r"const\s+MAX_CHARS\s*=\s*(\d+)")


def _frontend_max_chars() -> int:
    """从前端源码里解析出那个字数上限。

    解析不到就抛错而不是返回默认值 —— 否则守卫会"看起来在跑、其实什么都没比"
    （同 `test_frontend_alignment.py::_frontend_error_codes` 的口径）。
    """
    assert FRONTEND_FIELD_LIST.is_file(), f"前端文件不在了：{FRONTEND_FIELD_LIST}"
    text = FRONTEND_FIELD_LIST.read_text(encoding="utf-8")
    found = _FRONTEND_MAX_CHARS.findall(text)
    assert found, (
        "前端 PortraitFieldList.vue 里没有解析到 `const MAX_CHARS = <数字>` —— "
        "守卫会变成空跑。请把上限写成一个字面量常量（其余地方引用它），"
        "别改成从接口读或拼出来的值。"
    )
    assert len(set(found)) == 1, f"前端声明了不止一个 MAX_CHARS：{sorted(set(found))}"
    return int(found[0])


def test_the_field_length_limit_is_the_same_on_both_sides() -> None:
    """后端拒超长的那个数字，必须与前端给用户看的那个数字相等。

    两边用途不同（后端**拒**、前端**只提示**），但用户读到的是同一句话：
    "最多 40 个字"。数字一漂，他看到的规则与实际执行的规则就不是同一条 ——
    这跟错误码漂一位是同一类问题：不报错，只是用户被莫名其妙地拦住。
    """
    from zhiyin_business.services.profile import MAX_FIELD_VALUE_CHARS

    backend = MAX_FIELD_VALUE_CHARS
    assert isinstance(backend, int) and backend > 0, (
        f"后端上限必须是正整数，现在是 {backend!r}"
    )

    frontend = _frontend_max_chars()
    assert frontend == backend, (
        f"字数上限漂了：前端 {FRONTEND_FIELD_LIST.name} 写 {frontend}，"
        f"后端 services/profile.py 的 MAX_FIELD_VALUE_CHARS 是 {backend}。\n"
        "两边一起改：前端那个常量只用于计数提示（不静默截断），"
        "真正拒超长的是后端 —— 它才是上限的出处。"
    )
