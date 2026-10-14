// 临时探针：SpecView.vue:435-437 的 ConfidenceBadge 旧对象入参是否仍然可用
import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const msgs = []
page.on('console', (m) => msgs.push(`${m.type()}: ${m.text()}`))
page.on('pageerror', (e) => msgs.push(`pageerror: ${e.message}`))
await page.goto('http://127.0.0.1:5180/#/spec', { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)
const out = await page.evaluate(() =>
  [...document.querySelectorAll('.cf')].map((el) => ({
    cls: el.className,
    label: el.querySelector('.cf__label')?.textContent.trim(),
    bars: el.querySelectorAll('.cf__bar').length,
    on: el.querySelectorAll('.cf__bar--on').length,
  })),
)
console.log('SpecView 上的 ConfidenceBadge（旧对象入参）：')
console.log(JSON.stringify(out, null, 2))
const errs = msgs.filter((m) => /pageerror|\[vue\]|error/i.test(m))
console.log('页面错误：', errs.length ? errs.slice(0, 5) : '无')
console.log('Vue prop 警告：', msgs.filter((m) => /Invalid prop|type check failed/i.test(m)).length)
await browser.close()
