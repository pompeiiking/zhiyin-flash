<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { capabilities, downloadTemplate, pretty, type Capability, type ModuleKind } from './client'
const props = defineProps<{ account: string }>()
const emit = defineEmits<{ projects: [] }>()
const form = reactive({ kind: 'application' as ModuleKind, module_id: '', name: '', owner: props.account })
const items = ref<Capability[]>([])
const error = ref('')
const busy = ref(false)
onMounted(async () => { try { items.value = await capabilities() } catch (e) { error.value = String(e) } })
async function download() { busy.value = true; error.value = ''; try { await downloadTemplate(form) } catch (e) { error.value = String(e) } finally { busy.value = false } }
</script>
<template>
  <section class="dev-start">
    <h2>从一个清楚的数据接口开始</h2><p>供团队内部授权开发者使用。先确定输入、输出和平台能力，再开发组件；同一份声明用于检查、预览和部署。</p>
    <ol class="journey"><li><strong>领取模板</strong><span>选择应用或技能，了解数据契约。</span></li><li><strong>本地开发</strong><span>实现功能、声明输出结构，补齐示例和测试。</span></li><li><strong>提交版本</strong><span>上传单模块 ZIP，保留版本和开发分支。</span></li><li><strong>自动验收与发布</strong><span>查看真实门禁结果，通过后按项目策略部署。</span></li></ol>
    <p v-if="error" role="alert" class="dev-alert">{{ error }}</p>
    <form class="dev-panel dev-form" @submit.prevent="download"><h3>生成你的模块模板</h3>
      <label>模块类型<select v-model="form.kind"><option value="application">应用模块 · 平台内完整功能</option><option value="tool">技能组件 · 供智能体调用</option><option value="hybrid">应用与技能 · 同时提供两种入口</option></select></label>
      <label>模块编号<input v-model="form.module_id" required pattern="[a-z][a-z0-9_]{1,47}" placeholder="例如 weekly_tasks" /></label>
      <label>模块名称<input v-model="form.name" required maxlength="80" placeholder="例如 本周任务" /></label>
      <label>负责人<input v-model="form.owner" required maxlength="80" /></label>
      <button class="primary" :disabled="busy">{{ busy ? '正在生成…' : '下载开发模板 ZIP' }}</button>
      <p>模块编号应与之后创建的项目编号相同。模板包含声明、处理逻辑、示例、测试以及该类型需要的界面。</p>
    </form>
    <h3>可以连接的平台能力</h3><p>身份由平台注入；通过 SDK 获取当前用户的数据，结果按声明结构返回。需要新能力时先扩展并登记平台契约。</p>
    <div class="capability-grid"><article v-for="item in items" :key="item.id" class="dev-panel"><h4>{{ item.id }} <small>{{ item.operation === 'read' ? '读取' : '业务操作' }}</small></h4><p>{{ item.description }}</p><small>{{ item.user_scoped ? '仅当前用户数据' : '共享能力' }}</small><details><summary>输入与输出契约</summary><strong>输入</strong><pre>{{ pretty(item.input_schema) }}</pre><strong>输出</strong><pre>{{ pretty(item.output_schema) }}</pre></details></article></div>
    <p v-if="!items.length && !error">正在读取能力目录…</p>
    <button class="primary" @click="emit('projects')">创建项目并提交版本 →</button>
  </section>
</template>
