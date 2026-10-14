// Capture the repaired reminder state flow separately from the initial paired screenshots.
import { createRequire } from 'node:module'
import { join, resolve } from 'node:path'
import { mkdirSync } from 'node:fs'
const require=createRequire(import.meta.url)
let chromium
for(const path of [process.env.PW_PATH,'playwright',join(process.env.LOCALAPPDATA??'','npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)){try{chromium=require(path).chromium;break}catch{}}
if(!chromium)throw new Error('Playwright is required; set PW_PATH.')
const out=resolve(process.env.C2_SHOTS??'../.tmp-shots/c2-repair-final')
mkdirSync(out,{recursive:true})
const browser=await chromium.launch()
try{
 for(const width of [1440,390,858]){
  const context=await browser.newContext({viewport:{width,height:width<768?844:1000},reducedMotion:'reduce'})
  const page=await context.newPage()
  await page.goto((process.env.C2_URL??'http://127.0.0.1:5199')+'/#/reminders?as=mid&data=demo')
  for(const [state,button] of [['read','标为已读'],['later','稍后再看'],['done','现在处理']]){
   await page.getByRole('button',{name:button,exact:true}).first().click()
   await page.locator(`.c2-reminder[data-state="${state}"]`).waitFor()
   await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('.app__main')?.scrollTo(0,0)})
   await page.screenshot({path:join(out,`app-reminders-${state}-${width}.png`),fullPage:true})
  }
  await context.close()
 }
 console.log('Saved read/later/done reminder state evidence at three widths')
}finally{await browser.close()}
