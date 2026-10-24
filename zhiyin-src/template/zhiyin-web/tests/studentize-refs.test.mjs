import test from 'node:test'
import assert from 'node:assert/strict'
import { studentizeRefs } from '../src/lib/format.ts'

test('内部追溯引用翻译成学生可读的话', () => {
  assert.equal(studentizeRefs('chsi-pdf://imports/chsi-pdf-3b8e6654a194d4a92b8b7faf2fa19bc6f'), '学信网学籍报告（PDF 导入）')
  assert.equal(studentizeRefs('derived://study_year/enrolled_at=2024-08-22'), '按入学日期推算')
  assert.equal(studentizeRefs('field:enrollment_status'), '学籍状态')
  assert.equal(studentizeRefs('field:school 与 field:major 一致'), '学校 与 专业 一致')
  assert.equal(studentizeRefs('evidence:enrollment_status:0 与 evidence:enrollment_status:1 同源'), '学籍状态的第1份材料 与 学籍状态的第2份材料 同源')
  assert.equal(studentizeRefs('conflict:9f1c2b3a 一条未裁定'), '一条待核对的冲突 一条未裁定')
})

test('评估正文整句翻译后不残留内部记号', () => {
  const line = 'field:enrollment_status 直接记录为"在籍（注册学籍）"，来源为 chsi-pdf://imports/chsi-pdf-3b8e6654a194d4a92b8b7faf2fa19bc6f 导入记录。'
  const out = studentizeRefs(line)
  assert.ok(!/field:|chsi-pdf:\/\//.test(out), out)
  assert.match(out, /学籍状态 直接记录为"在籍（注册学籍）"/)
  assert.match(out, /学信网学籍报告（PDF 导入） 导入记录/)
})

test('http(s) 链接与普通文本原样保留', () => {
  const url = '来源：https://www.chsi.com.cn/ 在线验证页'
  assert.equal(studentizeRefs(url), url)
  assert.equal(studentizeRefs('这份材料还没有在线核验。'), '这份材料还没有在线核验。')
  assert.equal(studentizeRefs(''), '')
  assert.equal(studentizeRefs(undefined), '')
})
