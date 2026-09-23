<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import gsap from 'gsap'
import { useEscLayer } from '@/composables/useEscLayer'

/**
 * 打开一个模块时的呈现方式。
 *
 * 【这一稿：一页摊在桌面上的稿纸】
 *
 * 前几稿的问题出在**高度**上：舞台写死 760px，而内容（尤其空状态）只有两三百
 * 像素高 —— 于是打开画像面板看到的是一大块白板中间孤零零一小条，
 * 用户的判词是"灾难"。高度写死的另一面是：内容比它高的时候又被裁掉。
 *
 * 这一稿改两件事：
 *   1. **高度跟着内容走**（`height: auto` + `max-height`）。内容少，
 *      纸就小；内容多，纸长到上限之后内部滚动。图纸永远不比内容高出一大截。
 *   2. **开页签**。标题条左侧是一条 6px 的**色带**（模块色），整条轻微倾斜 ——
 *      像一本稿纸侧面贴的标签。哪一页是哪个模块，不看字也认得出。
 *
 * 其余不动：从来源气泡长出来（位置关系读得懂"这块是被点开的"）、
 * 遮罩不让页面消失、关闭时反向收回。遮罩改成**平的**：不做径向渐变光晕 ——
 * 那圈绿光正是"发浑"的来源之一。
 */
const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    /** 来源气泡的 data-block，用来做"从这里长出来" */
    from?: string
    tone?: 'accent' | 'fact' | 'plain'
    /**
     * wide 是控制台里那种大舞台；mid 给内容更少的详情（门户的卡）；
     * tall 给"左边一列清单 + 右边一段长文"这种两栏页（画像）——
     * 它比 wide 只高 40px，但正是那 40px 让两栏在 1440×900 上不用内部滚动。
     */
    size?: 'wide' | 'mid' | 'tall'
  }>(),
  { subtitle: '', from: '', tone: 'accent', size: 'wide' }
)

const emit = defineEmits<{ (e: 'close'): void }>()

const stage = ref<HTMLElement | null>(null)
const scrim = ref<HTMLElement | null>(null)
let closed = false
/** 打开前焦点在哪儿，关掉之后还回去 —— 键盘用户不该被丢在页面顶部 */
let restoreFocus: HTMLElement | null = null

const reduced = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const sourceEl = () =>
  props.from ? document.querySelector<HTMLElement>(`[data-block="${props.from}"]`) : null

/** 把舞台映射到来源气泡的那块矩形上，作为动画的起点 */
function originTransform() {
  const el = stage.value
  const src = sourceEl()
  if (!el || !src) return null
  const s = src.getBoundingClientRect()
  const p = el.getBoundingClientRect()
  if (!p.width || !p.height) return null
  // 等比缩放（非等比会把里面的文字拉变形），再平移到气泡中心
  const scale = Math.max(0.24, Math.min(s.width / p.width, s.height / p.height))
  return {
    x: s.left + s.width / 2 - (p.left + p.width / 2),
    y: s.top + s.height / 2 - (p.top + p.height / 2),
    scale,
  }
}

/** 在来源气泡的位置点一盏很淡的灯，交代"从这儿打开的" */
function markOrigin() {
  const src = sourceEl()
  if (!src || !scrim.value) return
  const r = src.getBoundingClientRect()
  scrim.value.style.setProperty('--ox', `${r.left + r.width / 2}px`)
  scrim.value.style.setProperty('--oy', `${r.top + r.height / 2}px`)
}

onMounted(() => {
  restoreFocus = document.activeElement as HTMLElement | null
  markOrigin()
  stage.value?.focus({ preventScroll: true })

  if (reduced()) return
  const el = stage.value
  const origin = originTransform()

  if (scrim.value) {
    gsap.fromTo(scrim.value, { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'power2.out' })
    /* 同上：遮罩也不能留在中间态，否则底下的画布一直是亮的（见下面的兜底说明） */
    settle(scrim.value, 700, 'opacity')
  }
  if (!el) return

  if (origin) {
    /*
     * 注意这里**不动 filter**。
     * 原来是 from blur(14px) → blur(0)，等于让这张 1180×760 的面板每一帧重做一次
     * 全尺寸模糊，持续 0.64 秒 —— 打开浮层那种"慢、卡"的感觉就是这么来的。
     * 位移 + 缩放 + 透明度已经足够表达"从气泡里长出来"。
     */
    gsap.fromTo(
      el,
      { ...origin, opacity: 0.3 },
      {
        x: 0, y: 0, scale: 1, opacity: 1,
        duration: 0.64,
        ease: 'expo.out',
        onComplete: () => settle(el, 0, 'transform,opacity'),
      }
    )
    settle(el, 900, 'transform,opacity')
  } else {
    // 找不到来源（例如从别的入口打开）时退化成缩放淡入
    gsap.fromTo(
      el,
      { opacity: 0, scale: 0.965 },
      {
        opacity: 1, scale: 1,
        duration: 0.52, ease: 'expo.out',
        onComplete: () => settle(el, 0, 'transform,opacity'),
      }
    )
    settle(el, 800, 'transform,opacity')
  }
})

/**
 * 到点强制落到终态 —— **打开的动画不许有"中间态"**。
 *
 * 这条是踩出来的。动画由 gsap 的时针（requestAnimationFrame）驱动，而时针会被
 * 系统压住：后台标签页、省电模式、还有截屏工具把页面挂起的那一瞬。被压住的
 * 时候，面板就停在"半透明 + 缩小一半 + 偏到气泡那一角"的样子 ——
 * 用户看到的是**浮层的内容和底下的画布叠在一起**，两块字互相压着，
 * 读起来像整个页面坏了（用户就是这么报的：截图里浮层是"幽灵"状态）。
 *
 * 所以除了 onComplete，再挂一条定时兜底：真到点了就直接写终态、
 * 把内联的 transform/opacity 清掉。慢一点没关系，"最终一定对"不能让位给动画。
 */
function settle(el: HTMLElement, after: number, props: string) {
  const done = () => {
    if (!el.isConnected) return
    gsap.killTweensOf(el)
    gsap.set(el, { clearProps: props })
  }
  if (after <= 0) return done()
  window.setTimeout(done, after)
}

/** 关：先收回来源气泡，再卸载 */
function requestClose() {
  if (closed) return
  closed = true
  const el = stage.value
  const origin = reduced() ? null : originTransform()

  if (!el || !origin) {
    emit('close')
    return
  }
  if (scrim.value) gsap.to(scrim.value, { opacity: 0, duration: 0.26, ease: 'power2.in' })
  /*
   * 关闭也要有兜底：跟打开同一个道理 —— 时针被压住时，这段 0.32 秒的收场
   * 会永远停在第一帧，面板赖着不走、点"关闭"像没反应。
   * 到点无论如何都卸掉它（emit 之后组件就没了）。
   */
  let closedOut = false
  const finish = () => {
    if (closedOut) return
    closedOut = true
    emit('close')
  }
  window.setTimeout(finish, 520)
  gsap.to(el, {
    ...origin,
    opacity: 0.18,
    duration: 0.32,
    ease: 'power2.in',
    onComplete: finish,
  })
}

// Esc 归最上面那一层：如果抽屉开着，Esc 先关抽屉，这一层等着接手
useEscLayer(requestClose)

onBeforeUnmount(() => {
  if (stage.value) gsap.killTweensOf(stage.value)
  if (scrim.value) gsap.killTweensOf(scrim.value)
  /*
   * 焦点还给谁：优先还给打开它之前那个元素。
   * 但画布上的块是 drag 的，pointerdown 被 preventDefault 之后浏览器根本不会把焦点给它，
   * 所以 activeElement 常常是 body —— 这时退回到"来源气泡"本身，
   * 语义上正好也更对：从哪一块打开的就回到哪一块。
   */
  const back = restoreFocus && restoreFocus !== document.body ? restoreFocus : sourceEl()
  back?.focus?.({ preventScroll: true })
})
</script>

<template>
  <div class="layer" role="dialog" aria-modal="true" :aria-label="props.title">
    <button ref="scrim" class="layer__scrim" type="button" aria-label="关闭" @click="requestClose" />

    <div
      ref="stage"
      class="deck"
      :class="[`tone-${props.tone}`, `deck--${props.size}`]"
      tabindex="-1"
    >
      <!-- 开页签：一条色带 + 模块名。它和下面的内容之间有 16px 空气 -->
      <header class="deck__bar sheet">
        <div class="deck__titles">
          <span class="label">{{ props.subtitle }}</span>
          <h2 class="deck__title">{{ props.title }}</h2>
        </div>
        <button class="btn ghost deck__close" type="button" @click="requestClose">
          关闭
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="currentColor" stroke-width="1.4"
                  stroke-linecap="round" />
          </svg>
        </button>
      </header>

      <div class="deck__grid"><slot /></div>
    </div>
  </div>
</template>

<style scoped>
.layer {
  position: fixed; inset: 0; z-index: var(--z-overlay);
  display: grid; place-items: center;
  padding: var(--s6);
}

/*
 * 遮罩：一层平的墨，不是黑场。
 *
 * 之前这里是两个径向渐变（一圈绿光 + 一圈暗角）。绿光那圈是"色系发浑"
 * 的一部分：它把底下的界面染成一件说不清颜色的东西。现在只压一层中性墨，
 * 页面还在，但退到后面去了。
 */
.layer__scrim {
  position: absolute; inset: 0;
  background: rgba(18, 17, 14, 0.44);
}

/*
 * 舞台：**高度由内容决定**。
 *
 * 这是这一稿唯一的结构性改动，也是"打开以后是一大片空白"的正面解法：
 * 写死高度意味着图纸永远比内容大，空状态看起来就是"没画完的一屏"。
 *
 * 限高仍然要有（长内容不能把浮层顶出屏幕），超过之后由 .deck__grid 内部滚动。
 */
.deck {
  position: relative;
  width: min(1180px, 100%);
  height: auto;
  max-height: min(820px, 100%);
  /* 网格项的 min-height 默认是 auto：内容更高时它会顶破容器，把整层撑出屏幕。
     这里明确归零，高度由内容说了算，内部该滚的地方自己滚。 */
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: var(--s4);
  outline: none;          /* 焦点落在这里，但不要画出焦点框 */
  will-change: transform, opacity;
}
.deck--mid { width: min(760px, 100%); max-height: min(680px, 100%); }
.deck--tall { max-height: min(860px, 100%); }

/*
 * 开页签。
 *
 * 左侧那条 6px 的色带是**模块色**（--deck-ink，由 tone / size 定），
 * 整条轻微倾斜 0.25 度 —— 一页稿纸侧面贴的标签不会是水平贴的。
 */
.deck__bar {
  display: flex; align-items: center; gap: var(--s3);
  padding: 10px var(--s3) 10px var(--s4);
  border-left: 6px solid var(--deck-ink, var(--accent));
  border-radius: var(--r-md);
  transform: rotate(-0.25deg);
  animation: sheet-in 460ms var(--ease-expo) both;
}
/* 模块色：accent（默认蓝）· fact（事实蓝）· plain（墨） */
.tone-accent { --deck-ink: var(--accent); }
.tone-fact { --deck-ink: var(--fact); }
.tone-plain { --deck-ink: var(--ink-1); }

.deck__titles { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.deck__title { font-size: var(--t-h2); letter-spacing: 0; }
/*
 * 右边只剩一个"关闭"。
 *
 * 这里原来还有一句「Esc 收起」。它整条拿掉，理由有两层：
 *   · 它是**说明我们怎么实现的**，不是给用户的动作 —— 一页浮层上写键盘键名，
 *     对不用键盘的人是一行看不懂的字，对用键盘的人是多看一句；
 *   · Esc 本身照旧生效（见 useEscLayer），只是不再写在脸上。
 * 关闭键改为自己顶到最右（原来靠那句提示语的 margin-left:auto 把它推过去）。
 */
.deck__close { margin-left: auto; }

/*
 * ⚠️ 这一格**没有底色**，它是透明的舞台。
 *
 * 这里曾经补过一层奶油纸 + 描边 + 圆角（因为当时有四个浮层的内容直接铺在这一格上，
 * 字压在遮罩的暗底上读不清）。代价是：打开任何一个模块，看到的是
 * "一条顶栏 + 一整块纯色大板" —— 板上再摆几张卡，就成了"板子套板子"。
 *
 * 现在改回**浮空的薄片**：纸感交给每个模块自己的 `.sheet`（见 base.css），
 * 这一格只负责排布与滚动。所以那四个直接把内容铺在这儿的浮层
 * （今日简报 / 匹配与推荐 / 本周课表 / 绑定）各自补上了薄片 —— 见它们自己的注释。
 */
.deck__grid {
  min-height: 0; position: relative;
  /*
   * ⚠️ 这一格同时要满足两件事，缺一件就会把内容**裁在外面**：
   *
   *   1. 让它成为 flex 容器 —— 插进来的浮层根节点（如 `.bind`）写的是
   *      `flex: 1; min-height: 0; overflow: auto`，那三个属性只有在 flex 父节点里
   *      才成立。此前这里是普通块级元素，于是那些属性全部失效，内容按自身高度
   *      （实测 723px）撑开，被外层的 overflow 裁掉 —— 用户看到的就是
   *      "写着贴到下面，但下面什么都没有"，而且没有滚动条，怎么找都找不到。
   *   2. `overflow: auto` 作为兜底：万一某个浮层没写自己的滚动，内容依然可达。
   */
  display: flex;
  flex-direction: column;
  overflow: auto;
}

@media (max-width: 900px) {
  .layer { padding: var(--s4); }
  .deck { max-height: min(820px, 100%); }
}
/*
 * 手机上不再把它当"一屏浮层"，而是当一页内容：
 * 高度交给内容，滚动交给这一层 —— 手机上不该出现两个各自滚动的小窗口。
 */
@media (max-width: 700px) {
  .layer { padding: var(--s2); align-items: start; overflow: auto; }
  .deck { height: auto; }
  .deck__bar { padding: var(--s2) var(--s2) var(--s2) var(--s4); }
}
</style>
