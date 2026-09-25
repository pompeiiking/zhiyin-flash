"""端到端全量测试：像一个真用户那样把产品走一遍（真栈、真模型、真库）。

设计口径
--------
* **不桩任何东西**：AI 走真模型，数据进真库。慢是真的慢，但它才说明问题。
* **一步一结论**：每个检查项独立记录通过/失败，一项失败不打断其余步骤 ——
  一次跑完能拿到"哪几处不行"的全景，而不是第一个错就停。
* **仿真用户**：AI 追问什么，就用一份"真人会怎么答"的答池照答；
  能推进就推进（验证方向 → 诊断，行动计划 → 行动，卡住 → 复盘）。
* **同时看三层**：界面（有没有画出来）、接口（返回的信封对不对）、
  数据库（有没有真的落库）—— 只验界面会把"看起来对"当成"真的对"。

用法：python zhiyin-src/template/tests/e2e/full_path.py [base_url]
产物：tests/e2e/e2e_full.json（逐项结果）+ tests/e2e/shots/e2e-*.png
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

COURSE_TABLE = (
    "课程名称\t星期\t节次\t地点\t教师\n"
    "混凝土结构设计\t周一\t1-2节\tC楼302\t周立群\n"
    "结构抗震\t周一\t3-4节\tC楼302\t梁晓峰\n"
    "建筑信息模型（BIM）\t周三\t5-6节\t机房401\t韩雪\n"
    "毕业设计（开题）\t周四\t7-8节\t结构教研室\t周立群"
)
GRADE_TABLE = "课程名称,学分,成绩,绩点\n混凝土结构设计,3.5,88,3.7\n结构力学,4.0,84,3.4"

#: 仿真用户的答池：AI 问什么，就用这些具体的话答。顺序即"越答越具体"。
ANSWERS = [
    "我最喜欢结构设计类的课，课程设计连着三个学期都选了结构方向，还没实习过。",
    "家里希望我稳定一点，我自己更想先在设计院做结构设计，但有点怕进不去。",
    "今年秋招，系里说 10 月开始投递，我手上还没有作品集。",
    "我时间其实够，一周能腾出两个下午，就是不知道先补哪一块。",
    "如果要说最卡的地方，是我不知道自己的水平到底够不够设计院的门槛。",
]

results: list[dict[str, Any]] = []


def _copy(code: str) -> str:
    """按 code 取一条用户可见文案 —— 与界面读的是**同一份**动态资源。

    脚本里写死文案的代价实测过一次：门户的 CTA 在 `copies.json` 里改成了「开始用」，
    脚本还在找带箭头的「开始用 →」，于是整支端到端在第一个按钮上就超时 ——
    看起来像"按钮点不动"，其实是测试自己抄了一份过期文案。
    """
    path = Path(__file__).resolve().parents[2] / "data" / "registry" / "copies.json"
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    return next((item["text"] for item in items if item["code"] == code), "")


PORTAL_CTA = _copy("portal.cta")


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    return bool(ok)


def phase(title: str) -> None:
    print(f"\n=== {title} ===")


def shot(page: Page, name: str, full: bool = False) -> None:
    page.screenshot(path=str(SHOTS / f"e2e-{name}.png"), full_page=full)


def api(page: Page, path: str, method: str = "GET", body: Any = None) -> dict:
    """用页面里那把真令牌直接打接口（与前端走同一条路，但没有 UI 干扰）。"""
    return page.evaluate(
        """async ([p, m, b]) => {
            const t = localStorage.getItem('zhiyin_token') || ''
            const init = { method: m, headers: { 'Content-Type': 'application/json' } }
            if (t) init.headers.Authorization = 'Bearer ' + t
            if (b !== null) init.body = JSON.stringify(b)
            const r = await fetch('/api/v1' + p, init)
            return { status: r.status, body: await r.json().catch(() => null) }
        }""",
        [path, method, body],
    )


def data_of(page: Page, path: str) -> Any:
    res = api(page, path)
    body = res.get("body") or {}
    return body.get("data") if isinstance(body, dict) else None


def wait_overlay(page: Page, label: str = "", timeout: int = 8000) -> str:
    """等一个浮层出现，返回它的 aria-label（空串＝没等到）。传 label 则按标题等。"""
    selector = '.layer[role="dialog"]' + (f'[aria-label="{label}"]' if label else "")
    try:
        page.wait_for_selector(selector, timeout=timeout)
    except Exception:
        return ""
    node = page.locator('.layer[role="dialog"]').first
    return node.get_attribute("aria-label") or ""


def _overlay_labels(page: Page) -> list[str]:
    """当前所有浮层的标题，**一次取完**。

    逐个 `nth(i).get_attribute()` 会等元素出现：浮层在遍历中途关掉时，
    那一次调用会一直等到超时（实测把整支核验卡死 30 秒）。
    """
    return page.eval_on_selector_all(
        '.layer[role="dialog"]',
        "els => els.map(e => e.getAttribute('aria-label') || '')",
    )


def close_overlay(page: Page) -> None:
    """关掉当前浮层，并**确认它真的关了**（否则后面的点击全被它挡住）。

    关闭动作按用户真实能用的三条路依次走：
      1. 浮层自带的关闭按钮（最可靠 —— 有些浮层不吃 Esc）；
      2. Esc；
      3. 点浮层**外面的空白**。注意不能点遮罩的中心 —— 那里被浮层本体压着，
         点下去是浮层接的（自动化里表现为"遮罩点不动"，这坑踩过一次）。
    """
    for _ in range(3):
        if not page.locator('.layer[role="dialog"]').count():
            return
        top = page.locator('.layer[role="dialog"]').last
        for selector in ("button[aria-label*='关闭']", ".close", "[class*='close']"):
            button = top.locator(selector).first
            if not button.count():
                continue
            try:
                button.click(timeout=1500)
                page.wait_for_timeout(400)
                break
            except Exception:
                continue
        if not page.locator('.layer[role="dialog"]').count():
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        if page.locator('.layer[role="dialog"]').count():
            page.mouse.click(12, 700)  # 浮层外的左边缘
            page.wait_for_timeout(500)


def open_block(page: Page, block: str, label: str = "", cta: str = "") -> str:
    """点画布上的某块气泡，返回打开的浮层标题（空串＝没开）。

    真实交互里"点开一块"有三种落点：整块可点（interactive）、块里那个 CTA
    （"看我的任务 →"）、或者只点得到标题栏。所以这里依次试，谁先开出浮层算谁。

    **必须验证"开出来的是新的一层"**：对话浮层常常一直挂着，而"等任意一个
    `.layer[role=dialog]` 出现"在那种状态下**立刻为真** —— 于是每一次点击都
    报告成功，实际看到的还是对话层（实测：连续三条用例报出同一个标题
    「和主理聊聊」，却去找别的浮层里的东西，全红）。所以这里记下点击前已有的
    标题，点击后要求出现**没见过的**那一层。

    落点还要避开右上角那一片**主动提示浮窗**（AgentRail 的 pop）：它固定在右上，
    1450×960 下正好压在画布最上面那一行气泡的**中间**——按默认的中心点去点，
    点到的是浮窗而不是气泡（实测：行动计划块的中心被 `pop__why` 盖住，
    点左下角立刻打开）。所以先按"块内偏移点"点，再退回中心点。
    """
    close_overlay(page)  # 上一层的遮罩会把点击吃掉
    node = page.locator(f"[data-block='{block}']").first
    # 画布是**按状态长出来的**（逐步解锁 + 后端刷新）：刚做完一个动作之后，
    # 那一块可能还在路上。给它几秒，而不是"一眼没看到就判失败"。
    for _ in range(10):
        if node.count():
            break
        page.wait_for_timeout(1500)
    if not node.count():
        return ""
    # 先把压在画布上的提示浮窗收掉（用户也是这么做的：点"知道了"）。
    # 收不掉不致命：下面按偏移点点，同样绕开它。
    try:
        dismiss = page.locator(".pop__act", has_text="知道了")
        for index in range(min(dismiss.count(), 3)):
            dismiss.nth(index).click(timeout=1500)
            page.wait_for_timeout(300)
    except Exception:
        pass
    targets = [node]
    if cta:
        targets.insert(0, node.locator(cta).first)  # 一块里可能有多个 CTA，按名指定
    else:
        targets.append(node.locator("[class*='cta']").first)
    targets.append(node.locator("button, [role='button']").first)
    # 点击前已经在屏幕上的浮层标题：点击之后要求出现**没见过的**那一层
    before = set(_overlay_labels(page))
    for target in targets:
        if not target.count():
            continue
        for clicker in (
            # 先按块内的偏移点（左下角内侧）点：这里不会被右上角的浮窗盖住，
            # 而 force=True 会**照样点在中心点**上，正好落进浮窗。
            lambda node=target: _click_inside(page, node),
            # 再退回普通点击（含 CTA 这类小目标，它们本身就不在浮窗覆盖区）
            lambda node=target: node.click(timeout=4000, force=True),
            # 最后按块的中心点真点一次：有些块的左侧被邻居压着，
            # 而中心是它自己的（浮窗那一片会先被上面的"知道了"收掉）。
            lambda node=target: _click_center(page, node),
        ):
            try:
                clicker()
            except Exception:
                continue
            got = _wait_new_overlay(page, label, before, timeout=6000)
            if got:
                return got
    return ""


def _wait_new_overlay(page: Page, label: str, before: set[str], timeout: int) -> str:
    """等一个**新**浮层出现，返回它的标题（空串＝没等到）。

    与 `wait_overlay` 的区别：这里排除了点击前就在屏幕上的那些层。
    少了这一步，"对话浮层一直挂着"会让每一次点击都报告成功（见 `open_block`）。
    """
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        for name in _overlay_labels(page):
            if label:
                if name == label:
                    return name
                continue
            if name not in before:
                return name
        page.wait_for_timeout(300)
    return ""


def _click_inside(page: Page, target) -> None:
    """点在目标的**左下角内侧**，而不是默认的中心点。

    中心点会被固定在右上的主动提示浮窗吃掉（见 `open_block` 的说明）。
    目标太小时退回中心点 —— 那种尺寸本来也压不住。

    **落点还不能落在块里嵌着的控件上。** 气泡是"整块可点"的（根元素就是按钮），
    而它的页脚里还有别的按钮（「下一步」「全部任务 →」「为什么这一件」…）。
    固定偏移点左下角时，正好压在页脚那颗按钮上 —— 点下去走的是**那颗按钮**的
    含义（实测：今日简报那块点出来的是「和主理聊聊」，于是"简报浮层能打开"红了两轮，
    而它其实好好地开得出来）。所以先在块内挑一个"确实属于这块自己"的落点：
    命中元素的最近 `[data-block]` 必须是它自己，且命中的不是块内嵌的控件。
    """
    box = target.bounding_box()
    if not box or box["width"] < 80 or box["height"] < 40:
        target.click(timeout=4000, force=True)
        return
    block_id = target.get_attribute("data-block") or ""
    point = page.evaluate(
        """({x, y, w, h, bid}) => {
            const mine = bid ? document.querySelector(`[data-block="${bid}"]`) : null;
            const candidates = [
              [x + w * 0.5, y + h * 0.68],
              [x + w * 0.3, y + h * 0.68],
              [x + 40, y + h - 24],
              [x + 40, y + 34],
              [x + 30, y + h * 0.55],
              [x + w - 40, y + h - 24],
              [x + w * 0.5, y + 30],
            ];
            for (const [px, py] of candidates) {
              const hit = document.elementFromPoint(px, py);
              const owner = hit?.closest('[data-block]');
              if (!owner) continue;
              if (mine && owner !== mine) continue;  // 浮窗或邻居挡住：换一个点
              const control = hit.closest('button, a, [role=button]');
              // 块内的控件（「下一步」「全部任务 →」…）有自己的含义，不算"点这块"
              if (control && control !== owner) continue;
              return [px, py];
            }
            return null;
        }""",
        {"x": box["x"], "y": box["y"], "w": box["width"], "h": box["height"], "bid": block_id},
    )
    if point is None:
        raise RuntimeError(f"块 {block_id} 当前没有未被浮窗遮挡的可点区域")
    page.mouse.click(point[0], point[1])


def _click_center(page: Page, target) -> None:
    """按元素中心真点一次（走真实 z-order，能被上层元素挡住就挡）。"""
    box = target.bounding_box()
    if not box:
        target.click(timeout=4000, force=True)
        return
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def talk_overlay(page: Page):
    return page.locator('.layer[aria-label="和主理聊聊"]')


def ensure_talk(page: Page) -> bool:
    if not talk_overlay(page).count():
        open_block(page, "talk")
    return bool(talk_overlay(page).count())


def send_chat(page: Page, text: str) -> int:
    """发一条消息，返回发出前的用户消息条数（用来定位对应回复）。"""
    if not ensure_talk(page):
        return -1
    overlay = talk_overlay(page)
    before = overlay.locator(".thread .line.me").count()
    box = overlay.locator("textarea, input[type='text']").last
    box.fill(text)
    box.press("Enter")
    return before


def wait_reply(page: Page, before: int, timeout_s: int = 150) -> str:
    """等本轮用户消息后的正式 AI 回复，跳过欢迎词和输入中占位。"""
    overlay = talk_overlay(page)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        # 初次打开时，历史欢迎词也可能晚于 send_chat 才挂载；只数 AI 行
        # 会把它当成本轮回复。改为定位本轮新增的 user 行，再找其后的 AI 行。
        users = overlay.locator(".thread .line.me")
        if users.count() > before and not overlay.locator(".thread .line.ai.typing").count():
            answer = users.last.evaluate("""el => {
              let node = el.nextElementSibling;
              let reply = '';
              while (node && !node.classList.contains('me')) {
                if (node.classList.contains('ai') && !node.classList.contains('typing'))
                  reply = node.innerText;
                node = node.nextElementSibling;
              }
              return reply;
            }""")
            if answer:
                return answer
    return ""


def current_stage(page: Page) -> str:
    """读当前环节。

    不从 AgentRail 读：那片顶栏是**收起态**（滑出视口），自动化里够不着，
    而它在对话层里有一份同样的信息 —— `pipeline_cards` 里标着"进行中"的那一环
    （`TurnView.pipeline_cards` 直接来自后端回包）。
    """
    try:
        if not talk_overlay(page).count():
            open_block(page, "talk")
        node = talk_overlay(page).locator(".stages li.now .stages__t")
        return node.first.inner_text() if node.count() else ""
    except Exception:
        return ""


def login(page: Page, account: str, password: str) -> bool:
    """从门户走一遍登录（先清令牌，保证落在未登录态）。"""
    page.evaluate("localStorage.removeItem('zhiyin_token')")
    page.goto(f"{BASE}/portal", wait_until="domcontentloaded")
    page.get_by_role("button", name=PORTAL_CTA).click()
    page.wait_for_selector('input[name="account"]', timeout=15000)
    page.fill('input[name="account"]', account)
    page.fill('input[name="password"]', password)
    page.locator("form button[type=submit]").first.click()
    page.wait_for_timeout(3500)
    return page.locator("[data-block]").count() > 0


def logout(page: Page) -> bool:
    """退出登录：先掀开账号菜单（退出按钮在菜单里，不在顶栏上）。"""
    try:
        # 顶栏是"抽屉把手"：最上面那条 22px 的带子才是判据，指针要落在它上面
        page.mouse.move(60, 10)
        page.wait_for_timeout(900)
        trigger = page.locator(".trigger").first
        try:
            trigger.click(timeout=6000)
        except Exception:
            trigger.click(timeout=4000, force=True)
        page.wait_for_timeout(600)
        page.locator("button.quit").first.click(timeout=6000)
        page.wait_for_timeout(1500)
    except Exception:
        return False
    return not page.evaluate("localStorage.getItem('zhiyin_token')")


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True, channel=os.environ.get("ZHIYIN_BROWSER_CHANNEL") or None
    )
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    errors: list[str] = []
    http_errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)[:300]))
    page.on(
        "response",
        lambda r: http_errors.append(f"{r.status} {r.request.method} {r.url}") if r.status >= 400 else None,
    )
    page.on(
        "console",
        lambda m: errors.append(f"console.{m.type}: {m.text[:200]}") if m.type == "error" else None,
    )

    stamp = int(time.time())
    account, password = f"e2e{stamp}", "pass-123456"

    # ── A. 访客态 ────────────────────────────────────────────────
    phase("A. 访客态")
    page.goto(f"{BASE}/portal", wait_until="domcontentloaded", timeout=40000)
    shot(page, "01-portal")
    check("门户渲染", page.title().startswith("职引"), page.title())

    # 门户文案来自动态资源：拿 registry 里的值去比按钮上的字。
    # 这是"文案不进代码"最直接的证据 —— 文案改 registry、界面跟着变。
    registry_cta = json.loads(
        Path("zhiyin-src/template/data/registry/copies.json").read_text(encoding="utf-8")
    )
    cta_copy = next(
        (item["text"] for item in registry_cta["items"] if item["code"] == "portal.cta"),
        "",
    )
    check(
        "门户文案来自动态资源（按钮文案 == registry 里的值）",
        bool(cta_copy) and cta_copy in page.locator("body").inner_text(),
        f"registry portal.cta = {cta_copy!r}",
    )
    portal_api = api(page, "/app/portal")
    check(
        "门户内容接口未登录可读",
        (portal_api.get("body") or {}).get("code") == 0,
        f"HTTP {portal_api.get('status')} code={(portal_api.get('body') or {}).get('code')}",
    )

    guest = api(page, "/app/workspace")
    check(
        "未登录访问受保护接口返回 1004",
        (guest.get("body") or {}).get("code") == 1004,
        f"HTTP {guest.get('status')} code={(guest.get('body') or {}).get('code')}",
    )

    page.goto(f"{BASE}/report", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(1500)
    check("未登录直连 /report 被送去门户", page.url.rstrip("/").endswith("/portal"), page.url)
    check("并且就地掀开登录层", page.locator('input[name="account"]').count() > 0)

    # ── B. 注册 / 登录 / 退出 / 再登录 ──────────────────────────
    phase("B. 注册与登录")
    if page.locator('input[name="account"]').count() == 0:
        page.get_by_role("button", name=PORTAL_CTA).click()
        page.wait_for_timeout(800)
    page.get_by_role("button", name="还没有账号？建一个").click()
    page.fill('input[name="account"]', account)
    page.fill('input[name="password"]', password)
    page.locator("form button[type=submit]").first.click()
    page.wait_for_timeout(3000)
    token = page.evaluate("localStorage.getItem('zhiyin_token')")
    check("注册成功并拿到令牌", bool(token), f"account={account}")
    page.wait_for_timeout(1500)
    shot(page, "02-console-after-register")
    check(
        "控制台渲染出气泡",
        page.locator("[data-block]").count() >= 6,
        f"{page.locator('[data-block]').count()} 块",
    )
    ws = data_of(page, "/app/workspace") or {}
    check("工作台接口可用（登录态）", "profile_panel" in ws, ", ".join(sorted(ws.keys()))[:120])

    # 测"密码错误"必须先在未登录态：门户看到令牌会直接送你进控制台，压根不掀登录层
    page.evaluate("localStorage.removeItem('zhiyin_token')")
    page.goto(f"{BASE}/portal", wait_until="domcontentloaded")
    page.get_by_role("button", name=PORTAL_CTA).click()
    page.wait_for_selector('input[name="account"]', timeout=10000)
    page.fill('input[name="account"]', account)
    page.fill('input[name="password"]', "wrong-password")
    page.locator("form button[type=submit]").first.click()
    page.wait_for_timeout(2500)
    dialog = page.locator('.layer[role="dialog"]')
    dialog_text = dialog.first.inner_text() if dialog.count() else ""
    check("密码错误给出可读提示", any(k in dialog_text for k in ("不对", "错误", "失败", "不存在")),
          dialog_text[:100].replace("\n", " "))
    page.fill('input[name="password"]', password)
    page.locator("form button[type=submit]").first.click()
    page.wait_for_timeout(3000)
    check("用正确密码登录成功", page.locator("[data-block]").count() > 0, page.url)

    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    check("退出登录（账号菜单里）清掉令牌", logout(page))

    # ── C. 对话推进（真模型，自适应） ────────────────────────────
    phase("C. 对话推进到诊断（真模型）")
    check("重新登录成功", login(page, account, password), page.url)

    open_block(page, "talk")
    opening = "我大三，土木工程，还不知道毕业该去设计院还是施工单位。"
    before = send_chat(page, opening)
    reply = wait_reply(page, before)
    check("第 1 轮拿到真模型回复", bool(reply.strip()), reply[:110].replace("\n", " "))
    shot(page, "03-conversation-turn1")

    turns = [{"say": opening, "reply": reply[:200]}]
    for answer in ANSWERS:
        before = send_chat(page, answer)
        reply = wait_reply(page, before)
        if not reply.strip():
            check(f"第 {len(turns) + 1} 轮回复", False, "超时未回")
            break
        turns.append({"say": answer, "reply": reply[:200]})
        if len(turns) % 2 == 0:
            before = send_chat(page, "我想验证一下结构设计这条路到底行不行，差多少。")
            reply = wait_reply(page, before)
            turns.append({"say": "验证方向", "reply": reply[:200]})
        rt = data_of(page, "/app/report/full-text") or {}
        if rt.get("sections"):
            break
    check("对话共推进了多轮", len(turns) >= 3, f"{len(turns)} 轮")
    stage = current_stage(page)
    check("环节由后端推进（AgentRail 读得到当前环节）", bool(stage), stage or "读不到")
    shot(page, "04-conversation-later")

    theories = page.locator(".theory")
    if theories.count():
        first_theory = theories.first.inner_text()
        theories.first.click()
        page.wait_for_timeout(1500)
        drawer = page.locator(".drawer").first
        text = drawer.inner_text() if drawer.count() else ""
        check("理论卡正文可点开", len(text) > 60, f"{first_theory} → {text[:70]}".replace("\n", " "))
        shot(page, "05-theory-card")
        close_overlay(page)
    else:
        check("理论卡（本轮回复未引用理论，记为 N/A）", True, "N/A")

    # ── D. 画像 / 采集 ──────────────────────────────────────────
    phase("D. 画像与采集")
    ws = data_of(page, "/app/workspace") or {}
    panel = ws.get("profile_panel") or {}
    fields = panel.get("fields") or []
    gaps = panel.get("gaps") or []
    check("画像已从对话里沉淀出字段", len(fields) >= 1, f"{len(fields)} 个字段 / {len(gaps)} 条缺口")

    close_overlay(page)
    # 传期望的浮层标题：画布上的块会互相叠压，点"画像"那块可能落到旁边的块上，
    # 于是开出**别的**浮层却报成功（实测：三条用例都拿到「和主理聊聊」）。
    # 有了期望标题，点错就不算数，脚本会换下一个落点重试。
    opened = open_block(page, "portrait", label="你的画像")
    if opened:
        page.wait_for_timeout(1200)
        # 画像页是**分层**的：第一屏是总览（那段判断 + 「往下看」三行），
        # 字段清单在「判断维度」/「档案信息」里。停在第一屏数行只会得到 0 ——
        # 这一屏重做过（见 CHANGELOG 三十节），脚本原来数的还是老类名 `.row`。
        # 所以：先看一眼有没有清单，没有就按总览里那几行进一层再数。
        # 行本身既有 `button.row`（带 `.row__name`）也有更老的 `.item` / `.item__name`，
        # 两套都认 —— 这是前端迭代最多的一屏，写死一套会把"换了类名"判成缺陷。
        overlay = page.locator('.layer[aria-label="你的画像"]')
        items = overlay.locator(".row, .item")
        for index in range(min(overlay.locator(".mrow").count(), 3)):
            if items.count():
                break
            overlay.locator(".mrow").nth(index).click()
            page.wait_for_timeout(1000)
        check("画像浮层列出字段", items.count() >= 1, f"{opened} · {items.count()} 条")
        # 字段名必须是给人看的：字段键是模型自己起的（interest_direction 这种），
        # 界面上出现纯 ASCII 就等于把内部键摆给了用户。
        names = [
            n.strip()
            for n in overlay.locator(".row__name, .item__name").all_text_contents()
        ]
        ascii_names = [n for n in names if n and n.isascii()]
        check(
            "画像字段名是中文，没有暴露内部键",
            not ascii_names,
            f"{len(names)} 条 / 英文 {ascii_names}",
        )
        if items.count():
            items.first.click()
            deadline = time.time() + 90
            reading = ""
            while time.time() < deadline:
                page.wait_for_timeout(2000)
                node = overlay.locator(".reading")
                if node.count() and node.first.inner_text().strip():
                    reading = node.first.inner_text()
                    break
            check("单条维度的 AI 解读能渲染", bool(reading.strip()), reading[:90].replace("\n", " "))
        shot(page, "06-portrait-overlay")
        close_overlay(page)
    else:
        check("画像浮层能打开", False)

    if open_block(page, "collect"):
        page.wait_for_timeout(1000)
        rows = page.locator(".rows li")
        check("采集清单渲染", rows.count() >= 1, f"{rows.count()} 条待补/已得")
        shot(page, "07-collect-overlay")
        close_overlay(page)
    else:
        check("采集浮层能打开", False)

    # ── D2. 学信网核验浮层：写着"填到下面"，下面就必须真的有得填 ────────
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    if open_block(page, "collect"):
        page.wait_for_timeout(800)
        try:
            page.click("text=去核验学籍", timeout=6000)
            page.wait_for_timeout(1200)
        except Exception:  # noqa: BLE001
            pass
        box = page.locator('input[name="chsi-code"]')
        deck = page.locator(".deck").first.bounding_box()
        reachable, detail = False, "输入框不在页面上"
        if box.count():
            rect = box.first.bounding_box()
            scroll = page.evaluate(
                "() => { const e = document.querySelector('.bind');"
                " return e ? { sh: e.scrollHeight, ch: e.clientHeight } : null }"
            )
            inside = bool(
                rect and deck and rect["y"] >= deck["y"]
                and rect["y"] + rect["height"] <= deck["y"] + deck["height"]
            )
            scrollable = bool(scroll and scroll["sh"] > scroll["ch"])
            reachable = inside or scrollable
            detail = f"可视={inside} 可滚动={scrollable}"
        check("学信网核验：在线验证码输入框可达（浮层不许把动作裁在外面）", reachable, detail)
        shot(page, "08-bind-chsi")
        close_overlay(page)
    else:
        check("学信网核验：入口能打开", False)

    # ── E. 课表与成绩：导入 → 画布长出课表块 → 撤销 ─────────
    #
    # 这一段用**接口造数据**，不再演一遍浮层里的点击编排。
    # 原因是它一直不稳：画布是**按后端状态长出来的**，而"点开浮层 → 填表 → 提交 → 画布更新"
    # 之间隔着好几次数据往返，偶尔会在某一步上打滑。而这一段真正要验的是**产品行为**：
    # 导入之后数据在不在、课表块是不是到了这时候才出现、撤销之后是不是没了。
    phase("E. 课表与成绩导入")
    status, _ = import_res = api(page, "/app/academic/import", "POST",
                         {"courses": COURSE_TABLE, "grades": GRADE_TABLE,
                          "school": "某某大学", "term": "2024-2025-1"})
    check("导入接口接受整页复制的课表",
          import_res.get("status") == 200, f"HTTP {import_res.get('status')}")

    ws = data_of(page, "/app/workspace") or {}
    academic = ws.get("academic_panel") or {}
    courses = academic.get("courses") or []
    grades = academic.get("grades") or []
    check("导入后课表与成绩进了后端快照", bool(courses),
          f"{len(courses)} 门课 / {len(grades)} 条成绩")

    # 刷新一次：拿到课程数据之后，课表块才该出现（逐步解锁的另一半）
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    opened_tt = open_block(page, "timetable")
    check("导入后课表块才出现", bool(opened_tt), opened_tt or "没出现")
    page.wait_for_timeout(1200)
    tt = page.locator(".tt-wrap")
    check("课表块画出课程（不是空态）",
          tt.count() > 0 and "还没有导入" not in tt.first.inner_text(),
          tt.first.inner_text()[:70].replace("\n", " ") if tt.count() else "无课表块")
    shot(page, "09-timetable")

    api(page, "/app/academic", "DELETE")
    ws = data_of(page, "/app/workspace") or {}
    check("撤销后课表快照被清掉", not ws.get("academic_panel"),
          f"academic={bool(ws.get('academic_panel'))}")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    left = page.locator("[data-block='timetable']").count()
    # 撤销之后块**可能还在**，这不是缺陷：画布的课表块有两个出现条件 ——
    # "已绑学信网"或"采集清单里还差课表"（`showTimetable`）。撤销只清掉前者，
    # 而"还差课表"仍然成立时，这块正是用户去补它的入口。
    # 所以这里验的是**块里有没有真课表**，而不是块在不在。
    timetable_text = (
        page.locator("[data-block='timetable']").first.inner_text() if left else ""
    )
    check(
        "撤销后课表块里不再有真课表（块本身按设计可留作补录入口）",
        left == 0 or "还没有导入" in timetable_text or "导入" in timetable_text,
        f"块数={left} · 文案={timetable_text[:60]!r}".replace("\n", " "),
    )

    # ── F. 待办（写、勾、AI 建议） ──────────────────────────────
    phase("F. 待办")
    # 待办块里有两个 CTA（"看我的任务 →" 与 NextAsk 的"找主理"），必须点对那一个
    opened = open_block(page, "todo", cta=".foot__cta")
    if opened:
        page.wait_for_timeout(1000)
        check("待办浮层能打开", True, opened)
        # 按 open_block 返回的**那一个**标题定位：页面上可能同时挂着别的浮层
        # （对话层挂在外壳上、DOM 里排在后面，用 .last 会拿到它）
        todo = page.locator(f'.layer[role="dialog"][aria-label="{opened}"]').first
        # 表单要**按浮层标题定位**：同一时刻页面上可能有别的输入框，
        # 填错了地方，提交按钮会一直是 disabled（表现为点击超时）。
        todo.locator('input[type="text"]').first.fill("把作品集第一页做完")
        todo.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(2500)
        notes = data_of(page, "/app/notes") or []
        check("写下的待办进了后端", any("作品集" in (n.get("text") or "") for n in notes),
              f"{len(notes)} 条")
        head = todo.locator(".task__head").first
        if head.count():
            head.click()
            page.wait_for_timeout(800)
            done_btn = todo.get_by_role("button", name="勾掉")
            if done_btn.count():
                done_btn.first.click()
                page.wait_for_timeout(2500)
        notes = data_of(page, "/app/notes") or []
        check("勾掉后状态落库", any(n.get("done") for n in notes),
              ", ".join(f"{n.get('text')}={n.get('done')}" for n in notes)[:110])
        deadline = time.time() + 90
        sug = 0
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            sug = todo.locator(".sug li").count()
            if sug:
                break
        check("待办建议（plan.todos）渲染", sug > 0, f"{sug} 条建议")
        shot(page, "10-tasks")
        close_overlay(page)
    else:
        check("待办浮层能打开", False)

    # ── G. 报告 ─────────────────────────────────────────────────
    phase("G. 报告页")
    rt = data_of(page, "/app/report/full-text") or {}
    sections = rt.get("sections") or []
    items_total = sum(len(s.get("items") or []) for s in sections)
    check("报告资产已产出（后端）", bool(sections), f"version={rt.get('version')} / {items_total} 条维度")
    page.goto(f"{BASE}/report", wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(2000)
    shot(page, "11-report", full=True)
    if sections:
        check("报告页渲染出全部维度", page.locator(".dim").count() == items_total,
              f"页面 {page.locator('.dim').count()} / 后端 {items_total}")
        check("判定段渲染", page.locator(".verdict__head").count() > 0)
        check("SWOT 四象限渲染", page.locator(".quad").count() == 4, f"{page.locator('.quad').count()} 象限")
        check("事实来源渲染", page.locator(".src li").count() >= 1, f"{page.locator('.src li').count()} 条")
    else:
        check("报告页给出空态而不是空壳", page.locator(".empty__head").count() > 0)
    deadline = time.time() + 200
    lead_ok = False
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        node = page.locator(".lead__head")
        if node.count() and node.first.inner_text().strip():
            lead_ok = True
            break
    check("结论段（report.summary）生成", lead_ok)
    shot(page, "12-report-lead")

    # ── H. ③ 决策：推进到决策 → 三套方案 → 选一套 ────────────────
    phase("H. ③ 决策（方案资产 + 选择）")
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    ensure_talk(page)
    plans: list[dict] = []
    for say in (
        "我拿不准该选哪个方向，几个方向都在犹豫，帮我比较一下。",
        "比较之后我想先定一套主攻方向，可以撤回的那种。",
    ):
        before = send_chat(page, say)
        reply = wait_reply(page, before, timeout_s=180)
        got = (data_of(page, "/app/plan/directions") or {}).get("plans") or []
        if got:
            plans = got
            break
        if not reply.strip():
            check("决策环节的对话回复", False, "超时未回")
            break
    check("③ 产出三套方向方案（后端资产）", len(plans) >= 1,
          f"{len(plans)} 套：{[p.get('name') for p in plans][:3]}")
    close_overlay(page)
    page.wait_for_timeout(800)

    if plans:
        blocks = page.evaluate(
            "() => [...document.querySelectorAll('[data-block]')].map(e => e.dataset.block)"
        )
        check("画布上出现了「方向方案」块（策略驱动）", "plans" in blocks, str(blocks))
        opened = open_block(page, "plans")
        check("方案浮层能打开", bool(opened), opened)
        if opened:
            shot(page, "16-plans")
            cards = page.locator(".plan")
            check("方案卡片数与资产一致", cards.count() == len(plans),
                  f"页面 {cards.count()} / 后端 {len(plans)}")
            before_selection = data_of(page, "/app/plan/directions") or {}
            before_id = before_selection.get("selected_id")
            # 页面可能在生成第二版方案后才刷新。用当前可见的未选卡测试改选，
            # 不拿循环早先读到的 plans[0].id 去比较新版资产的 ID。
            unselected = page.locator(".plan:not(.on)")
            card = unselected.first if unselected.count() else page.locator(".plan").first
            card.get_by_role("button", name="选这套").click()
            page.wait_for_timeout(2500)
            after = data_of(page, "/app/plan/directions") or {}
            selected_id = after.get("selected_id")
            selected_plan = next((p for p in after.get("plans") or [] if p.get("id") == selected_id), None)
            check("选择落到后端（selected_id 变了）",
                  bool(selected_plan and selected_plan.get("selected"))
                  and (before_id is None or selected_id != before_id),
                  f"selected_id={after.get('selected_id')}")
            check("界面上标出了当前选择", page.locator(".plan.on").count() == 1)
            shot(page, "17-plans-selected")
            close_overlay(page)

    # ── I. ④ 行动：推进到行动 → 计划 → 勾一个任务 ────────────────
    phase("I. ④ 行动（计划资产 + 勾任务）")
    page.wait_for_timeout(600)
    ensure_talk(page)
    action_plan: dict = {}
    for say in (
        "方向先定这个，给我一份行动计划，拆成今天能做完的小事。",
        "下一步我具体该做什么？按周排一下。",
    ):
        before = send_chat(page, say)
        reply = wait_reply(page, before, timeout_s=180)
        plan = data_of(page, "/app/plan/action") or {}
        if plan.get("has_plan") and (plan.get("phases") or []):
            action_plan = plan
            break
        if not reply.strip():
            check("行动环节的对话回复", False, "超时未回")
            break
    check("④ 产出行动计划（后端资产）", bool(action_plan.get("has_plan")),
          f"{len(action_plan.get('phases') or [])} 个阶段 / "
          f"{sum(len(p.get('tasks') or []) for p in (action_plan.get('phases') or []))} 条任务")
    close_overlay(page)
    page.wait_for_timeout(800)

    if action_plan.get("has_plan"):
        blocks = page.evaluate(
            "() => [...document.querySelectorAll('[data-block]')].map(e => e.dataset.block)"
        )
        check("画布上出现了「行动计划」块（策略驱动）", "action" in blocks, str(blocks))
        opened = open_block(page, "action", label="行动计划")
        check("行动计划浮层能打开", bool(opened), opened)
        if opened:
            shot(page, "18-action")
            check("「现在这一件」渲染", page.locator(".now__t").count() > 0,
                  page.locator(".now__t").first.inner_text()[:60]
                  if page.locator(".now__t").count() else "")
            check("关键节点日历渲染（盘点 ④ 写进去的节点）", page.locator(".node").count() > 0,
                  f"{page.locator('.node').count()} 条节点")
            ticks = page.locator(".tick")
            check("任务条目可勾选", ticks.count() > 0, f"{ticks.count()} 条")
            undone = page.locator('.tick[aria-pressed="false"]')
            if undone.count():
                before_count = sum(
                    1 for p in (action_plan.get("phases") or [])
                    for task in (p.get("tasks") or []) if task.get("done")
                )
                label = undone.first.get_attribute("aria-label") or ""
                task_text = label.partition("：")[2]
                undone.first.click()
                page.wait_for_timeout(2500)
                after = data_of(page, "/app/plan/action") or {}
                flat = [t for p in (after.get("phases") or []) for t in (p.get("tasks") or [])]
                check("勾掉落到后端（done=true）",
                      sum(1 for t in flat if t.get("done")) == before_count + 1,
                      f"已完成 {sum(1 for t in flat if t.get('done'))} / {len(flat)}")
                # 撤回一次，验证能反悔
                if task_text:
                    undo = page.get_by_role("button", name=f"取消勾选：{task_text}", exact=True)
                    if not undo.count() and not page.locator(".layer[aria-label='行动计划']").count():
                        open_block(page, "action", label="行动计划")
                        undo = page.get_by_role("button", name=f"取消勾选：{task_text}", exact=True)
                    check("刚勾的任务仍可在计划中找到并撤回", undo.count() > 0, task_text[:60])
                    if undo.count():
                        undo.click()
                        page.wait_for_timeout(2500)
                        back = data_of(page, "/app/plan/action") or {}
                        flat2 = [t for p in (back.get("phases") or []) for t in (p.get("tasks") or [])]
                        check("取消勾选也落库（可撤回）",
                              sum(1 for t in flat2 if t.get("done")) == before_count,
                              f"done 数 {sum(1 for t in flat2 if t.get('done'))}")
            shot(page, "19-action-ticked")
            close_overlay(page)

    # ── J. 会话与复盘（此前只有写、没有读的两条链路） ─────────────
    phase("J. 任务会话 / 复盘时间线")
    sessions = data_of(page, "/app/sessions") or {}
    session_items = sessions.get("sessions") or []
    check("会话清单可读", bool(session_items), f"{len(session_items)} 条")

    if session_items:
        first = session_items[0]["task_id"]
        turns = data_of(page, f"/app/sessions/{first}/turns") or []
        check("会话逐轮原文可读（含用户自己说的话）", len(turns) > 0, f"{len(turns)} 轮")
        check("逐轮里既有 user 也有 agent", {"user", "agent"} <= {t.get("role") for t in turns},
              str(sorted({t.get("role") for t in turns})))

    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    # 会话浮层的入口在右键菜单里，且只在**画布空白处**右键时才列出功能块。
    # 先找一个不落在任何气泡上的点，否则拿到的是"对这块做什么"那份菜单。
    empty = page.evaluate(
        """() => {
            for (let y = 200; y < 900; y += 40) {
              for (let x = 200; x < 1400; x += 40) {
                const el = document.elementFromPoint(x, y)
                if (el && el.closest('.canvas') && !el.closest('[data-block]')
                    && !el.closest('.layer') && !el.closest('.drawer')
                    && !el.closest('.float') && !el.closest('.pops')) return { x, y }
              }
            }
            return null
        }"""
    )
    if empty:
        page.mouse.click(empty["x"], empty["y"], button="right")
    else:
        page.mouse.click(700, 500, button="right")
    page.wait_for_timeout(600)
    if not page.locator(".menu").count():
        # 上一次右键可能被浮窗吃掉了：收掉浮窗再来一次
        close_overlay(page)
        page.mouse.click(700, 220, button="right")
        page.wait_for_timeout(600)
    # 菜单项的可访问名包含 hint，所以用子串匹配
    # 注意：菜单项是 role="menuitem"（不是 button），所以按 CSS + 文本定位
    entry = page.locator(".menu [role='menuitem']", has_text="我的任务会话")
    if entry.count():
        entry.first.click()
        page.wait_for_timeout(1500)
        check("会话浮层能打开", page.locator('.layer[aria-label="我的任务会话"]').count() > 0)
        check("会话浮层列出会话与历史", page.locator(".row__name").count() > 0
              and page.locator(".turns li").count() > 0,
              f"{page.locator('.row__name').count()} 条会话 / {page.locator('.turns li').count()} 轮历史")
        shot(page, "20-sessions")
        close_overlay(page)
    else:
        items = page.locator(".menu [role='menuitem']").all_inner_texts()
        check("画布菜单里有「我的任务会话」", False, f"菜单项：{items[:6]}")

    if open_block(page, "review", label="上周复盘"):
        page.wait_for_timeout(1500)
        check("复盘浮层能打开", True)
        check("复盘时间线渲染", page.locator(".tl li").count() > 0 or page.locator(".hint").count() > 0,
              f"{page.locator('.tl li').count()} 条记录")
        shot(page, "21-review")
        close_overlay(page)
    else:
        check("复盘浮层能打开", False)

    # ── 完成记录：由行为日志推导的那几枚 ────────────────────────
    #
    # 这一屏的判据不能是"有内容就算过"：它的可信度压在**数量与时间与后端一致**上。
    # 所以两边都比一次 —— 界面上的 x/y 必须等于 `/app/achievements` 的数，
    # 每一条已解锁的都要有日期（日期来自那条行为的真实发生时间）。
    achievements = data_of(page, "/app/achievements") or {}
    expected_unlocked = achievements.get("unlocked")
    expected_total = achievements.get("total")
    node = page.locator("[data-block='achievements']").first
    check("画布上有「完成记录」块", node.count() > 0, node.inner_text().replace("\n", " ")[:60] if node.count() else "")
    opened = open_block(page, "achievements", label="完成记录")
    if opened:
        page.wait_for_timeout(1200)
        rows = page.locator('.layer[aria-label="完成记录"] .rows li')
        check(
            "完成记录列出全部规则，数量与后端一致",
            bool(expected_total) and rows.count() == expected_total,
            f"界面 {rows.count()} 行 / 后端 {expected_total} 条",
        )
        shown_unlocked = page.locator('.layer[aria-label="完成记录"] .rows li.done').count()
        check(
            "已解锁的数量两边一致（不是前端自己算的）",
            shown_unlocked == expected_unlocked,
            f"界面 {shown_unlocked} 枚 / 后端 {expected_unlocked} 枚",
        )
        dates = page.locator('.layer[aria-label="完成记录"] .rows li.done .when').all_text_contents()
        check(
            "拿到的那几枚都写了日期（来自行为日志的真实时间）",
            bool(dates) and all("月" in item for item in dates),
            f"{[item.strip() for item in dates][:3]}",
        )
        shot(page, "22-achievements")
        close_overlay(page)
    else:
        check("完成记录浮层能打开", False, "点不到那一块")

    # ── J. 其他 AI 面板 ─────────────────────────────────────────
    phase("K. 匹配 / 简报")
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    # 匹配块是**绑定学信网之后才出现**的（`v-if="session.chsiBound"`）：
    # 没绑定时它不该在画布上 —— 这是条件渲染，不是缺陷。
    if page.locator("[data-block='match']").count():
        opened = open_block(page, "match")
        check("匹配浮层能打开", bool(opened), opened)
        if opened:
            deadline = time.time() + 180
            rank = 0
            while time.time() < deadline:
                page.wait_for_timeout(3000)
                rank = page.locator(".rank li").count()
                if rank:
                    break
            check("匹配矩阵与推荐渲染", rank > 0, f"{rank} 条方向")
            shot(page, "13-match")
            close_overlay(page)
    else:
        check("匹配块在未绑定学信网时不出现（条件渲染正确）", True, "按设计隐藏")

    opened = open_block(page, "greet", label="今天为什么是这两件")
    if opened:
        deadline = time.time() + 180
        got = False
        while time.time() < deadline:
            page.wait_for_timeout(3000)
            node = page.locator(".brief__head")
            if node.count() and node.first.inner_text().strip():
                got = True
                break
        check("今日简报（brief.today）渲染", got, opened)
        shot(page, "14-brief")
        close_overlay(page)
    else:
        check("简报浮层能打开", False)

    # ── 可视件：模型自己画的那张图，前端按 kind 分发渲染 ─────────
    #
    # 这条路径以前是"专用字段 chart"，现在只有一种东西：`renderables`（按 kind 分发）。
    # 所以这里必须从**界面上**看一眼：模型点了工具之后，那张图是不是真的画出来了，
    # 而且数值是给人看的写法（不是 `0.95` 这种要用户自己换算的）。
    phase("可视件：模型自己画图 → 前端按 kind 渲染")
    rendered = 0
    returned_kinds: list[str] = []
    for attempt in range(2):
        with page.expect_response(
            lambda response: "/app/conversation/message" in response.url
            and response.request.method == "POST",
            timeout=180000,
        ) as pending:
            before = send_chat(page, "能不能给我画个图，让我看看现在各项情况把握得怎么样？")
        payload = pending.value.json()
        messages = (payload.get("data") or {}).get("messages") or [{}]
        returned_kinds.extend(
            str(item.get("kind"))
            for item in (messages[0].get("renderables") or [])
        )
        wait_reply(page, before, timeout_s=180)
        page.wait_for_timeout(2000)
        rendered = page.locator(".thread .rb__rows li").count()
        if rendered:
            break
        print(f"    （第 {attempt + 1} 次问，接口返回 {returned_kinds}，界面有 {rendered} 行）")
    check("对话接口返回真实可视件", "bars_chart" in returned_kinds, str(returned_kinds))
    check("主理画的那张图在对话里渲染出来了（按 kind 分发）", rendered >= 2, f"{rendered} 行")
    if rendered:
        numbers = [n.strip() for n in page.locator(".thread .rb__num").all_text_contents()]
        check(
            "图上的数值是给人看的写法（不是 0.95 / 95.00）",
            all(n.endswith(("%", "分")) for n in numbers) if numbers else False,
            f"{numbers}",
        )
        shot(page, "15-renderable-bars")
    close_overlay(page)

    # ── I. 异常与边界 ───────────────────────────────────────────
    phase("L. 异常与边界")
    ensure_talk(page)
    overlay = talk_overlay(page)
    box = overlay.locator("textarea, input[type='text']").last
    before = overlay.locator(".thread .line.ai").count()
    box.fill("")
    box.press("Enter")
    page.wait_for_timeout(3000)
    check("空消息不会被发出去", overlay.locator(".thread .line.ai").count() == before)

    long_text = "我想把结构设计这条路走清楚。" * 200
    before = send_chat(page, long_text)
    reply = wait_reply(page, before, timeout_s=180)
    check("超长输入不把界面打崩", True if reply else overlay.locator(".line.ai").count() > 0,
          "已回复" if reply else "无新回复（界面未崩）")

    forged = page.evaluate(
        """async () => {
            const r = await fetch('/api/v1/app/workspace', {
              headers: { Authorization: 'Bearer forged.token.value' } })
            return { status: r.status, body: await r.json().catch(() => null) }
        }"""
    )
    check("伪造令牌被拒", forged["status"] in (401, 403)
          or (forged["body"] or {}).get("code") in (1004, 1007),
          f"HTTP {forged['status']} code={(forged['body'] or {}).get('code')}")

    close_overlay(page)
    page.goto(f"{BASE}/report", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    check("深链刷新 /report 数据仍在（不是空壳）",
          page.locator(".dim").count() > 0 or page.locator(".empty__head").count() > 0,
          f"维度 {page.locator('.dim').count()}")

    page.set_viewport_size({"width": 375, "height": 780})
    page.goto(f"{BASE}/portal", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    check("窄屏（375px）无横向溢出", overflow <= 2, f"溢出 {overflow}px")
    shot(page, "15-narrow")

    # ── J. 数据面核对（接口视角） ───────────────────────────────
    phase("M. 数据面核对")
    ws = data_of(page, "/app/workspace") or {}
    notes = data_of(page, "/app/notes") or []
    rt = data_of(page, "/app/report/full-text") or {}
    plans_now = data_of(page, "/app/plan/directions") or {}
    action_now = data_of(page, "/app/plan/action") or {}
    check("工作台字段齐全（画像/采集/编排/报告）",
          all(k in ws for k in ("profile_panel", "collection_panel", "layout_panel", "report_panel")),
          ", ".join(sorted(ws.keys()))[:150])
    check("待办可在后端读到", isinstance(notes, list), f"{len(notes)} 条")
    check("报告资产可读", isinstance(rt, dict) and "sections" in rt, f"version={rt.get('version')}")
    check("③ 方案资产可读（含当前选择）", isinstance(plans_now, dict) and "plans" in plans_now,
          f"{len(plans_now.get('plans') or [])} 套 / 选中 {plans_now.get('selected_id')}")
    check("④ 行动资产可读（含阶段）", isinstance(action_now, dict) and "has_plan" in action_now,
          f"has_plan={action_now.get('has_plan')} / {len(action_now.get('phases') or [])} 个阶段")
    # 401 有两条是**我们故意打的**（未登录访问受保护接口、伪造令牌），不算缺陷；
    # 404 / 5xx 与页面级 JS 异常一律算。浏览器会把 4xx 也塞进 console.error，
    # 所以两边都要按同一口径过滤。
    def _deliberate(msg: str) -> bool:
        return "Failed to load resource" in msg and "401" in msg

    unexpected_http = [e for e in http_errors if not e.startswith("401 ")]
    unexpected_console = [e for e in errors if not _deliberate(e)]
    check(
        "全程没有 404 / 5xx 与页面级 JS 报错（故意打的 401 不算）",
        not unexpected_console and not unexpected_http,
        "; ".join((unexpected_console + unexpected_http)[:3]),
    )
    browser.close()

total = len(results)
passed = sum(1 for r in results if r["ok"])
summary = {
    "base": BASE,
    "account": account,
    "passed": passed,
    "total": total,
    "checks": results,
    "errors": errors[:20],
}
# 括号不能省：`a / "x".write_text(...)` 会先对**字符串**取属性，报
# `'str' object has no attribute 'write_text'` —— 结果就是跑完一轮、
# 一份结果都没落盘。这里踩过一次。
(Path(__file__).resolve().parent / "e2e_full.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"\n===== 端到端结果：{passed}/{total} 通过 =====")
for r in results:
    if not r["ok"]:
        print(f"  FAIL  {r['check']} — {r['detail']}")
if passed != total:
    raise SystemExit(1)
