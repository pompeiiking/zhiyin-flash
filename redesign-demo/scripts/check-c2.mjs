// Browser checks for the C2 migration. Run against the local Vite demo, never service mode.
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'
import { join } from 'node:path'
const require = createRequire(import.meta.url)
const candidates = [process.env.PW_PATH, 'playwright', join(process.env.LOCALAPPDATA || '', 'npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)
let chromium
for (const path of candidates) { try { chromium = require(path).chromium; break } catch {} }
if (!chromium) throw new Error('Playwright is required. Set PW_PATH to its installed module directory.')
const base = process.env.C2_URL || 'http://127.0.0.1:5199'
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: {width:1440,height:1000}, reducedMotion:'reduce' })
const page = await context.newPage()
const errors=[]
page.on('pageerror', error=>errors.push(String(error)))
page.on('console', message=>{if(message.type()==='error') errors.push(message.text())})
const go = async route=>{await page.goto(`${base}/#/${route}?as=mid&data=demo`);await page.waitForTimeout(250)}
try {
 await go('directions')
 await page.locator('.c2-score-table').waitFor()
 const initial = await page.locator('.c2-rank-reading strong').textContent()
 assert(initial.includes('79') && initial.includes('78') && initial.includes('69'), 'Default ranking must reproduce the approved C2 demo scale')
 for (const [label,value] of [['专业对口',1],['岗位数量',1],['起薪水平',1],['稳定性',5],['通勤与地点',5]]) {
  await page.getByRole('slider',{name:label+'看重程度'}).fill(String(value))
 }
 assert((await page.locator('.c2-ranked-direction h2').first().textContent()).includes('材料检测'), 'Changing priorities must change the winning direction')
 await page.getByRole('link',{name:'个人画像',exact:true}).first().click()
 await page.locator('.profile-page').waitFor()
 await page.getByRole('link',{name:'方向方案',exact:true}).first().click()
 await page.locator('.c2-score-table').waitFor()
 assert((await page.locator('.c2-ranked-direction h2').first().textContent()).includes('材料检测'),'Priorities must survive route changes, like the interactive prototype')
 await page.getByRole('button',{name:'恢复同等权重'}).click()
 assert.equal(await page.locator('.c2-rank-reading strong').textContent(),initial,'Reset must restore the comparison')
 await page.locator('.c2-ranked-direction .btn').first().click()
 assert.equal(await page.locator('.c2-ranked-direction--picked').count(),1)
 await page.locator('.direction-confirm button').click()
 assert((await page.locator('.direction-current').textContent()).includes('半导体'), 'Confirming a candidate must update the current direction')
 console.log('PASS direction weights, ranking, route persistence, reset, selection and confirmation')

 await go('report')
 await page.locator('.c2-report-verdict').first().click()
 assert(await page.locator('.c2-dimension--active').count()>0,'Selecting a judgment must expose its supporting dimensions')
 assert(await page.locator('.c2-dimension--dim').count()>0,'Other dimensions must recede without being removed')
 await page.locator('.c2-report-verdict').first().click()
 assert.equal(await page.locator('.c2-dimension--dim').count(),0)
 console.log('PASS report judgment and evidence linkage')

 await go('profile')
 const count = await page.locator('.p7-row').count()
 await page.getByRole('button',{name:'按来源',exact:true}).click()
 assert.equal(await page.locator('.p7-row').count(),count,'Reordering must preserve the information pool')
 assert(await page.locator('.p7-group').count()>1)
 console.log('PASS profile information regrouping')

 await go('home')
 const before = parseInt(await page.locator('.hm-side__n').textContent(),10)
 await page.getByRole('button',{name:'标记完成',exact:true}).first().click()
 const after = parseInt(await page.locator('.hm-side__n').textContent(),10)
 assert(after<before,'Completing a task must recalculate remaining time')
 await page.locator('.journey-complete').waitFor()
 console.log('PASS task completion, remaining time and feedback')

 await go('notes')
 const checks=page.getByRole('button',{name:/^完成：/})
 assert(await checks.count()>0,'Notes must expose completion controls')
 const beforeNotes=await checks.count();await checks.first().click();assert.equal(await checks.count(),beforeNotes-1)
 assert(await page.getByRole('button',{name:/^恢复：/}).count()>0)
 console.log('PASS notes completion')

 await go('chat')
 await page.getByRole('button',{name:'官网红',exact:true}).click()
 assert.equal(await page.locator('html').getAttribute('data-accent'),'red')
 await page.getByRole('button',{name:'深色',exact:true}).click()
 assert.equal(await page.locator('html').getAttribute('data-theme'),'dark')
 await page.getByRole('button',{name:'紧凑',exact:true}).click()
 assert.equal(await page.locator('html').getAttribute('data-style'),'dense')
 await page.getByRole('button',{name:'校徽蓝',exact:true}).click()
 await page.getByRole('button',{name:'浅色',exact:true}).click()
 await page.getByRole('button',{name:'常规',exact:true}).click()
 await page.getByRole('button',{name:'搜索与跳转',exact:false}).click()
 assert(await page.locator('dialog[open]').count()>0)
 await page.keyboard.press('Escape')
 console.log('PASS appearance axes and command search')

 for (const width of [1440,1280,900,390]) {
  await page.setViewportSize({width,height:width===390?844:1000})
  for(const route of ['chat','profile','report','directions','home','plan','schedule','academic','notes','intel','review','tools']) {
   await go(route)
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)
   assert(!overflow,`${route} overflows at ${width}px`)
   assert.equal(await page.locator('#boot-error').count(),0)
   if(width>=768) assert(await page.locator('.desk-sidebar').isVisible(),`Desktop navigation missing at ${width}`)
  }
  console.log(`PASS 12 routes at ${width}px`)
 }
 assert.deepEqual(errors,[],'Browser console and page errors')
 console.log('PASS all C2 interaction and responsive checks')
} finally { await browser.close() }
