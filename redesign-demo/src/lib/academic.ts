import type { AcademicCourseView } from '../api/backend-types'
/** Partial records remain visible in the source list, without claiming a timetable slot. */
export function hasCourseTime(course: AcademicCourseView) {
  return Number.isInteger(course.weekday) && course.weekday! >= 1 && course.weekday! <= 7
    && Number.isInteger(course.start_period) && course.start_period! >= 1
    && Number.isInteger(course.end_period) && course.end_period! >= course.start_period!
}
export function courseTimeLabel(course: AcademicCourseView) {
  return hasCourseTime(course)
    ? '周' + ['', '一', '二', '三', '四', '五', '六', '日'][course.weekday!] + ' · ' + course.start_period + '–' + course.end_period + '节'
    : '时间待补充'
}
