import { computed, onMounted, onUnmounted, readonly, ref } from 'vue'
export type NavigationLayout = 'desktop' | 'mobile'
const preference = ref<NavigationLayout | null>(null)
const compact = ref(typeof window !== 'undefined' && window.innerWidth < 1000)
try {
  const stored = localStorage.getItem('zhiyin-demo-navigation')
  if (stored === 'desktop' || stored === 'mobile') preference.value = stored
} catch { /* unavailable storage does not prevent preview */ }
export const navigation = {
  mode: computed(() => preference.value ?? (compact.value ? 'mobile' : 'desktop')),
  compact: readonly(compact),
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
