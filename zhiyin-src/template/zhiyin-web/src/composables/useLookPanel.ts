import { ref } from 'vue'

/**
 * 外观台的开合与落点。
 *
 * 外观台挂在 `App.vue` 上（三页都在），而开它的入口有三处：控制台左上角
 * 「外观台」那颗字（就在账号那颗的右边）、报告页顶栏、门户页右上角。
 * 三处要开的是**同一张**面板，所以这份状态既不能放在面板自己身上（别的页够不着），
 * 也不该各开一张（会出现三张叠着）。一个共享的 ref 就够 —— 不必上 store。
 *
 * `anchor` 决定面板从哪一侧落下：字在左上角就从左边落，在门户右上角就从右边落。
 * 面板是 `fixed` 的浮层，跟着触发点的方向走，才不会"人在左、台在右"。
 */
export const lookPanelOpen = ref(false)

export const lookPanelAnchor = ref<'left' | 'right'>('left')

export function openLookPanel(anchor: 'left' | 'right' = 'left') {
  lookPanelAnchor.value = anchor
  lookPanelOpen.value = true
}

/**
 * 「外观台」那三个字自身的行为：**同一处再点一次就收起**。
 *
 * 不这么写的话，字只能开不能关 —— 用户点了没反应（其实已经开着），
 * 于是被迫去点别处或按 Esc 才能收回。换一处点则重新落点（左/右）。
 */
export function toggleLookPanel(anchor: 'left' | 'right' = 'left') {
  if (lookPanelOpen.value && lookPanelAnchor.value === anchor) {
    lookPanelOpen.value = false
    return
  }
  openLookPanel(anchor)
}

export function closeLookPanel() {
  lookPanelOpen.value = false
}
