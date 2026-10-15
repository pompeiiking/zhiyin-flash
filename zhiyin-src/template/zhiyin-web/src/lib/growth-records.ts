import {badgeCopy} from './server-copy'
import { computed } from 'vue'
import { systemData } from './system-data'
const labels:Record<string,string>={first_answer:'认真回答过一次',first_gap_claim:'认领过一条差距',decision_made:'做出过一次选择',first_task_done:'完成过一件任务',first_review:'回头复盘过一次'}
export const growthRecords=computed(()=>(systemData.achievements?.items??[]).map(r=>({id:r.key,title:badgeCopy(r.key,'label',labels[r.key]||'成长记录'),source:'系统行为记录',topic:'成长记录',method:'由服务端记录确认',at:r.unlocked_at??null,done:!!r.unlocked,evidence:[r.unlocked?'已达到该项成长条件':'尚未达到该项成长条件'],next:badgeCopy(r.key,'how',r.unlocked?'继续下一步':'继续咨询与行动')})))
