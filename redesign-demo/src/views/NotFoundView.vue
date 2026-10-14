<script setup lang="ts">
import { WORKSPACE_GROUPS, WORKSPACE_PRIMARY, PORTAL_LINK } from '../lib/workspace-nav'

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
        <li class="links__item">
          <RouterLink class="links__a" :to="WORKSPACE_PRIMARY.to">{{ WORKSPACE_PRIMARY.label }}</RouterLink>
          <span class="links__hint">{{ WORKSPACE_PRIMARY.hint }}</span>
        </li>
        <template v-for="g in WORKSPACE_GROUPS" :key="g.key">
          <li v-for="item in g.items" :key="item.key" class="links__item">
            <RouterLink class="links__a" :to="item.to">{{ item.label }}</RouterLink>
            <span class="links__hint">{{ g.label }} · {{ item.hint }}</span>
          </li>
        </template>
        <!-- 只列**真实的学生路由**。原来这里还渲染 HELP_LINKS（/spec /tools /path），
             等于把内部文档当成"现在有效的地址"推荐给学生；门户也不该混进这个列表。 -->
        <li class="links__item">
          <RouterLink class="links__a" :to="PORTAL_LINK.to">{{ PORTAL_LINK.label }}</RouterLink>
          <span class="links__hint">{{ PORTAL_LINK.hint }}</span>
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

/* 【2026-10-14 · wave3】这一列链接是 404 页**唯一的功能**，原来只有 24px 高
   （实测 `a.links__a` 13 个，56–70×24）—— 手指点不准。
   为什么不是"把字号放大"：字号档位只有 12/14/16/20/30，这一列是列表项不是标题，
   14px 是对的；缺的是**可点区**，所以抬的是盒子（display:block + 上下 padding + min-height），
   文字本身的视觉重量一点没变。
   为什么 min-height 写成 36 而不是走 --sp-*：36/44 是触控目标的硬线（DESIGN-LANGUAGE
   卡片内次要 ≥36），不是间距阶梯 —— 挂到 --sp-* 上会跟着密度轴缩水，把一条无障碍下限
   变成可调值。workspace.css:200 的 `min-height: 44px` 是同一类写法。
   为什么不用 flex:1 撑满整行：`.links__item` 是 `space-between` 的两列，
   右列是 12px 的说明文字，左列拿到 flex:1 后窄屏上会被右列挤到换行。 */
.links__a {
  display: block;
  /* 硬线写成字面量、内距走令牌：密度轴改 --sp-2 时外观跟着变，
     但 min-height 兜住 36 这条无障碍下限，不会跟着缩。 */
  min-height: 36px;
  padding: var(--sp-2) 0;
  font-size: var(--fs-14);
  color: var(--c-primary);
}

.links__hint {
  font-size: var(--fs-12);
  color: var(--c-text-3);
  text-align: right;
}
</style>
