/*
 * 课表的**形状与刻度**。
 *
 * 课与成绩本身来自后端：学生在绑定浮层里贴进原文，后端解析成快照
 * （`GET /app/workspace` 的 `academic_panel.courses`）。
 * 这里只留"一周怎么摆"这件界面上的事 —— 节次刻度与星期列，
 * 它们是排版参数，不是数据。
 */

export interface Course {
  id: string
  name: string
  teacher: string
  /** 1 = 周一 … 7 = 周日 */
  day: number
  /** 第几节开始、连上几节 */
  start: number
  span: number
  place: string
  /** 学分 */
  credit: number
  type: '必修' | '选修' | '实践'
  /** 成绩。还没考就是 undefined */
  score?: number
  /** 这门课和职业目标的关系 —— 由智能体算出来，可点开看依据 */
  why: string
  /** 它撑起画像里的哪一条 */
  supports: string[]
}

/** 课表按周几分列，早上第 1-3 节、下午 4-8 节、晚上 9-10 节 */
export const PERIODS = ['1-2 节', '3-4 节', '5-6 节', '7-8 节', '9-10 节']
export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五']
