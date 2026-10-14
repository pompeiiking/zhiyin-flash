import {createRequire} from 'node:module'
import {join} from 'node:path'
import {strict as assert} from 'node:assert'
const require=createRequire(import.meta.url)
let chromium
for(const path of [process.env.PW_PATH,'playwright',join(process.env.LOCALAPPDATA||'','npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)){try{chromium=require(path).chromium;break}catch{}}
if(!chromium)throw new Error('Set PW_PATH to Playwright')
const browser=await chromium.launch(), base=process.env.C2_URL||'http://127.0.0.1:5199'
const go=async(page,route,account='mid')=>{await page.goto(`${base}/#/${route}?as=${account}&data=demo`);await page.waitForSelector('.app h1:visible')}
try{
 const context=await browser.newContext(), page=await context.newPage()
 await go(page,'notes')
 assert.equal(await page.locator('.c2-note-row').count(),24)
 await page.getByRole('searchbox',{name:'查找个人记录'}).fill('访谈')
 assert.equal(await page.locator('.c2-note-row').count(),2)
 await page.getByRole('button',{name:'按做没做完',exact:true}).click()
 assert.equal(await page.locator('.c2-note-row').count(),2)
 await page.getByRole('searchbox',{name:'查找个人记录'}).fill('不存在的关键词')
 await page.getByRole('heading',{name:'没有找到这条记录'}).waitFor()
 await page.getByRole('button',{name:'查看全部记录',exact:true}).click()
 assert.equal(await page.locator('.c2-note-row').count(),24)
 console.log('PASS richer records, local search, regrouping and empty recovery')
 await go(page,'reminders')
 const titles=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('zhiyin-context-workspace')).data.noticeQueue.map(n=>n.task.title))
 assert.equal(titles.length,4);assert.equal(new Set(titles).size,4)
 for(let i=0;i<4;i++)await page.locator('.c2-reminder[data-state="pending"] .btn').first().click()
 assert.equal(await page.locator('.c2-reminder[data-state="done"]').count(),4)
 const added=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('zhiyin-context-workspace')).data.tasks.map(t=>t.title))
 for(const title of titles)assert(added.includes(title),'Reminder must add its own action')
 await page.reload();await page.locator('.c2-reminder').first().waitFor()
 assert.equal(await page.locator('.c2-reminder[data-state="done"]').count(),4)
 console.log('PASS four distinct reminder actions and reload history')
 await go(page,'portal')
 for(const label of ['聊清楚','看依据','迈一步']){await page.getByRole('button',{name:label,exact:true}).click();assert((await page.locator('.pe-story__body').innerText()).trim().length>20)}
 assert.equal(await page.locator('#boot-error').count(),0)
 console.log('PASS portal conversation, judgment and action stages')
 await context.close()
 const fresh=await browser.newContext(), fp=await fresh.newPage()
 await go(fp,'settings','fresh')
 assert((await fp.locator('.c2-key-values').innerText()).includes('学校与专业待补充'))
 await go(fp,'report','fresh');assert.equal(await fp.locator('.c2-report-side').count(),0)
 await go(fp,'notes','fresh');assert.equal(await fp.locator('.c2-note-row').count(),0)
 console.log('PASS fresh account does not inherit seeded profile, report or records')
 await fresh.close()
 // Simulate a saved older workspace: edits, deletions and imported material survive enrichment.
 const migration=await browser.newContext(), mp=await migration.newPage()
 await mp.addInitScript(()=>{
  localStorage.setItem('zhiyin-demo-auth','mid')
  sessionStorage.setItem('zhiyin-context-data',JSON.stringify({identity:'mid:0',data:{demoDataVersion:2,dataMode:'demo',notes:[{id:'note-2',kind:'goal',text:'已修改的个人目标',done:true},{id:'personal-note',kind:'todo',text:'自己新增的记录',done:false}],academicOrigin:'local',academic:{courses:[{name:'本人导入的课程'}],grades:[],school:'本人学校'},intelOrigin:'live',intel:[{id:'personal-intel',title:'自己的资讯'}],histories:{'session-resume':[{id:'session-resume-question',from:'me',text:'自己改过的问题'},{id:'session-resume-answer',from:'host',text:'自己保存的回答'}]}}}))
 })
 await go(mp,'notes')
 const saved=await mp.evaluate(()=>JSON.parse(sessionStorage.getItem('zhiyin-context-data')).data)
 assert(!saved.notes.some(n=>n.id==='note-1'),'Removed original record must not be revived')
 assert.equal(saved.notes.find(n=>n.id==='note-2').text,'已修改的个人目标')
 assert(saved.notes.find(n=>n.id==='personal-note'))
 assert.equal(saved.academic.courses[0].name,'本人导入的课程')
 assert.equal(saved.intel[0].id,'personal-intel')
 assert.equal(saved.histories['session-resume'][0].text,'自己改过的问题')
 assert.equal(saved.demoDataVersion,3)
 console.log('PASS fixture migration preserves edited, deleted, personal and online records')
 await migration.close()
 const responsive=await browser.newContext({reducedMotion:'reduce'}), rp=await responsive.newPage(), errors=[]
 rp.on('pageerror',e=>errors.push(String(e)))
 rp.on('console',e=>{if(e.type()==='error'||(e.type()==='warning'&&e.text().includes('Failed to resolve component')))errors.push(e.text())})
 const routes=['chat','profile','report','directions','home','plan','schedule','academic','notes','intel','review','tools','settings','reminders','guide','gallery','login','achievements','notfound','spec','portal','path']
 for(const [width,height] of [[375,812],[844,390]]){
  await rp.setViewportSize({width,height})
  for(const route of routes){
   await go(rp,route)
   assert.equal(await rp.locator('#boot-error').count(),0)
   assert(!await rp.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),`${route} overflows at ${width}×${height}`)
  }
  console.log(`PASS 22 pages at ${width}×${height} with reduced motion`)
 }
 await rp.goto(`${base}/#/?portal=classic`);await rp.waitForSelector('.app h1:visible')
 assert.equal(await rp.locator('#boot-error').count(),0)
 assert.deepEqual(errors,[])
 console.log('PASS original portal variant, browser errors and missing component checks')
 await responsive.close()
}finally{await browser.close()}
