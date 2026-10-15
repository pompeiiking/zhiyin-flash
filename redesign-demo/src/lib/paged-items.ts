import { computed, onMounted, onUnmounted, ref, watch, type ComputedRef } from 'vue'

/** Keep searches and mutations on a valid page; print the complete collection. */
export function usePagedItems<T>(source: ComputedRef<readonly T[]>, size = 6) {
  const page = ref(1), printing = ref(false)
  const media = typeof window !== 'undefined' ? window.matchMedia('print') : null
  const updatePrint = () => { printing.value = !!media?.matches }
  const beforePrint = () => { printing.value = true }
  const afterPrint = () => { printing.value = false }
  watch(source, () => { page.value = 1 })
  onMounted(() => { updatePrint();media?.addEventListener('change', updatePrint);window.addEventListener('beforeprint',beforePrint);window.addEventListener('afterprint',afterPrint) })
  onUnmounted(() => { media?.removeEventListener('change',updatePrint);window.removeEventListener('beforeprint',beforePrint);window.removeEventListener('afterprint',afterPrint) })
  const paged = computed(() => printing.value ? source.value : source.value.slice((page.value - 1) * size, page.value * size))
  return { page, paged }
}
