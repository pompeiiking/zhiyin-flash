<script setup lang="ts">
import DetailPopover from '../../components/DetailPopover.vue'
import UiIcon from '../../components/UiIcon.vue'

interface EnrollmentRow { label: string; value: string }

defineProps<{ enrollmentRows: EnrollmentRow[]; isVerified: boolean }>()
const emit = defineEmits<{ verify: [] }>()
</script>

<template>
<section class="enrollment" aria-labelledby="enrollment-title"><header><div><span class="enrollment__eyebrow">学校档案</span><h2 id="enrollment-title">学籍信息 <DetailPopover title="学籍信息说明" label="查看学籍信息说明"><p>核对学校、专业与在读状态，查看学籍核验结果。</p></DetailPopover></h2></div><button class="btn" @click="emit('verify')"><UiIcon name="shield" :size="16" />{{ isVerified ? '重新核验' : '核验学籍' }}</button></header><dl><div v-for="item in enrollmentRows" :key="item.label"><dt>{{item.label}}</dt><dd :class="{'is-missing':item.value==='待补充'}">{{item.value}}</dd></div></dl><footer><span :class="['enrollment__state', isVerified ? 'is-verified' : '']"><i />{{ isVerified ? '已包含学信来源' : '尚未完成学信核验' }}</span><RouterLink class="ws-text-link" to="/grades">查看我的成绩<UiIcon name="arrow" :size="14" /></RouterLink></footer></section>
</template>

<style scoped>
.enrollment{margin:18px 0 24px;padding:22px 24px;border:1px solid var(--c-border);border-radius:var(--r-lg);background:var(--c-surface)}.enrollment header{display:flex;align-items:start;justify-content:space-between;gap:24px}.enrollment__eyebrow{font-size:var(--fs-12);font-weight:var(--fw-semibold);color:var(--c-primary)}.enrollment h2{margin-top:3px;font-size:var(--fs-18);font-weight:var(--fw-semibold)}.enrollment header p{max-width:64ch;margin-top:5px;font-size:var(--fs-13);line-height:1.7;color:var(--c-text-2)}.enrollment dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-top:20px;border-top:1px solid var(--c-border);border-bottom:1px solid var(--c-border)}.enrollment dl>div{padding:15px 16px}.enrollment dl>div+div{border-left:1px solid var(--c-border)}.enrollment dt{font-size:var(--fs-12);color:var(--c-text-3)}.enrollment dd{margin-top:6px;font-size:var(--fs-14);font-weight:var(--fw-medium);color:var(--c-text)}.enrollment dd.is-missing{font-weight:var(--fw-regular);color:var(--c-text-3)}.enrollment footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:14px}.enrollment__state{display:flex;align-items:center;gap:7px;font-size:var(--fs-12);color:var(--c-text-3)}.enrollment__state i{width:7px;height:7px;border-radius:50%;background:var(--c-border-strong)}.enrollment__state.is-verified{color:var(--c-primary)}.enrollment__state.is-verified i{background:var(--c-primary)}
@media(max-width:760px){.enrollment{padding:18px}.enrollment header{flex-direction:column}.enrollment header .btn{width:100%}.enrollment dl{grid-template-columns:1fr 1fr}.enrollment dl>div:nth-child(3){border-left:0;border-top:1px solid var(--c-border)}.enrollment dl>div:nth-child(4){border-top:1px solid var(--c-border)}.enrollment footer{align-items:flex-start;flex-direction:column}}

/* 与视图共用同一 44px 触控基线：本组件标记需要在本组件的 scoped 块里保留同一声明。 */
.p7 .btn { min-height: 44px; }
.p7 .ws-text-link { min-height: 44px; }
</style>
