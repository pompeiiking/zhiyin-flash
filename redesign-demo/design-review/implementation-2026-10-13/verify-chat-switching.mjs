import {createRequire} from 'node:module'
import {join,dirname} from 'node:path'
import {fileURLToPath} from 'node:url'
import {readFile,writeFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const i=process.argv.indexOf('--runtime'),require=createRequire(join(process.argv[i+1],'package.json')),{chromium}=require('playwright'),out=dirname(fileURLToPath(import.meta.url))
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true})
try{const p=await browser.newPage({viewport:{width:390,height:844}});await p.goto('http://127.0.0.1:5281/#/chat?as=mid',{waitUntil:'networkidle'});await p.getByRole('textbox',{name:'咨询内容',exact:true}).fill('我现在做不动，想把行动改小一点');await p.getByRole('button',{name:'发送',exact:true}).click();await p.waitForTimeout(650);assert.ok(await p.getByRole('button',{name:'复制顾问回复',exact:true}).last().isDisabled());assert.ok(await p.getByRole('button',{name:'新对话',exact:true}).isDisabled());await p.waitForTimeout(1000);assert.equal(await p.getByRole('button',{name:'新对话',exact:true}).isDisabled(),false);const file=join(out,'confirmation-results.json'),data=JSON.parse(await readFile(file,'utf8'));data.results.push({id:'streaming-keeps-session-switching-locked',status:'passed'});await writeFile(file,JSON.stringify(data,null,2));console.log('Streaming session guard passed')}finally{await browser.close()}
