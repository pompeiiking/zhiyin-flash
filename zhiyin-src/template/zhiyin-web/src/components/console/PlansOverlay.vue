<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import { track } from '@/api/client'
import {
  getDirectionPlans,
  selectDirectionPlan,
  type DirectionPlan,
  type DirectionPlans,
} from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { failureText } from '@/lib/failure'

/**
 * ③ 决策 —— 三套方向方案。
 *
 * 这一屏回答的是"我该往哪走"，口径是**可撤回的选择 + 依据**，不给唯一答案：
 *   · 三套方案都来自 ③ 环节产出的资产（主攻 / 平行 / 保底），不是前端拼的；
 *   · 每套都带匹配度、契合依据、差距要点、主要风险 —— 让你能比较，而不是被劝服；
 *   · 选中随时可撤回（再选另一套就是撤回），所以界面上没有"取消选择"这种状态。
 *
 * 匹配度的口径（三叶草契合度 × 可达性）由后端给：分值必须能解释，
 * 口径本身就得对用户可见 —— 一个没有口径的分数，用户只能信或不信。
 */
const session = useSessionStore()

const data = ref<DirectionPlans | null>(null)
const loading = ref(true)
const error = ref('')
const busy = ref('')

const plans = computed<DirectionPlan[]>(() => data.value?.plans ?? [])
const selectedId = computed(() => data.value?.selected_id ?? null)

/*
 * 方案角色 → 人话。
 *
 * 取值必须与内核契约 `PlanRole`（main / parallel / fallback）逐字对齐：
 * 此前这里写的是 primary / safety，两个键永远匹配不上，
 * 于是方案卡上直接显示 "main" 与 "fallback" 两个英文词。
 * 认不出来的取值不进界面，退回「方案」这个中性说法。
 */
const ROLE_LABEL: Record<string, string> = {
  main: '主攻',
  parallel: '平行',
  fallback: '保底',
}
const roleLabel = (role: string) => ROLE_LABEL[role] ?? '方案'

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getDirectionPlans()
  } catch (cause) {
    error.value = failureText(cause)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  // 打开这一屏 = 用户在做"方案对比"这件事（注册表里的 decision_compare）。
  // 放在加载之后：条数是这一屏到底摆了几套方案，不是猜的。
  track('decision_compare', { plans: data.value?.plans?.length ?? 0 })
})

async function choose(plan: DirectionPlan) {
  busy.value = plan.id
  try {
    data.value = await selectDirectionPlan(plan.id)
    /*
     * 换了方案：库里的方向选择变了 —— 工作台面板、关键节点日历、还有"下一步"
     * 都跟着它。这里是一次**重拉 + 通知**：只通知不重拉的话，那几处不会自己去问，
     * 用户从这一屏退出去看到的还是换之前的样子。
     */
    void session.revalidate()
    session.openDrawer(
      `已选「${plan.name}」`,
      '这个选择随时可撤回 —— 再选另一套就是撤回',
      [
        { source: '你选的', detail: `${roleLabel(plan.role)} · ${plan.name}`, confidence: 1, at: '刚刚' },
        { source: '为什么它值得选', detail: plan.fit_reason || '这一套的契合依据还没写下来。', confidence: plan.match_score, at: '生成时' },
        { source: '要盯着什么', detail: plan.main_risk || '这一套的主要风险还没写下来。', at: '生成时' },
      ],
    )
  } catch (cause) {
    error.value = failureText(cause)
  } finally {
    busy.value = ''
  }
}

/** 去看匹配矩阵（AI 现算的那张图）——它是方案的依据，不是方案本身 */
function openMatrix() {
  session.openOverlay('match')
}

const pct = (v: number) => `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`
</script>

<template>
  <Overlay
    title="方向方案"
    :subtitle="selectedId ? '已选一套 · 随时可撤回' : '三套方案 · 选一套，随时可撤回'"
    from="plans"
    size="wide"
    @close="session.closeOverlay()"
  >
    <p v-if="loading" class="label hint">正在读你的方案…</p>
    <p v-else-if="error" class="warn" role="alert">{{ error }}</p>

    <div v-else-if="!plans.length" class="empty sheet">
      <h3 class="empty__t editorial">还没有方向方案。</h3>
      <p class="empty__d">
        方案来自「决策」这一步：画像与报告齐了之后，跟主理把"我该往哪走"聊清楚，
        三套方案会落到这里（主攻 / 平行 / 保底），之后每次打开读的都是那一版。
      </p>
      <button class="btn" type="button" @click="session.callTalk()">去和主理聊聊</button>
    </div>

    <template v-else>
      <div class="grid">
        <article
          v-for="plan in plans"
          :key="plan.id"
          class="plan sheet"
          :class="{ on: plan.id === selectedId }"
        >
          <header class="plan__head">
            <span class="label plan__role" :data-role="plan.role">
              {{ roleLabel(plan.role) }}
            </span>
            <h3 class="plan__name">{{ plan.name }}</h3>
            <span class="plan__score mono" :title="data?.match_score_method">
              {{ plan.match_score == null ? '待核验' : plan.match_score.toFixed(2) }}
            </span>
          </header>

          <span v-if="plan.match_score != null" class="plan__bar" aria-hidden="true">
            <i :style="{ width: pct(plan.match_score) }" />
          </span>

          <p v-if="plan.target_desc" class="plan__target">{{ plan.target_desc }}</p>

          <p class="plan__row">
            <span class="label">契合依据</span>{{ plan.fit_reason || '—' }}
          </p>

          <div v-if="(plan.gaps ?? []).length" class="plan__gaps">
            <span class="label">要补的差距 {{ (plan.gaps ?? []).length }} 条</span>
            <ul>
              <li v-for="(gap, i) in plan.gaps ?? []" :key="i">
                <span class="plan__gap-req">{{ gap.requirement }}</span>
                <span v-if="gap.suggestion" class="plan__gap-how">{{ gap.suggestion }}</span>
              </li>
            </ul>
          </div>

          <p class="plan__row risk">
            <span class="label">主要风险</span>{{ plan.main_risk || '—' }}
          </p>

          <footer class="plan__foot">
            <button
              v-if="plan.id === selectedId"
              class="btn ghost"
              type="button"
              disabled
            >
              当前选择
            </button>
            <button
              v-else
              class="btn primary"
              type="button"
              :disabled="busy === plan.id"
              @click="choose(plan)"
            >
              {{ busy === plan.id ? '正在记下…' : '选这套' }}
            </button>
            <span v-if="plan.id === selectedId" class="label plan__note">
              选它是可撤回的：再选另一套就是撤回
            </span>
          </footer>
        </article>
      </div>

      <p class="label foot">
        {{ plans.some((plan) => plan.match_score != null) ? '匹配度怎么算：' + data?.match_score_method : '当前没有可核验的匹配分数。' }}
        <button class="link" type="button" @click="openMatrix">看匹配矩阵怎么算的 →</button>
      </p>
    </template>
  </Overlay>
</template>

<style scoped>
.hint { color: var(--ink-3); }
.warn { color: var(--warn); font-size: var(--fs-small); }

.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--s4); }
.plan { padding: var(--s5); display: flex; flex-direction: column; gap: var(--s3); }
.plan.on { border: var(--bw) solid var(--accent); }

.plan__head { display: flex; align-items: baseline; gap: var(--s2); }
.plan__role {
  padding: 1px var(--s2); border-radius: var(--r-pill);
  background: var(--fill-hover); color: var(--ink-2);
}
.plan__role[data-role='primary'] { background: var(--accent-soft); color: var(--mk-green); }
.plan__name { font-size: var(--fs-body); color: var(--ink-1); }
.plan__score { margin-left: auto; color: var(--ink-1); }
.plan__bar { display: block; height: 5px; border-radius: 3px; background: var(--fill-hover); overflow: hidden; }
.plan__bar i { display: block; height: 100%; background: var(--mk-green); }
.plan__target { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7; }
.plan__row { font-size: var(--fs-small); color: var(--ink-1); line-height: 1.7; }
.plan__row .label { margin-right: var(--s2); color: var(--ink-3); }
.plan__row.risk { color: var(--ink-2); }
.plan__gaps { display: flex; flex-direction: column; gap: 6px; }
.plan__gaps .label { color: var(--ink-3); }
.plan__gaps ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.plan__gaps li { display: flex; flex-direction: column; font-size: var(--fs-small); color: var(--ink-1); }
.plan__gap-how { color: var(--ink-3); }
.plan__foot { margin-top: auto; display: flex; align-items: center; gap: var(--s2); }
.plan__note { color: var(--ink-3); }

.empty { padding: var(--s6); display: flex; flex-direction: column; gap: var(--s3); align-items: flex-start; }
.empty__t { font-size: var(--fs-lg); color: var(--ink-1); }
.empty__d { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.8; max-width: 60ch; }

.foot { margin-top: var(--s5); color: var(--ink-3); line-height: 1.7; }
.link { color: var(--accent); }
</style>
