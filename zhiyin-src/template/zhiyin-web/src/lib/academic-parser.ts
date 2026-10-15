import type { AcademicCourseView, AcademicGradeView } from '../api/backend-types'
// Parse copied/exported tables locally so users can check every row before replacing a snapshot.
function table(source: string): string[][] {
  const delimiter = source.split(/\r?\n/)[0]?.includes('\t') ? '\t' : ','
  const rows: string[][] = []; let row: string[] = [], field = '', quoted = false
  const input = source.replace(/^\uFEFF/,'').replace(/\r\n/g,'\n')
  for (let i=0;i<input.length;i++) {
    const c=input[i]
    if(c==='"') { if(quoted&&input[i+1]==='"'){field+='"';i++}else quoted=!quoted }
    else if(c===delimiter&&!quoted){row.push(field.trim());field=''}
    else if(c==='\n'&&!quoted){row.push(field.trim());if(row.some(Boolean))rows.push(row);row=[];field=''}
    else field+=c
  }
  if(quoted)throw new Error('表格中的引号没有成对结束，请检查导出内容。')
  row.push(field.trim());if(row.some(Boolean))rows.push(row)
  return rows
}
const aliases: Record<string,string> = {'课程':'name','课程名称':'name','科目':'name','课程名':'name','星期':'weekday','周几':'weekday','星期几':'weekday','开始节次':'start_period','起始节次':'start_period','结束节次':'end_period','节次':'periods','上课节次':'periods','周次':'weeks','地点':'place','教室':'place','教师':'teacher','任课教师':'teacher','成绩':'score','分数':'score','学分':'credit','绩点':'point','学期':'term','类别':'category'}
export function parseAcademicTable<T extends AcademicCourseView | AcademicGradeView>(source: string, kind: 'courses'|'grades'): T[] {
  if(!source.trim())return []
  const rows=table(source), headers=(rows.shift()??[]).map(h=>aliases[h]??h)
  if(!headers.includes('name'))throw new Error('表格第一行需要“课程名称”列。可以从教务表格复制含表头的内容。')
  return rows.map((cells,index)=>{
    const record: Record<string, string | number> = {}
    headers.forEach((h,i)=>{if(cells[i])record[h]=cells[i]})
    if(!String(record.name??'').trim())throw new Error('第'+(index+2)+'行缺少课程名称。')
    if(kind==='courses') {
      if(record.weekday!==undefined){const w=String(record.weekday).replace(/星期|周/g,'');const weekday=/^\d$/.test(w)?Number(w):['一','二','三','四','五','六','日'].indexOf(w)+1;record.weekday=w==='天'?7:weekday;if(Number(record.weekday)<1||Number(record.weekday)>7)throw new Error('第'+(index+2)+'行星期应为1–7或周一至周日。')}
      if(record.periods){const match=String(record.periods).replace(/第|节/g,'').match(/^(\d+)(?:\s*[-–~至]\s*(\d+))?$/);if(!match)throw new Error('第'+(index+2)+'行节次应为数字或范围，例如1–4。');record.start_period=Number(match[1]);record.end_period=Number(match[2]??match[1]);delete record.periods}
      for(const key of ['start_period','end_period'])if(record[key]!==undefined){record[key]=Number(record[key]);if(!Number.isInteger(record[key])||Number(record[key])<1)throw new Error('第'+(index+2)+'行节次需要正整数。')}
      if(record.start_period!==undefined&&record.end_period!==undefined&&Number(record.start_period)>Number(record.end_period))throw new Error('第'+(index+2)+'行结束节次不能早于开始节次。')
    }
    return record as T
  })
}
