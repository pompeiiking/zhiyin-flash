import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import assert from 'node:assert/strict'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PW_PATH || join(process.env.LOCALAPPDATA, 'npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright'))
const out = resolve('../.tmp-shots/avatar-navigation'); mkdirSync(out,{recursive:true})
const browser = await chromium.launch(), errors=[], results=[]
const base=process.env.APP_URL || 'http://127.0.0.1:5199'
try {
 for(const width of [1440,390]) {
  const context=await browser.newContext({viewport:{width,height:width===390?844:1000}}), page=await context.newPage()
  page.on('pageerror',e=>errors.push(e.message))
  const go=async(route,title)=>{await page.goto(`${base}/#/${route}?as=mid&data=demo`);await page.getByRole('heading',{level:1,name:title,exact:true}).waitFor()}
  await go('plan','阶段计划')
  assert.equal(await page.locator('.workspace-section-nav').count(),0,'No added page-level route menu')
  if(width===1440) {
   assert.equal(await page.locator('.desk-nav .c2-nav-group').count(),4)
   assert.equal(await page.locator('.desk-nav a').count(),12)
  } else {
   assert.equal(await page.locator('.ws-bookmarks a').count(),4)
   assert.equal(await page.getByRole('button',{name:'更多功能',exact:true}).count(),1)
  }
  await page.keyboard.press('Control+k');await page.getByRole('textbox',{name:'搜索命令'}).waitFor()
  const choices=await page.locator('.ws-command-results').innerText()
  for(const forbidden of ['重置','切换场景']) assert(!choices.includes(forbidden),`ordinary search exposes ${forbidden}`)
  await page.getByRole('textbox',{name:'搜索命令'}).fill('诊断报告')
  await page.keyboard.press('Enter');await page.getByRole('heading',{level:1,name:'诊断报告',exact:true}).waitFor()
  await go('directions','方向方案')
  await page.getByRole('button',{name:'调整选择偏好',exact:true}).click()
  const group=page.getByRole('group',{name:'专业对口的重要程度',exact:true})
  await group.getByText('适中',{exact:true}).click();await page.keyboard.press('ArrowRight')
  assert(await group.getByRole('radio',{name:'较高',exact:true}).isChecked())
  await page.reload();await page.getByRole('button',{name:'调整选择偏好',exact:true}).click();await group.waitFor();assert(await group.getByRole('radio',{name:'较高',exact:true}).isChecked())
  assert.equal(await page.locator('input[type="range"]').count(),0)
  await page.keyboard.press('Escape')
  await page.screenshot({path:join(out,`directions-${width}.png`)})
  await go('gallery','通用组件与状态');const gallery=page.locator('.robot-preview')
  const ids=await page.locator('svg [id]').evaluateAll(nodes=>nodes.map(n=>n.id));assert.equal(ids.length,new Set(ids).size,'SVG paint ids must be unique')
  const missing=await gallery.locator('svg [fill],[filter],[stroke]').evaluateAll(nodes=>nodes.flatMap(n=>['fill','filter','stroke'].flatMap(key=>{const m=n.getAttribute(key)?.match(/url\(#([^)]*)\)/);return m&&!document.getElementById(m[1])?[m[1]]:[]})))
  assert.deepEqual(missing,[])
  assert.equal(await gallery.locator('.robot-avatar').count(),4)
  assert.equal(new Set(await gallery.locator('.robot-avatar').evaluateAll(nodes=>nodes.map(n=>n.dataset.agent))).size,4)
  for(const [label,state,part,animation] of [['思考','thinking','eyes','robot-consider'],['回复','speaking','mouth','robot-speak'],['完成','done','head','robot-nod']]) {
   await gallery.getByRole('button',{name:label,exact:true}).click()
   assert.equal(await gallery.locator(`.robot-avatar[data-state="${state}"]`).count(),4)
   const names=await gallery.locator(`[data-part="${part}"]`).evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n).animationName))
   assert(names.every(n=>n.includes(animation)),`${state} must animate actual SVG parts`)
  }
  await gallery.getByRole('button',{name:'待命',exact:true}).click()
  await gallery.screenshot({path:join(out,`robots-${width}-light.png`)})
  await page.evaluate(()=>{document.documentElement.dataset.theme='dark'})
  await gallery.screenshot({path:join(out,`robots-${width}-dark.png`)})
  await gallery.getByRole('button',{name:'思考',exact:true}).click();await page.emulateMedia({reducedMotion:'reduce'})
  assert((await gallery.locator('[data-part]').evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n).animationName))).every(n=>n==='none'),'Reduced motion must disable SVG animation')
  results.push({width,navigation:'pass',keyboardWeights:'pass',identity:'pass',motion:'pass',reducedMotion:'pass'})
  console.log(`PASS ${width}: original grouped navigation, no added page route menu, search, keyboard preferences, robot identities/paint ids/motion/reduced motion`)
  await context.close()
 }
 assert.deepEqual(errors,[]);writeFileSync(join(out,'verification.json'),JSON.stringify({results,errors},null,2))
} finally {await browser.close()}
