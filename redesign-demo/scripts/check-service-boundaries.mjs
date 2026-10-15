// Reviewer fix confirmation: preview/local content must not claim online success.
import {createRequire} from 'node:module'
import {mkdirSync} from 'node:fs'
import {join,resolve} from 'node:path'
import {strict as assert} from 'node:assert'
const require=createRequire(import.meta.url)
let chromium
for(const path of [process.env.PW_PATH,'playwright',join(process.env.LOCALAPPDATA||'','npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)){try{chromium=require(path).chromium;break}catch{}}
if(!chromium)throw new Error('Set PW_PATH to Playwright')
const browser=await chromium.launch(), base=process.env.C2_URL||'http://127.0.0.1:5199', out=resolve(process.env.BOUNDARY_SHOTS||'.tmp-shots/service-boundaries')
mkdirSync(out,{recursive:true})
try{
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:width===390?844:1000},reducedMotion:'reduce'}),page=await context.newPage(),requests=[]
  page.on('request',r=>{if(r.url().includes('/api/v1'))requests.push(r.url())})
  await page.goto(`${base}/#/academic?as=mid&data=demo`)
  await page.getByRole('button',{name:'提供在线验证码',exact:true}).click()
  await page.getByRole('button',{name:'查看核验示例',exact:true}).click()
  await page.getByRole('button',{name:'读取当前资料',exact:true}).click()
  await page.getByText('已读取当前学校资料，核验流程预览没有提交在线验证码。',{exact:true}).waitFor()
  assert.equal(requests.length,0,'Preview must not submit a verification code or call an online workspace')
  assert(!(await page.locator('dialog[open]').innerText()).includes('已读取核验后的个人资料'))
  await page.getByRole('button',{name:'读取当前资料',exact:true}).scrollIntoViewIfNeeded()
  await page.screenshot({path:join(out,`academic-preview-${width}.png`)})
  await page.goto(`${base}/#/intel?as=mid&data=demo`)
  const note=page.locator('.intelligence-result').first()
  await note.waitFor();const text=await note.innerText()
  assert(text.includes('职业探索'))
  assert(!/演示|正式资讯服务/.test(text))
  await note.scrollIntoViewIfNeeded();await page.screenshot({path:join(out,`intel-local-${width}.png`)})
  assert.equal(requests.length,0)
  await context.close()
  const failure=await browser.newContext({viewport:{width,height:width===390?844:1000},reducedMotion:'reduce'}),fp=await failure.newPage()
  await fp.route('**/api/v1/**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({code:1007,message:'Unavailable',data:null})}))
  await fp.goto(`${base}/#/academic?as=mid&data=service`)
  await fp.getByRole('button',{name:'提供在线验证码',exact:true}).click()
  await fp.getByRole('button',{name:'查看核验示例',exact:true}).click()
  await fp.getByRole('button',{name:'读取当前资料',exact:true}).click()
  await fp.getByText('当前学校资料没有读取成功。原内容仍保留，可重试读取。',{exact:true}).waitFor()
  assert(!(await fp.locator('dialog[open]').innerText()).includes('核验结果已取得'))
  await fp.getByRole('button',{name:'读取当前资料',exact:true}).scrollIntoViewIfNeeded()
  await fp.screenshot({path:join(out,`academic-read-failure-${width}.png`)})
  await failure.close()
  console.log(`PASS reviewer fixes at ${width}px: preview read, local intel and mocked read failure`)
 }
}finally{await browser.close()}
