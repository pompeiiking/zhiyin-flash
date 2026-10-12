import { computed, onMounted, onUnmounted, readonly, ref } from 'vue'
export type NavigationLayout = 'desktop' | 'mobile'
const preference = ref<NavigationLayout | null>(null)
const sidebarCollapsed = ref(false)
const compact = ref(typeof window !== 'undefined' && window.innerWidth < 1000)
try {
  const stored = localStorage.getItem('zhiyin-demo-navigation')
  if (stored === 'desktop' || stored === 'mobile') preference.value = stored
  sidebarCollapsed.value = localStorage.getItem('zhiyin-demo-sidebar-collapsed') === 'true'
} catch { /* unavailable storage does not prevent preview */ }
export const navigation = {
  mode: computed(() => preference.value ?? (compact.value ? 'mobile' : 'desktop')),
  compact: readonly(compact),
  sidebarCollapsed: readonly(sidebarCollapsed),
  setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed
    try { localStorage.setItem('zhiyin-demo-sidebar-collapsed', String(collapsed)) } catch { /* session preference still works */ }
  },
  set(mode: NavigationLayout) {
    preference.value = mode
    try { localStorage.setItem('zhiyin-demo-navigation', mode) } catch { /* session preference still works */ }
  },
}
export function useNavigationLayout() {
  const resize = () => { compact.value = window.innerWidth < 1000 }
  onMounted(() => { resize(); window.addEventListener('resize', resize) })
  onUnmounted(() => window.removeEventListener('resize', resize))
  return navigation
}
