// 临时验证脚本（不属于交付物，放在 _tools/ 下）
// 用法：node _tools/infra-b/measure.mjs <tag>
import { mkdirSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)

const tag = process.argv[2] ?? 'run'
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const OUT = '_shots/infra-b'
mkdirSync(OUT, { recursive: true })

const result = {}
const browser = await chromium.launch()

const readActive = (page) => page.evaluate(() => {
  const a = document.activeElement
  return a ? {
    tag: a.tagName,
    cls: typeof a.className === 'string' ? a.className : null,
    text: (a.textContent || '').trim().slice(0, 24),
  } : null
})

const boxOf = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s)
  if (!el) return null
  const r = el.getBoundingClientRect()
  const cs = getComputedStyle(el)
  return {
    box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    radius: cs.borderRadius,
    position: cs.position,
    inset: `${cs.top} ${cs.right} ${cs.bottom} ${cs.left}`,
    bottomGap: Math.round(innerHeight - r.bottom),
    transformOrigin: cs.transformOrigin,
    pb: cs.paddingBottom,
    classes: el.className,
    vh: innerHeight,
    vw: innerWidth,
  }
}, sel)

// ---------- 1. 桌面：焦点恢复实测（登录路径） ----------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.pf-login', { timeout: 15000 })

  const steps = []
  steps.push({ step: '初始', active: await readActive(page) })

  const trigger = page.locator('.pf-login')
  await trigger.focus()
  steps.push({ step: '点击前（trigger 已 focus）', active: await readActive(page) })

  await trigger.click()
  await page.waitForSelector('.ws-sheet[open]', { timeout: 15000 })
  await page.waitForTimeout(350)
  steps.push({ step: '弹层打开后', active: await readActive(page), hash: await page.evaluate(() => location.hash) })
  result.desktopDialog = await boxOf(page, '.ws-sheet[open]')
  await page.screenshot({ path: `${OUT}/${tag}-desktop-dialog.png` })

  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)
  steps.push({
    step: 'Esc 关闭后',
    active: await readActive(page),
    hash: await page.evaluate(() => location.hash),
    dialogOpen: await page.evaluate(() => !!document.querySelector('.ws-sheet[open]')),
  })
  result.desktopFocus = steps

  // 再验一次"背景点击关闭 + 焦点"与"重新打开"
  await trigger.click()
  await page.waitForSelector('.ws-sheet[open]', { timeout: 8000 })
  await page.waitForTimeout(250)
  await page.mouse.click(30, 450)
  await page.waitForTimeout(400)
  steps.push({ step: '背景点击关闭后', active: await readActive(page), dialogOpen: await page.evaluate(() => !!document.querySelector('.ws-sheet[open]')) })

  await ctx.close()
}

// ---------- 2. 移动端 390×844 ----------
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  })
  const page = await ctx.newPage()
  const shots = {}
  async function measure(label, sel = '.ws-sheet[open]') {
    shots[label] = await boxOf(page, sel)
    await page.screenshot({ path: `${OUT}/${tag}-mobile-${label}.png` })
  }

  // 2a 默认形态（dialog）：确认/表单类，移动端仍居中
  await page.goto(`${BASE}/#/?signin=1`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.ws-sheet--dialog[open]', { timeout: 15000 })
  await page.waitForTimeout(400)
  await measure('signin-dialog')

  // 2b sheet 形态（--inspector 旧 prop 解析为 sheet）：移动端应为底部面板
  await page.goto(`${BASE}/#/chat`, { waitUntil: 'networkidle', timeout: 25000 })
  await page.waitForTimeout(800)
  let sheetInfo = null
  try {
    const probe = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')]
      const hit = btns.find(b => (b.getAttribute('aria-label') || '').includes('个人画像'))
      return {
        total: btns.length,
        found: !!hit,
        visible: hit ? hit.getClientRects().length > 0 : null,
        cls: hit ? hit.className : null,
        hash: location.hash,
      }
    })
    sheetInfo = { probe }
    if (probe.found) {
      // 触发元素可能在窄屏被 CSS 隐藏；Vue 的监听在元素上，直接触发 click 仍然有效
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('button')].find(x => (x.getAttribute('aria-label') || '').includes('个人画像'))
        b.click()
      })
      await page.waitForSelector('.ws-sheet--sheet[open]', { timeout: 8000 })
      await page.waitForTimeout(500)
      await measure('sheet-bottom')
      sheetInfo.opened = true
      sheetInfo.triggerVisible = probe.visible
      // 手势：按住把手向下拖 260px 应关闭
      const gb = await page.locator('.ws-sheet--sheet[open] .ws-sheet__grabber').boundingBox()
      if (gb) {
        const cx = gb.x + gb.width / 2
        const cy = gb.y + gb.height / 2
        await page.mouse.move(cx, cy)
        await page.mouse.down()
        for (let i = 1; i <= 10; i++) { await page.mouse.move(cx, cy + i * 28); await page.waitForTimeout(16) }
        await page.mouse.up()
        await page.waitForTimeout(500)
        result.dragClose = {
          stillOpen: await page.evaluate(() => !!document.querySelector('.ws-sheet--sheet[open]')),
          active: await readActive(page),
        }
      } else {
        result.dragClose = { error: 'grabber not found' }
      }
    }
  } catch (e) {
    sheetInfo = { err: String(e).slice(0, 200) }
  }
  result.sheetProbe = sheetInfo
  result.mobileShots = shots
  await ctx.close()
}

// ---------- 3. 折叠统计（只读） ----------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const audit = {}
  for (const p of ['/report', '/plan', '/directions', '/notes', '/academic', '/schedule', '/tools']) {
    try {
      await page.goto(`${BASE}/#${p}`, { waitUntil: 'networkidle', timeout: 25000 })
      await page.waitForTimeout(400)
      audit[p] = await page.evaluate(() => {
        const details = [...document.querySelectorAll('details')]
        const depth = (el) => { let n = 0, cur = el.parentElement; while (cur) { if (cur.tagName === 'DETAILS') n++; cur = cur.parentElement } return n }
        const one = (s) => document.querySelectorAll(s).length
        return {
          totalDetails: details.length,
          closed: details.filter(d => !d.open).length,
          maxDepth: details.reduce((m, d) => Math.max(m, depth(d) + 1), 0),
          wsFold: one('.ws-fold'), wsContext: one('.ws-context'),
          planStage: one('.plan-stage'), wsTaskDetails: one('.ws-task__details'),
          expEvidence: one('.exp-evidence'),
        }
      })
    } catch (e) { audit[p] = { error: String(e).slice(0, 120) } }
  }
  result.foldAudit = audit
  await ctx.close()
}

await browser.close()
writeFileSync(`${OUT}/${tag}.json`, JSON.stringify(result, null, 2), 'utf8')
console.log(JSON.stringify(result, null, 2))
