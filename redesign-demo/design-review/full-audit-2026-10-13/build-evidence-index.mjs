import {readFile,writeFile,readdir,access} from 'node:fs/promises'
import {dirname,join,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const out=dirname(fileURLToPath(import.meta.url)),allRecords=[],allScenarios=[]
for(const prefix of ['browser','additional','remaining']){const d=JSON.parse(await readFile(join(out,prefix+'-observations.json'),'utf8'));allRecords.push(...d.records);allScenarios.push(...d.scenarios)}
const records=[...new Map(allRecords.map(x=>[x.id,x])).values()]
const baseline=records.filter(r=>/^\d+-(portal|chat|profile|report|directions|home|plan|schedule|academic|notes|review|intel|tools|path|spec|not-found)$/.test(r.id))
const actions=records.filter(r=>!baseline.includes(r))
const row=r=>`| ${r.id} | ${r.viewport.width}×${r.viewport.height} | ${r.horizontalOverflow?'整页溢出，见具体判断':'无整页溢出'} | ${r.screenshot?'[截图]('+r.screenshot+')':'仅测量/文字'} · [文字](states/${r.id}.txt) |`
const shots=(await readdir(join(out,'screens'))).filter(x=>x.endsWith('.jpg'))
const references=JSON.parse(await readFile(join(out,'reference-observations.json'),'utf8'))
const index=`# 状态与截图证据索引

日期：2026-10-13。参见[总调研报告](总调研报告.md)和[逐页八维表](逐页八维审查表.md)。当前提交305666d；隔离的Chrome浏览器、本地Vite演示。索引列的是现状证据，没有新设计效果图。

总计${allScenarios.length}个检查场景，${allRecords.length}条测量记录，去重${records.length}个状态标识，${shots.length}张本地页面截图。无未完成的脚本定位检查；产品问题仍见报告。原始重复记录保留，索引使用同标识最后一次观测。320/768的基线只测量和记录文字，1280/390保存全页截图。

## 基线：16路由×4视口

| 状态标识 | 实际视口 | 整页宽度检查 | 证据 |
|---|---|---|---|
${baseline.map(row).join('\n')}

## 展开、操作、异常、设置和辅助场景

| 状态标识 | 实际视口 | 整页宽度检查 | 证据 |
|---|---|---|---|
${actions.map(row).join('\n')}

即时处理中截图：[桌面](screens/1280-chat-processing.jpg)、[手机](screens/390-chat-processing.jpg)。这两张在处理瞬间保存，未另行计入DOM测量。

## 外部官方参考

| 参考 | 实际结果 | 证据 |
|---|---|---|
${references.map(r=>`| [${r.id}](${r.url}) | HTTP${r.status??'不可达'}；${r.result==='read-and-captured'?'已读并截图':r.result==='response-not-useful'?'无可用正文，未作为视觉依据':'未取得页面'} | ${r.desktop?'[桌面]('+r.desktop+')':''}${r.mobile?' · [手机]('+r.mobile+')':''} · [页面文字](references/${r.id}.txt) |`).join('\n')}

FullCalendar最终有效路径为/demos；旧路径404记录不计为参考组件。本轮只实际观察当前月/周示例，不宣称其它懒加载视图全部交互验证。

## 原始数据与可复查脚本

- [主要观察](browser-observations.json)、[键盘/主题/异常补查](additional-observations.json)、[目标/入口/场景补查](remaining-observations.json)。
- [18种配置的报告文字对比度初筛](theme-contrast-observations.json)，只作局部初筛，不是整站合规结论。
- [首次定位失败记录](first-pass-observations.json)，当前已针对失败补查，不能把这些工具错误当作UI错误。
- [设计扫描](detector.json)，建议需按当前挂载页面、门户保留要求和实际语义复核。
- [打印证据](report-print-evidence.pdf)，只作为现状检查，未作为最终报告排版交付。
- 复查脚本：audit-browser.mjs、audit-additional.mjs、audit-remaining.mjs、inspect-references.mjs；使用已有Chrome/Playwright，不安装库。脚本中的页面变化只在隔离演示会话。
`
await writeFile(join(out,'证据索引.md'),index)
const broken=[]
for(const name of ['总调研报告.md','逐页八维审查表.md','证据索引.md']){
 const source=await readFile(join(out,name),'utf8')
 for(const match of source.matchAll(/\]\(([^)]+)\)/g)){const target=match[1];if(/^(https?:|#)/.test(target))continue;try{await access(resolve(out,target))}catch{broken.push({file:name,target})}}
}
const matrix=await readFile(join(out,'逐页八维审查表.md'),'utf8')
const summary={date:'2026-10-13',scenarios:allScenarios.length,baselineScenarios:allScenarios.filter(x=>x.id.startsWith('baseline-')).length,nonBaselineScenarios:allScenarios.filter(x=>!x.id.startsWith('baseline-')).length,measurementRecords:allRecords.length,uniqueStateIds:records.length,screenshots:shots.length,unfinishedInspections:allScenarios.filter(x=>x.status!=='observed'),matrixRows:(matrix.match(/^\| [A-H] \|/gm)||[]).length,brokenLocalReportLinks:broken}
await writeFile(join(out,'report-validation.json'),JSON.stringify(summary,null,2))
console.log(JSON.stringify(summary,null,2));if(broken.length||summary.matrixRows!==104||summary.unfinishedInspections.length)process.exitCode=1
