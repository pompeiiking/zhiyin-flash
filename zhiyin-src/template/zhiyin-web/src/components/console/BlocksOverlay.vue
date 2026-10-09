<script setup lang="ts">
/**
 * 全部组件 —— 画布上放哪些块、按什么顺序。
 *
 * 为什么要有这一屏：画布此前的能力是"全都摆出来、你自己拖"，而 issue #22/#25 说的
 * 正是它的反面 —— 卡片过多、找不到重点，也没有"我只想留三块"这个动作。
 * 管理能力其实早就有（右键菜单里的「叫出某块」「全部叫出来」「全部重排」），
 * 但它只存在于**右键**里，而没有人会去右键空白处 —— 等于没有。
 *
 * 这一屏给三个动作，都**持久**（刷新、重开浏览器还在）：
 *   收起 / 放回 / 上下挪一位；另有"回到默认"。
 *
 * 三条纪律写在这里，免得以后被"优化"掉：
 *   1. 「收起」是**用户说的**，不是"这块没用了" —— 所以文案不评价它，也不劝他留下；
 *   2. 收起的块**不消失**，它就在这一屏里，随时能放回（入口上的小数字也是这个意思）；
 *   3. 排序只挪一位，不用拖 —— 这里是一张清单，拖拽属于画布。
 */
import { computed } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import GlyphIcon from '@/components/ui/GlyphIcon.vue'
import { BLOCK_LABELS, BLOCK_ORDER } from '@/lib/blocks'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

/** 画布上真正渲染的可能比 BLOCK_ORDER 多（数据驱动的块），两边合起来才是全量 */
const allIds = computed(() => {
  const seen = new Set<string>()
  const out: string[] = []
  for (const id of [...session.blocksOrder, ...BLOCK_ORDER, ...session.layout.map((b) => b.id)]) {
    if (!seen.has(id)) {
      seen.add(id)
      out.push(id)
    }
  }
  return out
})

const labelOf = (id: string) =>
  BLOCK_LABELS[id] ?? session.layout.find((b) => b.id === id)?.label ?? id

/** 从后端策略里拿一句"这块是干什么的"；没有就不编 */
const hintOf = (id: string) => session.layout.find((b) => b.id === id)?.hint ?? ''

const isHidden = (id: string) => session.blocksHidden.includes(id)

/**
 * 面板说的每一句话，都以**画布上报的事实**为准（`session.canvasBlocks` / `canvasPresent`）。
 *
 * 面板曾经自己推：按"顺序前 N 个"猜哪些块在画布上。猜错的后果很具体 ——
 * 它把一块还没数据的块（没绑学信网时的「匹配与推荐」就是）标成「摆着」，
 * 用户点「放回」发现画面什么都没变：面板说的和看得见的事对不上。
 *
 * 现在只有三种状态，全部来自画布：
 *   · showing —— 此刻真的在画布上；
 *   · stored  —— 数据上存在、只是没摆出来（用户收的，或被核心区上限挡着）→ 可以「放回」；
 *   · waiting —— 它**自己的数据还没到**（课表等课表到位、匹配等学籍绑定）→
 *     此时"放回"是个空动作，所以不给这个按钮，只说明为什么还看不到它。
 */
type RowState = 'showing' | 'stored' | 'waiting'

const stateOf = (id: string): RowState => {
  if (isHidden(id)) return 'stored'
  if (session.canvasBlocks.includes(id)) return 'showing'
  return session.canvasPresent.includes(id) ? 'stored' : 'waiting'
}
const isOff = (id: string) => stateOf(id) !== 'showing'
const offCanvas = computed(() => allIds.value.filter((id) => stateOf(id) === 'stored').length)
const waiting = computed(() => allIds.value.filter((id) => stateOf(id) === 'waiting').length)

/**
 * 放回一块。
 *
 * **点"放回"就是"我要自己管"**：如果画布此前还是"没管过"的状态（只铺核心区），
 * 光把这块从收起名单里去掉是不够的 —— 它照样进不了核心区那八块。
 * 所以同时把当前这份顺序记下来（`blocksOrder` 非空即视为"用户管着"），
 * 核心区上限随之让位，这块就真的回来了。
 */
function restore(id: string) {
  const before = session.blocksHidden.length > 0 || session.blocksOrder.length > 0
  session.showBlock(id)
  if (!before) session.setBlocksOrder([...allIds.value])
}

/**
 * 上移/下移一位。
 *
 * 写回的是**用户那份顺序**（`blocksOrder`）：它是持久的，也是画布读取顺序时的第一顺位。
 * 那份顺序里原本可能没有这个块（比如课表这种数据驱动的块）——所以先把当前这份
 * "合起来看到的顺序"整份写下去，而不是在原数组里换位置（那样会把它挤丢）。
 */
function move(id: string, delta: number) {
  const list = [...allIds.value]
  const at = list.indexOf(id)
  const to = at + delta
  if (at < 0 || to < 0 || to >= list.length) return
  list.splice(at, 1)
  list.splice(to, 0, id)
  session.setBlocksOrder(list)
}
</script>

<template>
  <Overlay
    title="全部组件"
    :subtitle="
      [
        offCanvas ? `${offCanvas} 块收着` : `全部 ${allIds.length} 块都摆在外面`,
        waiting ? `${waiting} 块还没有数据` : '',
      ]
        .filter(Boolean)
        .join(' · ')
    "
    from="blocks"
    @close="session.closeOverlay()"
  >
    <p class="lead sheet">
      画布是你的桌面，不是一份必须全部摊开的东西。收起只是不摆出来 ——
      它一直在这里，随时放回去。收过或排过之后，画布就完全按你这份来。
    </p>

    <ul class="rows sheet">
      <li v-for="(id, index) in allIds" :key="id" :class="{ 'is-off': isOff(id) }">
        <span class="rows__n label">{{ index + 1 }}</span>
        <span class="rows__body">
          <span class="rows__name">{{ labelOf(id) }}</span>
          <span v-if="hintOf(id)" class="label rows__hint">{{ hintOf(id) }}</span>
        </span>

        <!--
          状态三种，都来自画布上报的事实。
          「还没有」这一类**不给动作**：它自己的数据没到，按「放回」也不会出现 —— 那是空动作，
          而空动作正是这个面板此前最让人不信的地方。
        -->
        <span class="label rows__state" :class="{ 'is-off': isOff(id) }">
          {{ stateOf(id) === 'showing' ? '摆着' : stateOf(id) === 'stored' ? '收着' : '还没有' }}
        </span>

        <span class="rows__acts">
          <button
            class="act"
            type="button"
            :disabled="index === 0"
            :aria-label="`把「${labelOf(id)}」上移一位`"
            title="上移一位"
            @click="move(id, -1)"
          >
            <GlyphIcon name="arrow-up" :size="12" />
          </button>
          <button
            class="act"
            type="button"
            :disabled="index === allIds.length - 1"
            :aria-label="`把「${labelOf(id)}」下移一位`"
            title="下移一位"
            @click="move(id, 1)"
          >
            <GlyphIcon name="arrow-down" :size="12" />
          </button>
          <button
            v-if="stateOf(id) === 'stored'"
            class="act act--main"
            type="button"
            @click="restore(id)"
          >
            放回
          </button>
          <button
            v-else-if="stateOf(id) === 'showing'"
            class="act"
            type="button"
            @click="session.hideBlockForGood(id)"
          >
            收起
          </button>
          <!-- 还没有：不给按钮，那句话在行尾说明它为什么还不出现 -->
          <span v-else class="label rows__wait">等它的数据</span>
        </span>
      </li>
    </ul>

    <footer class="foot">
      <span class="label foot__k">
        {{ offCanvas ? `还有 ${offCanvas} 块收着 —— 它们没丢，随时放回` : '现在全都摆在画布上' }}
      </span>
      <button class="label foot__b" type="button" :disabled="!offCanvas" @click="session.showAllBlocks()">
        全部放回
      </button>
      <button
        class="label foot__b"
        type="button"
        :disabled="!session.blocksOrder.length"
        title="回到后端策略给的顺序"
        @click="session.resetBlocksOrder()"
      >
        恢复默认顺序
      </button>
    </footer>
  </Overlay>
</template>

<style scoped>
.lead {
  padding: var(--s4) var(--s5);
  font-size: var(--fs-small);
  color: var(--ink-2);
  line-height: 1.75;
}

.rows { list-style: none; margin: 0; padding: var(--s2) var(--s3); display: grid; }
.rows li {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) 68px auto;
  align-items: center;
  gap: var(--s3);
  padding: var(--s2) var(--s2);
  border-top: 1px solid var(--line-1);
}
.rows li:first-child { border-top: 0; }
/* 收着的那几行淡一档：它们仍然可读，但不再争"现在这一屏"的注意力 */
.rows li.is-off { opacity: 0.72; }
.rows__n { color: var(--ink-3); }
.rows__body { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.rows__name { font-size: var(--fs-small); color: var(--ink-1); }
.rows__hint { color: var(--ink-3); }
.rows__state { color: var(--ink-3); }
.rows__state.is-off { color: var(--mk-orange); }
/* 「还没有」不是"被收起来了"，用中性的说明语气，别和"收着"共用同一个警示色 */
.rows__wait { color: var(--ink-3); }
.rows__acts { display: flex; align-items: center; gap: 6px; }

.act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  min-height: 26px;
  padding: 0 8px;
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  background: var(--n-1);
  font-size: var(--t-xs);
  transition: color var(--dur-micro) var(--ease-out), border-color var(--dur-micro) var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
.act:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
}
.act:disabled { opacity: 0.45; cursor: not-allowed; }
.act--main { color: var(--accent); border-color: var(--accent); }

/* 块被收起 / 放回这一下的反馈：不做动画，只把状态说清楚（这一屏是清单，不是画布） */
.foot { display: flex; align-items: center; gap: var(--s4); }
.foot__k { color: var(--ink-3); margin-right: auto; }
.foot__b { color: var(--accent); }
.foot__b:disabled { color: var(--ink-3); cursor: default; }
</style>
