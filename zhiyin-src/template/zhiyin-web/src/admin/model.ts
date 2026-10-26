import type { CheckRecord, ModuleView, PlatformStatus, ReleaseJob } from './client'

/** 模块种类：应用提供完整界面，技能供智能体调用，hybrid 两者都有。 */
export type ModuleKind = 'application' | 'tool' | 'hybrid'

export type StatusTone = 'ok' | 'warn' | 'danger' | 'muted' | 'running'

export interface AdminStats {
  modules: number
  enabled: number
  disabled: number
  blocked: number
  requested: number
  failedChecks: number
  pendingVersions: number
  workerHealthy: boolean
}

export interface AttentionItem {
  id: string
  title: string
  detail: string
  tab: 'modules' | 'releases' | 'workflows' | 'system'
  tone: StatusTone
  action: string
}

export const MODULE_KIND_LABEL: Record<ModuleKind, string> = {
  application: '应用模块',
  tool: '技能组件',
  hybrid: '应用与技能',
}

export function moduleKind(module: ModuleView): ModuleKind {
  return (module.manifest.kind || 'application') as ModuleKind
}

export function moduleStatus(module: ModuleView): { label: string; tone: StatusTone } {
  if (module.effective_enabled) return { label: '已启用', tone: 'ok' }
  if (module.policy.enabled) return { label: '受阻', tone: 'warn' }
  return { label: '未启用', tone: 'muted' }
}

/** 一眼看清这个模块被授予了什么；不给“权限分”这种没有口径的数字。 */
export function moduleGrantSummary(module: ModuleView): string {
  const parts = [
    (module.policy.reads ?? []).length ? `读取 ${(module.policy.reads ?? []).length}` : '',
    (module.policy.actions ?? []).length ? `操作 ${(module.policy.actions ?? []).length}` : '',
    (module.policy.agents ?? []).length ? `智能体 ${(module.policy.agents ?? []).length}` : '',
  ].filter(Boolean)
  return parts.join(' · ') || '尚未授权'
}

export function adminStats(
  modules: ModuleView[],
  jobs: ReleaseJob[],
  checks: CheckRecord[],
  platform?: PlatformStatus,
): AdminStats {
  const enabled = modules.filter(module => module.effective_enabled).length
  const blocked = modules.filter(module => module.policy.enabled && !module.effective_enabled).length
  const requested = jobs.filter(job => job.status === 'requested').length
  const failedChecks = checks.filter(check => check.passed === false).length
  return {
    modules: modules.length,
    enabled,
    disabled: modules.length - enabled,
    blocked,
    requested,
    failedChecks,
    pendingVersions: platform?.pending_versions ?? 0,
    workerHealthy: platform?.worker.healthy === true,
  }
}

/** 只列“现在真的需要人处理”的事，不把一般信息也塞进待办。 */
export function attentionItems(
  stats: AdminStats,
  modules: ModuleView[],
  checks: CheckRecord[],
  platform?: PlatformStatus,
): AttentionItem[] {
  const items: AttentionItem[] = []
  if (stats.requested) {
    items.push({
      id: 'approvals',
      title: `${stats.requested} 个发布任务等待确认`,
      detail: '确认后才进入执行队列；未确认的任务不会改动环境。',
      tab: 'releases',
      tone: 'warn',
      action: '去确认',
    })
  }
  if (stats.blocked) {
    const names = modules
      .filter(module => module.policy.enabled && !module.effective_enabled)
      .slice(0, 3)
      .map(module => module.manifest.name)
    items.push({
      id: 'blocked-modules',
      title: `${stats.blocked} 个模块已授权但实际不可用`,
      detail: `${names.join('、')}${stats.blocked > names.length ? ' 等' : ''} 的所属应用未启用。`,
      tab: 'modules',
      tone: 'danger',
      action: '查看模块',
    })
  }
  if (stats.failedChecks) {
    const latest = checks.find(check => check.passed === false)
    items.push({
      id: 'checks',
      title: `最近检查中有 ${stats.failedChecks} 次未通过`,
      detail: latest?.errors?.[0]?.message || '检查报告保留了具体模块与文件位置。',
      tab: 'releases',
      tone: 'danger',
      action: '查看检查',
    })
  }
  if (platform && !stats.workerHealthy) {
    items.push({
      id: 'worker',
      title: '自动验收执行器离线或尚无心跳',
      detail: platform.worker.last_seen ? `最近心跳 ${platform.worker.last_seen}` : '还没有收到执行器心跳。',
      tab: 'system',
      tone: 'warn',
      action: '检查环境',
    })
  }
  return items
}

export const JOB_STATUS: Record<string, { label: string; tone: StatusTone }> = {
  requested: { label: '待确认', tone: 'warn' },
  queued: { label: '等待执行', tone: 'muted' },
  running: { label: '执行中', tone: 'running' },
  succeeded: { label: '成功', tone: 'ok' },
  failed: { label: '失败', tone: 'danger' },
  rolled_back: { label: '已回滚', tone: 'danger' },
}

export const JOB_KIND: Record<string, string> = {
  deploy: '构建并部署',
  rollback: '恢复版本',
  check: '完整检查',
}

export function jobStatus(status: string) {
  return JOB_STATUS[status] || { label: status || '未知状态', tone: 'muted' as StatusTone }
}

export function sortJobs(jobs: ReleaseJob[]): ReleaseJob[] {
  return [...jobs].sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
}

export function shortTime(value?: string | null): string {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date)
}
