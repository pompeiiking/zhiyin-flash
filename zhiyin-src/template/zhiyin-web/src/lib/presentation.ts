const origins: Record<string, string> = { '计划拆下来的': '方案任务', '建议的': '系统建议', '自己写的': '个人创建', '关键节点': '关键节点' }
const attributions: Record<string, string> = { '任务太大': '任务负担过高', '方法不对': '执行方法需调整', '方向要重估': '方向需重新评估' }
export function taskOriginLabel(value: string) { return origins[value] ?? value }
export function attributionLabel(value?: string | null) { return value ? attributions[value] ?? value : '' }
