<script setup lang="ts">
import DetailPopover from '../../components/DetailPopover.vue'
import EvidenceState from '../../components/EvidenceState.vue'
import UiIcon from '../../components/UiIcon.vue'
import { studentVoice } from '../../lib/student-voice'
import type { Conclusion, GapRow } from '../../lib/use-profile-conclusions'

interface DossierIdentity { name: string; line: string }
interface DossierProgress { known: number; total: number; gap: number }
interface DossierConfBand { key: string; title: string; count: number }
interface DossierSnapshot { label: string; title: string; state: string; detail: string }

defineProps<{
  identity: DossierIdentity
  progress: DossierProgress
  confBands: DossierConfBand[]
  loading: boolean
  livePanel?: object | null
  serviceError: string
  profileSnapshot: DossierSnapshot
  priorityConclusions: Conclusion[]
  priorityGaps: GapRow[]
  known: unknown[]
  needsCheck: unknown[]
}>()

const emit = defineEmits<{
  verify: []
  tab: [tab: 'facts' | 'judgments' | 'gaps' | 'sources']
  'jump-conclusion': [key: string]
}>()
</script>

<template>
    <section class="profile-dossier" aria-labelledby="profile-dossier-title">
      <header class="profile-dossier__header">
        <div class="profile-dossier__identity">
          <div class="profile-dossier__portrait" aria-hidden="true">{{ identity.name.slice(0,1) }}</div>
          <div>
            <p class="profile-dossier__label">个人画像</p>
            <h2 id="profile-dossier-title">{{ identity.name }}</h2>
            <p>{{ identity.line }}</p>
          </div>
          <DetailPopover title="个人资料概况" label="查看个人资料概况"><p>已记录 {{ progress.known }} 条信息，{{ progress.gap }} 条可以继续补充。</p><p>{{ confBands[0]?.title }} {{ confBands[0]?.count ?? 0 }} 条，{{ confBands[2]?.title }} {{ confBands[2]?.count ?? 0 }} 条。</p></DetailPopover>
        </div>
        <div class="profile-dossier__coverage">
          <div><span>已记录资料</span><strong>{{ progress.known }}<small> / {{ progress.total }}</small></strong><EvidenceState :state="progress.gap ? 'missing' : 'recorded'" /></div>
          <div class="profile-dossier__track" role="progressbar" :aria-label="'已记录资料'" :aria-valuemin="0" :aria-valuemax="progress.total" :aria-valuenow="progress.known" :aria-valuetext="'已记录 '+progress.known+' 条，共 '+progress.total+' 条，可以补充 '+progress.gap+' 条'"><i v-for="n in progress.total" :key="n" aria-hidden="true" :class="{'is-known':n<=progress.known}"/></div>
          <p>{{ loading && !livePanel ? '正在读取资料…' : serviceError ? '资料读取失败，请重试核对' : !livePanel ? '尚未读取资料' : !progress.known && !progress.gap ? '暂无个人资料，可从咨询开始补充' : progress.gap ? `还有 ${progress.gap} 条可以补充，不影响继续交流` : '当前没有列出的可补充项' }}</p>
        </div>
      </header>

      <div class="profile-dossier__statement">
        <span>{{ profileSnapshot.label }}</span>
        <div class="profile-dossier__statement-main">
          <strong>{{ profileSnapshot.title }}</strong>
          <small>{{ profileSnapshot.detail }}</small>
        </div>
        <div class="profile-dossier__statement-actions">
          <span>{{ profileSnapshot.state }}</span>
          <DetailPopover :title="profileSnapshot.title" label="查看当前画像判断"><template #trigger>查看判断</template><p>{{ profileSnapshot.detail }}</p><p>画像会随补充资料、核对来源和实际行动继续更新。</p></DetailPopover>
        </div>
      </div>

      <div class="profile-dossier__body">
        <section class="profile-directions" aria-labelledby="profile-directions-title">
          <header>
            <div><h3 id="profile-directions-title">正在浮现的方向 <DetailPopover title="方向说明" label="查看方向说明"><p>这些是接下来值得验证的假设，不是替你做出的职业定论。</p></DetailPopover></h3></div>
            <button class="ws-text-button" type="button" @click="emit('tab','judgments')">查看完整分析<UiIcon name="arrow" :size="14"/></button>
          </header>
          <ul v-if="priorityConclusions.length">
            <li v-for="item in priorityConclusions" :key="item.key">
              <DetailPopover class="profile-direction" :title="item.label" :label="item.label + '：' + studentVoice(item.brief)" side="bottom"><template #trigger>
                <span class="profile-direction__mark" aria-hidden="true"></span><span><strong>{{ item.label }}</strong><small>{{ studentVoice(item.brief) || '这条判断暂时没有摘要。' }}</small></span><UiIcon name="info" :size="16" aria-hidden="true"/>
              </template><p>{{ studentVoice(item.full || item.brief) }}</p><p class="profile-popover-meta">{{ item.section }} · {{ item.deps.length ? item.deps.length + ' 项资料支撑' : '逐项依据待核对' }}</p><p v-if="item.note">判断说明：{{ item.note }}</p><p v-if="item.risk">需要留意：{{ item.risk }}</p><p v-if="item.missingKeys.length">仍缺 {{ item.missingKeys.length }} 项关键资料。</p><button class="ws-text-button" type="button" @click="emit('jump-conclusion', item.key)">在完整分析中核对</button></DetailPopover>
            </li>
          </ul>
          <div v-else class="profile-focus-empty">
            <span>方向尚未形成</span>
            <strong>{{ priorityGaps.length ? '还可以进一步了解这些信息' : '可以结合已有资料继续探索' }}</strong>
            <ol v-if="priorityGaps.length" aria-label="可以继续了解的信息">
              <li v-for="item in priorityGaps.slice(0,3)" :key="item.key"><i aria-hidden="true" />{{ item.label }}</li>
            </ol>
            <RouterLink class="ws-text-link" to="/chat">继续探索与比较<UiIcon name="arrow" :size="14" /></RouterLink>
          </div>
        </section>

        <section class="profile-next" aria-labelledby="profile-next-title">
          <p class="profile-next__label">下一步只做一件事</p>
          <template v-if="priorityGaps[0]">
            <h3 id="profile-next-title">{{ priorityGaps[0].label }}</h3>
            <div class="profile-next__suggestion"><span>建议行动</span><strong>{{ studentVoice(priorityGaps[0].next) }}</strong></div>
            <DetailPopover class="profile-next__reason" :title="'为什么先补充' + priorityGaps[0].label" label="查看这项信息的影响"><template #trigger>为什么先补这项</template><p>{{ priorityGaps[0].why }}</p><p v-if="priorityGaps[0].affects.length">它会影响 {{ priorityGaps[0].affects.map(item => item.label).join('、') }}。</p></DetailPopover>
            <button v-if="priorityGaps[0].source === 'chsi'" type="button" class="btn btn--primary" @click="emit('verify')">核验学籍信息<UiIcon name="arrow" :size="14"/></button>
            <RouterLink v-else class="btn btn--primary" :to="'/chat?gap='+encodeURIComponent(priorityGaps[0].key)+'&label='+encodeURIComponent(priorityGaps[0].label)">去补充这条信息<UiIcon name="arrow" :size="14"/></RouterLink>
            <button class="ws-text-button" type="button" @click="emit('tab','gaps')">查看全部待补充信息</button>
          </template>
          <template v-else>
            <h3 id="profile-next-title">{{ progress.gap ? '继续补齐资料' : known.length ? '核对已有资料' : '补充个人资料' }}</h3>
            <p>{{ progress.gap ? '还有 ' + progress.gap + ' 项资料待补充（学校、专业、学历、在读状态等）；可以先核对已有资料，也可以从对话里逐项补齐。' : known.length ? '当前没有明确缺口，可以从标为“待核对”的信息开始确认。' : '先补充所学专业或一段经历，帮助系统了解你的情况。' }}</p>
            <RouterLink v-if="progress.gap || !known.length" class="ws-text-link" :to="known.length ? '/profile?tab=gaps' : '/chat'">{{ known.length ? '查看待补字段' : '开始补充' }}<UiIcon name="arrow" :size="14" /></RouterLink>
          </template>
          <p v-if="needsCheck.length" class="profile-next__check">另有 {{ needsCheck.length }} 项资料需要核对</p>
        </section>
      </div>
    </section>
</template>

<style scoped>
/* 与视图共用同一 44px 触控基线：本组件标记需要在本组件的 scoped 块里保留同一声明。 */
.p7 .btn { min-height: 44px; }
.p7 .ws-text-button,
.p7 .ws-text-link { min-height: 44px; }
</style>
