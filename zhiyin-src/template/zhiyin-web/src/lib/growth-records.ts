import { badgeCopy } from './server-copy'
import { computed } from 'vue'
import { systemData } from './system-data'

type GrowthRecordMeta = {
  stage: string
  order: number
  to: string
  actionLabel: string
  purpose: string
}

const labels: Record<string, string> = {
  first_answer: '认真回答过一次',
  first_gap_claim: '认领过一条差距',
  decision_made: '做出过一次选择',
  first_task_done: '完成过一件任务',
  first_review: '回头复盘过一次'
}

const recordMeta: Record<string, GrowthRecordMeta> = {
  first_answer: { stage: '说清现状', order: 1, to: '/chat', actionLabel: '去说明现状', purpose: '把当前处境说清楚，让后续建议有真实依据。' },
  first_gap_claim: { stage: '认领重点', order: 2, to: '/chat', actionLabel: '继续咨询', purpose: '把一项差距变成你愿意处理的明确问题。' },
  decision_made: { stage: '确定方向', order: 3, to: '/directions', actionLabel: '去比较方向', purpose: '留下你认真比较并选择过的方向，方便之后调整。' },
  first_task_done: { stage: '开始行动', order: 4, to: '/home', actionLabel: '查看今日行动', purpose: '把计划推进到一次真实完成，而不只停留在想法里。' },
  first_review: { stage: '回看调整', order: 5, to: '/review', actionLabel: '去做复盘', purpose: '用真实执行结果校正判断，决定接下来怎样调整。' }
}

function cleanCopy(value: string) {
  return value.replace(/\s*[—–]+\s*/g, '，')
}

export const growthRecords = computed(() => (systemData.achievements?.items ?? [])
  .map((record, index) => {
    const meta = recordMeta[record.key] ?? {
      stage: '其他记录',
      order: 100 + index,
      to: '/chat',
      actionLabel: '继续咨询',
      purpose: '留下这次行动的真实记录。'
    }
    const done = Boolean(record.unlocked)
    return {
      id: record.key,
      title: cleanCopy(badgeCopy(record.key, 'label', labels[record.key] || '完成记录')),
      stage: meta.stage,
      order: meta.order,
      to: meta.to,
      actionLabel: meta.actionLabel,
      purpose: meta.purpose,
      source: '系统行为记录',
      requirement: cleanCopy(badgeCopy(record.key, 'how', done ? '继续下一步' : '继续咨询与行动')),
      at: record.unlocked_at ?? null,
      done
    }
  })
  .sort((left, right) => left.order - right.order))
