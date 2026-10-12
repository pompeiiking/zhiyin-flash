<script setup lang="ts">
import { NAV_SECTIONS } from '../lib/nav'

/**
 * 地址不存在。
 *
 * 为什么要专门有一页：`#/` 后面匹配不到任何路由时，`<RouterView>` 什么都不渲染 ——
 * 结果是**外壳（顶栏）在、中间完全空白、控制台也没有任何报错**。
 * 用户看到的就是"页面坏了"，而且无从判断是自己打错了还是程序崩了。
 * （截图：`_nope.png` 就是这个状态。）
 *
 * 所以兜底页要有三件事：说清是什么情况、给出**现在有效的地址**、以及一条退路。
 * 页面对未登录也可见（meta.public）—— 一个坏地址不该再触发登录流程。
 */
</script>

<template>
  <div class="page">
    <header class="page__head">
      <div class="hstack hstack-3 between wrap">
        <div>
          <h1 class="page__title">这个地址不存在</h1>
          <p class="page__sub">
            多半是一个旧链接（界面改过几轮，地址变过），或者地址敲错了一个字符。
          </p>
        </div>
        <RouterLink class="btn btn--primary" to="/">回到门户</RouterLink>
      </div>
    </header>

    <section class="card card--pad" style="margin-top: var(--sp-5)">
      <h2 class="card__title">现在有效的地址</h2>
      <ul class="links">
        <li v-for="s in NAV_SECTIONS" :key="s.key" class="links__item">
          <RouterLink class="links__a" :to="s.to">{{ s.label }}</RouterLink>
          <span class="links__hint">{{ s.subs.map((x) => x.label).join(' · ') || '—' }}</span>
        </li>
        <li class="links__item">
          <RouterLink class="links__a" to="/spec">设计规范</RouterLink>
          <span class="links__hint">色板、皮肤、动效那张表</span>
        </li>
        <li class="links__item">
          <RouterLink class="links__a" to="/path">大一到大四 · 七步操作路径</RouterLink>
          <span class="links__hint">含界面截图</span>
        </li>
      </ul>
    </section>

    <p class="t-note" style="margin-top: var(--sp-4)">
      如果你是从别人的消息里点的这个链接，请让对方重新发一次 —— 老链接不保证还有效。
    </p>
  </div>
</template>

<style scoped>
.links {
  margin-top: var(--sp-4);
}

.links__item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-3) 0;
  border-bottom: var(--bw-1) solid var(--c-border);
}

.links__item:last-child {
  border-bottom: none;
}

.links__a {
  font-size: var(--fs-14);
  color: var(--c-primary);
}

.links__hint {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  text-align: right;
}
</style>
