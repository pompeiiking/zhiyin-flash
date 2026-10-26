import { api } from '@/api/client'
import type { components } from '@/api/types'
import type { ModuleView, ReleaseJob } from '@/modules/client'
import type { PlatformStatus } from '@/developer/client'

export type AdminContext = components['schemas']['ModuleDeveloperContext']
export type ModulePolicy = components['schemas']['ModulePolicy']
export type CheckRecord = {
  id: string
  actor?: string
  created_at?: string
  passed?: boolean
  errors?: { module?: string; file?: string; message?: string }[]
  modules?: Record<string, unknown>
  source_revision?: string
  scope?: string
}
export type { ModuleView, ReleaseJob, PlatformStatus }

const json = (method: string, body: unknown) => ({ method, body: JSON.stringify(body) })

/** 管理台只调用已经存在的开发者/管理员接口，不在前端另造一份“管理数据”。 */
export const adminClient = {
  context: () => api<AdminContext>('/developer/context'),
  modules: () => api<ModuleView[]>('/developer/modules'),
  savePolicy: (moduleId: string, policy: ModulePolicy) =>
    api<ModulePolicy>(`/developer/modules/${encodeURIComponent(moduleId)}/policy`, json('PUT', policy)),
  checks: () => api<CheckRecord[]>('/developer/checks'),
  runChecks: () => api<CheckRecord>('/developer/checks', { method: 'POST' }),
  releases: () => api<ReleaseJob[]>('/developer/releases'),
  approve: (jobId: string) => api<ReleaseJob>(`/developer/releases/${encodeURIComponent(jobId)}/approve`, { method: 'POST' }),
  platform: () => api<PlatformStatus>('/developer/platform-status'),
  reloadConfig: () => api<Record<string, unknown>>('/app/config/reload', { method: 'POST' }),
}
