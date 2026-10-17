import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// Load the display-layer copy helper without a bundler.
function load() {
  const source = readFileSync(new URL('../src/lib/student-voice.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  vm.runInNewContext(code, { exports })
  return exports
}
const voice = load()

test('advisor-voice instructions are rewritten to second person for students', () => {
  assert.equal(voice.studentVoice('问一句：这三个月里有没有哪段时间是被课程或考试占住的？'), '建议补充：这三个月里有没有哪段时间是被课程或考试占住的？')
  assert.equal(voice.studentVoice('再问一句：除了 Python 和 Excel，你还用过 SQL 吗？'), '建议补充：除了 Python 和 Excel，你还用过 SQL 吗？')
  assert.equal(voice.studentVoice('问问他有没有人留言或点赞'), '问问你有没有人留言或点赞')
  assert.equal(voice.studentVoice('问她的导师要一份岗位说明'), '问问你的导师要一份岗位说明')
  // 已经是学生语言的就原样返回
  assert.equal(voice.studentVoice('补上三个月内的课业或考试占用时间'), '补上三个月内的课业或考试占用时间')
  assert.equal(voice.studentVoice(''), '')
  assert.equal(voice.studentVoice(undefined), '')
})

test('report version diff uses student language instead of internal numbering', () => {
  const text = voice.studentVersionDiff('② 诊断产出：15 维与 SWOT / 依赖 7 项个人信息')
  assert.doesNotMatch(text, /②|SWOT|15 维|依赖 7 项/)
  assert.match(text, /诊断结论与优势\/短板/)
  assert.match(text, /参考了 7 项个人信息/)
  // 没有编号/内部词时不要改写
  assert.equal(voice.studentVersionDiff('本版没有提供差异摘要。'), '本版没有提供差异摘要。')
})
