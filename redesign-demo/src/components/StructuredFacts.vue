<script setup lang="ts">
defineProps<{ value: unknown }>()
const labels:Record<string,string>={name:'名称',text:'内容',title:'标题',description:'说明',total:'总数',completed:'已完成',tasks:'任务',phase:'阶段',done:'完成状态',unlocked:'已达成',unlocked_at:'达成时间',items:'记录',key:'记录标识',has_plan:'已有计划',data:'结果',sources:'来源',status:'状态',message:'反馈',result:'结果',count:'数量',headline:'结论',body:'正文',because:'依据'}
function human(key:string){return labels[key]??key}
</script>
<template><ul v-if="Array.isArray(value)" class="ws-mini-list"><li v-for="(v,i) in value" :key="i"><StructuredFacts :value="v"/></li></ul><dl v-else-if="value!==null&&typeof value==='object'" class="structured-facts"><template v-for="(v,k) in value" :key="k"><dt>{{ human(String(k)) }}</dt><dd><StructuredFacts :value="v"/></dd></template></dl><span v-else>{{ typeof value==='boolean'?(value?'是':'否'):value ?? '未提供' }}</span></template>
