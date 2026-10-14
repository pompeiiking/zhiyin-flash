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
 assert((await page.locator('.direction-impact').textContent()).includes('半导体'), 'Confirming a candidate must update the current direction')
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
 for(const axis of ['按时间','按主题','按对结论的贡献','按可信度']) {
  await page.getByRole('button',{name:axis,exact:true}).click()
  assert.equal(await page.locator('.p7-row').count(),count,`${axis} must preserve the same profile information`)
 }
 await go('report')
 const dimensionCount=await page.locator('.report-dimension').count()
 for(const axis of ['按时间','按主题','按对结论的贡献','按来源']) {
  await page.getByRole('tab',{name:axis,exact:true}).click()
  assert.equal(await page.locator('.report-dimension').count(),dimensionCount,`${axis} must preserve all report conclusions`)
 }
 await page.locator('.c2-report-verdict').first().click()
 assert.equal(await page.locator('.c2-dimension--active').count(),3,'The first judgment must link to its three specific conclusions')
 console.log('PASS profile/report axes preserve the information pool and specific judgment dependencies')

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
 const noteCount=await page.locator('.c2-note-row').count()
 for(const axis of ['按做没做完','按它怎么来的','按目标 / 待办']) {
  await page.getByRole('button',{name:axis,exact:true}).click()
  assert.equal(await page.locator('.c2-note-row').count(),noteCount,'Notes regrouping must preserve every record')
 }
 await go('intel')
 await page.locator('.c2-filter-row').first().getByRole('button',{name:/岗位示例/}).click()
 assert.equal(await page.locator('.desk-intel-item').count(),5,'Category filters must select actual matching records')
 await page.getByRole('button',{name:'清空筛选',exact:true}).click()
 assert.equal(await page.locator('.desk-intel-item').count(),12,'Clearing filters must restore the same information pool')
 await go('tools')
 assert.equal(await page.locator('.c2-tool-grid article').count(),6)
 assert.equal(await page.locator('.c2-tool-chain > li').count(),4)
 await page.getByRole('button',{name:'按当前状态',exact:true}).click()
 assert.equal(await page.locator('.c2-tool-grid article').count(),6,'Tool grouping must preserve all six tools')
 await go('reminders')
 const noticeCount=await page.locator('.c2-reminder').count()
 if(noticeCount){await page.getByRole('button',{name:'标为已读',exact:true}).first().click();assert.equal(await page.locator('.c2-reminder[data-state="read"]').count(),1,'Read must retain the unresolved notice');await page.getByRole('button',{name:'稍后再看',exact:true}).first().click();await go('home');await go('reminders');assert.equal(await page.locator('.c2-reminder').count(),noticeCount,'Handled notices remain in history across route changes');assert.equal(await page.locator('.c2-reminder[data-state="later"]').count(),1,'Postponed state must survive navigation')}
 await go('notfound')
 await page.getByRole('button',{name:'无权限',exact:true}).click()
 assert((await page.locator('h1').textContent()).includes('权限'))
 await page.getByRole('button',{name:'服务不可用',exact:true}).click()
 assert((await page.locator('h1').textContent()).includes('服务'))
 await go('reminders')
 if(await page.locator('.c2-reminder[data-state="later"]').count()) {
  await page.getByRole('button',{name:'恢复到待处理',exact:true}).first().click()
  assert.equal(await page.locator('.c2-reminder[data-state="pending"]').count(),1,'Postponed notices must return with their original action')
  await page.getByRole('button',{name:'稍后再看',exact:true}).first().click()
  await page.getByRole('button',{name:'现在处理',exact:true}).first().click()
  assert.equal(await page.locator('.c2-reminder[data-state="done"]').count(),1,'Postponed notices must still resolve to the original action')
  assert.equal(await page.locator('.c2-reminder[data-state="pending"]').count(),0)
 }
 console.log('PASS notes, intel, six-tool workflow, reminder history and error states')
 await go('review')
 const reviewCount=await page.locator('.review-group .ws-timeline > li').count()
 assert(reviewCount>4,'The review pool must include actual growth evidence')
 let previousGroups=''
 for(const axis of ['按来源','按时间看','按主题','按对结论的贡献']) {
  await page.getByRole('tab',{name:axis,exact:true}).click()
  assert.equal(await page.locator('.review-group .ws-timeline > li').count(),reviewCount,'Review axes must preserve the combined information pool')
  const signature=(await page.locator('.review-group__head').allTextContents()).join('|')
  assert.notEqual(signature,previousGroups,`${axis} must actually regroup records`)
  previousGroups=signature
 }
 await go('achievements')
 assert.equal(await page.locator('.c2-growth-record').count(),6)
 for(const axis of ['按时间','按主题','按怎么确认的','按来源']) {await page.getByRole('button',{name:axis,exact:true}).click();assert.equal(await page.locator('.c2-growth-record').count(),6)}
 await go('academic')
 const danger=await page.locator('.btn--danger').first().evaluate(el=>({background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color}))
 assert.notEqual(danger.background,'rgba(0, 0, 0, 0)');assert.notEqual(danger.background,danger.color,'Destructive actions must have visible text')
 await go('report')
 await page.getByRole('button',{name:'标记为待重算',exact:true}).click()
 await go('home');await go('report')
 assert((await page.locator('.c2-report-recheck').textContent()).includes('已标记为待重算'),'Review request must survive navigation without claiming recalculated values')
 await go('gallery')
 assert.equal(await page.locator('.c2-family').count(),12)
 await page.getByRole('button',{name:'按在哪一页用',exact:true}).click()
 assert.equal(await page.locator('.c2-family').count(),12)
 assert.equal(await page.locator('.c2-state-matrix tbody tr').count(),4)
 await go('guide')
 assert.equal(await page.locator('.c2-faq').count(),4)
 await page.locator('.c2-faq summary').first().click()
 assert(await page.locator('.c2-faq p').first().isVisible())
 await go('schedule')
 assert.equal(await page.locator('.c2-profile-stat').count(),3)
 await go('plan')
 assert((await page.locator('.ws-heading__meta').textContent()).includes('2026-10-14'),'Deadline calculations must expose their demo date basis')
 assert((await page.locator('.c2-stage-window').allTextContents()).join(' ').includes('逾期'))
 assert(await page.locator('.c2-stage-handoff').count()>0)
 console.log('PASS reviewer fixes: effective review axes, evidence, action visibility, report state, supporting responsibilities and deadlines')

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
  for(const route of ['chat','profile','report','directions','home','plan','schedule','academic','notes','intel','review','tools','settings','reminders','guide','gallery','login','achievements','notfound','spec']) {
   await go(route)
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)
   assert(!overflow,`${route} overflows at ${width}px`)
   assert.equal(await page.locator('#boot-error').count(),0)
   if(width>=768) assert(await page.locator('.desk-sidebar').isVisible(),`Desktop navigation missing at ${width}`)
  }
  console.log(`PASS 20 workspace routes at ${width}px`)
 }
 assert.deepEqual(errors,[],'Browser console and page errors')
 console.log('PASS all C2 interaction and responsive checks')
} finally { await browser.close() }
