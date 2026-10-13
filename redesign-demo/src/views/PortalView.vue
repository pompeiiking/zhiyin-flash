<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PortalProposal from './PortalProposalView.vue'
import PortalClassic from './PortalClassicView.vue'

const route = useRoute()
const router = useRouter()
const classic = computed(() => route.query.portal === 'classic')
const settings = ref<HTMLDetailsElement | null>(null)
async function switchPortal(original: boolean) {
  if (settings.value) settings.value.open = false
  const query = { ...route.query }
  if (original) query.portal = 'classic'
  else delete query.portal
  await router.replace({ path: '/', query })
  await nextTick()
  settings.value?.querySelector('summary')?.focus()
}
</script>

<template>
  <component :is="classic ? PortalClassic : PortalProposal">
    <template #portal-switch>
      <details ref="settings" class="pv-settings" @keydown.esc="settings && (settings.open=false)"><summary>演示设置</summary><div class="pv-settings__body"><span class="pv-switcher__label">门户版本</span><div class="pv-switcher__buttons" role="group" aria-label="门户版本"><button :aria-pressed="!classic" @click="switchPortal(false)">新版</button><button :aria-pressed="classic" @click="switchPortal(true)">原版</button></div></div></details>
    </template>
  </component>
</template>

<style scoped>
.pv-switcher { display: flex; align-items: center; gap: 12px; flex: none; }
.pv-settings { position: relative; flex: none; font-size: var(--fs-14); color: var(--c-text-2); }
.pv-settings summary { cursor: pointer; min-height: 40px; display: flex; align-items: center; padding: 8px 12px; }
.pv-settings__body { position: absolute; right: 0; top: 100%; z-index: 10; width: max-content; max-width: calc(100vw - 32px); padding: 20px; border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-surface); }
.pv-settings__body .pv-switcher__label { display: block; margin-bottom: 12px; }
.pv-switcher__label { color: var(--c-text-3); font-size: var(--fs-12); white-space: nowrap; }
.pv-switcher__buttons { display: flex; padding: 3px; border: 1px solid var(--c-border-strong); border-radius: var(--r-md); background: var(--c-surface); }
.pv-switcher__buttons button { padding: 7px 14px; min-height: 36px; font-size: var(--fs-14); border-radius: var(--r-sm); color: var(--c-text-3); white-space: nowrap; }
.pv-switcher__buttons button[aria-pressed='true'] { background: var(--c-primary-weak); color: var(--c-primary); font-weight: 600; }
.pv-switcher__buttons button:hover { color: var(--c-primary); }
@media (max-width: 920px) { .pv-switcher__label { display: none; } }
@media (max-width: 760px) { .pv-switcher__buttons button { padding: 6px 10px; min-height: 34px; font-size: var(--fs-12); } }
</style>
