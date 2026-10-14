<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { activeGroup } from '../lib/workspace-nav'
const route = useRoute()
const group = computed(() => activeGroup(route)?.label)
defineProps<{ title: string; description: string }>()
/* =============================================================================
 * meta 槽 —— 页头的**第三行**
 * -----------------------------------------------------------------------------
 * 【为什么加在共享组件里，而不是每页自己拼一行】靶子 c2 的每张登录内页页头都是
 * 三行：`h1` / `pgh__lead` / `.pgh__meta`（演示数据 tag + 日期或规模 conf）。
 * 真实页原来只有两行，于是"这一页有多少东西、其中多少是待核对的"这类
 * **状态与品质**信息在页头无处落脚（DESIGN-LANGUAGE §4.4 / §6 第 7 问）。
 * 如果让每页自己在 description 里塞一串小字，同一件事就会出现 5 种写法 ——
 * 这正是本工程已经栽过 4 次的"同一条规范散在多处"。
 *
 * 【为什么是可选槽】现有 9 个调用点一个都不用改（不传就一行都不渲染），
 * 所以这次改动对其它页面是**零影响**的 —— 需要 meta 的页面自己决定内容与样式，
 * 组件只管"它在第 3 行、在标题列里、在导语下面"这件事。
 * ========================================================================== */
</script>
<template>
  <header class="ws-heading">
    <div>
      <h1>{{ title }}</h1>
      <p><span v-if="group" class="page-context">{{ group }} · </span>{{ description }}</p>
      <!-- 第 3 行：这一页的规模 / 状态 / 品质标。样式归调用方（本页 scoped），
           组件只负责它在标题列里、在导语之下。 -->
      <div v-if="$slots.meta" class="ws-heading__meta"><slot name="meta" /></div>
    </div>
    <div v-if="$slots.default" class="ws-heading__actions"><slot /></div>
  </header>
</template>
