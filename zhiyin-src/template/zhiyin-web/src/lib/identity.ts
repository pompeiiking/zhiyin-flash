/*
 * 身份的展示口径。
 *
 * 角色名由后端给（guest / student / mentor / admin），界面只把它翻成人话。
 * 翻译表放在这里而不是各组件里：同一句话在两个地方各写一遍，迟早会不一样。
 */

/** 取值必须与后端 `zhiyin_kernel.enums.UserRole` 对齐，多一个少一个都会显示成英文原值 */
const ROLE_LABEL: Record<string, string> = {
  student: '学生',
  guest: '游客',
  mentor: '导师',
  admin: '管理员',
}

export function roleLabel(role: string | null | undefined): string {
  if (!role) return '未登录'
  return ROLE_LABEL[role] ?? role
}

/** 头像里那个字：中文取第一个字，英文取首字母 */
export function initialOf(name: string): string {
  const t = name.trim()
  if (!t) return '·'
  return /[a-zA-Z]/.test(t[0]) ? t[0].toUpperCase() : t[0]
}
