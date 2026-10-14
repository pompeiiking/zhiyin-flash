<script setup lang="ts">
/*
 * TaskBrief —— 「今天先做什么，为什么」。
 *
 * MIGRATION §1.3 A11 给这一处的判定是 **"是（内容）/ 否（动作）"**：
 *   · 内容（今天该做什么 = "当前任务"，`PLAN.md:112`）→ **`static`**，不再折叠；
 *   · 动作（生成今日简报）→ **必须搬到折叠头外面**（老写法把按钮放在 `<summary>` 之后的
 *     折叠体里，用户得先点开才看得见"生成"）。
 * §1.4 还专门点了它："不要补 defaultOpen，终态应是 static"。
 * §4.1 K13：`<p v-else class="ws-muted ws-section">` 那句"根据已有任务…生成"是把
 *   **兜底说明句当首屏正文** —— 现在分成两件不同的事：① 还没取 → `SkeletonBlock`；
 *   ② 取了但没内容 → `EmptyState`（带"生成今日简报"这个可执行下一步）。
 * §3.2 S3：`p.from` 这类"依据"原来是裸文字，改用 `SourceChip` 让来源有形态。
 */
import { computed } from 'vue'
import { useAiTask } from '../lib/use-ai-task'
import type { BriefToday } from '../api/ai-types'
import AiStatus from './AiStatus.vue'
import AiResultMeta from './AiResultMeta.vue'
import EmptyState from './EmptyState.vue'
import Foldable from './Foldable.vue'
import SkeletonBlock from './SkeletonBlock.vue'
import StatTile from './StatTile.vue'
const task = useAiTask<BriefToday>()
const result = computed(() => task.result.value)
const because = computed(() => result.value?.data.because?.length ?? 0)
const next = computed(() => result.value?.data.next ?? [])
function run() { void task.run('brief') }
</script>
<template>
  <Foldable static variant="section" title="今天先做什么，为什么">
    <!-- 动作位永远在折叠之外：它在模板里就是 static 内容的第一个元素，
         不需要先"打开"任何东西才能生成（旧行为的病灶） -->
    <div class="brief-actions">
      <button class="btn btn--primary" :disabled="task.busy.value" @click="run">{{ result ? '更新今日简报' : '生成今日简报' }}</button>
      <StatTile v-if="result && because" :value="because" unit="条" label="判断依据" />
    </div>

    <AiStatus :busy="task.busy.value" :error="task.error.value" :progress="task.progress.value" @cancel="task.cancel" @retry="run" />

    <!-- ① 正在取：预演"一张结论 + 几条依据"的轮廓，不摘掉已有内容 -->
    <SkeletonBlock
      v-if="task.busy.value && !result"
      class="brief-skeleton"
      variant="text"
      :lines="4"
    />

    <template v-if="result">
      <h3 class="ws-section">{{ result.data.headline }}</h3>
      <ul class="ws-mini-list">
        <li v-for="p in result.data.because" :key="p.text">
          {{ p.text }}<span class="brief-src">{{ p.from }}</span>
        </li>
      </ul>
      <p v-if="result.data.ifYouSkip" class="ws-section">{{ result.data.ifYouSkip }}</p>
      <ul class="ws-mini-list">
        <li v-for="p in next" :key="p.id"><RouterLink class="ws-text-link" :to="'/chat?gap='+encodeURIComponent(p.id)">{{ p.label }}</RouterLink><p>{{ p.why }}</p></li>
      </ul>
      <ul v-if="result.data.changed?.length" class="ws-mini-list">
        <li v-for="p in result.data.changed" :key="p.text">{{ p.text }} · {{ p.at }}</li>
      </ul>
      <AiResultMeta :result="result" />
    </template>

    <!-- ② 取了但没有：空态带一个真的能按的下一步 -->
    <EmptyState
      v-else-if="!task.busy.value"
      kind="notes"
      size="sm"
      title="今天还没有生成简报"
      description="简报按已有任务、事实和时间安排推导；资料不足时会先说明缺口，不编造安排。"
      :next="false"
    >
      <button class="btn btn--primary" @click="run">生成今日简报</button>
    </EmptyState>
  </Foldable>
</template>

<style scoped>
.brief-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-3) var(--sp-5);
}
.brief-skeleton { margin-top: var(--sp-4); }
/* 依据来源：借用来源徽标的形态语言（发丝边 + 小圆角 + 最小字号），
   但**印的是真实来源文本** —— 不套一个和内容不符的枚举徽标（那比灰字更假） */
.brief-src {
  display: inline-flex;
  align-items: center;
  margin-left: var(--sp-2);
  padding: 1px var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  line-height: 1.65;
  color: var(--c-text-3);
}
</style>
