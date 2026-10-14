// 在现网页面里把已打开弹层临时改成 sheet 形态，验证"sheet 在移动端 = 底部面板"这条 CSS 本身成立。
// 不改任何源码，只在页面运行时改一下 class 与 dialog.open。
import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/?signin=1`, { waitUntil: 'networkidle' })
await page.waitForSelector('.ws-sheet--dialog[open]', { timeout: 15000 })
await page.waitForTimeout(300)

const result = await page.evaluate(async () => {
  const d = document.querySelector('.ws-sheet--dialog[open]')
  const keepOpen = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'open')
  Object.defineProperty(d, 'open', { configurable: true, get: () => keepOpen.get.call(d), set: () => {} })
  Object.defineProperty(d, 'close', { configurable: true, value: () => {} })
  d.classList.remove('ws-sheet--dialog')
  d.classList.add('ws-sheet--sheet')
  // 补一次入场（原本的 [open] 动画在 class 变更前已经播完，这里重放一次同样的 keyframes）
  d.getAnimations().forEach(a => a.cancel())
  d.animate([{ opacity: .6, transform: 'translateY(100%)' }, { opacity: 1, transform: 'none' }], { duration: 240, easing: 'ease-out', fill: 'forwards' })
  await new Promise(r => setTimeout(r, 400))
  const r = d.getBoundingClientRect()
  const cs = getComputedStyle(d)
  const grab = d.querySelector('.ws-sheet__grabber')
  const gs = grab ? getComputedStyle(grab) : null
  return {
    classes: d.className,
    box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    bottomGap: Math.round(innerHeight - r.bottom),
    radius: cs.borderRadius,
    maxHeight: cs.maxHeight,
    grabberDisplay: gs?.display ?? null,
    grabberInDom: !!grab,
    // 把手：这个（dialog 形态的）实例本来不渲染把手，所以从样式表里查规则本身
    grabberRule: (() => {
      for (const sheet of document.styleSheets) {
        let rules
        try { rules = sheet.cssRules } catch { continue }
        const found = []
        const walk = (list, media) => {
          for (const rule of list) {
            if (rule.media) { walk(rule.cssRules, rule.conditionText || rule.media.mediaText); continue }
            if (rule.selectorText && /grabber/.test(rule.selectorText)) found.push({ media, selector: rule.selectorText.slice(0, 90), css: rule.cssText.replace(/\s+/g, ' ').slice(0, 180) })
          }
        }
        walk(rules, null)
        if (found.length) return found
      }
      return null
    })(),
    bodyPaddingBottom: getComputedStyle(d.querySelector('.ws-sheet__body')).paddingBottom,
    // 证明安全区规则真的写进了选择器（不靠计算值，因为 Playwright 不模拟刘海，env() 会解析成 0）
    safeAreaRules: (() => {
      const hits = []
      for (const sheet of document.styleSheets) {
        let rules
        try { rules = sheet.cssRules } catch { continue }
        const walk = (list, media) => {
          for (const rule of list) {
            if (rule.media) { walk(rule.cssRules, rule.conditionText || rule.media.mediaText); continue }
            if (rule.selectorText && /grabber|sheet__body|ws-sheet--sheet/.test(rule.selectorText) && /safe-area-inset|sheet-radius-mobile|sheet-mobile-max-h/.test(rule.cssText)) {
              hits.push({ media, selector: rule.selectorText.slice(0, 120), css: rule.cssText.replace(/\s+/g, ' ').slice(0, 220) })
            }
          }
        }
        walk(rules, null)
      }
      return hits
    })(),
  }
})
await page.waitForTimeout(200)
await page.screenshot({ path: '_shots/infra-b/css-proof-sheet-mobile.png' })
console.log(JSON.stringify(result, null, 2))
await browser.close()
