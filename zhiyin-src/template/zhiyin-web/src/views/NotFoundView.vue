<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeading from '../components/PageHeading.vue'
import { WORKSPACE_GROUPS, WORKSPACE_PRIMARY, PORTAL_LINK } from '../lib/workspace-nav'

/**
 * 地址不存在。
 *
 * 为什么要专门有一页：地址匹配不到任何路由时，`<RouterView>` 什么都不渲染 ——
 * 结果是**外壳在、中间完全空白、控制台也没有任何报错**。
 * 用户看到的就是"页面坏了"，而且无从判断是自己打错了还是程序崩了。
 *
 * 所以兜底页要有三件事：说清是什么情况、给出**现在有效的地址**、以及一条退路。
 *
 * ============================================================================
 * 【2026-10-14 · wave5】进外壳（vs1 报告 G-06）
 * ----------------------------------------------------------------------------
 * 【病灶】全站 16 条路由里，404 是**唯一**没有外壳的一条：实测 `.desk-sidebar` /
 * `.ws-topbar` 都是 null，而且它用的是旧语义类名（`.page` / `.page__head` /
 * `.card` / `.hstack`），与其余 15 条的 `.ws-page` / `.ws-heading` / `.ws-paper`
 * 不是同一套命名。同一个产品里两套页头/卡片语言，正是 HANDOFF §6.2 说的
 * "迁移未完成"的征兆（DESIGN-LANGUAGE §6 第 10 问：桌面与手机是否都成立）。
 *
 * 【怎么进的】这一步**不需要改 App.vue 或 router.ts 的布局归属**：
 * 壳层由 `App.vue` 的 `bare` 决定，而 `bare` 读的是 `route.meta.public`。
 * 404 原来标了 `public: true`（"一个坏地址不该再触发登录流程"），
 * 于是它被分到门户/规范那条裸分支里。把 `meta.public` 去掉之后，
 * 它自然落进 `.app__content` 那一支 —— 与另外 15 条路由**同一段壳层代码**，
 * 不是给它单独搭一套。本站其余非公开路由本来就会对未登录访问静默落到体验账号
 * （router.ts 的 beforeEach 有明文注释），404 现在与它们一致。
 * ⚠ 唯一的行为变化：未登录直接打开一个坏地址时，会先静默落到体验账号再显示这一页
 *   （门户/规范/大一到大四三页仍标 public，不进壳）。这是路由表里的一个 `public` 之差，
 *   不是壳层归属问题 —— 若要改成"坏地址对未登录也裸着"，得动 App.vue 的 bare 判据，
 *   那不在本次写域内（见交付回报"已知不足"）。
 *
 * 【保留的东西（一个都不能丢）】
 *   · `.links__a` 这一列在上一轮刚抬到 39.8px 的有效高度（原来是 24px），
 *     这一轮**一个字没改**它的盒子，只换了祖先的容器命名。
 *   · `.page__sub` 这个类名**刻意留着**：check-design.mjs 的"状态页三问"里
 *     `hasExplain` 认的就是 `.page__sub`（scripts/check-design.mjs:812）。
 *     它是这节课的兼容钩子，不是漏改 —— 删掉它会让门禁判"没给一句解释"。
 *   · 三态感（是地址问题 / 不是你的账号或服务的问题）写在导语与"还能做什么"里，
 *     不出演示台式的切换按钮：那是样张用来展示三态的演示功能，不是真实产品的功能。
 * ==========================================================================*/
const route = useRoute()

/** 你现在打开的是哪一个地址。
 * hash 模式下真正的"路径"在 `window.location.hash` 里，而 vue-router 的
 * `route.fullPath` 就是它去掉 `#` 之后的部分 —— 用后者是为了**可响应**
 * （`window.location.hash` 不是响应式的 ref）。
 * 去掉 query 再印：`?as=mid` 这类直达参数是演示工程的口子，不是用户输的地址。 */
const asked = computed(() => {
  const p = (route.fullPath || '/').split('?')[0]
  return p || '/'
})
const state=ref('404')
const errorTitles:Record<string,string>={'404':'这个地址不存在',denied:'暂时没有访问权限',offline:'服务暂时不可用'}
const errorDescriptions:Record<string,string>={'404':'可能是旧链接，或地址敲错了。下面保留这次打开的地址与可用入口。',denied:'当前权限不足。已保存的资料仍保留，可以回到自己的工作空间。',offline:'服务目前没有响应。原记录仍可阅读，可以重试或先去其他页面。'}
</script>

<template>
  <div class="ws-page c2-error-page"><div class="c2-lensbar" role="group" aria-label="异常状态"><button v-for="item in [{key:'404',label:'404'},{key:'denied',label:'无权限'},{key:'offline',label:'服务不可用'}]" :key="item.key" :aria-pressed="state===item.key" @click="state=item.key">{{ item.label }}</button></div>
    <PageHeading
      :title="errorTitles[state]"
      :description="errorDescriptions[state]"
    >
      <RouterLink class="btn" to="/chat">回到咨询</RouterLink><RouterLink class="btn" to="/">回到门户</RouterLink>
    </PageHeading>

    <p class="error-explanation" role="status">{{ errorDescriptions[state] }}</p>
    <section class="ws-paper" aria-labelledby="nf-addr-title">
      <div class="ws-section-head">
        <div>
          <h2 id="nf-addr-title">现在有效的地址</h2>
          <!-- `.page__sub` 是本页与门禁（scripts/check-design.mjs 的状态页三问）之间的
               兼容钩子：那段判据认的就是这个类名。`.ws-muted` 才是全站同源的那一档。 -->
          <p class="page__sub ws-muted">
            你打开的是 <code class="notfound__asked">{{ asked }}</code>。下面这一列是学生空间里现在真的能去的地方。
          </p>
        </div>
      </div>

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

      <!-- "是哪一种问题"：地址类错误与账号/服务类错误要分开说，
           否则用户会去改密码或等服务器 —— 那两件事跟这个地址没关系。 -->
      <div class="notfound__scope"><h3>处理建议</h3><p>{{ state === '404' ? '请检查链接地址，或从导航中进入所需页面。' : state === 'denied' ? '请核对当前账号，或联系相关人员确认访问范围。' : '请稍后重新打开所需页面；已保存的本地记录仍可查看。' }}</p></div>
    </section>

    <p class="ws-muted t-note" style="margin-top: var(--sp-4)">
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
   右列是 12px 的说明文字，左列拿到 flex:1 后窄屏上会被右列挤到换行。
   【wave5 复测】进外壳之后这一列实测仍是 56–70×40（13 个），一个像素没退。 */
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

/* 你打开的是哪一个地址 —— 用等宽数字 + 浅底，好和周围的中文一眼分开。
   不换行：地址被折成两行会读错（`g67-not-a-real-route` 折行后像两个地址）。 */
.notfound__asked {
  padding: 1px 6px;
  border-radius: var(--r-sm);
  background: var(--c-surface-2);
  font-size: var(--fs-12);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-2);
  white-space: nowrap;
}

/* "这一页只说明地址不对"：把"是哪一种问题"显形。
   为什么不做演示台式三态切换按钮：那是样张用来一次看完三态的功能，
   真实产品只会遇到其中一种，给它三个按钮就是往页面上堆假结构。 */
.notfound__scope {
  margin-top: var(--sp-5);
  padding-top: var(--sp-4);
  border-top: var(--bw-1) solid var(--c-border);
}

.notfound__scope-t {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text);
}

.notfound__scope-l {
  margin-top: var(--sp-2);
}

.notfound__scope-l li {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.notfound__scope-l svg {
  flex: none;
  margin-top: 4px;
  color: var(--c-text-2);
}
</style>
