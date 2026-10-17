import {api,authToken} from './client'
import type {ActionPlanView,TaskEdit,PhaseEdit,Preferences,Semester,ReviewEdit,NotificationEdit,MeasurementEdit,MeasurementRecordView,PreferencesEdit,SemesterEdit,DirectionWeightsEdit,DirectionWeights,ConversationTurnView} from './backend-types'
type MeasurementBatch=Omit<MeasurementEdit,'expected'>
const write=(method:string,body:unknown)=>({method,body:JSON.stringify(body)})
export type Notice={id:string;title:string;body:string;occurred_at?:string;status:string;snoozed_until?:string;action?:{kind?:string;label?:string};related_task_id?:string}
export type Review=ReviewEdit & {id:string;task_text:string;updated_at:string;applied_at:string|null;history:Review[]}
export type Comparison={version:number|null;method:string;weights:DirectionWeights;plans:{id:string;name:string;score:number|null;missing:string[];measurements:MeasurementBatch['measurements'];opportunity:number|null;feasibility:number|null}[]}
export type Measurements={items:MeasurementBatch[];history:MeasurementBatch[]}
export const studentApi={
 preferences:()=>api<Preferences>('/app/preferences'),savePreferences:(v:PreferencesEdit)=>api<Preferences>('/app/preferences',write('PUT',v)),
 saveTask:(v:TaskEdit,id?:string)=>api<ActionPlanView>('/app/plan/action/tasks'+(id?'/'+encodeURIComponent(id):''),write(id?'PUT':'POST',v)),
 savePhase:(v:PhaseEdit,id?:string)=>api<ActionPlanView>('/app/plan/action/phases'+(id?'/'+encodeURIComponent(id):''),write(id?'PUT':'POST',v)),
 notifications:()=>api<Notice[]>('/app/notifications'),notification:(id:string,v:NotificationEdit)=>api<Notice>('/app/notifications/'+encodeURIComponent(id),write('PATCH',v)),
 reviews:()=>api<{items:Review[];reasons:Record<string,number>}>('/app/reviews'),saveReview:(v:ReviewEdit,id?:string)=>api<Review>('/app/reviews'+(id?'/'+id:''),write(id?'PUT':'POST',v)),applyReview:(id:string)=>api<Review>('/app/reviews/'+id+'/apply',{method:'POST'}),
 semester:()=>api<Semester|null>('/app/schedule/semester'),saveSemester:(v:SemesterEdit)=>api<Semester>('/app/schedule/semester',write('PUT',v)),
 workload:(start:string)=>api<{configured:boolean;weeks:{start:string;course_minutes:number;task_minutes:number;remaining_minutes:number|null}[];conflicts:{first:string;second:string;at:string}[];missing:string[];capacity_method?:string}>('/app/schedule/workload?start='+start),
 measurements:()=>api<Measurements>('/app/measurements'),saveMeasurements:(v:MeasurementEdit)=>api<MeasurementRecordView>('/app/measurements',write('POST',v)),
 weights:()=>api<DirectionWeights>('/app/plan/direction-weights'),saveWeights:(v:DirectionWeightsEdit)=>api<DirectionWeights>('/app/plan/direction-weights',write('PUT',v)),compare:()=>api<Comparison>('/app/plan/direction-comparison'),
 snapshot:(type:string,version:number)=>api<{version:number;content:unknown}>('/app/assets/'+type+'/versions/'+version+'/content'),
 sessionSnapshot:(id:string)=>api<ConversationTurnView|null>('/app/sessions/'+encodeURIComponent(id)+'/snapshot'),
}
export async function downloadExport(id:string,filename:string){
 const token=authToken(),response=await fetch('/api/v1/app/assets/download/'+encodeURIComponent(id),{headers:{Authorization:'Bearer '+token}})
 if(authToken()!==token)throw new Error('账号已变更，请重新下载。')
 if(!response.ok)throw new Error('文件下载失败，请重新生成后再试。')
 const blob=await response.blob();if(authToken()!==token)throw new Error('账号已变更，请重新下载。')
 const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
