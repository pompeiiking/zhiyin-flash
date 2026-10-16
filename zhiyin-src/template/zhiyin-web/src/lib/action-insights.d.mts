import type { ActionPlanView, ActionTaskView, DirectionPlanView } from '../api/backend-types'
import type { DeepReadonly } from 'vue'
export type ActionRow = ActionTaskView & {phaseIndex:number;phase:string}
export function dateKey(value?:string|null):string
export function deadline(value?:string|null,now?:Date):{label:string;days:number|null;overdue:boolean}
export function actionRows(plan?:DeepReadonly<ActionPlanView>|null):ActionRow[]
export function actionStatusMatches(task:DeepReadonly<ActionTaskView>,filter:string):boolean
export function taskGroup(task:ActionTaskView,now?:Date):'done'|'undated'|'overdue'|'today'|'upcoming'
export function directionRanking<T extends DeepReadonly<DirectionPlanView>>(plans:readonly T[],order:string):T[]
