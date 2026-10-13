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
async function contrasts(p){return p.evaluate(()=>{
 const rgb=v=>{const m=v.match(/[\d.]+/g);return m?m.slice(0,4).map(Number):[0,0,0,0]}
 const composite=(f,b)=>{const a=f.length>3?f[3]:1;return[0,1,2].map(i=>f[i]*a+b[i]*(1-a))}
 const background=e=>{const chain=[];for(let n=e;n;n=n.parentElement)chain.unshift(n);let color=[255,255,255];for(const n of chain)color=composite(rgb(getComputedStyle(n).backgroundColor),color);return color}
 const luminance=a=>a.map(v=>{const c=v/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0)
 const result=[];for(const e of document.querySelectorAll('p,span,button,a,small,h1,h2,h3,dt,dd,label,text')){const r=e.getBoundingClientRect();if(!r.width||!r.height||!e.textContent?.trim()||!Array.from(e.childNodes).some(n=>n.nodeType===3&&n.textContent.trim()))continue;const s=getComputedStyle(e),bg=background(e),fg=composite(rgb(s.color),bg),l1=luminance(bg),l2=luminance(fg),ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);const size=parseFloat(s.fontSize),large=size>=24||(size>=18.66&&parseInt(s.fontWeight)>=700);if(ratio<(large?3:4.5))result.push({text:e.textContent.trim().slice(0,100),class:e.className.baseVal??e.className,size:s.fontSize,color:s.color,bg:bg.map(Math.round),ratio:+ratio.toFixed(2),disabled:e.disabled??false})}
 return {theme:document.documentElement.dataset.theme,accent:document.documentElement.dataset.accent,style:document.documentElement.dataset.style,approximateLowContrast:result}
})}
async function focusInfo(p){return p.evaluate(()=>({active:document.activeElement?.outerHTML.slice(0,300),insideDialog:!!document.activeElement?.closest('dialog[open],[role=dialog]')}))}
try{
for(const width of [1280,390]){
 const c=await context({width,height:width===390?844:900}),p=await c.newPage()
 await step(width+'-dialog-keyboard',async()=>{await go(p,'/profile');const trigger=p.getByRole('button',{name:'账号与演示设置',exact:true});await trigger.focus();await trigger.press('Enter');await p.getByRole('dialog',{name:'账号与演示设置',exact:true}).waitFor();const opened=await focusInfo(p);for(let i=0;i<12;i++)await p.keyboard.press('Tab');const cycled=await focusInfo(p);await p.keyboard.press('Escape');const closed=await p.getByRole('dialog').count();const returned=await focusInfo(p);return{opened,cycled,closed,returned}})
 await step(width+'-task-shrink-accept-reject-arrange',async()=>{await go(p,'/home');await p.getByRole('button',{name:'先拆成 5 分钟',exact:true}).click();await capture(p,width+'-task-shrunk');await p.getByRole('tab',{name:/等待中/}).click();await openDetails(p);const accept=p.getByRole('button',{name:'采纳建议',exact:true});const accepted=await accept.count();if(accepted)await accept.first().click();await openDetails(p);const reject=p.getByRole('button',{name:'拒绝建议',exact:true});const rejected=await reject.count();if(rejected)await reject.first().click();await openDetails(p);const arrange=p.getByRole('button',{name:'安排执行',exact:true});const arranged=await arrange.count();if(arranged)await arrange.first().click();await capture(p,width+'-task-suggestion-actions');return{acceptedCandidates:accepted,rejectedCandidates:rejected,arrangedCandidates:arranged}})
 await step(width+'-history-options-draft',async()=>{await go(p,'/chat');await p.getByRole('textbox',{name:'咨询内容',exact:true}).fill('跨页面草稿审查');await go(p,'/profile');await go(p,'/chat');const draftAfterRoute=await p.getByRole('textbox',{name:'咨询内容',exact:true}).inputValue();if(width===1280)await p.getByRole('button',{name:'新建咨询',exact:true}).click();else await p.getByRole('button',{name:'新对话',exact:true}).click();await capture(p,width+'-new-chat');const entries=p.locator('.dialogue-starters button');const entryCount=await entries.count();if(entryCount)await entries.first().click();else{await p.getByRole('textbox',{name:'咨询内容',exact:true}).fill('希望先了解兴趣');await p.getByRole('button',{name:'发送',exact:true}).click()}await p.waitForTimeout(1600);const options=p.locator('.dialogue-options button');const optionCount=await options.count();if(optionCount)await options.first().click();await p.waitForTimeout(1600);await capture(p,width+'-chat-option-response');if(width===390){await p.getByRole('button',{name:'历史会话',exact:true}).click();await capture(p,width+'-chat-history');await p.getByRole('dialog').locator('button').filter({hasText:'先了解自己的兴趣与能力'}).click()}else await p.getByRole('button',{name:/先了解自己的兴趣与能力/}).click();await capture(p,width+'-history-restored');return{draftAfterRoute,entryCount,optionCount}})
 await step(width+'-notifications-empty-and-action',async()=>{await go(p,'/home');await p.getByRole('button',{name:/提醒，/}).click();await capture(p,width+'-notice-open');const d=p.getByRole('dialog',{name:'提醒',exact:true});const primary=d.locator('.btn--primary');const actionText=await primary.innerText();await primary.click();await p.getByRole('button',{name:/提醒，/}).click();await capture(p,width+'-notice-empty');await p.keyboard.press('Escape');return{actionText,url:p.url()}})
 await step(width+'-tabs-keyboard',async()=>{await go(p,'/academic');const tab=p.getByRole('tab',{name:'课程表',exact:true});await tab.focus();await p.keyboard.press('ArrowRight');await p.keyboard.press('Enter');await capture(p,width+'-tabs-keyboard');return{active:await focusInfo(p),selected:await p.locator('[role=tab][aria-selected=true]').innerText()}})
 await c.close()
}
await step('login-keyboard-320',async()=>{const c=await context({width:320,height:740}),p=await c.newPage();await p.goto(base+'/#/?signin=1',{waitUntil:'networkidle'});await capture(p,'login-320');const initial=await focusInfo(p);await p.keyboard.press('Escape');const escapeCloses=await p.getByRole('dialog',{name:'登录',exact:true}).count()===0;const sequence=[];for(let i=0;i<16;i++){await p.keyboard.press('Tab');sequence.push(await focusInfo(p))}await capture(p,'login-focus-escape');await c.close();return{initial,escapeCloses,focusEscaped:sequence.some(x=>!x.insideDialog),sequence}})
await step('skin-keyboard-320',async()=>{const c=await context({width:320,height:740}),p=await c.newPage();await go(p,'/report');await p.getByRole('button',{name:'皮肤',exact:true}).click();await capture(p,'skin-320');await p.getByRole('button',{name:'深色',exact:true}).click();await p.keyboard.press('Escape');const stillOpen=await p.getByRole('dialog',{name:'选择皮肤',exact:true}).count()>0;await c.close();return{escapeAfterInnerControlLeavesOpen:stillOpen}})
await step('touch-short-viewport',async()=>{const c=await context({width:390,height:844},{isMobile:true,hasTouch:true}),p=await c.newPage();await go(p,'/home');await p.getByRole('button',{name:'标记完成',exact:true}).tap();await p.getByRole('button',{name:'更多功能',exact:true}).tap();await capture(p,'touch-more');await p.getByRole('button',{name:'关闭面板',exact:true}).tap();await go(p,'/chat');await p.setViewportSize({width:390,height:450});await p.getByRole('textbox',{name:'咨询内容',exact:true}).focus();await p.getByRole('textbox',{name:'咨询内容',exact:true}).fill('缩短可视高度时的输入检查');const x=await capture(p,'short-chat-input');await c.close();return{viewport:x.viewport,doc:x.doc,composer:x.blocks.filter(b=>b.class.includes('ws-composer')),touch: true}})
await step('attachments-limits',async()=>{const c=await context({width:390,height:844}),p=await c.newPage();await go(p,'/chat');const file=p.locator('.ws-composer input[type=file]');await file.setInputFiles({name:'大材料.md',mimeType:'text/markdown',buffer:Buffer.alloc(2*1024*1024+1,65)});await capture(p,'attachment-size-error');for(let i=0;i<6;i++)await file.setInputFiles({name:'材料'+i+'.md',mimeType:'text/markdown',buffer:Buffer.from('示例')});await capture(p,'attachment-count-error');await c.close()})
await step('chat-clipboard',async()=>{const c=await context({width:390,height:844},{permissions:['clipboard-read','clipboard-write']}),p=await c.newPage();await go(p,'/chat');await p.getByRole('button',{name:'复制顾问回复',exact:true}).last().click();const copied=await p.evaluate(()=>navigator.clipboard.readText());await c.close();return{copiedChars:copied.length,copiedPrefix:copied.slice(0,80)}})
const themeChecks=[]
for(const theme of ['light','dark','system'])for(const accent of ['blue','red'])for(const style of ['plain','dense','soft']){await step('skin-'+theme+'-'+accent+'-'+style,async()=>{const c=await context({width:390,height:844},{colorScheme:'dark'}),p=await c.newPage();await p.goto(base+'/#/report?as=mid&theme='+theme+'&accent='+accent+'&style='+style,{waitUntil:'networkidle'});await p.waitForTimeout(500);await openDetails(p);await p.waitForTimeout(500);const m=await metrics(p),contrast=await contrasts(p);themeChecks.push({query:{theme,accent,style},viewport:m.viewport,overflow:m.horizontalOverflow,mainFont:m.texts.find(t=>t.tag==='P'),...contrast});await c.close();return{effective:contrast.theme,overflow:m.horizontalOverflow,lowContrastCount:contrast.approximateLowContrast.length}})}
await writeFile(join(out,'theme-contrast-observations.json'),JSON.stringify(themeChecks,null,2))
await step('text-spacing-stress',async()=>{const c=await context({width:390,height:844}),p=await c.newPage();const checked=[];for(const path of ['/chat','/profile','/report','/directions','/home','/schedule','/academic','/notes','/review','/intel']){await go(p,path);await p.addStyleTag({content:'* {line-height:1.5 !important;letter-spacing:.12em !important;word-spacing:.16em !important} p {margin-bottom:2em !important}'});checked.push(await capture(p,'spacing-'+path.slice(1)))}await c.close();return checked.map(x=>({id:x.id,overflow:x.horizontalOverflow}))})
await step('keyboard-fail-route',async()=>{const c=await context({width:1280,height:900}),p=await c.newPage();await p.route('**/src/views/IntelView.vue*',r=>r.abort('failed'));await p.goto(base+'/#/intel?as=mid',{waitUntil:'domcontentloaded'}).catch(()=>{});await p.waitForTimeout(2400);await capture(p,'route-load-failure');const message=await p.locator('body').innerText();await c.close();return{text:message.slice(-700)}})
}finally{
 await writeFile(join(out,'additional-observations.json'),JSON.stringify({records,scenarios},null,2));await browser.close();console.log(JSON.stringify({records:records.length,scenarios:scenarios.length,failed:scenarios.filter(s=>s.status!=='observed')},null,2))
}
