"""端到端（浏览器）：画布上的块，是不是跟着别处的动作一起动。

为什么单独有一支：`loop_verify.py` 那支打的是接口，它能证明"库里真的变了、
模型真的重算了"，但**看不出界面有没有跟着变**。而界面这边是各块各取数的：
同一个动作改完库，有的块会重拉、有的块停在进来那一刻 —— 它不报错，
只是安静地显示旧值。用户看到的就是"这两块说的不是一回事"。

这支脚本盯一件最典型的事：

    在「行动计划」浮层里勾掉一件任务 → 画布上那块「待办」的数字要不要跟着变。

判据不是"看起来变了没有"，而是工作台面板那句**确定性**的计数
（`N 个阶段 · 任务 x/y 已完成`）：同一个数前后**相差 1** 才算联动生效。

顺带看一处更细的：如果被勾掉的那件事正好到期在今天，日历那一天应当从
「待做」变成「已做」（跨两个浮层、跨两份数据源）。

跑法（先 `docker compose up -d`，或本机把前后端跑起来）：

    python zhiyin-src/template/tests/e2e/linkage_probe.py [web_base] [api_base]

默认 Web `http://127.0.0.1:5173`、API `http://127.0.0.1:8000`。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date
from typing import Any

from playwright.sync_api import sync_playwright

WEB = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173").rstrip("/")
API = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000").rstrip("/") + "/api/v1"

#: 走到 ④ 用的答池：与 loop_verify 同一套口径（真人会怎么答，就怎么答）。
ANSWERS = [
    "我大三，计算机专业，还不知道毕业该去做产品还是写代码。",
    "我做过两个课程项目，一个是推荐系统，一个是数据可视化大屏，还没实习过。",
    "今年开始准备求职，10 月想开始投递，手上只有一版简历。",
    "我一周能腾出两个下午，就是不知道先补哪一块。",
    "我最担心的是简历上写的东西没法让人当场问下去。",
]

results: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    return bool(ok)


def call(path: str, method: str = "GET", body: Any = None, token: str = "") -> dict[str, Any]:
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
            return {"code": payload.get("code"), "data": payload.get("data"), "message": payload.get("message", "")}
    except urllib.error.HTTPError as exc:
        return {"code": exc.code, "data": None, "message": exc.read().decode()[:200]}


def say(task_id: str, message: str, token: str, option_id: str = "") -> dict[str, Any]:
    body: dict[str, Any] = {"task_id": task_id, "message": message}
    if option_id:
        body["option_id"] = option_id
    return call("/app/conversation/message", "POST", body, token).get("data") or {}


def walk_to_act(token: str) -> tuple[str, dict[str, Any]]:
    """把账号走到 ④ 行动：有画像 → 有报告 → 有方向 → 有行动计划。

    这一段走的是**接口**而不是界面：它是准备工作，不是被检验的东西；
    被检验的是"东西都在了之后，界面上一个动作能不能带动别的块"。
    """
    task_id = (call("/app/task/enter", "POST", {"task_code": "confused"}, token).get("data") or {}).get(
        "task_id"
    ) or ""
    for answer in ANSWERS:
        say(task_id, answer, token)
        if (call("/app/report/full-text", token=token).get("data") or {}).get("sections"):
            break
    # ②→③：认领一条差距（有选项就用它，没有就按默认那条说）
    claim = say(task_id, "我先去抄 3 条岗位职责，看看它到底要什么。", token)
    options = (claim.get("guide") or {}).get("options") or []
    say(
        task_id,
        (options[0].get("label") if options else "") or "我先去抄 3 条岗位职责",
        token,
        option_id=(options[0].get("option_id") if options else "") or "gap_1",
    )
    say(task_id, "那接下来呢", token)
    # ③→④：选一套方案，再要计划
    plans = (call("/app/plan/directions", token=token).get("data") or {}).get("plans") or []
    if not plans:
        say(task_id, "我拿不准该选哪个方向，帮我比较一下，给几套可以改的方案。", token)
        plans = (call("/app/plan/directions", token=token).get("data") or {}).get("plans") or []
    if plans:
        call(f"/app/plan/directions/{plans[0]['id']}/select", "POST", {}, token)
    say(task_id, "那就按这套来，接下来我该做什么？", token)
    action = call("/app/plan/action", token=token).get("data") or {}
    # 走到 ④ 有时要多说一两句（模型上一步可能还在比较方向）。
    # 这里最多催三次，每次都换一句更像人会说的话 —— 换了环境（比如刚部署的干净库）
    # 这一路的落点会和上次不完全一样，一次没到就判"这支探针跑不下去"太脆。
    nudges = [
        "给我一份行动计划，拆成今天能做完的小事。",
        "先把这周要做的事列出来，一条一条的就行。",
        "我就要一个能今天勾掉的任务清单。",
    ]
    for nudge in nudges:
        if action.get("has_plan"):
            break
        say(task_id, nudge, token)
        action = call("/app/plan/action", token=token).get("data") or {}
    return task_id, action


def progress_bubble(page: Any) -> str:
    """画布上那块「待办」里的计数句（`N 个阶段 · 任务 x/y 已完成`）。"""
    node = page.locator("[data-block='todo'] .now__title").first
    return node.inner_text().strip() if node.count() else ""


def done_count(text: str) -> int:
    """从 `… 任务 3/14 已完成` 里把 3 取出来；读不出来返回 -1（判成失败，不猜）。"""
    try:
        tail = text.split("任务", 1)[1].strip()
        return int(tail.split("/", 1)[0].strip())
    except (IndexError, ValueError):
        return -1


def main() -> int:
    account = f"link-{uuid.uuid4().hex[:8]}"
    token = (call("/app/auth/register", "POST", {"account": account, "password": "pass-123456"}).get("data") or {}).get(
        "token"
    ) or ""
    if not token:
        print("注册失败")
        return 1
    print(f"账号 {account}（密码 pass-123456）")

    task_id, plan = walk_to_act(token)
    tasks = [t for p in (plan.get("phases") or []) for t in (p.get("tasks") or [])]
    print(f"准备完成：{len(plan.get('phases') or [])} 个阶段 / {len(tasks)} 条任务，未完成 {sum(1 for t in tasks if not t.get('done'))} 条\n")
    next_task = plan.get("next_task") or (tasks[0] if tasks else {})
    if not next_task.get("task_id"):
        print("没有可勾的任务，这支探针跑不下去")
        return 1
    # 优先勾**今天到期**的那一件：截图与日历那一条才看得见（日历默认停在今天）
    today = date.today().isoformat()
    target = next(
        (
            item
            for item in tasks
            if not item.get("done") and str(item.get("due_date") or "")[:10] == today
        ),
        next_task,
    )
    print(f"准备勾掉：{str(target.get('text'))[:40]}（截止 {str(target.get('due_date') or '—')[:10]}）\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.goto(WEB + "/portal", wait_until="networkidle")
        page.evaluate("t => localStorage.setItem('zhiyin_token', t)", token)
        page.goto(WEB + "/", wait_until="networkidle")
        page.wait_for_timeout(5000)
        # 压在画布上的提示浮窗先收掉：它挡住可点区域，会让后面的点击落到别处
        for index in range(page.locator(".pop__act", has_text="知道了").count()):
            try:
                page.locator(".pop__act", has_text="知道了").nth(index).click(timeout=1500)
                page.wait_for_timeout(200)
            except Exception:  # noqa: BLE001 - 已经收掉的那条不算失败
                pass

        before_text = progress_bubble(page)
        before_done = done_count(before_text)
        check("画布上的「待办」读得到计数句", before_done >= 0, before_text)

        # ── 在计划浮层里勾掉第一件 ────────────────────────────────
        block = page.locator("[data-block='action']").first
        check("画布上有「行动计划」这一块", block.count() > 0, "")
        box = block.bounding_box()
        page.mouse.click(box["x"] + 40, box["y"] + box["height"] - 24)
        page.wait_for_timeout(2500)
        # 按 aria-label 精确找那一行：写的是「勾掉：<任务原文>」
        exact = page.locator(f"button.tick[aria-label='勾掉：{target.get('text')}']")
        tick = exact if exact.count() else page.locator(".tick").first
        check("计划浮层里能点到勾选按钮", tick.count() > 0, page.locator(".layer[role='dialog']").first.get_attribute("aria-label") or "")
        if tick.count():
            tick.click()
            page.wait_for_timeout(4000)  # 勾完这一下会带一轮后台重拉
        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)

        after_text = progress_bubble(page)
        after_done = done_count(after_text)
        check(
            "勾掉一件之后，画布上那块「待办」跟着 +1（不是停在点之前那句）",
            after_done == before_done + 1,
            f"{before_text!r} → {after_text!r}",
        )

        # ── 日历那一天：同一件事应当显示「已做」 ──────────────────
        day = str(target.get("due_date") or "")[:10]
        if not day:
            print("  （这一件没有截止日，日历那一条跳过 —— 不属于失败）")
        elif day != today:
            print(f"  （勾掉的那一件到期在 {day}，而日历停在今天，这一条跳过 —— 不属于失败）")
        else:
            calendar = page.locator("[data-block='calendar']").first
            if calendar.count():
                # 用块里那颗「看今天」打开：日历那一块整体**不是**一个可点的大按钮
                # （里面的每一格自己要能点，按钮里嵌按钮是无效结构），所以按坐标
                # 点空白处什么都不会发生 —— 这一条必须点一个明确的入口。
                today_chip = calendar.locator("button.chip")
                if today_chip.count():
                    today_chip.first.click()
                else:
                    cbox = calendar.bounding_box()
                    page.mouse.click(cbox["x"] + 40, cbox["y"] + cbox["height"] - 24)
                page.wait_for_timeout(2500)
                sheet = page.locator(".day-sheet").first
                text = sheet.inner_text() if sheet.count() else ""
                # 一行是一条 `<li>`：状态（已做/待做）与正文是两个 `<span>`，
                # 按行取会让它们分开。所以按 li 取整行，再看这一行里有没有「已做」。
                line = ""
                rows = sheet.locator("li")
                for index in range(rows.count()):
                    row_text = rows.nth(index).inner_text().replace("\n", " ")
                    if str(target.get("text") or "")[:8] in row_text:
                        line = row_text.strip()
                        break
                check(
                    "那件事在日历里是「已做」（两个浮层读的是同一份事实）",
                    bool(line) and "已做" in line,
                    line or f"那一天没看到这件事（{day}）· 整块：{text[:120]!r}",
                )
            else:
                print("  （画布上这一刻没有日历块，日历那一条跳过 —— 不属于失败）")

        browser.close()

    passed = sum(1 for item in results if item["ok"])
    print(f"\n===== 组件联动：{passed}/{len(results)} 通过 =====")
    for item in results:
        if not item["ok"]:
            print(f"  FAIL  {item['check']} — {item['detail']}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
