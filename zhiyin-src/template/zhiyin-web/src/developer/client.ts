import { api, authToken } from '@/api/client'
import type { components } from '@/api/types'
import { jsonRequest, type ModuleView } from '@/modules/client'

type Schema = components['schemas']
export type JsonObject = Record<string, unknown>
export type ModuleKind = NonNullable<ModuleView['manifest']['kind']>
export type Project = Schema['DeveloperProjectView']
export interface Gate { id?: string; name?: string; stage?: string; status?: string; passed?: boolean; message?: string; path?: string; errors?: unknown[]; [key: string]: unknown }
// These envelopes expose extensible JSON in OpenAPI. Normalize only the fields
// rendered by the UI; all fixed protocol fields remain generated DTO aliases.
export type Version = Omit<Schema['DeveloperVersionView'], 'report' | 'events'> & {
  report: JsonObject & { gates: Gate[] }; events: { stage: string; message: string }[]
}
export type PlatformStatus = Required<Pick<Schema['DeveloperPlatformStatus'], 'base_commit' | 'pending_versions'>> & {
  worker: { last_seen: string | null; healthy: boolean }; environment: { revision: string | null; url: string }
}
export type Capability = Schema['ModuleCapability']
export type WorkflowNode = Schema['ModuleFlowNode']
export type WorkflowDraft = Schema['ModuleFlowDraft']
export type Workflow = Schema['ModuleFlowView']
export type WorkflowRun = Omit<Schema['ModuleFlowRun'], 'trace'> & { trace: (JsonObject & { node_id: string; module_id: string; operation: string; status: string; error?: string })[] }
const object = (value: unknown): JsonObject => value && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {}
const text = (value: unknown): string | undefined => typeof value === 'string' ? value : undefined
function normalizeVersion(value: Schema['DeveloperVersionView']): Version {
  const report = value.report || {}
  const gates = Array.isArray(report.gates) ? report.gates.map((item): Gate => {
    const gate = object(item)
    return { ...gate, id: text(gate.id), name: text(gate.name), stage: text(gate.stage), status: text(gate.status), message: text(gate.message), path: text(gate.path), passed: typeof gate.passed === 'boolean' ? gate.passed : undefined, errors: Array.isArray(gate.errors) ? gate.errors : undefined }
  }) : []
  return { ...value, report: { ...report, gates }, events: (value.events || []).map(event => ({ stage: text(event.stage) || '', message: text(event.message) || '' })) }
}
function normalizeRun(value: Schema['ModuleFlowRun']): WorkflowRun {
  return { ...value, trace: (value.trace || []).map(item => ({ ...item, node_id: text(item.node_id) || '', module_id: text(item.module_id) || '', operation: text(item.operation) || '', status: text(item.status) || '', error: text(item.error) })) }
}
const path = (id: string) => encodeURIComponent(id)
export const projects = () => api<Project[]>('/developer/projects')
export const createProject = (body: Schema['DeveloperProjectCreate']) => api<Project>('/developer/projects', jsonRequest('POST', body))
export const saveProject = (id: string, body: Schema['DeveloperProjectUpdate']) => api<Project>(`/developer/projects/${path(id)}`, jsonRequest('PUT', body))
export const versions = async (id: string) => (await api<Schema['DeveloperVersionView'][]>(`/developer/projects/${path(id)}/versions`)).map(normalizeVersion)
export const getVersion = async (id: string) => normalizeVersion(await api<Schema['DeveloperVersionView']>(`/developer/versions/${path(id)}`))
export const uploadVersion = async (id: string, body: Schema['DeveloperUpload']) => normalizeVersion(await api<Schema['DeveloperVersionView']>(`/developer/projects/${path(id)}/versions`, jsonRequest('POST', body)))
export const retryVersion = async (id: string) => normalizeVersion(await api<Schema['DeveloperVersionView']>(`/developer/versions/${path(id)}/retry`, jsonRequest('POST', {})))
export const releaseVersion = (id: string) => api<Schema['ReleaseJob']>(`/developer/versions/${path(id)}/release`, jsonRequest('POST', {}))
export const platformStatus = async (): Promise<PlatformStatus> => {
  const value = await api<Schema['DeveloperPlatformStatus']>('/developer/platform-status')
  return { base_commit: value.base_commit || '', pending_versions: value.pending_versions || 0, worker: { last_seen: text(value.worker?.last_seen) || null, healthy: value.worker?.healthy === true }, environment: { revision: text(value.environment?.revision) || null, url: text(value.environment?.url) || '' } }
}
export const capabilities = () => api<Capability[]>('/developer/capabilities')
export const workflows = () => api<Workflow[]>('/developer/workflows')
export const saveWorkflow = (body: WorkflowDraft) => api<Workflow>('/developer/workflows', jsonRequest('POST', body))
export const publishWorkflow = (id: string, revision: number) => api<Workflow>(`/developer/workflows/${path(id)}/publish`, jsonRequest('POST', { expected_revision: revision }))
export const unpublishWorkflow = (id: string, revision: number) => api<Workflow>(`/developer/workflows/${path(id)}/unpublish`, jsonRequest('POST', { expected_revision: revision } satisfies Schema['ModuleFlowPublish']))
export const runWorkflow = async (id: string, body: Schema['ModuleFlowRunRequest']) => normalizeRun(await api<Schema['ModuleFlowRun']>(`/developer/workflows/${path(id)}/run`, jsonRequest('POST', body)))
export const workflowRuns = async (id: string) => (await api<Schema['ModuleFlowRun'][]>(`/developer/workflows/${path(id)}/runs`)).map(normalizeRun)
export const pretty = (value: unknown) => JSON.stringify(value, null, 2)
export function parseObject(text: string, label: string): JsonObject {
  const value: unknown = JSON.parse(text)
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label}必须是 JSON 对象。`)
  return value as JsonObject
}
export async function downloadPackage(url: string, filename: string) {
  const response = await fetch(`/api/v1${url}`, { headers: { Authorization: `Bearer ${authToken()}` } })
  if (!response.ok || response.headers.get('content-type')?.includes('application/json')) {
    const body = await response.json().catch(() => null) as { message?: string } | null
    throw new Error(body?.message || `下载失败：HTTP ${response.status}`)
  }
  const objectUrl = URL.createObjectURL(await response.blob())
  const link = document.createElement('a'); link.href = objectUrl; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}
export const downloadTemplate = (body: { kind: ModuleKind; module_id: string; name: string; owner: string }) => downloadPackage(`/developer/templates?${new URLSearchParams(body)}`, `${body.module_id}-template.zip`)
export const downloadVersion = (version: Version) => downloadPackage(`/developer/versions/${path(version.id)}/package`, `${version.project_id}-${version.version}.zip`)
export const statusLabel: Record<string, string> = { queued: '等待执行', running: '执行中', passed: '验收通过', failed: '失败', succeeded: '成功', blocked: '等待处理', skipped: '未执行', pending: '等待执行', error: '失败' }
