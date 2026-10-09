"""查顶栏那颗按钮：没登录时它说什么。

用户报过"左上角的登录框怎么还有个已登录的名字" —— 那是兜底文案写成了
`'已登录'`，于是**没登录时它也说自己已登录**。这里把两种状态都量一遍。
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.environ.get("ZHIYIN_BROWSER_CHANNEL") or None)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 一、伪造令牌（换库/过期之后的真实样子）
    page.goto(BASE + "/portal", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.evaluate("() => localStorage.setItem('zhiyin_token', 'forged.token.value')")
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_timeout(4000)
    print("伪造令牌时 顶栏:", page.locator(".who__name").first.inner_text())
    print("伪造令牌时 登录层已掀开:", page.locator('.layer[aria-label="登录职引"]').count() > 0)

    # 二、干净状态（没有令牌）
    page.evaluate("() => localStorage.clear()")
    page.goto(BASE + "/portal", wait_until="networkidle")
    page.wait_for_timeout(2500)
    trigger = page.locator(".account .trigger")
    print("未登录时 顶栏:", page.locator(".who__name").first.inner_text() if page.locator(".who__name").count() else "(无)")
    if trigger.count():
        trigger.first.click()
        page.wait_for_timeout(800)
        print("点它是掀登录层，而不是账号面板:", page.locator('.layer[aria-label="登录职引"]').count() > 0)
    browser.close()
