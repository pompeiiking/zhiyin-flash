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
try{
  for(const viewport of [{width:1280,height:900},{width:390,height:844},{width:320,height:740},{width:768,height:1024}]){
    const c=await context(viewport),p=await c.newPage();const errors=[];p.on('pageerror',e=>errors.push(String(e)))
    for(const [id,path]of routes){await step('baseline-'+viewport.width+'-'+id,async()=>{await go(p,path);const observed=await capture(p,viewport.width+'-'+id,'Current route baseline',viewport.width===1280||viewport.width===390);if(observed.viewport.width!==viewport.width)throw new Error('Viewport mismatch');return{heading:observed.headings[0]?.text,overflow:observed.horizontalOverflow,pageErrors:[...errors]}})}
    await c.close();console.log('baseline width '+viewport.width+' completed')
  }
  for(const width of [1280,390]){
    const c=await context({width,height:width===390?844:900}),p=await c.newPage()
    await step(width+'-navigation',async()=>{
      await go(p,'/chat');if(width===1280){await p.getByRole('button',{name:'收起侧栏',exact:true}).click();await capture(p,width+'-sidebar-collapsed');await p.getByRole('button',{name:'展开侧栏',exact:true}).click()}
      else{await p.getByRole('button',{name:'更多功能',exact:true}).click();await capture(p,width+'-more-directory');await p.keyboard.press('Escape')}
      await p.keyboard.press('Control+k');await p.getByRole('textbox',{name:'搜索命令',exact:true}).fill('不存在的功能检索');await capture(p,width+'-search-empty');await p.getByRole('textbox',{name:'搜索命令',exact:true}).fill('诊断报告');await p.keyboard.press('Enter');await p.getByRole('heading',{name:'诊断报告',exact:true}).waitFor();return{route:await p.url(),accountButtons:await p.getByRole('button',{name:'账号与演示设置',exact:true}).count()}
    })
    await step(width+'-profile-fields-edit',async()=>{
      await go(p,'/profile');await openDetails(p,'.ws-evidence details');await capture(p,width+'-profile-expanded');await p.getByRole('button',{name:'更正信息',exact:true}).first().click();await capture(p,width+'-profile-edit');const dialog=p.getByRole('dialog');const input=dialog.locator('textarea');await input.fill('');await dialog.getByRole('button',{name:/保存|确认/}).click();await capture(p,width+'-profile-error');await input.fill('审查用专业示例');await dialog.getByRole('button',{name:/保存|确认/}).click();await p.getByRole('tab',{name:'本人填写',exact:true}).click();await capture(p,width+'-profile-corrected');return{corrected:await p.getByText('审查用专业示例',{exact:true}).count()}
    })
    await step(width+'-report-expanded-versions',async()=>{
      await go(p,'/report');await openDetails(p);await capture(p,width+'-report-expanded');await p.getByRole('combobox',{name:'报告版本',exact:true}).selectOption('v1');await capture(p,width+'-report-old-version');await p.getByRole('link',{name:'诊断结果',exact:true}).click();await capture(p,width+'-report-return-current');return{version:await p.getByRole('combobox',{name:'报告版本',exact:true}).inputValue()}
    })
    await step(width+'-directions-select-compare',async()=>{
      await go(p,'/directions');await p.getByRole('button',{name:'选择这个方向',exact:true}).first().click();await capture(p,width+'-direction-selected');await p.getByRole('button',{name:'选择这个方向',exact:true}).first().click();await capture(p,width+'-direction-reselected');await p.getByRole('tab',{name:'逐项对照',exact:true}).click();await openDetails(p);await capture(p,width+'-direction-matrix-quadrant');return{selectedControls:await p.getByRole('button',{name:/已选择/}).count()}
    })
    await step(width+'-task-complete-restore-sources',async()=>{
      await go(p,'/home');const title=await p.locator('.journey-focus h2').innerText();await p.getByRole('button',{name:'标记完成',exact:true}).click();await capture(p,width+'-task-completed');await p.getByRole('link',{name:'查看复盘记录',exact:true}).click();const inReview=(await p.locator('main').innerText()).includes(title);await capture(p,width+'-task-in-review');await go(p,'/home');await p.getByRole('button',{name:'恢复任务',exact:true}).click();await capture(p,width+'-task-restored');await p.getByRole('tab',{name:/等待中/}).click();await openDetails(p);await capture(p,width+'-tasks-waiting');await go(p,'/plan');await p.getByRole('tab',{name:'执行任务',exact:true}).click();await openDetails(p);await capture(p,width+'-phase-tasks');await p.getByRole('tab',{name:'任务来源',exact:true}).click();await openDetails(p);await capture(p,width+'-task-sources');return{title,inReview}
    })
    await step(width+'-schedule-views-day-advice',async()=>{
      await go(p,'/schedule');await p.getByRole('button',{name:'10月15日',exact:true}).click();await p.getByRole('button',{name:'查看当日建议',exact:true}).click();await capture(p,width+'-calendar-day-advice');await p.getByRole('tab',{name:'一周课表',exact:true}).click();await capture(p,width+'-course-timetable');return{courseText:await p.locator('.desk-time-grid').innerText()}
    })
    await step(width+'-academic-import-verify-revoke',async()=>{
      await go(p,'/academic');await p.getByRole('tab',{name:'课程表',exact:true}).click();await capture(p,width+'-academic-courses');await p.getByRole('tab',{name:'成绩记录',exact:true}).click();await capture(p,width+'-academic-grades');await p.getByRole('button',{name:'导入课表与成绩',exact:true}).click();const d=p.getByRole('dialog',{name:'导入课表与成绩',exact:true});await d.getByRole('button',{name:'演示导入',exact:true}).click();await capture(p,width+'-academic-empty-error');await d.getByLabel('课表 JSON（可留空）').fill('{bad');await d.getByRole('button',{name:'演示导入',exact:true}).click();await capture(p,width+'-academic-json-error');await d.getByRole('button',{name:'上传文件',exact:true}).click();await d.locator('input[type=file]').first().setInputFiles({name:'audit.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify([{name:'跨节审查课程',weekday:1,start_period:1,end_period:4,place:'示例教室'},{name:'单节审查课程',weekday:3,start_period:3,end_period:3},{name:'周末审查课程',weekday:6,start_period:1,end_period:2},{name:'缺时间审查课程'}]))});await d.getByRole('button',{name:'演示导入',exact:true}).click();await capture(p,width+'-academic-import-success');await p.getByRole('button',{name:'提供在线验证码',exact:false}).click();const v=p.getByRole('dialog',{name:'核对学籍资料',exact:true});await v.getByRole('button',{name:'查看核验示例',exact:true}).click();await capture(p,width+'-verify-empty-error');await v.getByLabel('在线验证码',{exact:true}).fill('DEMO-2026');await v.getByRole('button',{name:'查看核验示例',exact:true}).click();await capture(p,width+'-verify-success');await go(p,'/schedule');await p.getByRole('tab',{name:'一周课表',exact:true}).click();await capture(p,width+'-courses-edge-cases');const repeats=await p.getByText('跨节审查课程',{exact:true}).count();await go(p,'/academic');await p.getByRole('button',{name:'撤回导入资料',exact:true}).click();await capture(p,width+'-academic-revoked');await go(p,'/schedule');await p.getByRole('tab',{name:'一周课表',exact:true}).click();await capture(p,width+'-course-empty');return{crossPeriodCopies:repeats}
    })
    await step(width+'-notes-all-actions',async()=>{
      await go(p,'/notes');await p.getByRole('button',{name:'添加',exact:true}).click();await capture(p,width+'-notes-empty-error');const field=p.getByRole('textbox',{name:'写下一件事',exact:true});const text='审查用待办：核对报告的来源与下一步';await field.fill(text);await p.getByRole('button',{name:'添加',exact:true}).click();await capture(p,width+'-notes-added');await field.fill(text);await p.getByRole('button',{name:'添加',exact:true}).click();const duplicateCount=await p.getByText(text,{exact:true}).count();await p.getByRole('button',{name:'完成：'+text,exact:true}).click();await capture(p,width+'-notes-completed');await p.getByRole('button',{name:'恢复：'+text,exact:true}).click();await capture(p,width+'-notes-restored');await field.fill('待办草稿');await p.getByRole('tab',{name:/个人目标/}).click();await p.getByRole('textbox',{name:'写下一个目标',exact:true}).fill('目标草稿');await p.getByRole('tab',{name:/我的待办/}).click();const draftRetained=await field.inputValue();await p.getByRole('button',{name:'删除：'+text,exact:true}).click();await capture(p,width+'-notes-deleted');return{duplicateCount,draftRetained}
    })
    await step(width+'-review-feedback-intervention',async()=>{
      await go(p,'/review');await p.getByRole('button',{name:'执行方法需调整',exact:true}).click();await capture(p,width+'-review-method');await p.getByRole('button',{name:'方向需重新评估',exact:true}).click();await capture(p,width+'-review-direction');await p.getByRole('button',{name:'任务负担过高',exact:true}).click();await p.getByRole('button',{name:'添加调整任务',exact:true}).click();await capture(p,width+'-review-task-added');await p.getByRole('button',{name:'查看提醒示例',exact:true}).click();await capture(p,width+'-intervention-modal');await p.keyboard.press('Escape');if(await p.getByRole('dialog').count()){const b=p.getByRole('button',{name:/关闭|稍后|暂/}).last();if(await b.isVisible())await b.click()}await go(p,'/review?view=achievements');await capture(p,width+'-achievements');return{url:await p.url()}
    })
    await step(width+'-intel-read-filter-match',async()=>{
      await go(p,'/intel');await p.getByRole('button',{name:'加载资讯示例',exact:true}).click();await capture(p,width+'-intel-populated');const links=await p.locator('.desk-intel-item__source a').evaluateAll(es=>es.map(e=>({text:e.textContent,href:e.href})));await p.getByRole('textbox',{name:'筛选资讯',exact:true}).fill('没有这种资讯的审查关键词');await capture(p,width+'-intel-no-results');await p.getByRole('button',{name:'清除筛选',exact:true}).click();await p.getByRole('button',{name:'职业匹配',exact:true}).click();await capture(p,width+'-career-match-panel');await p.getByRole('link',{name:'查看方向示例',exact:true}).click();await capture(p,width+'-intel-to-directions');return{links,url:await p.url()}
    })
    await step(width+'-chat-panels-materials-flow',async()=>{
      await go(p,'/chat');await p.getByRole('button',{name:'个人画像',exact:true}).click();await capture(p,width+'-chat-profile-panel');await p.keyboard.press('Escape');await p.getByRole('button',{name:'咨询成果',exact:true}).click();await capture(p,width+'-chat-outcomes');await p.getByRole('button',{name:/方法依据/}).click();await capture(p,width+'-chat-theory-nested');await p.keyboard.press('Escape');await p.keyboard.press('Escape');await p.locator('.ws-chat-flow').focus();await p.keyboard.press('Control+Home');await openDetails(p,'.dialogue-thread details');await capture(p,width+'-chat-evidence-handoff');await p.locator('.ws-composer input[type=file]').setInputFiles({name:'empty.md',mimeType:'text/markdown',buffer:Buffer.alloc(0)});await capture(p,width+'-attachment-empty-error');await p.locator('.ws-composer input[type=file]').setInputFiles({name:'审查用材料.md',mimeType:'text/markdown',buffer:Buffer.from('匿名示例材料。')});await capture(p,width+'-attachment-added');await p.getByRole('button',{name:'移除附件：审查用材料.md',exact:true}).click();await p.getByRole('textbox',{name:'咨询内容',exact:true}).fill('我现在做不动，想把任务改小一点。');await p.getByRole('button',{name:'发送',exact:true}).click();const thinking=await p.getByText('正在分析咨询内容…',{exact:true}).isVisible();await p.screenshot({path:join(out,'screens',width+'-chat-processing.jpg'),type:'jpeg',quality:83});await p.waitForTimeout(1600);await capture(p,width+'-chat-replied');const task=p.getByRole('button',{name:'加入行动计划',exact:true});if(await task.count())await task.last().click();await capture(p,width+'-chat-action-added');const copy=p.getByRole('button',{name:'复制顾问回复',exact:true});await copy.last().click();await capture(p,width+'-chat-copy-feedback');return{thinkingObserved:thinking}
    })
    await c.close()
  }
  for(const path of ['/chat','/profile','/report','/directions','/home','/plan','/schedule','/academic','/notes','/review','/intel','/tools']){await step('fresh-'+path.slice(1),async()=>{const c=await context({width:390,height:844});const p=await c.newPage();await go(p,path,'fresh');await capture(p,'fresh-'+path.slice(1),'Fresh account state');await c.close()})}
  await step('portal-login-errors-example',async()=>{const c=await context({width:390,height:844});const p=await c.newPage();await p.goto(base+'/#/',{waitUntil:'networkidle'});const choices=p.locator('.pe-story__choices button');for(let i=0;i<await choices.count();i++){await choices.nth(i).click();await capture(p,'portal-example-'+i)}await p.getByRole('button',{name:'开始第一个问题',exact:true}).click();await capture(p,'login-open');await p.getByRole('button',{name:'进入演示',exact:true}).click();await capture(p,'login-empty-error');await p.getByLabel('密码',{exact:true}).fill('local-audit-only');await p.getByRole('button',{name:'进入演示',exact:true}).click();await capture(p,'login-success');await c.close()})
  for(const variant of [{id:'dark',query:'theme=dark'},{id:'red',query:'accent=red'},{id:'dark-red',query:'theme=dark&accent=red'},{id:'dense',query:'style=dense'},{id:'soft',query:'style=soft'}]){await step('theme-'+variant.id,async()=>{const c=await context({width:390,height:844});const p=await c.newPage();await p.goto(base+'/#/report?as=mid&'+variant.query,{waitUntil:'networkidle'});await openDetails(p);await capture(p,'theme-'+variant.id);await c.close()})}
  await step('reduced-motion',async()=>{const c=await context({width:390,height:844},{reducedMotion:'reduce'});const p=await c.newPage();await go(p,'/');await capture(p,'reduced-portal');await go(p,'/home');await p.getByRole('button',{name:'标记完成',exact:true}).click();return await capture(p,'reduced-task-complete')})
  await step('print-report',async()=>{const c=await context({width:1280,height:900});const p=await c.newPage();await go(p,'/report');await p.emulateMedia({media:'print'});await p.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));await capture(p,'report-print');const visible=await p.locator('main').innerText();await p.pdf({path:join(out,'report-print-evidence.pdf'),format:'A4',printBackground:true});await c.close();return{dimensionEvidenceVisible:visible.includes('查看分值与依据'),printedTextChars:visible.length}})
}finally{
  await writeFile(join(out,'browser-observations.json'),JSON.stringify({researchDate:'2026-10-13',baseCommit:'305666d',base,engine:'isolated installed Chrome / Playwright',records,scenarios:retry?[...prior.scenarios.filter(s=>!retryIds.has(s.id)),...scenarios]:scenarios,initialInspectionFailures:prior?.scenarios.filter(s=>s.status==='inspection_failed')},null,2)+'\n')
  await browser.close()
  console.log(JSON.stringify({records:records.length,scenarios:scenarios.length,failed:scenarios.filter(s=>s.status==='inspection_failed')},null,2))
}
