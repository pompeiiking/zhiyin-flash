import { defineAsyncComponent, type Component } from 'vue'
import type { ModuleView } from './client'

// Vite discovers reviewed components at build time. No user-supplied URL or script is executed.
const imports = import.meta.glob('../../../zhiyin-modules/zhiyin_modules/*/*.vue')
const components: Record<string, Component> = {}
for (const [path, load] of Object.entries(imports)) {
  const parts = path.split('/')
  components[`${parts[parts.length - 2]}/${parts[parts.length - 1]}`] = defineAsyncComponent(load as () => Promise<Component>)
}
export function moduleComponent(module: ModuleView, slot: 'card' | 'detail' | 'conversation') {
  const file = module.manifest[slot]
  return file ? components[`${module.manifest.id}/${file}`] : undefined
}
