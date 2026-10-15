import type {
  CalendarMark,
  ChatTurn,
  CollectItem,
  DirectionPlan,
  Grade,
  Notice,
  ProfileField,
  ReportSection,
  ReviewItem,
  TaskItem,
} from './types'


/** Empty defaults: personal records are exclusively loaded from the backend. */
export const STUDENT = {name:'当前用户',grade:'待补充',major:'待补充',school:'待补充',currentHost:'咨询顾问',hosts:[] as {key:string;state:string;note:string}[]}
export const PROFILE_FIELDS:ProfileField[]=[]
export const COLLECT_ITEMS:CollectItem[]=[]
export const REPORT_SECTIONS:ReportSection[]=[]
export const SELF_RADAR:{label:string;value:number}[]=[]
export const THRESHOLD_COMPARE:{label:string;mine:number;requirement:number;note:string}[]=[]
export const REPORT_SUMMARY=''
export const REPORT_VERSIONS:{id:string;label:string;at:string;change:string;fit:number}[]=[]
export const DIRECTION_PLANS:DirectionPlan[]=[]
export const TASKS_BY_GRADE:Record<Grade,TaskItem[]>={freshman:[],sophomore:[],junior:[],senior:[]}
export const CALENDAR_MARKS:CalendarMark[]=[]
export const CHAT_TURNS:ChatTurn[]=[]
export const NOTICES:Notice[]=[]
export const REVIEW_ITEMS:ReviewItem[]=[]
export const REVIEW_CONCLUSION=''
export const INTERVENTION={host:'行动支持顾问',title:'',body:'',action:'',secondary:'',rules:[] as string[]}
