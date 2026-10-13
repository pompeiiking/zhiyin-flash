import {createRequire} from 'node:module'
import {readFile,writeFile} from 'node:fs/promises'
import {dirname,join} from 'node:path'
import {fileURLToPath} from 'node:url'
const out=dirname(fileURLToPath(import.meta.url)), runtime=process.argv[2]
const require=createRequire(join(runtime,'package.json')), sharp=require('sharp')
const data=JSON.parse(await readFile(join(out,'browser-observations.json'),'utf8'))
const summary={records:data.records.length,scenarios:data.scenarios.length,failed:data.scenarios.filter(x=>x.status!=='observed'),overflow:data.records.filter(x=>x.horizontalOverflow).map(x=>({id:x.id,width:x.viewport.width,docWidth:x.doc.width})),baselines:data.records.filter(x=>/^\d+-/.test(x.id)&&!x.id.includes('sidebar')).map(x=>({id:x.id,docHeight:x.doc.height,smallTargets:x.targets.filter(t=>t.w<24||t.h<24).map(t=>({name:t.name,w:t.w,h:t.h})),bodyFonts:[...new Set(x.texts.filter(t=>t.tag==='P').map(t=>t.size+'/'+t.lineHeight))]})),actions:data.scenarios.filter(x=>x.details).map(x=>({id:x.id,details:x.details}))}
await writeFile(join(out,'evidence-summary.json'),JSON.stringify(summary,null,2))
const groups=[['portal','chat','profile','report','directions','home','plan','schedule'],['academic','notes','review','intel','tools','path','spec','not-found']]
for(const width of [1280,390])for(let group=0;group<groups.length;group++){
  const tileW=width===1280?400:210,tileH=width===1280?310:482,columns=4,items=[]
  for(let i=0;i<groups[group].length;i++){
    const id=width+'-'+groups[group][i],path=join(out,'screens',id+'.jpg'),m=await sharp(path).metadata()
    const screenshot=await sharp(path).extract({left:0,top:0,width:m.width,height:Math.min(m.height,width===1280?900:844)}).resize(tileW-8,tileH-30,{fit:'contain',background:'#e9edf3'}).toBuffer()
    const label=Buffer.from(`<svg width="${tileW}" height="26"><rect width="100%" height="100%" fill="#e9edf3"/><text x="8" y="18" font-family="sans-serif" font-size="14">${id}</text></svg>`)
    const left=(i%columns)*tileW,top=Math.floor(i/columns)*tileH
    items.push({input:label,left,top},{input:screenshot,left:left+4,top:top+26})
  }
  await sharp({create:{width:columns*tileW,height:tileH*2,channels:3,background:'#e9edf3'}}).composite(items).jpeg({quality:90}).toFile(join(out,`contact-${width}-${group+1}.jpg`))
}
console.log(JSON.stringify({records:summary.records,scenarios:summary.scenarios,failed:summary.failed,overflow:summary.overflow,actions:summary.actions.filter(x=>!/baseline/.test(x.id))},null,2))
