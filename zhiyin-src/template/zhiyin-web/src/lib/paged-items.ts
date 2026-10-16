import { computed, onMounted, onUnmounted, ref, watch, type ComputedRef, type WatchSource } from 'vue'

/** Keep searches and mutations on a valid page; print the complete collection. */
export function usePagedItems<T>(source: ComputedRef<readonly T[]>, size = 6, resetOn?: WatchSource) {
  const page = ref(1), printing = ref(false)
  const media = typeof window !== 'undefined' ? window.matchMedia('print') : null
  const updatePrint = () => { printing.value = !!media?.matches }
  const beforePrint = () => { printing.value = true }
  const afterPrint = () => { printing.value = false }
  watch(source, (items) => { page.value = Math.min(page.value, Math.max(1, Math.ceil(items.length / size))) })
  if (resetOn) watch(resetOn, () => { page.value = 1 })
  onMounted(() => { updatePrint();media?.addEventListener('change', updatePrint);window.addEventListener('beforeprint',beforePrint);window.addEventListener('afterprint',afterPrint) })
  onUnmounted(() => { media?.removeEventListener('change',updatePrint);window.removeEventListener('beforeprint',beforePrint);window.removeEventListener('afterprint',afterPrint) })
  const paged = computed(() => printing.value ? source.value : source.value.slice((page.value - 1) * size, page.value * size))
  return { page, paged }
}
