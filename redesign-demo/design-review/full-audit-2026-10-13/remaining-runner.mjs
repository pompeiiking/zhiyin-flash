import {createRequire} from 'node:module'
import {mkdir,writeFile,readFile} from 'node:fs/promises'
import {dirname,join,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const out=dirname(fileURLToPath(import.meta.url))
const arg=(name,fallback)=>{const i=process.argv.indexOf('--'+name);return i>=0?process.argv[i+1]:fallback}
const runtime=arg('runtime','')
if(!runtime)throw new Error('Pass the bundled package directory with --runtime')
const require=createRequire(join(runtime,'package.json'))
const {chromium}=require('playwright')
const base=arg('url','http://127.0.0.1:5281')
await mkdir(join(out,'screens'),{recursive:true})
await mkdir(join(out,'states'),{recursive:true})
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true})
const routes=[['portal','/','问出方向，一路陪你。'],['chat','/chat','咨询对话'],['profile','/profile','个人画像'],['report','/report','诊断报告'],['directions','/directions','方向方案'],['home','/home','今日行动'],['plan','/plan','行动计划'],['schedule','/schedule','日历与课表'],['academic','/academic','学籍与资料'],['notes','/notes','待办与目标'],['review','/review','复盘与记录'],['intel','/intel','岗位资讯'],['tools','/tools','应用工具'],['path','/path','大一到大四'],['spec','/spec','设计规范'],['not-found','/audit-missing','这个地址不存在']]
const retry=process.argv.includes('--retry')
const prior=retry?JSON.parse(await readFile(join(out,'browser-observations.json'),'utf8')):null
const records=prior?.records??[];const scenarios=[];const contexts=[]
const retryIds=new Set(prior?.scenarios.filter(s=>s.status==='inspection_failed').map(s=>s.id)??[])
async function context(viewport={width:1280,height:900},options={}){const c=await browser.newContext({viewport,locale:'zh-CN',timezoneId:'Asia/Shanghai',...options});contexts.push(c);return c}
async function go(page,path,account='mid'){
  const query=path.includes('?')?'&':'?'
  await page.goto(base+'/#'+path+query+'as='+account+'&theme=light',{waitUntil:'networkidle'})
  await page.locator('h1').first().waitFor({state:'visible',timeout:8000})
  await page.waitForTimeout(380)
}
async function metrics(page){return page.evaluate(()=>{
  const vis=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'}
  const rect=e=>{const r=e.getBoundingClientRect();return{x:+r.x.toFixed(1),y:+r.y.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}}
  const name=e=>e.getAttribute('aria-label')||e.innerText?.trim().slice(0,90)||e.getAttribute('placeholder')||e.tagName
  const targets=[...document.querySelectorAll('button,a[href],summary,input:not([type=file]),textarea,select')].filter(vis).map(e=>({tag:e.tagName,name:name(e),...rect(e),disabled:!!e.disabled}))
  const texts=[...document.querySelectorAll('h1,h2,h3,p,dt,dd,summary,small,label,button')].filter(vis).map(e=>{const s=getComputedStyle(e);return{tag:e.tagName,text:(e.innerText||'').trim().slice(0,120),font:s.fontFamily,size:s.fontSize,weight:s.fontWeight,lineHeight:s.lineHeight,color:s.color,...rect(e)}})
  const blocks=[...document.querySelectorAll('.app__main,.app__content,.ws-page,.ws-paper,.ws-aside,.ws-two-columns,.ws-chat-flow,.ws-composer,.ws-heading,.ws-bookmarks,.desk-time-grid,.ws-directions')].filter(vis).map(e=>({class:e.className,...rect(e),scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,padding:getComputedStyle(e).padding,gap:getComputedStyle(e).gap}))
  const images=[...document.images].map(e=>({src:e.getAttribute('src'),alt:e.alt,loaded:e.complete&&e.naturalWidth>0,...rect(e)}))
  const active=document.activeElement
  return{url:location.href,viewport:{width:innerWidth,height:innerHeight},doc:{width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight},horizontalOverflow:document.documentElement.scrollWidth>innerWidth+1,headings:[...document.querySelectorAll('h1,h2,h3')].filter(vis).map(e=>({tag:e.tagName,text:e.innerText})),targets,texts,blocks,images,dialogs:[...document.querySelectorAll('dialog[open],[role=dialog]')].filter(vis).map(e=>({label:e.getAttribute('aria-label'),...rect(e)})),active:{tag:active?.tagName,name:active?name(active):'',outline:active?getComputedStyle(active).outline:''},reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches,animations:document.getAnimations().map(a=>({name:a.animationName||a.transitionProperty||'',state:a.playState}))}
})}
async function capture(page,id,note='',takeShot=true){
  await page.waitForTimeout(280)
  const data=await metrics(page)
  const text=await page.locator('body').innerText()
  const entry={id,note,observedAt:new Date().toISOString(),...data}
  if(takeShot){entry.screenshot='screens/'+id+'.jpg';await page.screenshot({path:join(out,entry.screenshot),type:'jpeg',quality:83,fullPage:true,animations:'allow'})}
  await writeFile(join(out,'states',id+'.txt'),text)
  records.push(entry)
  return entry
}
async function step(id,fn){if(retry&&!retryIds.has(id))return;try{const details=await fn();scenarios.push({id,status:'observed',details:details??null});console.log('state '+id+' observed')}catch(error){scenarios.push({id,status:'inspection_failed',error:String(error).slice(0,800)});console.log('state '+id+' FAILED '+String(error).slice(0,160))}}
async function openDetails(page,selector='main details'){
  const list=page.locator(selector)
  for(let i=0;i<await list.count();i++){const d=list.nth(i);if(await d.isVisible()&&!await d.evaluate(e=>e.open))await d.locator(':scope > summary').click()}
}
try{for(const width of [1280,390]){
 const c=await context({width,height:width===390?844:900}),p=await c.newPage()
 await step(width+'-goal-all-actions',async()=>{await go(p,'/notes');await p.getByRole('tab',{name:/个人目标/}).click();await p.getByRole('button',{name:'添加',exact:true}).click();const field=p.getByRole('textbox',{name:'写下一个目标',exact:true});await field.fill('审查用目标：完成职业方向比较');await p.getByRole('button',{name:'添加',exact:true}).click();await p.getByRole('button',{name:'完成：审查用目标：完成职业方向比较',exact:true}).click();await capture(p,width+'-goal-completed');await p.getByRole('button',{name:'恢复：审查用目标：完成职业方向比较',exact:true}).click();await p.getByRole('button',{name:'删除：审查用目标：完成职业方向比较',exact:true}).click();return{remainingAuditGoal:await p.getByText('审查用目标：完成职业方向比较',{exact:true}).count()}})
 await step(width+'-reject-suggestion',async()=>{await go(p,'/home');await p.getByRole('tab',{name:/等待中/}).click();await openDetails(p);await p.getByRole('button',{name:'拒绝建议',exact:true}).first().click();await capture(p,width+'-suggestion-rejected')})
 await step(width+'-start-topic-scroll-ime',async()=>{await go(p,'/chat');await p.getByRole('button',{name:width===1280?'新建咨询':'新对话',exact:true}).click();await p.locator('.ws-chat-prompts button').first().click();await p.waitForTimeout(1600);await capture(p,width+'-topic-started');const input=p.getByRole('textbox',{name:'咨询内容',exact:true});await input.fill('输入法组合中的审查内容');const before=await p.locator('.dialogue-message').count();await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:true,bubbles:true});const after=await p.locator('.dialogue-message').count();await input.fill('我想知道够不够');await input.press('Enter');await p.waitForTimeout(1600);await p.locator('.ws-chat-flow').focus();await p.keyboard.press('Control+Home');const latest=p.getByRole('button',{name:'回到最新消息',exact:true});const available=await latest.count();if(available)await latest.click();await capture(p,width+'-latest-message');return{imeDidNotSend:before===after,latestControl:available}})
 await step(width+'-nav-all-entry-links',async()=>{const groups=[['画像与诊断','个人画像','/profile'],['画像与诊断','学籍与资料','/academic'],['画像与诊断','诊断报告','/report'],['方向选择','方向方案','/directions'],['方向选择','岗位资讯','/intel'],['行动与安排','行动计划','/home'],['行动与安排','日历与课表','/schedule'],['行动与安排','个人待办与目标','/notes'],['复盘与成长','复盘与记录','/review']];await go(p,'/chat');const reached=[];for(const [group,label,path]of groups){if(width===390)await p.getByRole('button',{name:'更多功能',exact:true}).click();const root=width===390?p.getByRole('dialog',{name:'更多功能',exact:true}):p.locator('.desk-nav');const link=root.getByRole('link',{name:label,exact:true});if(!await link.isVisible())await root.getByRole('button',{name:group,exact:true}).click();await link.click();await p.waitForTimeout(400);reached.push({label,pathReached:p.url().split('#')[1].split('?')[0],correct:p.url().split('#')[1].split('?')[0]===path})}return reached})
 await step(width+'-portal-classic',async()=>{await go(p,'/');await p.getByRole('button',{name:'原版',exact:true}).click();return await capture(p,width+'-portal-classic')})
 await step(width+'-grade-guide-scenes',async()=>{await go(p,'/path');const observed=[];for(const [label,key] of [['大一','freshman'],['大二','sophomore'],['大三','junior'],['大四','senior']]){const b=p.locator('.grade-choices button, .scenarios button').filter({hasText:label});if(await b.count())await b.first().click();else await p.getByRole('button',{name:new RegExp('^'+label)}).first().click();await capture(p,width+'-guide-'+key);observed.push({grade:label,mainText:(await p.locator('main').innerText()).slice(0,550)})}return observed})
 await c.close()
}}finally{await writeFile(join(out,'remaining-observations.json'),JSON.stringify({records,scenarios},null,2));await browser.close();console.log(JSON.stringify({records:records.length,scenarios:scenarios.length,failed:scenarios.filter(s=>s.status!=='observed')},null,2))}
