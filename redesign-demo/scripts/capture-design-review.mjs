import {createRequire} from 'node:module'
import {join,resolve} from 'node:path'
import {mkdirSync,writeFileSync} from 'node:fs'
const require=createRequire(import.meta.url),{chromium}=require(process.env.PW_PATH||join(process.env.LOCALAPPDATA,'npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright'))
const out=resolve('../.tmp-shots/application-visual');mkdirSync(out,{recursive:true})
const browser=await chromium.launch(),stats=[]
try{for(const width of [1440,390]){const context=await browser.newContext({viewport:{width,height:width===390?844:1000},reducedMotion:'reduce'}),page=await context.newPage()
for(const [route,title] of [['profile','个人画像'],['report','诊断报告'],['directions','方向方案'],['plan','阶段计划'],['home','今日行动'],['intel','岗位资讯'],['notes','待办与目标'],['review','复盘与记录']]){
await page.goto(`http://127.0.0.1:5199/#/${route}?as=mid&data=demo`);await page.getByRole('heading',{level:1,name:title,exact:true}).waitFor();await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:join(out,`${route}-${width}.png`)})
stats.push({route,width,...await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,height:document.documentElement.scrollHeight,profileRows:[...document.querySelectorAll('.p7-row')].slice(0,4).map(n=>({bottom:n.getBoundingClientRect().bottom,height:n.getBoundingClientRect().height})),sections:[...document.querySelectorAll('.profile-identity,.p7-block,.information-search,.p7-group__head')].slice(0,6).map(n=>({class:n.className,top:n.getBoundingClientRect().top,height:n.getBoundingClientRect().height}))}))})
}await context.close()}writeFileSync(join(out,'measurements.json'),JSON.stringify(stats,null,2))}finally{await browser.close()}
