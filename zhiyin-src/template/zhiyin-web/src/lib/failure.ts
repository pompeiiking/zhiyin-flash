import { BackendUnavailableError, UnauthorizedError } from '@/api/client'

/**
 * 一屏数据没读出来时，给用户看的那一句。
 *
 * 直接把 `cause.message` 摆到界面上是有过的做法，代价很具体：那是**层间消息**，
 * 写的时候对着的是写代码的人（"任务会话不存在：s-31f2"、"缺少提示词配置：
 * coach.clarify"）。用户看不懂，也不知道该做什么。
 *
 * 所以这里只给一句能行动的话，原始错误进控制台 ——
 * 排查需要的东西在那里，不在用户的界面上。
 */
export function failureText(cause: unknown, what = '这一屏'): string {
  if (cause instanceof UnauthorizedError) return '登录状态过期了，重新登录再看。'
  if (cause instanceof BackendUnavailableError) return '暂时连不上服务，稍后再试。'
  console.warn(`[${what}] 读取失败：`, cause)
  return '没读出来 —— 稍后再试一次。'
}
