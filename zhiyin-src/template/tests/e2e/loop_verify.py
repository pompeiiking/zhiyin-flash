"""五环节闭环的接口级端到端核验（真栈、真模型、真库）。

与 `full_path.py` 的分工：那一支走浏览器，验的是"界面有没有画出来"；
这一支只打接口，验的是**闭环本身走不走得动**、以及每个动作有没有真的落到库里。
两支互补：界面画出来了但库里没变，只有接口这一支看得出来。

它按一个真用户的样子把五个环节走一遍，每一步都同时看三层：

    ① 采集   画像真的写进去了、行为日志里有这一次动作
    ② 诊断   报告资产落地、每个历史版本都能点开（没有空版本）
    影响面   画像再变 → 不产生空版本、不谎报"跟着更新"
    ②→③     点认领选项 → 下一轮真的进决策
    ③ 决策   三套方案落地、选中落库
    ③→④     选中之后下一轮进行动
④ 行动   计划落地、节点进日历、勾掉任务落库
④→⑤     勾完任务下一轮进复盘
联动     事实一变（勾任务 / 导课表），依据它的模型产出真的重算 —— 而不是拿缓存那份
幂等     同一条消息重发不再跑模型
越权     别人的 task_id 取不到

用法（先 `docker compose up -d`，或本机跑起 8000 端口）：

    python zhiyin-src/template/tests/e2e/loop_verify.py [base_url]

产物：`tests/e2e/loop_verify.json`（逐项结果）。
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"
OUT = Path(__file__).resolve().parent / "loop_verify.json"

results: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    return bool(ok)


def phase(title: str) -> None:
    print(f"\n=== {title} ===")


def call(path: str, method: str = "GET", body: Any = None, token: str = "") -> dict[str, Any]:
    """打一次接口，返回 {status, code, data, message}。4xx 也如实返回，不抛。"""
    request = urllib.request.Request(
        API + path,
        method=method,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "status": response.status,
                "code": payload.get("code"),
                "data": payload.get("data"),
                "message": payload.get("message", ""),
            }
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
        return {
            "status": exc.code,
            "code": payload.get("code"),
            "data": payload.get("data"),
            "message": payload.get("message", ""),
        }


def say(task_id: str, message: str, token: str, option_id: str = "", client_msg_id: str = "") -> dict:
    """发一轮对话，返回回包 data；同时打出耗时与结果，便于人看。"""
    body: dict[str, Any] = {"task_id": task_id, "message": message}
    if option_id:
        body["option_id"] = option_id
    if client_msg_id:
        body["client_msg_id"] = client_msg_id
    started = time.time()
    result = call("/app/conversation/message", "POST", body, token)
    elapsed = time.time() - started
    data = result.get("data") or {}
    turns = data.get("messages") or [{}]
    print(f"    {elapsed:5.1f}s [{data.get('stage', '?')}] {turns[0].get('text', result.get('message', ''))[:90]}")
    return data


def ask_ai(path: str, token: str, body: Any = None) -> dict[str, Any]:
    """打一次 AI 任务（SSE），把终帧里的 `result` 取回来。

    只看结果信封：`meta.cached` 就是"这一段是**刚算的**还是**上一次算的**"——
    联动那几条检查靠它，不靠肉眼读文案。
    """
    request = urllib.request.Request(
        API + path,
        method="POST",
        data=json.dumps(body or {}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        raw = response.read().decode("utf-8")
    result: dict[str, Any] = {}
    for block in raw.split("\n\n"):
        line = block.strip()
        if not line.startswith("data: "):
            continue
        frame = json.loads(line[len("data: "):])
        if frame.get("result"):
            result = frame["result"]
    return result


def today_advice(token: str) -> dict[str, Any]:
    """打开"今天怎么用"这一天。

    时区偏移走请求体（后端按用户那边的日界线算"那一天"，库里存的是 UTC）。
    """
    today = datetime.now().date().isoformat()
    offset = int(datetime.now().astimezone().utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
    return ask_ai(f"/app/day/{today}/advice", token, {"arg": str(offset)})


def stage_of(task_id: str, token: str) -> str:
    sessions = (call("/app/sessions", token=token).get("data") or {}).get("sessions") or []
    for item in sessions:
        if item.get("task_id") == task_id:
            return item.get("stage") or ""
    return ""


def new_account() -> tuple[str, str]:
    account = f"loop-{uuid.uuid4().hex[:8]}"
    password = "pass-123456"
    registered = call("/app/auth/register", "POST", {"account": account, "password": password})
    return account, (registered.get("data") or {}).get("token") or ""


def intake(task_id: str, answers: list[str], token: str) -> dict:
    """一直答到报告出来（或答完手上的答案）。"""
    for index, answer in enumerate(answers):
        data = say(task_id, answer, token)
        report = call("/app/report/full-text", token=token).get("data") or {}
        if report.get("sections"):
            return data
        if index == len(answers) - 1:
            # 最后再补一句"验证方向"，这是设计里明确的一条推进入口
            return say(task_id, "我想验证一下这条路到底行不行、差多少。", token)
    return {}


ANSWERS = [
    "我大三，计算机专业，还不知道毕业该去做产品还是写代码。",
    "我做过两个课程项目，一个是推荐系统，一个是数据可视化大屏，还没实习过。",
    "今年开始准备求职，10 月想开始投递，手上只有一版简历。",
    "我一周能腾出两个下午，就是不知道先补哪一块。",
    "我最担心的是简历上写的东西没法让人当场问下去。",
]


def main() -> int:
    phase("准备：注册一个全新账号")
    account, token = new_account()
    check("注册并拿到令牌", bool(token), account)
    session = call("/app/task/enter", "POST", {"task_code": "confused"}, token).get("data") or {}
    task_id = session.get("task_id") or ""
    check("进入任务会话", bool(task_id), f"{task_id} stage={session.get('stage')}")

    # ── ① 采集 ────────────────────────────────────────────────
    phase("① 采集：画像沉淀 + 动作留痕 + 不为了外爬让用户等")
    collect_turns: list[dict] = []
    for answer in ANSWERS[:3]:
        collect_turns.append(say(task_id, answer, token))
    profile = (call("/app/workspace", token=token).get("data") or {}).get("profile_panel") or {}
    fields = profile.get("fields") or []
    check("画像真的从对话里沉淀出字段", len(fields) >= 2, f"{len(fields)} 个字段")
    check(
        "画像字段名是中文（没有把内部键摆给用户）",
        all(not (item.get("label") or "").isascii() for item in fields),
        ", ".join(str(item.get("label")) for item in fields)[:120],
    )
    # 采集这一档只读缓存：新账号缓存是空的，所以这一轮不该带回外部情报。
    # 改动前这里会现爬一遍（10 次请求、约 7 秒），refs 非空。
    refs = [len((turn.get("intel_refs") or [])) for turn in collect_turns]
    check("采集轮没有现爬外部情报（只读缓存）", all(count == 0 for count in refs), f"各轮 refs={refs}")

    # ── ② 诊断 ────────────────────────────────────────────────
    phase("② 诊断：报告落地")
    intake(task_id, ANSWERS[3:], token)
    report = call("/app/report/full-text", token=token).get("data") or {}
    sections = report.get("sections") or []
    check("报告资产已产出", bool(sections), f"version={report.get('version')} / {len(sections)} 组")
    check("报告结论不是空的", bool((report.get("verdict") or {}).get("title")), str((report.get("verdict") or {}).get("title"))[:80])

    versions_before = (call("/app/assets/report/versions", token=token).get("data") or [])
    check("第一个报告版本产生", len(versions_before) >= 1, f"{len(versions_before)} 版")

    # ── 影响面：传播只打标，重算才升版 ────────────────────────
    #
    # 判据必须分两步，否则会把**正确行为**判成缺陷：
    #   · 画像变了但没重算 → 只有影响面传播在跑，**不该**多出版本（以前会凭空 +1，
    #     而且那一版没有正文，点开是空白页）；
    #   · 回到②诊断真的重算 → 该 +1，并且必须给出「结论变化」告知。
    phase("影响面传播：只打标不升版；真重算才升版并给出告知")
    # 触发一次**真实的画像更新**：教务导入。
    #
    # 为什么不用"在采集里说一句"来触发（那是第一版判据，验证时被它绊住了）：
    # 采集门槛一旦过了，再落到采集的意图会被门禁直接顶回诊断 ——
    # **用户回不到①**，所以今天从对话这条路根本写不进画像。教务导入是另一条
    # 真实的写画像路径（`courses` / `scores`，来源=客观记录），而且它正好对应
    # 设计里"客观记录"这一类依据的入口。见 CHANGELOG 三十六节。
    imported = call(
        "/app/academic/import",
        "POST",
        {
            "courses": (
                "课程名称\t星期\t节次\t地点\t教师\n"
                "混凝土结构设计\t周一\t1-2节\tC楼302\t周立群"
            ),
            "grades": "",
            "term": "2026 秋",
        },
        token,
    )
    check(
        "教务导入写进了画像（客观记录这条来源真的会写）",
        bool((imported.get("data") or {}).get("wrote_profile")),
        str((imported.get("data") or {}).get("wrote_profile")),
    )
    versions_after = (call("/app/assets/report/versions", token=token).get("data") or [])
    check(
        "画像变了但还没重算：没有凭空多出版本（只打「待重算」标记）",
        len(versions_after) == len(versions_before),
        f"{len(versions_before)} → {len(versions_after)}（以前这里会 +1 且正文为空）",
    )
    empty_versions = []
    for item in versions_after:
        version = item.get("version")
        got = call(f"/app/report/full-text?version={version}", token=token).get("data") or {}
        if not got.get("sections"):
            empty_versions.append(version)
    check("版本下拉里每一版都点得开（没有空白页）", not empty_versions, f"空白版本 {empty_versions}")

    recomputed_count = len(versions_after)

    # 传播是异步的（Worker 每 60 秒扫一次），等那一版被标上"待重算"。
    marked = False
    deadline = time.time() + 120
    while time.time() < deadline:
        versions_now = call("/app/assets/report/versions", token=token).get("data") or []
        if versions_now and versions_now[-1].get("needs_recompute"):
            marked = True
            break
        time.sleep(6)
    check(
        "传播确实把这一版标成了「待重算」（接口可观察）",
        marked,
        f"最新版 needs_recompute={marked}",
    )
    marked_versions = (call("/app/assets/report/versions", token=token).get("data") or [])
    check(
        "打标没有带来新版本（只标记，不升版）",
        len(marked_versions) == recomputed_count,
        f"重算后 {recomputed_count} 版 → 打标后 {len(marked_versions)} 版",
    )

    # 回到②诊断：这一轮应该**真的重算**，并把"结论变了"如实告诉用户。
    #
    # 这里允许重试，理由要写清楚：模型偶尔会**完全不给结构化产出**
    # （日志里是"模型未返回可解析的结构化产出"，不是缺字段 —— 实测 31 项里碰到 1 次）。
    # 产品对这种降级的处理是如实说"这一轮我没能按格式产出内容，你再说一句"，
    # 用户也会再补一句。测试跟着人的做法走，但把降级次数打出来 ——
    # 不能因为"重试就好了"让它看不见。
    attempts = 0
    degraded = 0
    recompute: dict = {}
    versions_final = call("/app/assets/report/versions", token=token).get("data") or []
    while attempts < 3 and len(versions_final) == recomputed_count:
        attempts += 1
        recompute = say(
            task_id,
            "那我把课表上的空档也考虑进来，重新看一遍这条路到底行不行。",
            token,
        )
        if "没能按格式产出" in str(((recompute.get("messages") or [{}])[0]).get("text") or ""):
            degraded += 1
        versions_final = call("/app/assets/report/versions", token=token).get("data") or []

    print(f"    （重算尝试 {attempts} 次，其中模型产出不合契约 {degraded} 次）")
    check(
        "② 真的重算了一版（版本 +1，而不是假装更新）",
        len(versions_final) == recomputed_count + 1,
        f"{recomputed_count} → {len(versions_final)}（尝试 {attempts} 次，降级 {degraded} 次）",
    )
    disclosure = recompute.get("disclosure") or {}
    check(
        "重算那一轮给出了「结论变化」告知",
        # 同一轮可能既换了主理、又重算了旧结论：契约里只有一个位置，
        # 所以判据是"这句里说到了结论变化"，不是"kind 等于某一个值"。
        "结论" in (disclosure.get("text") or "")
        or disclosure.get("kind") == "conclusion_change",
        f"kind={disclosure.get('kind')} text={(disclosure.get('text') or '')[:80]}",
    )

    # ── ②→③：点认领选项 ──────────────────────────────────────
    phase("②→③：认领差距之后，闭环自己往前走")
    claim = say(task_id, "我先去抄 3 条岗位职责，看看它到底要什么。", token)
    options = ((claim.get("guide") or {}).get("options") or [])
    if options:
        say(task_id, options[0].get("label") or "我先去抄 3 条岗位职责", token, option_id=options[0].get("option_id") or "gap_1")
    else:
        say(task_id, "我先去抄 3 条岗位职责", token, option_id="gap_1")
    next_turn = say(task_id, "那接下来呢", token)
    check(
        "认领之后下一轮进入 ③ 决策",
        next_turn.get("stage") == "decide",
        f"stage={next_turn.get('stage')}",
    )
    behaviors = (call("/app/sessions", token=token).get("data") or {}).get("sessions") or []
    check("会话仍在进行中", bool(behaviors), f"{len(behaviors)} 条会话")

    # ── ③ 决策 ────────────────────────────────────────────────
    phase("③ 决策：三套方案 + 选中落库")
    plans = (call("/app/plan/directions", token=token).get("data") or {}).get("plans") or []
    if not plans:
        say(task_id, "我拿不准该选哪个方向，帮我比较一下，给几套可以改的方案。", token)
        plans = (call("/app/plan/directions", token=token).get("data") or {}).get("plans") or []
    check("③ 产出方向方案（后端资产）", len(plans) >= 2, f"{len(plans)} 套：{[p.get('name') for p in plans][:3]}")
    selected_id = ""
    if plans:
        picked = call(f"/app/plan/directions/{plans[0]['id']}/select", "POST", {}, token)
        selected_id = (picked.get("data") or {}).get("selected_id") or ""
        check("选中一套方案并落库", selected_id == plans[0]["id"], f"selected_id={selected_id}")

    # ── ③→④ ──────────────────────────────────────────────────
    phase("③→④：选中之后，闭环进行动")
    act_turn = say(task_id, "那就按这套来，接下来我该做什么？", token)
    action = call("/app/plan/action", token=token).get("data") or {}
    if not action.get("has_plan"):
        act_turn = say(task_id, "给我一份行动计划，拆成今天能做完的小事。", token)
        action = call("/app/plan/action", token=token).get("data") or {}
    check("④ 产出行动计划（后端资产）", bool(action.get("has_plan")), f"{len(action.get('phases') or [])} 个阶段")
    check("行动阶段真的在 ④", act_turn.get("stage") == "act", f"stage={act_turn.get('stage')}")
    nodes = call("/app/calendar", token=token).get("data") or []
    check("关键节点写进了日历（规划师写、教练读）", len(nodes) >= 1, f"{len(nodes)} 条节点")

    # ── 联动（一）：模型算出来的东西，会跟着事实变 ─────────────
    phase("联动：事实一变，依据它的模型产出真的重算")
    first = today_advice(token)
    check(
        "第一次打开「今天怎么用」是真算的",
        bool(first.get("data")) and first.get("meta", {}).get("cached") is False,
        f"cached={first.get('meta', {}).get('cached')} · {first.get('meta', {}).get('by', '')}",
    )
    again = today_advice(token)
    check(
        "同一份内容再打开一次走缓存（不是每次都烧一遍模型）",
        again.get("meta", {}).get("cached") is True,
        f"cached={again.get('meta', {}).get('cached')}",
    )

    # ── ④→⑤：勾掉第一个任务 ──────────────────────────────────
    phase("④→⑤：勾掉一件任务之后，闭环进复盘")
    task = action.get("next_task") or {}
    if task.get("task_id"):
        ticked = call(
            "/app/plan/action/tasks", "PATCH", {"task_id": task["task_id"], "done": True}, token
        )
        flat = [
            item
            for phase_item in ((ticked.get("data") or {}).get("phases") or [])
            for item in (phase_item.get("tasks") or [])
        ]
        check("勾掉任务落库（done=true）", any(item.get("done") for item in flat), f"已完成 {sum(1 for i in flat if i.get('done'))}/{len(flat)}")
        after_tick = today_advice(token)
        check(
            "勾掉一件任务之后，「今天怎么用」重算了（不再拿旧任务排）",
            after_tick.get("meta", {}).get("cached") is False,
            f"cached={after_tick.get('meta', {}).get('cached')}",
        )
    else:
        check("勾掉任务落库（done=true）", False, "没有可勾的任务")

    # ── 联动（二）：另一条事实来源 —— 导进来的课表 ─────────────
    weekday = "一二三四五六日"[datetime.now().weekday()]
    imported = call(
        "/app/academic/import",
        "POST",
        {
            "school": "某某大学",
            "term": "2025-2026 第一学期",
            "courses": f"数值分析\t周三\t3-4节\t教二楼203\n"
                       f"数据结构\t周{weekday}\t5-6节\t实验楼401",
        },
        token,
    )
    check("课表导入成功（另一条事实来源）", imported.get("code") in (None, 0), str(imported.get("message"))[:80])
    after_import = today_advice(token)
    check(
        "导完课表之后，「今天怎么用」重算了（课表也是它的依据）",
        after_import.get("meta", {}).get("cached") is False,
        f"cached={after_import.get('meta', {}).get('cached')}",
    )
    settled = today_advice(token)
    check(
        "重算之后又回到缓存（没有把缓存改成每次都重算）",
        settled.get("meta", {}).get("cached") is True,
        f"cached={settled.get('meta', {}).get('cached')}",
    )

    review_turn = say(task_id, "我做了一步，接下来呢", token)
    check(
        "勾掉任务之后下一轮进入 ⑤ 复盘",
        review_turn.get("stage") == "review",
        f"stage={review_turn.get('stage')}",
    )

    # ── 幂等 ──────────────────────────────────────────────────
    phase("幂等：同一条消息重发不该再跑一遍模型")
    marker = f"dup-{uuid.uuid4().hex[:6]}"
    first = say(task_id, "我担心投了没人回", token, client_msg_id=marker)
    started = time.time()
    second = say(task_id, "我担心投了没人回", token, client_msg_id=marker)
    elapsed = time.time() - started
    first_text = ((first.get("messages") or [{}])[0]).get("text")
    second_text = ((second.get("messages") or [{}])[0]).get("text")
    check("重发返回同一句原文", bool(second_text) and second_text == first_text, second_text or "")
    check("重发没有再等一次模型", elapsed < 3, f"{elapsed:.1f}s")

    # ── 会话与越权 ────────────────────────────────────────────
    phase("账本一致性与越权")
    turns = call(f"/app/sessions/{task_id}/turns", token=token).get("data") or []
    roles = {item.get("role") for item in turns}
    check("逐轮原文可读且两种角色都在", {"user", "agent"} <= roles, f"{len(turns)} 轮 {sorted(roles)}")
    check(
        "重发没有在历史里留第二段往返",
        sum(1 for item in turns if (item.get("text") or "").startswith("我担心投了没人回")) == 1,
        f"{len(turns)} 轮",
    )

    _, other_token = new_account()
    stolen = call(f"/app/sessions/{task_id}/turns", token=other_token)
    check(
        "别人的 task_id 取不到（按 1002 处理）",
        stolen.get("code") == 1002 or not stolen.get("data"),
        f"code={stolen.get('code')}",
    )

    total = len(results)
    passed = sum(1 for item in results if item["ok"])
    OUT.write_text(
        json.dumps({"base": BASE, "account": account, "passed": passed, "total": total, "checks": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n===== 五环节闭环：{passed}/{total} 通过 =====")
    for item in results:
        if not item["ok"]:
            print(f"  FAIL  {item['check']} — {item['detail']}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
