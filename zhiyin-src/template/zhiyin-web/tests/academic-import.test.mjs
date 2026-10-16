import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/academic-parser.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,TextDecoder,Uint8Array})
const {parseAcademicSource:parse,decodeAcademicFile:decode}=exports

test('academic import preserves numeric zero and rejects nested values before confirmation',()=>{
  const rows=parse('[{"name":"课程","score":0,"credit":2,"point":0}]','grades')
  assert.equal(rows[0].score,'0'); assert.equal(rows[0].point,'0')
  assert.throws(()=>parse('{"grades":[{"name":"课程","score":{"x":1}}]}','grades'),/文字或数值/)
  assert.throws(()=>parse('课程名称,成绩\n','grades'),/没有可导入/)
})
test('academic CSV and TSV handle quotes, line breaks, BOM and literal grades',()=>{
  const rows=parse('\uFEFF课程名称,成绩,学分\r\n"课程,实验\n实践",优秀,2','grades')
  assert.equal(rows[0].name,'课程,实验\n实践'); assert.equal(rows[0].score,'优秀')
  assert.equal(parse('课程名称\t成绩\n课程\t88','grades')[0].score,'88')
  assert.throws(()=>parse('课程名称,成绩\n"课程,80','grades'),/引号/)
})
test('JSON and tabular course times reject invalid ordering and weekday',()=>{
  for(const source of ['[{"name":"课程","weekday":8}]','[{"name":"课程","start_period":3,"end_period":2}]','课程名称,星期,节次\n课程,周八,1-2']) assert.throws(()=>parse(source,'courses'))
  assert.equal(parse('课程名称,星期,节次,地点\n课程,周日,1-2,"实验楼,101"','courses')[0].place,'实验楼,101')
})
test('file decoding supports UTF8 BOM, UTF16 and common GBK Chinese exports',()=>{
  const utf8=new TextEncoder().encode('\uFEFF课程名称,成绩\n课程,88')
  assert.equal(parse(decode(utf8.buffer),'grades')[0].score,'88')
  const gbk=Uint8Array.from([0xbf,0xce,0xb3,0xcc])
  assert.equal(decode(gbk.buffer),'课程')
  const utf16=Buffer.from('\ufeff课程名称,成绩\n课程,88','utf16le')
  assert.equal(parse(decode(utf16.buffer.slice(utf16.byteOffset,utf16.byteOffset+utf16.byteLength)),'grades')[0].score,'88')
})
