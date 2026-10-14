<script setup lang="ts">
/*
 * AiResultMeta —— 6 个 AI 面板共用的「这次结果是怎么来的」。
 *
 * 改动的唯一依据：`DESIGN-LANGUAGE §5` 的反例表 ——
 *   "溯源做成一个折叠的『来源』 → 要用户自己点开才知道，信息还是平面的"。
 * 老写法（`AiResultMeta:6`）整条溯源住在一个 `<details class="ws-context">` 里，
 * 折叠头只是一句空壳标题「依据与生成说明」，点开之前**一个来源都看不见** ——
 * 正是这条反例。MIGRATION §1.3 A9 也写了：" citations 的 source/detail/at 必须改
 * SourceChip，否则折叠一打开还是灰字，等于折了两次"。
 *
 * 所以现在：
 *   · **常驻的紧凑来源行**（`SourceChip` + `StatTile`）—— 不进折叠，不在灰字里；
 *   · citations 常驻（它们是"这次结论靠什么"的证据，不是"原始证据全文"）；
 *   · `rationale` 也常驻，**这一块里一个折叠都没有**。
 *     为什么连 `rationale` 也不折：`AiResultMeta` 的每一个消费方本身就是一个折叠
 *     （`TaskBrief` / `TimetableAdvice` / `TodoSuggestions` / `CareerMatchPanel` 的
 *     `.fold--section`，`ProfileInsights` 的弹层），内层再折一层就是**二级折叠**
 *     ——实测会被 `Foldable.vue:77-93` 的层级检测抓到：
 *     `[Foldable] 折叠被嵌套在第 2 层：「这次结果是怎么来的 · 1 条来源 · 本地演示 · 2026-10-13」`。
 *     `PLAN.md:114` 的"一页最多 1 层"说的是**折叠**，所以这里做 `static` 不算犯规，
 *     而且正好落在 `PLAN.md:112`："主信息默认可见"。
 *
 * 为什么 `SourceChip` 的 `source` 不是 citations 的自由文本：
 *   `SourceChip` 的 `source` 是**必填的 `ProfileSource` 七值枚举**（`SourceChip.vue:38`），
 *   而 `citation.source` 是自由文本（"咨询与课程记录"）—— 类型上喂不进去
 *   （MIGRATION §3.2 S3/S5/S7，U3 记的缺口）。而 AI 结果本身没有一个"来源枚举"字段，
 *   所以这里用 `user_edit`（"你自己改的"）在语义上**不成立**。
 *   折中且不撒谎的做法：把 `SourceChip` 降为 **`origin` 字段存在时的载体** ——
 *   `citation.origin` 是真实外链，有 origin 的条目用 `SourceChip` 的"教务记录"形态
 *   表达"这条来自可核对的外部记录"，其余自由文本来源保持可读的文本形态。
 *   （更好的形态需要一个 `ExternalSourceChip`，属于共享组件改动，已写进交付说明。）
 */
import { computed } from 'vue'
import SourceChip from './SourceChip.vue'
import StatTile from './StatTile.vue'
import type { AiResult } from '../api/ai-types'

const props = defineProps<{ result: AiResult<unknown> }>()

function sourceLink(value?: string) { return value && /^https?:\/\//i.test(value) ? value : undefined }

/* 生成时间：日期用 YYYY-MM-DD（CRAFT-BRIEF §4.2 规则 3），时刻不印 —— 它不参与判断 */
const at = computed(() => {
  const raw = props.result.meta.at
  if (!raw) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : raw
})

const demo = computed(() => props.result.meta.by.includes('本地演示'))
const sourceCount = computed(() => props.result.citations.length)
</script>

<template>
  <div class="ai-meta">
    <!-- ① 常驻的紧凑来源行：来源与生成说明默认可见，不进折叠 -->
    <div class="ai-meta__line">
      <!-- 计数读数走 value 路径：来源条数没有"分母"可言，
           硬给 denominator 会画出 100% 的进度条，反而在说"来源齐了" -->
      <StatTile
        v-if="sourceCount"
        class="ai-meta__count"
        :value="sourceCount"
        unit="条"
        label="来源"
      />
      <SourceChip
        v-for="(c, i) in result.citations.filter((x) => sourceLink(x.origin))"
        :key="`src-${i}`"
        source="record"
        :at="c.at ?? null"
      />
      <p class="ai-meta__by">
        <template v-if="demo">已保存的资料解读</template>
        <template v-else>{{ result.meta.by }}</template>
        <template v-if="at"> · {{ at }}</template>
        <template v-if="result.meta.cached"> · 已保存的结果</template>
      </p>
    </div>

    <!-- ② citations 常驻（不再是灰字 + 折叠） -->
    <ul v-if="sourceCount" class="ai-meta__sources">
      <li v-for="(c, i) in result.citations" :key="i" class="ai-meta__source">
        <span class="ai-meta__source-name">{{ c.source }}</span>
        <time v-if="c.at" class="ai-meta__time t-num">{{ c.at }}</time>
        <p class="ai-meta__detail">{{ c.detail }}</p>
        <a
          v-if="sourceLink(c.origin)"
          class="ws-text-link"
          :href="sourceLink(c.origin)"
          target="_blank"
          rel="noopener noreferrer"
        >核对原始来源</a>
      </li>
    </ul>
    <p v-else class="ai-meta__note">本次结果没有返回具体来源，请结合已有资料核对。</p>

    <!-- ③ 口径说明也常驻：本组件内没有任何折叠（消费方本身已经是折叠，内层再折一层就是二级折叠） -->
    <p v-if="result.rationale" class="ai-meta__why">
      <span class="ai-meta__why-key">口径</span>{{ result.rationale }}
    </p>
  </div>
</template>

<style scoped>
.ai-meta {
  margin-top: var(--sp-5);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
}

/* 常驻来源行：读数瓦片靠左，来源徽标与生成说明跟在后面，窄屏自动换行 */
.ai-meta__line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-3);
}
.ai-meta__count { flex: none; }
.ai-meta__by {
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.ai-meta__sources {
  margin-top: var(--sp-3);
  display: grid;
  gap: var(--sp-3);
}
.ai-meta__source {
  padding-left: var(--sp-3);
  border-left: var(--bw-2) solid var(--c-border);
}
.ai-meta__source-name {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--c-text);
}
.ai-meta__time {
  margin-left: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}
.ai-meta__detail {
  margin-top: var(--sp-1);
  max-width: 38em;
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-2);
}
.ai-meta__note {
  margin-top: var(--sp-3);
  font-size: var(--fs-14);
  color: var(--c-text-3);
}
/* 口径说明：常驻的一行，用"口径"这个小标签起头，和来源/正文分开读 */
.ai-meta__why {
  margin-top: var(--sp-3);
  max-width: 38em;
  font-size: var(--fs-12);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}
.ai-meta__why-key {
  display: inline-block;
  margin-right: var(--sp-2);
  padding: 1px var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-sm);
}
</style>
