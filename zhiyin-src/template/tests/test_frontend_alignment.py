"""前后端口径对齐守卫（跨语言，只能靠断言）。

为什么单独一个文件
------------------
前端 `zhiyin-web` 与后端是两套语言，几处**必须一致**的东西没有编译器兜底：

- `src/api/client.ts` 里的错误码数字 ↔ 后端 `ErrorCode` 枚举；
- 前端调用的每一条 `/api/v1/...` ↔ 后端真实路由（OpenAPI）；
- 反向：后端每条业务接口都该有人消费，否则"接口做完了但没人用"；
- `data/registry/routes.json` / `menus.json` 声明的路径 ↔ 前端真实路由；
- 前端 README 的「页面 → 组件」落位表 ↔ 真实 .vue 文件。

这四类症状都是"不报错的错"：错误码错一位 → UI 走进通用分支；路径漂移 → 运行时 404；
路由表指向不存在的页面 → 菜单点了没反应；落位表漂移 → 新人照表找文件扑空。
所以这里把它们变成机械可判。**跨语言的比对口径必须写下来，不能靠记忆。**
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = TEMPLATE_ROOT / "zhiyin-web"
SRC = WEB_ROOT / "src"
REGISTRY_DIR = TEMPLATE_ROOT / "data" / "registry"

CLIENT_TS = SRC / "api" / "client.ts"
TYPES_TS = SRC / "api" / "types.ts"
ROUTER_TS = SRC / "router.ts"
WEB_README = WEB_ROOT / "README.md"

FRONTEND_PREFIX = "/api/v1"
"""前端 baseURL。前端只写业务段（`/app/notes`），前缀由 client.ts 统一拼。"""

# 后端有、但一期前端不消费的接口。加一条之前先问：是不是"接口做完了没人用"？
# 会，就别加；不会（确属其他消费方），加上并写清谁在用。
FRONTEND_EXEMPT_PATHS: dict[str, str] = {
    "/api/v1/app/config/reload": "运维接口：改完配置在终端喊一声重载，不由前端消费",
}


def _frontend_sources() -> list[Path]:
    """前端源码（**不含生成物**）。

    `src/api/types.ts` 由 `npm run gen:api` 生成，它把后端每一条路径都列了一遍 ——
    那是它的职责。把它算进"前端调用的接口"，会让"豁免表里的是不是真被调用了"
    这类判断全部失真（实测：运维接口 `/app/config/reload` 被它顶出来）。
    """
    return sorted(
        p
        for p in SRC.rglob("*")
        if p.suffix in {".ts", ".vue"} and p != SRC / "api" / "types.ts"
    )


def _normalized(path: str) -> str:
    """归类路径参数：`/app/notes/${id}` 与 `/app/notes/{note_id}` 是同一条。"""
    path = path.split("?")[0]
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    return re.sub(r"\{[^}]*\}", "{}", path)


_COMMENT = re.compile(r"/\*[\s\S]*?\*/|//[^\n]*")


def _code_only(text: str) -> str:
    """去掉注释再抽取路径。

    注释里也常写路径（"这里读 `/app/assets/report/versions`"），
    那是给人看的说明，不是调用 —— 把它们算成"前端调用的接口"会让守卫开始报假警。
    """
    return _COMMENT.sub(" ", text)


def _registry(name: str) -> list[dict]:
    return json.loads((REGISTRY_DIR / name).read_text(encoding="utf-8"))["items"]


# --------------------------------------------------------------------------
# 1. 错误码：前端数字 ↔ 后端 IntEnum
# --------------------------------------------------------------------------


def _frontend_error_codes() -> dict[str, int]:
    """取出 `const CODE_X: Schema['ErrorCode'] = 1004` 这份表。

    只认带 `Schema['ErrorCode']` 标注的那些：标注本身就是"这个数字来自后端枚举"
    的声明，而 `npm run typecheck` 会检查它的取值确实在生成的联合类型里。
    解析不到就抛错而不是返回空 —— 否则守卫会"看起来在跑、其实什么都没比"。
    """
    text = CLIENT_TS.read_text(encoding="utf-8")
    found = re.findall(r"const (CODE_\w+)\s*:\s*Schema\['ErrorCode'\]\s*=\s*(\d+)", text)
    assert found, "client.ts 里没有解析到 `CODE_*: Schema['ErrorCode']` 声明——守卫会变成空跑"
    return {name: int(value) for name, value in found}


def test_frontend_error_codes_match_backend() -> None:
    """错误码是全站唯一的跨语言常量表，多一位少一位都会让 UI 走进错分支。

    两个方向都要对：名字必须能在后端 `ErrorCode` 里找到同名的成员，
    数值必须与它相等。少了 → 前端走通用分支；错了 → 走进别的分支；
    后端删码而前端没跟 → 这里也会失败。
    """
    from zhiyin_api.dto.common import ErrorCode as BackendErrorCode

    backend = {member.name: int(member.value) for member in BackendErrorCode}
    frontend = _frontend_error_codes()

    unknown = sorted(name for name in frontend if name.removeprefix("CODE_") not in backend)
    assert not unknown, (
        f"前端声明了后端没有的错误码：{unknown}。"
        f"后端现有：{sorted(backend)}（前端常量名去掉 CODE_ 前缀后应当同名）"
    )

    wrong = sorted(
        f"{name}= {frontend[name]}（后端 {name.removeprefix('CODE_')}={backend[name.removeprefix('CODE_')]}）"
        for name in frontend
        if frontend[name] != backend[name.removeprefix("CODE_")]
    )
    assert not wrong, "前后端错误码数值不一致（前端 src/api/client.ts ↔ 后端 api/dto/common.py）：\n  " + "\n  ".join(wrong)


# --------------------------------------------------------------------------
# 2. 接口清单：前端调用的 url ↔ 后端 OpenAPI
# --------------------------------------------------------------------------


def _frontend_urls() -> set[str]:
    """把前端真正请求的 `/api/v1/...` 收成一份集合。

    两种写法都要认：
      · `api<T>('/app/notes')` —— 业务段，前缀由 client.ts 统一拼；
      · `"/api/v1/app/brief/today"` —— AI 清单里写全的那种。
    """
    urls: set[str] = set()
    for path in _frontend_sources():
        text = _code_only(path.read_text(encoding="utf-8"))
        for business in re.findall(r"api<[^>]*>\(\s*[`'\"]([^`'\"]+)[`'\"]", text):
            urls.add(_normalized(FRONTEND_PREFIX + business))
        # 业务段也可能先赋给变量再传进去（登录 / 注册就是：`const path = mode === … ? '/app/auth/login' : …`）。
        # 只看"以 /app/ 开头的字符串"这一条口径：这个仓里没有别的字符串长这样。
        for business in re.findall(r"[`'\"](/app/[^`'\"]*)[`'\"]", text):
            urls.add(_normalized(FRONTEND_PREFIX + business))
        for absolute in re.findall(r"[`'\"](/api/v1/[^`'\"]*)[`'\"]", text):
            if absolute != FRONTEND_PREFIX:  # 纯前缀本身（模板串）不算一条接口
                urls.add(_normalized(absolute))
    # 模板串里的 base 拼接：`/api/v1${path}` 说明前缀是拼上去的，已经被上面的规则覆盖
    urls.discard(_normalized(FRONTEND_PREFIX))
    assert urls, "没解析到任何接口调用——守卫会变成空跑"
    return urls


def _backend_paths() -> set[str]:
    from zhiyin_api.app import create_app

    return {_normalized(path) for path in create_app().openapi()["paths"]}


def test_every_frontend_endpoint_exists_on_the_backend() -> None:
    """前端清单里的每个 url 都必须在后端真实存在。

    这是"404 而 OpenAPI 里看着有这条路由"的机械防线：前端拼错业务段、后端改了
    路径、前缀两处不一致，都会在这里失败。
    """
    unknown = sorted(_frontend_urls() - _backend_paths())
    assert not unknown, "前端引用了后端不存在的接口：\n  " + "\n  ".join(unknown)


def test_backend_business_endpoints_are_all_used_by_the_frontend() -> None:
    """反向：后端每条业务接口都必须有人消费（或写清豁免理由）。

    一期前端的消费面就是全部业务接口，所以"后端加了接口、前端不知道"应该立刻可见。
    豁免表见文件头的 `FRONTEND_EXEMPT_PATHS`。
    """
    exempt = set(FRONTEND_EXEMPT_PATHS)
    unused = sorted(_backend_paths() - _frontend_urls() - exempt - {"/healthz"})
    assert not unused, (
        "后端这些接口还没进前端（或没进豁免表）：\n  "
        + "\n  ".join(unused)
        + "\n确属非前端接口时，请加入本文件顶部的 FRONTEND_EXEMPT_PATHS 并注明用途。"
    )


def test_exempt_paths_still_exist_on_the_backend() -> None:
    """豁免表里的路径必须真实存在：否则它会一直豁免一条早就删掉的接口。"""
    missing = sorted(set(FRONTEND_EXEMPT_PATHS) - _backend_paths())
    assert not missing, (
        f"FRONTEND_EXEMPT_PATHS 里这些路径后端已经没有了：{missing}。"
        "把过期条目删掉，别让豁免表变成什么都挡不住的摆设。"
    )


def test_exempt_paths_are_not_secretly_used() -> None:
    """豁免表里的路径不能被前端真的调用 —— 那说明该把它从豁免表里删掉。

    这一条同样重要：豁免表如果只增不减，会出现"接口明明已经接上了，
    却还挂着一张'没人用'的免罪符"，下一个人读到这里会以为它没接。
    实测发生过：`/app/sessions` 与 `/app/assets/*` 接上之后，
    豁免表里那两条一直没人清。
    """
    used = sorted(set(FRONTEND_EXEMPT_PATHS) & _frontend_urls())
    assert not used, (
        f"这些接口前端已经在用了，却还挂在豁免表里：{used}。"
        "请从 FRONTEND_EXEMPT_PATHS 里删掉对应条目。"
    )


# --------------------------------------------------------------------------
# 3. 路由：routes.json / menus.json ↔ 前端 router.ts
# --------------------------------------------------------------------------


def _frontend_routes() -> dict[str, dict[str, object]]:
    """解析 router.ts 里的真实页面路由（重定向不算页面，跳过）。

    口径：`{ path: '/x', name: 'y', … }` 才算页面；`/login` 那种只有 redirect
    的老链接不为它做页面归属，也不该出现在动态路由表里。
    """
    text = ROUTER_TS.read_text(encoding="utf-8")
    routes: dict[str, dict[str, object]] = {}
    for path, name in re.findall(r"\{\s*path:\s*'([^']+)',\s*name:\s*'([^']+)'", text):
        routes[path] = {"name": name}
    # 公开路径（不需要登录）：守卫里的 publicPaths 数组
    public = set(re.findall(r"publicPaths\s*=\s*\[([^\]]*)\]", text)[0].replace("'", " ").split()) if "publicPaths" in text else set()
    for path in routes:
        routes[path]["require_login"] = path not in public
    assert routes, "没解析到 router.ts 的路由——守卫会变成空跑"
    return routes


def test_declared_routes_match_the_frontend_router() -> None:
    """`routes.json` 的 path / require_login 必须与前端路由逐条对齐。

    两边都是"这个页面在哪、要不要登录"的口径来源：前端用它做路由与拦截，
    动态资源用它下发页面属性。漂移时前端不报错，只会让某个页面的登录拦截
    与埋点归属对不上。
    """
    frontend = _frontend_routes()
    declared = _registry("routes.json")

    declared_paths = {item["path"] for item in declared}
    assert declared_paths == set(frontend), (
        "routes.json 与前端路由不是同一批页面：\n"
        f"  routes.json 有、前端没有：{sorted(declared_paths - set(frontend))}\n"
        f"  前端有、routes.json 没登记：{sorted(set(frontend) - declared_paths)}\n"
        "新增/删除页面时两处一起改：src/router.ts 与 data/registry/routes.json"
    )

    for item in declared:
        route = frontend[item["path"]]
        assert route["require_login"] == item["require_login"], (
            f"路径 {item['path']} 的 require_login 不一致："
            f"前端={route['require_login']} / routes.json={item['require_login']}"
        )


def test_menu_routes_point_at_real_routes() -> None:
    """顶层导航菜单指向的 route 必须是真实路由。

    菜单是动态资源，改一条不需要发版——代价是"指向不存在的路由"在运行时只会
    表现为点了没反应。这里挡住。
    """
    paths = set(_frontend_routes())
    for menu in _registry("menus.json"):
        assert menu["route"] in paths, (
            f"菜单 {menu['code']} 指向 {menu['route']}，但前端没有这条路由"
        )


# --------------------------------------------------------------------------
# 4. 生成物与落位表
# --------------------------------------------------------------------------


def test_api_types_are_generated_not_handwritten() -> None:
    """`src/api/types.ts` 必须是生成物，且覆盖到前端真正在用的视图。

    它曾经是一份手抄的接口清单：后端改字段，两边都不报错，只是界面上某个格子
    永远空着。现在钉住"它由 openapi-typescript 生成"，并顺带钉住生成源没跑偏。
    """
    text = TYPES_TS.read_text(encoding="utf-8")
    assert "This file was auto-generated by openapi-typescript" in text, (
        "src/api/types.ts 不是生成物。请运行：cd zhiyin-web && npm run gen:api"
    )
    for schema in ("WorkspacePageView", "ReportFullTextView", "TheoryCardView", "ConversationTurnView"):
        assert f"{schema}:" in text, (
            f"types.ts 里没有 {schema}——生成源（../contracts/openapi.json）可能过期，"
            "请先运行 python scripts/export_openapi.py 再 npm run gen:api"
        )


def _component_inventory() -> dict[str, Path]:
    return {p.stem: p for p in sorted((SRC / "components").rglob("*.vue"))}


def _readme_component_refs() -> set[str]:
    """取出前端 README 落位表里「页面文件」「主要组件」两列的引用（归一化为文件名）。

    README 里还有别的表格（数据来源、目录职责），它们写的是接口名与目录名，
    混进来会让守卫把正常的表格判成"文件不存在"——所以只读这一张表。
    """
    text = WEB_README.read_text(encoding="utf-8")
    table_start = text.index("## 二、页面 → 组件 → 接口")
    table_end = text.index("## 三、", table_start)
    references: set[str] = set()
    for row in text[table_start:table_end].splitlines():
        if not row.startswith("|"):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"页面 / 区块", "---"}:
            continue
        # 第 3 列是页面文件，第 4 列是主要组件
        for cell in (cells[2], cells[3]):
            flattened = cell.replace("{", " ").replace("}", " ").replace("`", "")
            for token in re.split(r"[、,，\s]+", flattened):
                token = token.strip()
                if not token:
                    continue
                name = token.split("/")[-1].removesuffix(".vue")
                # 组件是 PascalCase；`composables/useCanvasDrag`、`lib/tiling`
                # 这种小写路径不是组件，跳过（它们是"顺带提到"的支撑代码）
                if name[:1].isupper():
                    references.add(name)
    assert references, "没解析到前端落位表——守卫会变成空跑"
    return references


def test_frontend_placement_table_matches_real_files() -> None:
    """前端 README 的落位表 ↔ 真实文件（与后端 services 落位表守卫同源）。

    两个方向都查：表里写了不存在的文件 → 新人照表找会扑空；
    新增了组件而没进表 → 两个人各自新建同名组件也不会被发现。
    """
    referenced = _readme_component_refs()
    actual = set(_component_inventory()) | {p.stem for p in (SRC / "views").glob("*.vue")}
    actual.add("App")

    missing_files = sorted(name for name in referenced if name not in actual)
    undocumented = sorted(name for name in actual if name not in referenced)

    assert not missing_files, (
        f"前端落位表里写了、但文件不存在的组件/页面：{missing_files}。"
        "请补文件，或把表格里的名字改成真实文件名"
    )
    assert not undocumented, (
        f"这些组件/页面文件没有登记进前端 README 落位表：{undocumented}。"
        "新增组件请同时补表格（一人一格，避免并行时新建同名文件）"
    )


@pytest.mark.parametrize("relative", ["src/api/client.ts", "src/api/types.ts", "src/ai/registry.ts"])
def test_api_and_ai_files_are_documented(relative: str) -> None:
    """`src/api/` 与 `src/ai/` 的关键文件都要在 README 里说明职责（口径唯一处不许隐身）。"""
    assert (WEB_ROOT / relative).is_file(), f"{relative} 不存在"
    assert Path(relative).name in WEB_README.read_text(encoding="utf-8"), (
        f"{relative} 没有写进前端 README 的目录职责表"
    )


# --------------------------------------------------------------------------
# 5. 埋点事件码：前端发出去的码必须在注册表里（channel=frontend）
# --------------------------------------------------------------------------

#: 注册表里声明为 frontend、但前端还没有接线的事件码。
#: 加一条之前先问：这是"二期再做"，还是"声明了没人做"？后者应当去接线而不是豁免。
UNWIRED_FRONTEND_EVENTS: dict[str, str] = {
}


def _frontend_track_codes() -> set[str]:
    codes: set[str] = set()
    for path in _frontend_sources():
        codes |= set(re.findall(r"track\(\s*'([a-z_]+)'", path.read_text(encoding="utf-8")))
    assert codes, "没解析到前端的 track() 调用——守卫会变成空跑"
    return codes


def test_frontend_track_events_are_registered() -> None:
    """前端发出去的每个事件码，都必须在 `data/registry/track_events.json` 里登记。

    为什么值得守：后端的 `/app/track` 按注册表**收事件**，没登记的会被拒收
    （`accepted: false`），而前端埋点按设计是静默的 —— 于是整片埋点失效而没人发现。
    实测踩过：前端自己发明了一个 `talk_open`，`biz_track_event` 一直是 0 行。

    另外，注册表里声明为 frontend 却没人发的，也必须**显式列出来并写清原因**：
    不列就等于"声明了没人做"，那正是这张表最容易腐化的地方。
    """
    registry = {item["code"]: item for item in _registry("track_events.json")}
    frontend_codes = _frontend_track_codes()

    unknown = sorted(code for code in frontend_codes if code not in registry)
    assert not unknown, (
        f"前端发了未登记的事件码：{unknown}。"
        "要么在 data/registry/track_events.json 里登记，要么别发 —— 未登记的会被后端拒收。"
    )

    wrong_channel = sorted(
        code for code in frontend_codes if registry[code].get("channel") != "frontend"
    )
    assert not wrong_channel, (
        f"这些事件码在注册表里不是 frontend 通道：{wrong_channel}。"
        "前端不该发后端通道的事件（那是服务端自己记的）。"
    )

    declared = {item["code"] for item in _registry("track_events.json") if item.get("channel") == "frontend"}
    silent = sorted(declared - frontend_codes - set(UNWIRED_FRONTEND_EVENTS))
    assert not silent, (
        f"注册表声明为 frontend、但前端从没发送过，也没在豁免表里说明：{silent}。"
        "请接线，或加入本文件顶部的 UNWIRED_FRONTEND_EVENTS 并写清原因。"
    )

    stale_exemptions = sorted(set(UNWIRED_FRONTEND_EVENTS) & frontend_codes)
    assert not stale_exemptions, (
        f"这些事件前端已经发了，却还挂在「未接线」豁免表里：{stale_exemptions}。把过期条目删掉。"
    )
