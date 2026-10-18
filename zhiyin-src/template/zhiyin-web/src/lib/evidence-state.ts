/**
 * 证据状态（F5）：全站只认这五个状态，徽标/文案/颜色从这里取。
 *
 * 为什么要有这一层：画像说"待补充"、报告说"仍需验证"、方向说"尚待补充"，
 * 同一件事四个说法；学生无法判断"到底缺什么、能信到什么程度"。
 * 这里把状态收敛成：
 *   recorded      已记录        有来源、可选核对
 *   missing       待补充        还没有这条资料
 *   unverified    待核对        有内容，但还没与材料/现实核对
 *   verified      已核验        已与学校/材料核对过（学信核验、导入成绩等）
 *   out-of-scope  按资料范围未使用  有资料，但本报告/本次判断没有用到它
 *
 * 只做展示映射，不改后端字段；无法识别的状态回落为"待核对"，不隐藏。
 */
export type EvidenceState = 'recorded' | 'missing' | 'unverified' | 'verified' | 'out-of-scope'

export interface EvidenceStateMeta {
  label: string
  /** 一句解释，放在 title / 展开说明里 */
  hint: string
  /** 与 tokens.css 的语义色对应：主色=已核验，注意=待补充，中性=已记录/未使用 */
  tone: 'neutral' | 'primary' | 'attention'
}

export const EVIDENCE_STATE_META: Record<EvidenceState, EvidenceStateMeta> = {
  recorded: { label: '已记录', hint: '这条信息已经有来源，可以点开核对。', tone: 'neutral' },
  missing: { label: '待补充', hint: '这项资料还没有拿到，相关判断只能先按假设处理。', tone: 'attention' },
  unverified: { label: '待核对', hint: '已有内容，但还没有与材料或现实经历核对。', tone: 'attention' },
  verified: { label: '已核验', hint: '已经和学校资料或你上传的材料核对过。', tone: 'primary' },
  'out-of-scope': { label: '按资料范围未使用', hint: '有这项资料，但本次判断没有用到它。', tone: 'neutral' },
}

/** 把后端/文案里的松散说法归一到五态；认不出时按"待核对"，不假装已核验。 */
export function toEvidenceState(value: unknown): EvidenceState {
  const text = String(value ?? '').trim()
  if (!text) return 'unverified'
  // 组件 prop 直接传机器状态（'recorded' 等）时原样命中，不能落到"待核对"
  if (text in EVIDENCE_STATE_META) return text as EvidenceState
  if (/已核验|核验通过|verified/i.test(text)) return 'verified'
  if (/待补充|缺少|缺失|未获取|未取得|尚待补充/.test(text)) return 'missing'
  if (/未使用|范围外|不在本次|未纳入/.test(text)) return 'out-of-scope'
  if (/已记录|已收录|已有/.test(text)) return 'recorded'
  return 'unverified'
}

export function evidenceLabel(value: unknown): string {
  return EVIDENCE_STATE_META[toEvidenceState(value)].label
}

export function evidenceTone(value: unknown): EvidenceStateMeta['tone'] {
  return EVIDENCE_STATE_META[toEvidenceState(value)].tone
}
