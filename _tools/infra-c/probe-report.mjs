// 临时探针：确认 MeterRow 的新 API 对既有调用点（AssessmentView.vue:87/:88）的影响
import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const msgs = []
page.on('console', (m) => msgs.push(`${m.type()}: ${m.text()}`))
page.on('pageerror', (e) => msgs.push(`pageerror: ${e.message}`))

await page.goto('http://127.0.0.1:5180/#/report', { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)
// 走"查看报告示例"→ 拿到 fullReport，才会渲染那两处 MeterRow
const sample = page.getByRole('button', { name: /查看报告示例/ })
console.log('示例按钮命中数：', await sample.count())
if (await sample.count()) {
  await sample.first().click()
  await page.waitForTimeout(1800)
}
// 展开所有 details，让 MeterRow 真正渲染
await page.evaluate(() => document.querySelectorAll('details').forEach((d) => (d.open = true)))
await page.waitForTimeout(700)
console.log('页面上的按钮：', (await page.getByRole('button').allTextContents()).slice(0, 20).join(' | '))
console.log('details 数：', await page.locator('details').count())
console.log('.mtr 数：', await page.locator('.mtr').count())
console.log(
  'report-evidence 数：',
  await page.locator('.report-evidence').count(),
  ' / ws-stack 数：',
  await page.locator('.ws-stack').count(),
)
console.log('当前 URL：', page.url())
console.log('h1/h2 文本：', (await page.locator('h1, h2').allTextContents()).slice(0, 12).join(' | '))
console.log('ws-empty 文本：', (await page.locator('.ws-empty').allTextContents()).slice(0, 3).join(' | '))
console.log(
  'ws-text-button 文本：',
  (await page.locator('.ws-text-button').allTextContents()).slice(0, 8).join(' | '),
)

const meters = await page.evaluate(() =>
  [...document.querySelectorAll('.mtr')].map((m) => ({
    name: m.querySelector('.mtr__name')?.textContent.trim(),
    value: m.querySelector('.mtr__value')?.textContent.trim(),
    fillPct: m.querySelector('.mtr__fill')?.style.width ?? null,
    legend: [...m.querySelectorAll('.mtr__legend-item')].map((e) => e.textContent.trim().replace(/\s+/g, ' ')),
    isNull: m.classList.contains('mtr--empty'),
  })),
)
console.log('MeterRow 在 /report 上的实际渲染：')
console.log(JSON.stringify(meters, null, 2))
console.log('\n控制台（量纲守卫）：')
msgs.filter((m) => /MeterRow|StatTile|ConfidenceBadge/.test(m)).slice(0, 12).forEach((m) => console.log('  ' + m))
console.log(`\n共 ${meters.length} 个 .mtr，控制台告警 ${msgs.filter((m) => /MeterRow/.test(m)).length} 条`)
await page.screenshot({ path: '_shots/infra-c/report-after-api-change.png', fullPage: false })
await browser.close()
