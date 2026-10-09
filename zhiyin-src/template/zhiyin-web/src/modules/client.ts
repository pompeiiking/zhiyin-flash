import { api } from '@/api/client'
import type { components } from '@/api/types'
export type ModuleView = components['schemas']['ModuleView']
export type ModuleResult = components['schemas']['ModuleResult']
export type ModulePolicy = components['schemas']['ModulePolicy']
export type ReleaseJob = components['schemas']['ReleaseJob']
export type PreviewMode = 'fixture' | 'live'
export type DeveloperContext = components['schemas']['ModuleDeveloperContext']
export const jsonRequest = (method: string, body: unknown) => ({ method, body: JSON.stringify(body) })
export const listModules = (surface: 'application' | 'conversation' = 'application') => api<ModuleView[]>(`/app/modules?surface=${surface}`)
export const moduleData = (id: string, expected_version?: string) => expected_version
  ? api<ModuleResult>(`/app/modules/${encodeURIComponent(id)}/invoke`, jsonRequest('POST', { input: {}, expected_version }))
  : api<ModuleResult>(`/app/modules/${encodeURIComponent(id)}/data`)
export const previewModule = (id: string, mode: PreviewMode, fixture: string, input: Record<string, unknown> = {}, expected_version?: string) => api<ModuleResult>(`/developer/modules/${encodeURIComponent(id)}/preview`, jsonRequest('POST', { mode, fixture, input, expected_version }))
export const moduleAction = (id: string, action: string, payload: Record<string, unknown>, expected_version?: string) => api<ModuleResult>(`/app/modules/${encodeURIComponent(id)}/actions`, jsonRequest('POST', { action, payload, expected_version }))
