/**
 * 展示层文案清洗：把"写给顾问看的内部指令"变成"对学生说的第二人称说明"。
 *
 * 背景（深度测试 P2-02 / STU-002）：后端/模型给的"建议行动 / 优先行动 / 下一步"
 * 里会出现「问一句：这三个月里有没有哪段时间是被课程或考试占住的？」这类对顾问
 * 下指令的口吻，还有「问他有没有…」这种第三人称。学生看到会不知道"谁去问谁"。
 *
 * 这一层只改**显示出来的字符串**，不改接口、不改数据、不改逻辑：
 *   · 画像页（StudentView / ProfileInsights）与报告页（FullReportBody /
 *     AssessmentView）调同一个 `studentVoice()`，保证同一句话在两处口吻一致；
 *   · 报告版本记录的差异摘要（`diff_from_previous`，如「② 诊断产出：15 维与 SWOT /
 *     依赖 7 项个人信息」）用 `studentVersionDiff()` 换成学生语言（#4）。
 *
 * 清洗必须"看不出被清洗过"：没命中的文案原样返回。
 */

/** 内部口吻 → 面向学生的第二人称。 */
export function studentVoice(value: unknown): string {
  if (value === null || value === undefined) return ''
  let text = String(value).trim()
  if (!text) return ''

  text = text
    // 「问一句：…」「再问一句：…」→「建议补充：…」
    .replace(/(?:再)?问一句\s*[：:]\s*/g, '建议补充：')
    // 「问一句 + 空格」无冒号
    .replace(/(?:再)?问一句\s+/g, '建议补充：')
    // 直接以「问……」「问这次支教持续多久」开头的顾问指令 → 「建议补充：……」
    // （「问问他/她/他们」交给下一条改成第二人称，不走这个前缀替换）
    .replace(/^(?:再)?问(?![他她们问])/, '建议补充：')
    // 「问问他/她/他们有没有…」→ 第二人称
    .replace(/问问他们/g, '问问你们')
    .replace(/问他们/g, '问问你们')
    .replace(/问问他|问问她/g, '问问你')
    .replace(/问(?:他|她)/g, '问问你')
    // 建议句里的第三人称改成"你"（避开「其他」）
    .replace(/他们/g, '你们')
    .replace(/(?<!其)他/g, '你')
    .replace(/她/g, '你')
    // 「去问他有没有…」这类已由上面覆盖；再收拾「问问你一下」等重复
    .replace(/问问你一下/g, '问问你')
    // 内部自称句式
    .replace(/^(?:可以|需要)?帮你问(?:问|一下)/, '可以补充')
    // 收拾多余空白与标点前空格
    .replace(/[ \t\u3000]{2,}/g, ' ')
    .replace(/[ \t\u3000]+([，。；：！？、）])/g, '$1')
    .trim()

  return text
}

/**
 * 报告版本差异摘要 → 学生语言。
 * 输入例：`② 诊断产出：15 维与 SWOT / 依赖 7 项个人信息`
 * 输出例：`诊断结论与优势/短板；参考了 7 项个人信息`
 */
export function studentVersionDiff(value: unknown): string {
  if (value === null || value === undefined) return ''
  const raw = String(value).trim()
  if (!raw) return ''
  if (/本版没有提供差异摘要/.test(raw)) return raw

  // 先按 ①②③… 拆成独立条目；没有编号时整句当一条。
  const marked = raw.split(/(?=[①②③④⑤⑥⑦⑧⑨⑩])/).filter((part) => part.replace(/[①②③④⑤⑥⑦⑧⑨⑩\s]/g, '').length > 0)
  const parts = marked.length > 1 ? marked : [raw]

  const friendly = parts.map((part) => {
    let text = part.replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, '').trim()
    const bits: string[] = []
    // 「诊断产出：15 维与 SWOT」这种内部摘要 → 一句学生能懂的话
    if (/诊断产出/.test(text) && /(?:SWOT|维)/i.test(text)) {
      bits.push('诊断结论与优势/短板')
      text = text.replace(/诊断产出[：:][\s\S]*?(?=依赖|$)/, '').replace(/^[\s/／；;，,、]+/, '').trim()
    }
    // 「依赖 N 项个人信息」→「参考了 N 项个人信息」
    const dependency = text.match(/依赖\s*(\d+)\s*项(?:个人信息)?/)
    if (dependency) {
      bits.push(`参考了 ${dependency[1]} 项个人信息`)
      text = text.replace(/依赖\s*\d+\s*项(?:个人信息)?/g, '').replace(/^[\s/／；;，,、)）\]]+/, '').trim()
    }
    text = text
      .replace(/^(\d{1,2})[)）.、]\s*/, '')
      .replace(/SWOT/gi, '优势与短板分析')
      .replace(/诊断产出[：:]\s*/g, '诊断结论：')
      .replace(/(\d+)\s*维/g, '$1 个维度')
      .replace(/^[\s/／；;，,、]+/, '')
      .trim()
    if (text) bits.push(text)
    return bits.join('；')
  }).filter(Boolean)

  return friendly.length ? studentVoice(friendly.join('；')) : studentVoice(raw)
}
