<script setup lang="ts">
import { routeEnabled } from '../lib/features'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { TooltipContent, TooltipPortal, TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
import { WORKSPACE_GROUPS, WORKSPACE_PRIMARY, PORTAL_LINK, isNavActive, type NavItem } from '../lib/workspace-nav'
import { navigation } from '../lib/layout'
import { formatRelative } from '../lib/format'
import { demo } from '../store'
import { openSession } from '../lib/system-data'
import { toast } from '../store'
import UiIcon from './UiIcon.vue'
import { vScrollFade } from '../lib/scroll-fade'
import { backendDemo } from '../lib/backend-demo'
import BrandMark from './BrandMark.vue'
import AccountPopover from './AccountPopover.vue'
import { studyYearLabel } from '../lib/study-year'
const route = useRoute()
const router = useRouter()
defineEmits<{ newChat: []; collapse: [] }>()
const collapseButton = ref<HTMLButtonElement | null>(null)
defineExpose({ focusCollapse() { collapseButton.value?.focus() } })
/**
 * C2 导航是固定分组与平铺入口。各组不再套折叠目录；
 * 整体侧栏仍能收起，历史会话继续使用已有的恢复逻辑。
 */
const sessions = computed(() => [...backendDemo.state.sessions].sort((a, b) => ((b.last_message_at || b.last_active_at) ?? '').localeCompare((a.last_message_at || a.last_active_at) ?? '')))
async function resumeSession(id: string) {
  try { await openSession(id); await router.push('/chat') } catch(e) { toast((e as Error).message) }
}
const userName = computed(() => demo.state.account || '当前用户')

/**
 * 底部人名行的副行 = **专业 · 年级**（c2 靶子的 `.nav__me-s`）。
 * 专业取自 `data/student.ts` 的 `STUDENT.major`；年级取当前演示场景（`demo.use.scenario`），
 * 因为切年级（GradeSwitch / ⌘K）真的会换掉这个人所处的场景 —— 写死 STUDENT.grade
 * 就会出现"任务清单是大一的、人名行还写着大三"。
 */
const personSub = computed(() => {
  const fields = backendDemo.state.liveWorkspace?.profile_panel?.fields ?? []
  const major = fields.find(field => field.key === 'major')?.value
  const year = fields.find(field => field.key === 'study_year')?.value ?? fields.find(field => field.key === 'grade')?.value
  return [major, year ? studyYearLabel(year) : ''].filter(Boolean).join(' · ') || '个人资料待完善'
})
const chatActive = computed(() => isNavActive(WORKSPACE_PRIMARY, route))
/**
 * 主侧栏只铺"用户此刻要做什么"的四个分组；「帮助与工具」不进主滚动区，
 * 而是和"返回门户"一起放在页脚 —— 两页都稳定可见，也不会把本来就不够高的
 * 导航区再撑长 40 多像素（#8 的完成记录被压）。
 */
const navGroups = computed(() => WORKSPACE_GROUPS.filter((group) => group.key !== 'help'))
const helpItems = computed(() => WORKSPACE_GROUPS.find((group) => group.key === 'help')?.items ?? [])
/**
 * 导航计数徽标（c2 的 `.nav__badge`）—— **两个数字都来自真实状态，没有一个写死**：
 *   · 咨询对话 = `backendDemo.state.sessions` 的条数。侧栏「历史会话」表头读的是同一个字段
 *     （`backendDemo.ts:33` 初始化，`demo-fixtures.ts:27` 的 6 条演示会话），所以表头与徽标永远一致。
 *   · 今日行动 = `demo.state.tasks` 里 `bucket === 'now'` 的条数，与 `store.ts:138` 的
 *     `demo.use.now` 是同一份数据。大三档恰好是 3 件（与 c2 样张那个 3 数值相同），
 *     但样张的 3 是写死的，这里勾掉一件就变 2。
 * 0 件时不渲染徽标（`v-if` 在模板里），所以 fresh 账号不会挂一个"0"。
 */
const sessionCount = computed(() => backendDemo.state.sessions.length)
const nowCount = computed(() => demo.state.tasks.filter((t) => t.bucket === 'now').length)
const railMode = computed(() => navigation.width.value >= 768 && navigation.width.value < 1024)
function navCount(item: NavItem) { return item.key === 'home' ? nowCount.value : 0 }
function sessionDate(date?: string | null) { return date ? formatRelative(date) : '' }
</script>
<template>
  <aside id="student-desktop-sidebar" class="desk-sidebar" aria-label="桌面导航">
    <div class="desk-brand-row"><RouterLink class="desk-brand" to="/chat" aria-label="职引，回到对话"><BrandMark /></RouterLink><button ref="collapseButton" class="ws-icon-button desk-collapse" aria-label="收起侧栏" title="收起侧栏" aria-controls="student-desktop-sidebar" aria-expanded="true" @click="$emit('collapse')"><UiIcon name="sidebar" :size="19" /></button></div>

    <div v-scroll-fade class="desk-scroll">
    <TooltipProvider :delay-duration="120" :skip-delay-duration="80">
      <nav v-scroll-fade class="desk-nav" aria-label="学生空间导航"><div class="c2-chat-group-head"><h2>对话</h2><button class="c2-new-consult" aria-label="选择咨询主题" title="选择咨询主题" :disabled="demo.state.chatBusy" @click="$emit('newChat')"><UiIcon name="plus" :size="18" /></button></div>
        <TooltipRoot :disabled="!railMode">
          <TooltipTrigger as-child>
            <RouterLink :to="WORKSPACE_PRIMARY.to" class="desk-link desk-link--conversation" :aria-label="WORKSPACE_PRIMARY.label" :aria-current="isNavActive(WORKSPACE_PRIMARY, route) ? 'page' : undefined"><UiIcon :name="WORKSPACE_PRIMARY.icon" :size="20" /><span class="hf-label">{{ WORKSPACE_PRIMARY.label }}</span><span class="hf-tail" v-if="sessionCount || chatActive"><span v-if="sessionCount" class="hf-badge">{{ sessionCount }}</span><span v-if="chatActive" class="desk-link__dot" /></span></RouterLink>
          </TooltipTrigger>
          <TooltipPortal><TooltipContent class="desk-rail-tooltip" side="right" :side-offset="12" :collision-padding="8">{{ WORKSPACE_PRIMARY.label }}</TooltipContent></TooltipPortal>
        </TooltipRoot>
        <section v-for="group in navGroups" :key="group.key" class="c2-nav-group">
          <h2>{{ group.label }}</h2>
          <TooltipRoot v-for="item in group.items.filter(item => routeEnabled(item.to))" :key="item.key" :disabled="!railMode">
            <TooltipTrigger as-child>
              <RouterLink :to="item.to" :aria-label="item.label" class="desk-link" :aria-current="isNavActive(item, route) ? 'page' : undefined">
                <UiIcon :name="item.icon" :size="18" /><span class="hf-label">{{ item.label }}</span>
                <span v-if="navCount(item)" class="hf-badge">{{ navCount(item) }}</span>
              </RouterLink>
            </TooltipTrigger>
            <TooltipPortal><TooltipContent class="desk-rail-tooltip" side="right" :side-offset="12" :collision-padding="8">{{ item.label }}</TooltipContent></TooltipPortal>
          </TooltipRoot>
        </section>
      </nav>
    </TooltipProvider>
    <section v-if="chatActive" v-scroll-fade class="desk-history" aria-label="历史会话"><div class="desk-history__head"><h2>历史会话</h2><span>{{ backendDemo.state.sessions.length }}</span></div><button v-for="session in sessions" :key="session.task_id" class="desk-session" :title="session.task_name + '：' + (session.last_message || '')" :aria-pressed="route.path === '/chat' && session.task_id === demo.state.currentSessionId" :disabled="demo.state.chatBusy" @click="resumeSession(session.task_id)"><span>{{ session.task_name || '未命名咨询' }}</span><em class="desk-session__preview">{{ session.last_message || '还没有消息' }}</em><small><template v-if="session.message_count">{{ session.message_count }} 条 · </template>{{ sessionDate(session.last_message_at || session.last_active_at) }}</small></button><p v-if="!sessions.length" class="desk-history__empty">创建咨询后，会话将显示在这里。</p></section>
    </div>
    <!--
      页脚只留两样：账号（与顶栏、移动端指向**同一个「账号」抽屉**）、返回门户。
      原来这里并排四颗内部页链接（使用指南 / 应用工具 / 设计规范 / 返回门户），
      每颗 35×41 —— 既不到 44px，又让内部文档从导航裂缝漏回学生入口。
    -->
    <div class="desk-footer">
      <AccountPopover class="desk-person hf-person" side="right" align="end"><template #trigger><span class="desk-person__avatar">{{ userName.slice(0, 1) }}</span><span class="hf-person-text"><strong>{{ userName }}</strong><small>{{ personSub }}</small></span></template></AccountPopover>
      <div class="desk-footer__links"><RouterLink v-for="item in helpItems" :key="item.key" :to="item.to" :title="item.hint">{{ item.short || item.label }}</RouterLink><RouterLink :to="PORTAL_LINK.to">{{ PORTAL_LINK.label }}</RouterLink></div>
    </div>
  </aside>
</template>

<style scoped>
/*
  左侧栏：把 c2 靶子的 `.nav__mark` / `.nav__names` / `.nav__badge` / `.nav__me*` 落到真实侧栏上。
  为什么全写在这里（scoped）而不是 `workspace.css`：
    · `.desk-sidebar` / `.desk-brand` / `.desk-link` / `.desk-person` 这一族是 workspace.css
      （另一位作者独占，本轮不许改）里的**全局裸类**；scoped 规则带 `[data-v-*]` 后特异度
      高于它们，所以"只改这一处"在层叠上是成立的。
    · 反过来说，把这些靶子类名（`.nav__mark` 等）写进 scoped 会立刻被
      `scripts/check-classes.mjs` 拦下（同名类同时出现在全局与 scoped 且带版面属性），
      所以本组件一律用 `hf-` 前缀，不复用任何全局类名。
  与靶子的差异（回报里逐条点名）：
    · `.hf-mark` 15px/700 → `--fs-16`/`--fw-semibold`：本项目字号只有登记档（12/14/16/20/30/38）、
      字重只有 400/500/600 三档，15px 与 700 都不存在，不能为了样张偷偷加一档。
    · 投影取 `--e-1`（既有令牌）而不是 c2 的 `--sh-accent-2`：本项目**没有带主色的影令牌**，
      也不许在组件里写颜色字面量。要完全对上靶子那层蓝色浮起，得先加一个全局令牌 ——
      规则原样写在 `_shots/B-needs-workspace-css.md`，由 Lead 合并。
    · 品牌名与副标保持**上下两行**（靶子的 `.nav__names` 是行内、两个字并排）：
      侧栏实测内宽 200px，并排需要约 170px，一行之差就会挤掉右侧那颗 44px 的折叠按钮。
    · 底部头像保持本工程既有的 34px 圆形身份片（与顶栏 `.ws-account__avatar` 是同一颗），
      没有换成靶子的 30px 灰色方片：§5.2 这一项要的是"人名带专业年级"，头像形态不在差异项里，
      而 `--chip-1/2/ink` 这三个靶子令牌本工程也不存在。
*/
.hf-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
/* 徽标与"当前页"圆点一起收进尾组：两个都带 `margin-left:auto` 时会把空隙对半分，
   徽标就会飘到行的中间；用一个 auto 外边距的尾组，它们始终贴在同一侧。 */
.hf-tail {
  margin-left: auto;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.hf-badge {
  flex: none;
  min-width: 20px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--c-primary-weak);
  color: var(--c-primary);
  border: var(--bw-1) solid var(--c-primary-border);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  line-height: 1.5;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
/* 人名行：内容高而不是钉死 44px。
   全局 `.desk-person` 是 `height: 44px`，两行文字靠 line-height 压进去；
   副行现在是"专业 · 年级"（比原来的"大三 · 河北大学"长），万一对不齐换行，
   定高会让文字从盒子里溢出去压住页脚上边距。min-height 保住 44px 命中区。 */
.hf-person { height: auto; min-height: 44px; }
.hf-person-text { flex: 1 1 auto; min-width: 0; }
:global(.desk-rail-tooltip) { z-index:140; padding:7px 10px; border:1px solid var(--c-border); border-radius:9px; background:var(--c-surface); color:var(--c-text); box-shadow:var(--e-2); font-size:13px; line-height:1.4; }
@media (prefers-reduced-motion:no-preference) { :global(.desk-rail-tooltip) { animation:desk-rail-tooltip-in .12s ease-out; } }
@keyframes desk-rail-tooltip-in { from { opacity:0; transform:translateX(-4px); } }

/*
 * 【#8】1440×900 下导航内容比可视区高 42px，最后一项「完成记录」只露出 31px；
 * 同时全局 `scrollbar-width:none` 把滚动条藏掉了，看起来像被底部用户卡片压住。
 * 处理三步：
 *   ① 侧栏滚动区恢复细滚动条 + 边缘渐隐（v-scroll-fade 现在挂在真正滚动的 .desk-scroll 上），
 *      短屏（比如 768 高）仍然可以滚到每一项；
 *   ② 900 高度这一档把品牌行/分组间距收紧 48px，让 12 个入口在 900 高内完整落下，
 *      不需要滚动就能点到「完成记录」；
 *   ③ 页脚（账号卡 + 帮助/门户链接）是 flex 尾项，不覆盖滚动内容。
 * 选择器带 `#student-desktop-sidebar` 是为了压过 workspace.css / workspace-modern.css 的全局规则。
 */
#student-desktop-sidebar .desk-scroll {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-bottom: 2px;
  scrollbar-width: thin;
  scrollbar-color: var(--c-border-strong) transparent;
}
#student-desktop-sidebar .desk-scroll::-webkit-scrollbar { width: 6px; }
#student-desktop-sidebar .desk-scroll::-webkit-scrollbar-thumb { border-radius: 999px; background: var(--c-border-strong); }
#student-desktop-sidebar .desk-brand-row { margin-bottom: 8px; }
#student-desktop-sidebar .c2-nav-group { margin-top: 8px; }
#student-desktop-sidebar .desk-nav { padding-bottom: 2px; }
#student-desktop-sidebar .desk-footer { flex: none; padding-top: 12px; }
#student-desktop-sidebar .desk-footer__links { flex-wrap: wrap; gap: 0 14px; }
#student-desktop-sidebar .desk-footer__links a[aria-current='page'] { color: var(--c-primary); font-weight: var(--fw-semibold); }
#student-desktop-sidebar .desk-session__preview { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-text-3); font-size: 11px; font-style: normal; line-height: 1.4; }
</style>
