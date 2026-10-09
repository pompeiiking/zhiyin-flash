<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AuthLayer from '@/components/auth/AuthLayer.vue'
import GuideDock from '@/components/guide/GuideDock.vue'
import TalkOverlay from '@/components/console/TalkOverlay.vue'
import BlocksOverlay from '@/components/console/BlocksOverlay.vue'
import LookPanel from '@/components/theme/LookPanel.vue'
import VersionNotice from '@/components/VersionNotice.vue'
import { useSessionStore } from '@/stores/session'

/*
 * 登录浮层挂在这一层，不挂在某个页面里。
 * 它得能在任何一页被掀起来（门户点开始、控制台令牌过期），
 * 挂在页面里就会出现"这一页有、那一页没有"的分叉。
 */
const session = useSessionStore()
const route = useRoute()

/*
 * 后端数据的**唯一加载点**：外壳挂载时拉一次。
 *
 * 原来这件事写在控制台的 onMounted 里 —— 于是直接打开 `/report`（或刷新它）
 * 时 store 是空的，报告页会认真地说"报告还没生成"，而报告其实就在后端躺着。
 * 深链与刷新是常态，不该只有从控制台走过去才是对的。
 *
 * 登录成功后由 store 自己再拉一次（见 `signIn`）：那一刻身份刚变，数据必须换。
 */
onMounted(() => {
  void session.loadBackend()
})
</script>

<template>
  <RouterView />
  <!--
    导览（左下角那张常驻便签）只在**进门之后**的页面出现。
    门户是给还没进来的人看的：那一页只有一屏、没有可去的第二处，
    把"这一屏能去哪"的索引摆在访客脚边，等于把内部用法摆在橱窗里。
    控制台和报告页才是它该待的地方。
  -->
  <GuideDock v-if="route.name !== 'portal' && route.name !== 'developer'" />
  <!--
    对话挂全局，不挂控制台：它得能在**任何一页**被叫出来 ——
    在报告页看到一条看不懂的结论，最自然的反应是"我就这一句问问"，
    而不是先退回控制台再开口。挂在控制台里，这个动作就断了。
  -->
  <TalkOverlay v-if="session.overlay === 'talk'" />
  <!-- 全部组件：画布上放哪些块、按什么顺序（issue #22 的管理入口） -->
  <BlocksOverlay v-if="session.overlay === 'blocks'" />
  <AuthLayer v-if="session.authOpen" />
  <!--
    外观台的面板：挂全局，因为开它的那三个「外观台」字分别在三页上
    （控制台左上角账号右侧、报告页顶栏、门户页右上角）。
    面板自己 Teleport 到 body —— 控制台那条 chrome 会整块滑动，留在里面会被裁掉。
  -->
  <LookPanel />
  <VersionNotice />
</template>
