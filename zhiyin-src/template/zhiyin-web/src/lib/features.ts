import { auth } from './auth'

export function featureEnabled(feature: string): boolean {
  return !!auth.state.bootstrap && auth.state.bootstrap.feature_flags?.[feature] !== false
}

export function routeEnabled(path: string): boolean {
  const feature = ({ '/report': 'report_full_text', '/schedule': 'calendar', '/achievements': 'achievements' } as Record<string, string>)[path.split('?')[0]!]
  // Bootstrap failure is "unknown", not "feature disabled". Keeping the route
  // lets the page show its own retryable network error instead of replacing a
  // valid deep link with "此功能当前未开放".
  if (feature && !auth.state.bootstrap) return true
  return !feature || featureEnabled(feature)
}
