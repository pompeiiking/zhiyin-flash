import { auth } from './auth'

export function featureEnabled(feature: string): boolean {
  return !!auth.state.bootstrap && auth.state.bootstrap.feature_flags?.[feature] !== false
}

export function routeEnabled(path: string): boolean {
  const feature = ({ '/report': 'report_full_text', '/schedule': 'calendar', '/achievements': 'achievements' } as Record<string, string>)[path.split('?')[0]!]
  return !feature || featureEnabled(feature)
}
