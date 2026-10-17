<script setup lang="ts">
import { computed, ref, watch, type DeepReadonly } from 'vue'
import type { DirectionPlanListView, DirectionPlanView } from '../api/backend-types'
import DirectionScoring from './DirectionScoring.vue'
import InfoSheet from './InfoSheet.vue'
import StatusBanner from './StatusBanner.vue'

type Criterion = '方向目标' | '匹配依据' | '方向要求' | '当前情况' | '补齐建议' | '主要风险'

const props = defineProps<{
  plans: DeepReadonly<DirectionPlanListView>
  saving: boolean
  impact: { report: boolean; plan: boolean; checked: boolean }
  selectionChanged: boolean
}>()

defineEmits<{ select: [id: string] }>()

const roles: Record<string, string> = { main: '主攻方向', parallel: '平行方向', fallback: '保留方向' }
const shortRoles: Record<string, string> = { main: '主攻', parallel: '平行', fallback: '保留' }
const roleOrder: Record<string, number> = { main: 0, parallel: 1, fallback: 2 }
const criteria: readonly Criterion[] = ['方向目标', '匹配依据', '方向要求', '当前情况', '补齐建议', '主要风险']
const comparisonOpen = ref(false)
const compareView = ref<'content' | 'preference'>('content')
const mobileCriterion = ref<Criterion>('方向目标')
const activePlanId = ref('')
const candidate = ref('')

const orderedPlans = computed(() => [...(props.plans.plans ?? [])].sort((a, b) => (roleOrder[a.role] ?? 9) - (roleOrder[b.role] ?? 9)))
const selected = computed(() => props.plans.selected_id || props.plans.plans?.find(plan => plan.selected)?.id || '')
const selectedName = computed(() => props.plans.plans?.find(plan => plan.id === selected.value)?.name || '此前保存的方向')
const pending = computed(() => props.plans.plans?.find(plan => plan.id === candidate.value))
const activePlan = computed(() => orderedPlans.value.find(plan => plan.id === activePlanId.value) ?? orderedPlans.value[0])
const activeGaps = computed(() => activePlan.value?.gaps ?? [])
const firstExperiment = computed(() => activeGaps.value.find(gap => gap.suggestion)?.suggestion || '先找一位了解这个方向的人聊 20 分钟，记录最吸引你和最犹豫的地方。')
const invalidSelected = computed(() => !!selected.value && !props.plans.plans?.some(plan => plan.id === selected.value))
const impactMessage = computed(() => {
  // 还没有任何方向方案时，谈不上"方向变更影响"——空态只展示空态。
  if (!(props.plans.plans ?? []).length) return ''
  const affected: string[] = []
  if (props.impact.report) affected.push('诊断报告')
  if (props.impact.plan) affected.push('阶段计划')
  if (affected.length) return `${affected.join('与')}已标记为待更新；旧版本仍然保留。`
  if (props.selectionChanged) return props.impact.checked ? '方向已保存，报告与阶段计划当前无需重算。' : '方向已保存；更新状态暂未完整取得，可到版本记录继续核对。'
  return ''
})

watch(selected, id => {
  candidate.value = id
  activePlanId.value = id || orderedPlans.value[0]?.id || ''
}, { immediate: true })

function validScore(score: unknown): score is number {
  return typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 1
}

function values(plan: DeepReadonly<DirectionPlanView>, criterion: Criterion): readonly string[] {
  if (criterion === '方向目标') return [plan.target_desc || '尚未提供目标说明']
  if (criterion === '匹配依据') return [plan.fit_reason || '尚未提供匹配依据']
  if (criterion === '主要风险') return [plan.main_risk || '尚未提供具体风险，请进一步核对']
  const list = plan.gaps?.map(gap => criterion === '方向要求'
    ? gap.requirement
    : criterion === '当前情况'
      ? gap.current_state || '尚待补充'
      : gap.suggestion || '尚未提供建议') ?? []
  return list.length ? list : ['本次未提供差距明细']
}
</script>

<template>
  <section class="direction-details">
    <StatusBanner v-if="impactMessage" tone="warning" title="方向变更影响" :message="impactMessage" :dismissible="false" />
    <p v-if="invalidSelected" class="asset-notice" role="status">此前选择暂未出现在这次方案中。原选择记录仍保留，请重新读取或选择新的方向。</p>

    <template v-if="orderedPlans.length">
      <section class="route-workbench" aria-label="方向探索工作台">
        <section class="route-index" aria-label="路线总览">
          <header>
            <h2>方向概览</h2>
            <p>先看清每条路，再决定把精力放在哪里。</p>
          </header>

          <nav class="route-list" aria-label="切换查看已有方向">
            <button
              v-for="plan in orderedPlans"
              :key="plan.id"
              type="button"
              :aria-current="activePlan?.id === plan.id ? 'true' : undefined"
              @click="activePlanId = plan.id"
            >
              <span class="route-list__node" aria-hidden="true"></span>
              <span class="route-list__copy">
                <small>{{ roles[plan.role] ?? plan.role }}</small>
                <strong>{{ plan.name }}</strong>
                <span>{{ plan.target_desc || '目标仍待补充' }}</span>
              </span>
              <em v-if="selected === plan.id">当前</em>
              <em v-else-if="candidate === plan.id">待定</em>
            </button>
          </nav>

          <button class="route-index__compare" type="button" @click="compareView = 'content'; comparisonOpen = true">横向比较已有方向</button>
        </section>

        <article v-if="activePlan" class="route-sheet">
          <header class="route-sheet__head">
            <div class="route-sheet__status">
              <span>{{ shortRoles[activePlan.role] ?? activePlan.role }}</span>
              <i v-if="selected === activePlan.id">现在正在走</i>
              <i v-else-if="candidate === activePlan.id">准备调整到这里</i>
              <i v-else>还没有决定</i>
            </div>
            <h2>{{ activePlan.name }}</h2>
            <p>{{ activePlan.target_desc || '这条路最终想达到什么，还需要在咨询中补充。' }}</p>
          </header>

          <section class="route-rationale">
            <div>
              <h3>为什么会出现这条路</h3>
              <p>{{ activePlan.fit_reason || '目前还没有足够的经历或偏好作为判断依据。' }}</p>
            </div>
            <aside class="route-evidence" aria-label="匹配依据状态">
              <span>画像依据</span>
              <strong v-if="validScore(activePlan.match_score)">{{ Math.round(activePlan.match_score * 100) }}<small>/100</small></strong>
              <strong v-else>待补充</strong>
              <p>{{ validScore(activePlan.match_score) ? '这是参考信号，不是最终结论。' : '补充经历后再核对，不自动补分。' }}</p>
            </aside>
          </section>

          <section class="route-checkpoints">
            <header>
              <h3>走到这里，需要跨过什么</h3>
              <p>每个门槛都对应一次可执行的验证，不必现在就做终身决定。</p>
            </header>
            <ol v-if="activeGaps.length">
              <li v-for="(gap, index) in activeGaps" :key="index">
                <span class="checkpoint-mark" aria-hidden="true"></span>
                <div class="checkpoint-copy">
                  <strong>{{ gap.requirement || '待确认的方向要求' }}</strong>
                  <dl>
                    <div><dt>你现在</dt><dd>{{ gap.current_state || '尚未取得足够信息' }}</dd></div>
                    <div><dt>下一步</dt><dd>{{ gap.suggestion || '在咨询中补充这项经历或偏好' }}</dd></div>
                  </dl>
                </div>
              </li>
            </ol>
            <div v-else class="route-checkpoints__empty">
              <p>这条路线还没有形成可核对的门槛。</p>
              <RouterLink class="ws-text-link" to="/chat?topic=补充方向差距">去补充经历与要求</RouterLink>
            </div>
          </section>

          <section class="route-test">
            <div class="route-test__experiment">
              <span>先试走两周</span>
              <h3>{{ firstExperiment }}</h3>
              <p>完成后再回来判断：更想继续，还是应该换一条路。</p>
              <RouterLink class="ws-text-link" :to="`/chat?topic=${encodeURIComponent('验证方向：' + activePlan.name)}`">带着这个问题去咨询</RouterLink>
            </div>
            <div class="route-test__risk">
              <span>暂时别忽略</span>
              <p>{{ activePlan.main_risk || '目前没有明确风险记录，仍建议通过一次真实体验再判断。' }}</p>
            </div>
          </section>

          <footer class="route-decision">
            <div>
              <strong v-if="selected === activePlan.id">这条路已设为当前方向</strong>
              <strong v-else-if="candidate === activePlan.id">已经加入待确认</strong>
              <strong v-else>愿意把它作为接下来的重点吗？</strong>
              <p>选择可以调整，已有记录不会被删除。</p>
            </div>
            <button v-if="selected !== activePlan.id && candidate !== activePlan.id" class="btn btn--primary" type="button" @click="candidate = activePlan.id">把它设为候选</button>
            <span v-else-if="selected === activePlan.id" class="route-decision__current">当前方向</span>
            <span v-else class="route-decision__current">等待确认</span>
          </footer>
        </article>
      </section>

      <section v-if="candidate && candidate !== selected" class="pending-confirm" role="status">
        <div><span>确认方向调整</span><strong>「{{ selectedName }}」→「{{ pending?.name }}」</strong><p>保存后会检查诊断报告和阶段计划是否需要更新。</p></div>
        <div><button class="ws-text-button" type="button" :disabled="saving" @click="candidate = selected">先不调整</button><button class="btn btn--primary" type="button" :disabled="saving || !pending" @click="$emit('select', candidate)">{{ saving ? '正在保存…' : '确认调整' }}</button></div>
      </section>

      <nav class="ws-related" aria-label="方向方案相关页面"><RouterLink to="/report?focus=versions">核对报告更新状态</RouterLink><RouterLink to="/plan">查看阶段计划</RouterLink></nav>

      <InfoSheet :open="comparisonOpen" shape="panel" title="比较已有方向" description="先看路线本身的差异；仍然难选时，再用个人偏好复核。" @close="comparisonOpen = false">
        <nav class="compare-view-tabs" role="tablist" aria-label="比较方式">
          <button type="button" role="tab" :aria-selected="compareView === 'content'" @click="compareView = 'content'"><strong>内容对照</strong><span>目标、门槛与风险</span></button>
          <button type="button" role="tab" :aria-selected="compareView === 'preference'" @click="compareView = 'preference'"><strong>偏好复核</strong><span>专业、机会与地点</span></button>
        </nav>
        <template v-if="compareView === 'content'">
          <div class="compare-desktop local-table-scroll">
            <table class="fact-table"><caption class="sr-only">最新方向的目标、要求、现状、建议与风险</caption><thead><tr><th scope="col">比较项目</th><th v-for="plan in orderedPlans" :key="plan.id" scope="col"><small>{{ shortRoles[plan.role] ?? plan.role }}</small>{{ plan.name }}</th></tr></thead><tbody><tr v-for="criterion in criteria" :key="criterion"><th scope="row">{{ criterion }}</th><td v-for="plan in orderedPlans" :key="plan.id"><ol :class="{'ws-attention': criterion === '主要风险'}"><li v-for="(value, index) in values(plan, criterion)" :key="index">{{ value }}</li></ol></td></tr></tbody></table>
          </div>
          <div class="compare-mobile">
            <div class="compare-criterion-tabs" role="tablist" aria-label="选择比较维度"><button v-for="criterion in criteria" :key="criterion" type="button" role="tab" :aria-selected="mobileCriterion === criterion" @click="mobileCriterion = criterion">{{ criterion }}</button></div>
            <section class="compare-one-criterion"><h3>{{ mobileCriterion }}</h3><article v-for="plan in orderedPlans" :key="plan.id"><strong>{{ shortRoles[plan.role] ?? plan.role }} · {{ plan.name }}</strong><ol :class="{'ws-attention': mobileCriterion === '主要风险'}"><li v-for="(value, index) in values(plan, mobileCriterion)" :key="index">{{ value }}</li></ol></article></section>
          </div>
        </template>
        <DirectionScoring v-else />
        <div class="compare-confirm"><div><strong>{{ pending?.name || '尚未选择候选方向' }}</strong><p>{{ candidate === selected && selected ? '这是当前方向。' : '确认后保存选择，已有执行记录仍保留。' }}</p></div><button class="btn btn--primary" type="button" :disabled="saving || !pending || candidate === selected" @click="$emit('select', candidate)">{{ saving ? '正在保存…' : '确认方向' }}</button></div>
      </InfoSheet>
    </template>

    <section v-else class="direction-empty" aria-labelledby="direction-empty-title"><header><p>方向尚待形成</p><h2 id="direction-empty-title">先把考虑对象与判断依据放到同一处</h2><RouterLink class="btn btn--primary" to="/chat?question=请根据我的个人资料，帮我整理正在考虑的方向并说明还缺哪些依据">开始梳理方向</RouterLink></header><ol><li><span>01</span><div><strong>补充考虑对象</strong><p>可以有多个，也可以暂时说“还没定”。</p></div></li><li><span>02</span><div><strong>核对比较依据</strong><p>画像、报告与现实限制会一起参与判断。</p></div></li><li><span>03</span><div><strong>安排一次验证</strong><p>用可执行的小尝试降低选择的不确定性。</p></div></li></ol><footer><RouterLink to="/profile">核对个人画像</RouterLink><RouterLink to="/report">查看诊断报告</RouterLink></footer></section>

    <div class="information-print-only"><h2>方向比较明细</h2><section v-for="plan in orderedPlans" :key="plan.id"><h3>{{ plan.name }} · {{ shortRoles[plan.role] ?? plan.role }}</h3><section v-for="criterion in criteria" :key="criterion"><h4>{{ criterion }}</h4><ul><li v-for="(value, index) in values(plan, criterion)" :key="index">{{ value }}</li></ul></section></section></div>
  </section>
</template>

<style scoped>
.direction-details{display:grid;gap:24px}.route-workbench{display:grid;gap:18px}.route-index{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:18px 28px}.route-index>header h2{font-family:var(--font-title);font-size:var(--fs-20);line-height:1.35}.route-index>header p{margin-top:5px;color:var(--c-text-3);font-size:var(--fs-13);line-height:1.65}.route-list{grid-column:1/-1;grid-row:2;position:relative;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--c-border);border-bottom:1px solid var(--c-border)}.route-list::before{display:none}.route-list button{position:relative;display:grid;grid-template-columns:17px minmax(0,1fr) auto;align-items:start;gap:0 13px;min-width:0;padding:18px 20px 19px;text-align:left;color:var(--c-text-2);border-bottom:2px solid transparent}.route-list button+button{border-left:1px solid var(--c-border)}.route-list__node{position:relative;z-index:1;width:17px;height:17px;margin-top:3px;border:4px solid var(--c-surface);border-radius:50%;background:var(--c-border-strong);box-shadow:0 0 0 1px var(--c-border)}.route-list__copy{display:grid;gap:4px;min-width:0}.route-list__copy small{color:var(--c-text-3);font-size:var(--fs-12)}.route-list__copy strong{font-size:var(--fs-15);line-height:1.45;overflow-wrap:anywhere}.route-list__copy>span{display:-webkit-box;overflow:hidden;color:var(--c-text-3);font-size:var(--fs-12);line-height:1.55;-webkit-line-clamp:2;-webkit-box-orient:vertical}.route-list em{margin-top:1px;padding:2px 6px;border-radius:var(--r-pill);color:var(--c-text-3);background:var(--c-bg-2);font-size:11px;font-style:normal;white-space:nowrap}.route-list button[aria-current=true]{border-bottom-color:var(--c-primary);color:var(--c-text);background:linear-gradient(180deg,transparent,var(--c-primary-weak))}.route-list button[aria-current=true] .route-list__node{background:var(--c-primary);box-shadow:0 0 0 1px var(--c-primary-border),0 0 0 5px var(--c-primary-weak)}.route-list button[aria-current=true] .route-list__copy small,.route-list button[aria-current=true] em{color:var(--c-primary)}.route-list button[aria-current=true] em{background:var(--c-primary-weak)}.route-index__compare{grid-column:2;grid-row:1;justify-self:end;padding:4px 0;border-bottom:1px solid var(--c-border-strong);color:var(--c-text-2);font-size:var(--fs-13)}.route-index__compare:hover{border-color:var(--c-primary);color:var(--c-primary)}
.route-sheet{min-width:0;border:1px solid var(--c-border);border-radius:18px;background:var(--c-surface);box-shadow:0 18px 46px -38px color-mix(in srgb,var(--c-text) 48%,transparent);overflow:hidden}.route-sheet__head{padding:36px 40px 30px;border-bottom:1px solid var(--c-border)}.route-sheet__status{display:flex;align-items:center;gap:10px;margin-bottom:21px}.route-sheet__status span{color:var(--c-primary);font-size:var(--fs-13);font-weight:var(--fw-semibold)}.route-sheet__status i{padding-left:10px;border-left:1px solid var(--c-border-strong);color:var(--c-text-3);font-size:var(--fs-12);font-style:normal}.route-sheet__head h2{max-width:16em;font-family:var(--font-title);font-size:clamp(30px,3.4vw,44px);font-weight:var(--fw-semibold);line-height:1.14;letter-spacing:-.025em;overflow-wrap:anywhere}.route-sheet__head>p{max-width:650px;margin-top:14px;color:var(--c-text-2);font-size:var(--fs-16);line-height:1.75}.route-rationale{display:grid;grid-template-columns:minmax(0,1fr) 160px;gap:36px;padding:30px 40px;border-bottom:1px solid var(--c-border)}.route-rationale h3,.route-checkpoints>header h3{font-size:var(--fs-16);font-weight:var(--fw-semibold)}.route-rationale>div>p{max-width:650px;margin-top:10px;font-size:var(--fs-16);line-height:1.8}.route-evidence{padding-left:24px;border-left:1px solid var(--c-border)}.route-evidence>span{display:block;color:var(--c-text-3);font-size:var(--fs-12)}.route-evidence strong{display:block;margin:6px 0 5px;color:var(--c-primary);font-family:var(--font-title);font-size:var(--fs-20)}.route-evidence strong small{font-size:var(--fs-12);font-weight:var(--fw-regular)}.route-evidence p{color:var(--c-text-3);font-size:var(--fs-12);line-height:1.55}
.route-checkpoints{padding:32px 40px 36px}.route-checkpoints>header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:22px}.route-checkpoints>header p{max-width:390px;color:var(--c-text-3);font-size:var(--fs-12);line-height:1.65;text-align:right}.route-checkpoints ol{display:grid;margin:0;padding:0;list-style:none}.route-checkpoints li{position:relative;display:grid;grid-template-columns:18px minmax(0,1fr);gap:16px;padding:0 0 25px}.route-checkpoints li:last-child{padding-bottom:0}.route-checkpoints li:not(:last-child)::before{content:"";position:absolute;top:14px;bottom:0;left:8px;width:1px;background:var(--c-border-strong)}.checkpoint-mark{position:relative;z-index:1;width:17px;height:17px;margin-top:2px;border:4px solid var(--c-surface);border-radius:50%;background:var(--c-primary);box-shadow:0 0 0 1px var(--c-primary-border)}.checkpoint-copy{min-width:0;padding-bottom:2px}.checkpoint-copy>strong{display:block;margin-bottom:11px;font-size:var(--fs-15);line-height:1.55}.checkpoint-copy dl{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:0}.checkpoint-copy dl>div{padding-top:10px;border-top:1px solid var(--c-border)}.checkpoint-copy dt{margin-bottom:5px;color:var(--c-text-3);font-size:var(--fs-12)}.checkpoint-copy dd{margin:0;color:var(--c-text-2);font-size:var(--fs-13);line-height:1.65;overflow-wrap:anywhere}.route-checkpoints__empty{padding:20px 0;border-top:1px solid var(--c-border)}.route-checkpoints__empty p{margin-bottom:8px;color:var(--c-text-2)}
.route-test{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(220px,.65fr);border-top:1px solid var(--c-border);border-bottom:1px solid var(--c-border);background:var(--c-bg-1)}.route-test>div{padding:29px 40px}.route-test__experiment{border-right:1px solid var(--c-border)}.route-test span{color:var(--c-primary);font-size:var(--fs-12);font-weight:var(--fw-semibold)}.route-test h3{max-width:28em;margin:9px 0 8px;font-size:var(--fs-18);line-height:1.55}.route-test p{color:var(--c-text-2);font-size:var(--fs-13);line-height:1.7}.route-test .ws-text-link{display:inline-block;margin-top:14px}.route-test__risk p{margin-top:9px;color:var(--c-attention-strong)}.route-decision{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 40px}.route-decision strong{font-size:var(--fs-14)}.route-decision p{margin-top:4px;color:var(--c-text-3);font-size:var(--fs-12)}.route-decision__current{flex:none;color:var(--c-primary);font-size:var(--fs-13);font-weight:var(--fw-semibold)}
.pending-confirm{position:sticky;bottom:16px;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:16px 18px;border:1px solid var(--c-primary-border);border-left:4px solid var(--c-primary);border-radius:12px;background:var(--c-surface);box-shadow:var(--e-3)}.pending-confirm>div:first-child{display:grid;gap:3px}.pending-confirm>div:first-child>span{color:var(--c-primary);font-size:var(--fs-12);font-weight:var(--fw-semibold)}.pending-confirm strong{font-size:var(--fs-15)}.pending-confirm p{color:var(--c-text-3);font-size:var(--fs-12)}.pending-confirm>div:last-child{display:flex;align-items:center;gap:14px;flex:none}.compare-view-tabs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:0 0 24px;padding:5px;border-radius:12px;background:var(--c-surface-2)}.compare-view-tabs button{display:grid;gap:2px;min-height:56px;padding:9px 14px;border:1px solid transparent;border-radius:9px;text-align:left;color:var(--c-text-3)}.compare-view-tabs button strong{color:var(--c-text-2);font-size:var(--fs-14)}.compare-view-tabs button span{font-size:var(--fs-12)}.compare-view-tabs button[aria-selected=true]{border-color:var(--c-border);background:var(--c-surface);box-shadow:0 4px 14px -12px var(--c-text)}.compare-view-tabs button[aria-selected=true] strong{color:var(--c-primary)}.compare-mobile{display:none}.compare-confirm{position:sticky;bottom:0;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:24px -24px -24px;padding:16px 24px;border-top:1px solid var(--c-border);background:var(--c-surface);box-shadow:0 -8px 24px -20px var(--c-text)}.compare-confirm p{margin-top:3px;color:var(--c-text-3);font-size:var(--fs-12)}.fact-table th small{display:block;margin-bottom:4px;color:var(--c-primary)}.fact-table ol{margin:0;padding-left:18px}.direction-empty{display:grid;grid-template-columns:minmax(0,.9fr) minmax(360px,1.2fr);gap:38px;padding:32px 0;border-top:3px solid var(--c-primary);border-bottom:1px solid var(--c-border)}.direction-empty header>p{color:var(--c-primary);font-size:12px;font-weight:600}.direction-empty header h2{max-width:14em;margin:7px 0 22px;font-size:28px;line-height:1.38}.direction-empty ol{margin:0;padding:0;list-style:none}.direction-empty li{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;padding:13px 0;border-bottom:1px solid var(--c-border)}.direction-empty li>span{color:var(--c-primary);font-size:12px;font-variant-numeric:tabular-nums}.direction-empty li strong{font-size:15px}.direction-empty li p{margin-top:4px;color:var(--c-text-3);font-size:13px;line-height:1.6}.direction-empty footer{grid-column:1/-1;display:flex;gap:20px}.direction-empty footer a{display:inline-flex;align-items:center;min-height:44px;color:var(--c-primary);font-size:13px}
.route-list em{background:var(--c-surface-3)}
.route-test{background:var(--c-surface-2)}
@media(max-width:980px){.route-sheet__head,.route-rationale,.route-checkpoints,.route-decision{padding-left:30px;padding-right:30px}.route-test>div{padding-left:30px;padding-right:30px}}
@media(max-width:760px){.direction-details{gap:20px}.direction-empty{grid-template-columns:1fr;gap:18px;padding-top:26px}.direction-empty header h2{font-size:23px}.direction-empty footer{flex-wrap:wrap;gap:8px 20px}.route-workbench{gap:16px}.route-index{grid-template-columns:1fr;gap:14px;padding:0}.route-index>header{display:none}.route-list{grid-row:auto;grid-template-columns:repeat(3,minmax(150px,1fr));gap:8px;margin:0 -16px;padding:2px 16px 8px;border:0;overflow-x:auto;scroll-snap-type:x proximity}.route-list::before{display:none}.route-list button{display:block;padding:12px 13px;border:1px solid var(--c-border)!important;border-radius:10px;background:var(--c-surface);scroll-snap-align:start}.route-list button+button{border-left:1px solid var(--c-border)}.route-list button[aria-current=true]{border-color:var(--c-primary-border)!important;background:var(--c-primary-weak)}.route-list__node,.route-list__copy>span{display:none}.route-list__copy{gap:3px}.route-list__copy strong{font-size:var(--fs-13)}.route-list em{display:inline-block;margin-top:8px;background:transparent!important;padding:0}.route-index__compare{grid-column:1;grid-row:auto;justify-self:start;margin-left:2px}.route-sheet{border-radius:14px}.route-sheet__head{padding:28px 24px 24px}.route-sheet__head h2{font-size:30px}.route-sheet__head>p{font-size:var(--fs-14)}.route-rationale{grid-template-columns:1fr;gap:22px;padding:24px}.route-rationale>div>p{font-size:var(--fs-15)}.route-evidence{display:grid;grid-template-columns:auto auto;align-items:baseline;justify-content:start;gap:4px 10px;padding:14px 0 0;border-top:1px solid var(--c-border);border-left:0}.route-evidence strong{margin:0}.route-evidence p{grid-column:1/-1}.route-checkpoints{padding:26px 24px 30px}.route-checkpoints>header{display:block}.route-checkpoints>header p{margin-top:7px;text-align:left}.checkpoint-copy dl{grid-template-columns:1fr;gap:10px}.route-test{grid-template-columns:1fr}.route-test>div{padding:24px}.route-test__experiment{border-right:0;border-bottom:1px solid var(--c-border)}.route-decision{align-items:flex-start;padding:20px 24px}.compare-desktop{display:none}.compare-mobile{display:block}.compare-criterion-tabs{display:flex;gap:6px;padding-bottom:10px;overflow-x:auto;scroll-snap-type:x proximity}.compare-criterion-tabs button{flex:none;min-height:40px;padding:7px 12px;border:1px solid var(--c-border);border-radius:var(--r-pill);color:var(--c-text-2);background:var(--c-surface);scroll-snap-align:start}.compare-criterion-tabs button[aria-selected=true]{border-color:var(--c-primary);color:var(--c-primary);font-weight:var(--fw-semibold);background:var(--c-primary-weak)}.compare-one-criterion{margin-top:14px}.compare-one-criterion>h3{font-size:var(--fs-18)}.compare-one-criterion article{padding:14px 0;border-bottom:1px solid var(--c-border)}.compare-one-criterion ol{display:grid;gap:6px;margin:8px 0 0;padding-left:18px}.compare-confirm{margin:20px -20px -24px;padding:14px 20px calc(14px + env(safe-area-inset-bottom))}.compare-confirm .btn{flex:none}}
@media(max-width:520px){.route-sheet__head h2{font-size:28px}.route-sheet__status{align-items:flex-start;flex-direction:column;gap:5px;margin-bottom:16px}.route-sheet__status i{padding-left:0;border-left:0}.route-decision{flex-direction:column}.route-decision .btn{width:100%}.pending-confirm{bottom:76px;align-items:flex-start;flex-direction:column;gap:14px}.pending-confirm>div:last-child{width:100%;justify-content:flex-end}.compare-confirm{align-items:flex-end}.compare-confirm p{max-width:190px}}
@media(max-width:760px){.route-list{position:relative;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin:0;padding:0 0 10px;overflow:visible}.route-list::before{display:block;top:8px;right:16.66%;bottom:auto;left:16.66%;width:auto;height:1px}.route-list button{display:grid;grid-template-columns:1fr;justify-items:center;gap:7px;padding:0 6px 11px;border:0!important;border-bottom:2px solid transparent!important;border-radius:0;background:transparent;text-align:center}.route-list button[aria-current=true]{border-color:var(--c-primary)!important;background:transparent}.route-list__node{display:block;width:17px;height:17px;margin:0;border-width:4px}.route-list__copy{justify-items:center}.route-list__copy small{font-size:11px}.route-list__copy strong{display:-webkit-box;min-height:2.9em;overflow:hidden;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.route-list em{display:none}.route-index__compare{margin-left:0}}
@media(max-width:360px){.route-list button{padding-inline:3px}.route-list__copy strong{height:2.8em;min-height:2.8em;font-size:12px;line-height:1.4}}
</style>
