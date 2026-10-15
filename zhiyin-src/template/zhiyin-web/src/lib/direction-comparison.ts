import { reactive } from 'vue'
import { rememberSession } from './session-cache'

// Approved C2 synthetic comparison scale; no current recruitment claims.
export const directionCriteria = [
  { key:'major', label:'专业对口', scores:[90,74,84] },
  { key:'jobs', label:'岗位数量', scores:[90,74,70] },
  { key:'pay', label:'起薪水平', scores:[78,86,58] },
  { key:'stable', label:'稳定性', scores:[66,52,92] },
  { key:'place', label:'通勤与地点', scores:[70,60,88] },
]

// Like the prototype's closure, priorities survive page/view changes during this session.
export const directionPriorities = reactive<Record<string, number>>(
  Object.fromEntries(directionCriteria.map(criterion => [criterion.key, 3])),
)

rememberSession('direction-priorities', directionPriorities, directionCriteria.map(item => item.key))
