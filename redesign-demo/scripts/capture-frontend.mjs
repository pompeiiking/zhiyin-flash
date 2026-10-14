// Render every frontend route in isolated contexts; never change the user's tab.
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
const require = createRequire(import.meta.url)
let chromium
for (const path of [process.env.PW_PATH,'playwright',join(process.env.LOCALAPPDATA||'','npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)) {
  try { chromium=require(path).chromium; break } catch {}
}
if(!chromium)throw new Error('Set PW_PATH to Playwright')
const base=process.env.C2_URL||'http://127.0.0.1:5199'
const out=resolve(process.env.FRONTEND_SHOTS||'.tmp-shots/frontend-polish')
const defaultRoutes=['chat','profile','report','directions','home','plan','schedule','academic','notes','intel','review','tools','settings','reminders','guide','gallery','login','achievements','notfound','spec','portal']
const routes=process.env.FRONTEND_ROUTES?process.env.FRONTEND_ROUTES.split(','):defaultRoutes
const widths=(process.env.FRONTEND_WIDTHS||'1440,858,390').split(',').map(Number)
const browser=await chromium.launch(), records=[]
mkdirSync(out,{recursive:true})
try {
 for(const width of widths){
  const context=await browser.newContext({viewport:{width,height:width<768?844:1000},reducedMotion:'reduce'})
  const page=await context.newPage(), errors=[]
  page.on('pageerror',e=>errors.push(String(e)))
  page.on('console',e=>{if(e.type()==='error')errors.push(e.text())})
  for(const route of routes){
   await page.goto(`${base}/#/${route}?as=mid&data=demo`)
   await page.waitForSelector('.app h1:visible')
   await page.waitForTimeout(300)
   await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('.app__main')?.scrollTo(0,0)})
   await page.screenshot({path:join(out,`${route}-${width}.png`)})
   const state=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,text:document.body.innerText}))
   const matches=state.text.split('\n').filter(line=>/演示数据|虚构演示|演示环境|本次演示|本地演示/.test(line))
   records.push({route,width,overflow:state.overflow,labels:matches,errors:[...errors]})
   console.log(`${route} ${width}: overflow=${state.overflow}, labels=${matches.length}`)
  }
  await context.close()
 }
 writeFileSync(join(out,'route-audit.json'),JSON.stringify(records,null,2))
 if(records.some(r=>r.overflow||r.errors.length))process.exitCode=1
}finally{await browser.close()}
