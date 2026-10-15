import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { strict as assert } from 'node:assert'
const require = createRequire(import.meta.url)
let chromium
for (const path of [process.env.PW_PATH, 'playwright', join(process.env.LOCALAPPDATA || '', 'npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)) {
  try { chromium = require(path).chromium; break } catch {}
}
if (!chromium) throw new Error('Set PW_PATH to the installed Playwright module')
const base = process.env.APP_URL || 'http://127.0.0.1:5199'
const out = resolve(process.env.MODERN_SHOTS || '../.tmp-shots/workspace-modern')
mkdirSync(out, { recursive: true })
const routes = ['portal','chat','profile','report','directions','home','plan','schedule','academic','notes','intel','review','tools','settings','reminders','guide','gallery','login','achievements','notfound','spec','path']
const browser = await chromium.launch(), measurements = [], failures = []
const headings = {portal:'问出方向',profile:'个人画像',report:'诊断报告',directions:'方向方案',home:'今日行动',plan:'阶段计划',schedule:'日历与课表',academic:'学籍与资料',notes:'待办与目标',intel:'岗位资讯',review:'复盘与记录',tools:'工具',settings:'账号设置',reminders:'提醒',guide:'使用指南',gallery:'通用组件与状态',login:'登录',achievements:'成长记录',notfound:'这个地址不存在',spec:'设计规范',path:'大一到大四'}
const go = async (page, route, account = 'mid') => {
  await page.goto(`${base}/#/${route}?as=${account}&data=demo`)
  if (route === 'chat') await page.locator('.dialogue-page h1:visible').waitFor()
  else await page.getByRole('heading',{level:1,name:new RegExp(headings[route])}).waitFor()
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0,0); const main=document.querySelector('.app__main');if(main) main.scrollTop=0;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))) })
}
try {
  for (const width of [1440,390]) {
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 1000 }, reducedMotion: 'reduce' })
    const page = await context.newPage()
    page.on('pageerror', e => failures.push(e.message))
    for (const route of routes) {
      await go(page, route)
      const data = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth > innerWidth + 1, title: document.querySelector('h1')?.textContent, fatal: !!document.getElementById('boot-error') }))
      measurements.push({ route, width, ...data })
      assert(!data.overflow && !data.fatal, `${route} ${width}: overflow or fatal error`)
      if (width === 390 && route === 'profile') {
        const third = await page.locator('.p7-row:visible').nth(2).boundingBox()
        assert(third && third.y + third.height < 780,'Mobile profile must show at least three fields before bottom navigation')
      }
      if (width === 390 && route === 'intel') {
        const first = await page.locator('.intel-title:visible').first().boundingBox()
        assert(first && first.y + first.height < 780,'Mobile intel must show an actual result before bottom navigation')
      }
      await page.screenshot({ path: join(out, `${route}-${width}-top.png`) })
      await page.evaluate(() => { window.scrollTo(0,document.body.scrollHeight); const main = document.querySelector('.app__main'); if(main) main.scrollTop = main.scrollHeight })
      await page.screenshot({ path: join(out, `${route}-${width}-bottom.png`) })
    }
    await go(page,'profile')
    assert.equal(await page.locator('.profile-insights:visible').count(),0,'Facts must lead, not analysis empty state')
    assert.equal(await page.locator('.p7-row:visible').count(),12)
    await page.getByRole('button',{name:'选择个人信息组织方式',exact:true}).click()
    await page.locator('.detail-popover').getByRole('button',{name:'按来源',exact:true}).click()
    await page.keyboard.press('Escape')
    assert((await page.locator('.p7-group__head:visible').first().innerText()).includes('学校档案'),'Compact chooser must retain alternate organization modes')
    const fact = page.getByRole('button',{name:/^专业：/})
    await fact.click()
    await page.locator('.detail-popover:visible').waitFor()
    const popRect = await page.locator('.detail-popover').boundingBox()
    assert(popRect.x >= 0 && popRect.x + popRect.width <= width,'Popover must fit viewport')
    await page.screenshot({path:join(out,`profile-popover-${width}.png`)})
    await page.getByRole('button',{name:'更正信息',exact:true}).click()
    await page.locator('dialog[open] textarea').fill('已更正的专业')
    await page.getByRole('button',{name:'保存更正',exact:true}).click()
    assert((await fact.innerText()).includes('已更正的专业'))
    await page.getByRole('button',{name:'待补充 3',exact:true}).click()
    assert.equal(await page.locator('.p7-gap:visible').count(),3)
    await page.getByRole('button',{name:'分析与判断',exact:true}).click()
    assert.equal(await page.locator('.profile-insights:visible').count(),1)
    await page.getByRole('button',{name:'个人信息 12',exact:true}).click()
    await page.getByRole('button',{name:'查看个人画像说明',exact:true}).focus()
    await page.keyboard.press('Enter')
    await page.locator('.detail-popover:visible').waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await page.locator('.detail-popover:visible').count(),0,'Escape closes and does not reopen on focus return')
    await go(page,'chat')
    const composer = await page.locator('.ws-composer').boundingBox()
    assert(composer.y >= 0 && composer.y + composer.height <= (width === 390 ? 780 : 1000),'Composer must remain in visible work area')
    await page.getByRole('textbox',{name:'咨询内容'}).fill('如何安排近期行动？')
    const send = await page.locator('.composer-send').boundingBox(), help = await page.locator('.composer-actions .detail-trigger').boundingBox()
    assert(send.x >= help.x + help.width || send.y >= help.y + help.height,'Send and help must not overlap')
    await go(page,'directions')
    const sliders = page.locator('.c2-weight-list input')
    await sliders.first().fill('5')
    await page.reload();await page.locator('.c2-weight-list input').first().waitFor()
    assert.equal(await sliders.first().inputValue(),'5','Direction priorities survive reload')
    if(width === 390) assert(await page.locator('.direction-mobile-comparison').isVisible())
    await go(page,'intel')
    await page.getByRole('button',{name:'打开资讯筛选与排序',exact:true}).click()
    await page.locator('.detail-popover').getByRole('button',{name:'岗位要求 8',exact:true}).click()
    await page.keyboard.press('Escape')
    assert.equal(await page.locator('.intel-title:visible').count(),8,'Compact filter must affect actual results')
    await page.getByRole('button',{name:'清空筛选',exact:true}).click()
    assert.equal(await page.locator('.intel-title:visible').count(),24)
    const freshContext = await browser.newContext({viewport:{width,height:width===390?844:1000}}), freshPage=await freshContext.newPage()
    await go(freshPage,'profile','fresh')
    assert.equal(await freshPage.locator('.p7-row:visible').count(),0,'Fresh account must not inherit profile')
    await freshContext.close()
    console.log(`PASS ${width}: 22 routes, profile details/edit/tabs, keyboard close, chat composer, saved direction weights, fresh account`)
    await context.close()
  }
  assert.equal(failures.length,0,failures.join('\n'))
  writeFileSync(join(out,'verification.json'),JSON.stringify({measurements,failures},null,2))
} finally { await browser.close() }
