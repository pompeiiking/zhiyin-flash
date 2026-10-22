import { computed } from 'vue'
import { auth } from './auth'
import { backendDemo } from './backend-demo'
import { demo } from '../store'

/**
 * Student-facing display name.
 *
 * The account handle is an authentication identifier, never a name. Prefer the
 * student-provided profile field, then the bootstrap nickname, and only then a
 * neutral fallback. The backend currently mirrors the account into `nickname`
 * for accounts without a profile name, so that value must be rejected too.
 */
export function resolveDisplayName(): string {
  const account = demo.state.account
  const usable = (value: unknown) => {
    const text = typeof value === 'string' ? value.trim() : ''
    return !!text && text !== account
  }
  const fields = backendDemo.state.liveWorkspace?.profile_panel?.fields ?? []
  const name = fields.find(field => field.key === 'student_name' || field.key === 'name')?.value
  if (usable(name)) return String(name).trim()
  const nickname = auth.state.bootstrap?.identity?.nickname
  if (usable(nickname)) return String(nickname).trim()
  return '同学'
}

export const useDisplayName = () => computed(resolveDisplayName)
