// Historical first-round layout verification. Current layout is covered by verify-completion.mjs.
import { createRequire } from 'node:module'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFile, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const i = process.argv.indexOf('--runtime')
const require = createRequire(join(process.argv[i + 1], 'package.json'))
const { chromium } = require('playwright')
const out = dirname(fileURLToPath(import.meta.url))
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const results = []
try {
  for (const width of [1280, 390]) {
    const context = await browser.newContext({ viewport: { width, height: width === 1280 ? 900 : 844 } })
    const page = await context.newPage()
    const plans = {
      selected_id: null,
      plans: ['main', 'parallel', 'fallback'].map((role, index) => ({
        id: 'verified-' + index, name: '契约测试方向' + (index + 1), role,
        target_desc: '核对目标的实际说明', fit_reason: '以已提供的经历作为匹配依据',
        gaps: [{ requirement: '方向要求：完整作品', current_state: '当前情况：已有初稿', suggestion: '补齐建议：完善案例' }],
        main_risk: '作品范围还需要核对', selected: false,
      })),
    }
    let fail = false
    await page.route('**/api/v1/app/plan/directions', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: plans }) }))
    await page.route('**/api/v1/app/plan/directions/*/select', async route => {
      if (fail) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 1007, message: '测试中的服务失败' }) })
      await new Promise(resolve => setTimeout(resolve, 350))
      const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').at(-2))
      plans.selected_id = id
      plans.plans.forEach(plan => { plan.selected = plan.id === id })
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: plans }) })
    })
    await page.goto('http://127.0.0.1:5281/#/directions?as=mid', { waitUntil: 'networkidle' })
    await page.screenshot({ path: join(out, 'screens', width + '-directions.jpg'), type: 'jpeg', quality: 85, fullPage: true })
    await page.getByRole('button', { name: '获取最新方案', exact: true }).click()
    await page.locator('.direction-details').waitFor()
    assert.equal(await page.locator('.direction-details > article').count(), 3)
    const content = await page.locator('.direction-details').innerText()
    for (const text of ['方向要求：完整作品', '当前情况：已有初稿', '补齐建议：完善案例', '作品范围还需要核对']) assert.ok(content.includes(text))
    await page.getByRole('button', { name: '确认此方向', exact: true }).first().click()
    await page.getByRole('button', { name: '已确认此方向', exact: true }).waitFor()
    await page.screenshot({ path: join(out, 'screens', width + '-live-directions-mocked.jpg'), type: 'jpeg', quality: 85, fullPage: true })
    // Navigate through the application, preserving the shared store rather than reloading the document.
    await page.evaluate(() => { location.hash = '#/report' })
    await page.getByRole('heading', { name: '诊断报告', exact: true }).waitFor()
    await page.evaluate(() => { location.hash = '#/directions' })
    await page.getByRole('heading', { name: '方向方案', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: '已确认此方向', exact: true }).count(), 1)
    assert.ok((await page.locator('.direction-details').innerText()).includes('契约测试方向1'))
    fail = true
    await page.getByRole('button', { name: '确认此方向', exact: true }).first().click()
    await page.getByRole('alert').waitFor()
    assert.ok((await page.getByRole('alert').innerText()).includes('没有保存成功'))
    assert.equal(await page.getByRole('button', { name: '已确认此方向', exact: true }).count(), 1)
    assert.ok(await page.getByRole('button', { name: '确认此方向', exact: true }).first().isEnabled())
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    results.push({ id: width + '-live-directions-gaps-save-return-failure', status: 'passed', evidence: 'Controlled contract response; no real backend mutation' })
    await context.close()
  }
  const file = join(out, 'confirmation-results.json')
  const data = JSON.parse(await readFile(file, 'utf8'))
  const ids = new Set(results.map(result => result.id))
  data.results = data.results.filter(result => !ids.has(result.id)).concat(results)
  await writeFile(file, JSON.stringify(data, null, 2))
  await writeFile(join(out, 'live-directions-results.json'), JSON.stringify(results, null, 2))
  console.log(JSON.stringify(results))
} finally { await browser.close() }
