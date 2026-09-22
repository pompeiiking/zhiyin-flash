<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import { useSessionStore } from '@/stores/session'
import {
  groupIntel,
  readFetched,
  readIntelText,
  readList,
  readShares,
  toneOfKind,
  type IntelField,
} from '@/lib/intel'
import type { IntelItem } from '@/api/client'

/**
 * 外部情报 —— 一次看一条。
 *
 * 【为什么是分页，不是一长条】这一层原来把所有条目排成一条竖着的长页：
 * 实测 7 条要滚三屏，而且第一屏就已经看不到"还有几条、走到哪了"。
 * 情报是**一条一条看**的东西（每条的原文都自成一页），所以改成一次一条：
 *
 *   · 顶部：这批是按什么取的、什么时候、共几条；
 *   · 中部：一条完整的情报（正文 / 字段 / 占比条 / 小签 / 来源）；
 *   · 底部：`← 上一条` `第 3 / 7 条` `下一条 →`，键盘左右键也能翻；
 *   · 左侧那一行类别（专业 3 · 职业 2 · 校友案例 2）点一下就跳到那一类的第一条。
 *
 * 三个动作都在这一条上：**拿去问主理**（把它带进对话，这是情报与 AI 之间
 * 用户看得见的那次交接）、**看它的依据**（原文 + 来源，走全站统一的溯源抽屉）、
 * **打开原页面**（回到它爬来的那一页）。
 *
 * 口径没变：不编（取不到就说取不到，并说清怎么才能取到）、来源可点、
 * 字段读不出来就原样留着 —— 一个字的正文都不新增。
 */
const session = useSessionStore()

const items = computed(() => session.intel?.items ?? [])
/** 按 专业 → 职业 → 校友案例 的顺序摊平：翻页顺序就是这条链的顺序 */
const groups = computed(() => groupIntel(items.value))
const flat = computed(() => groups.value.flatMap((g) => g.items))

const stamp = computed(() => readFetched(session.intel?.fetchedAt ?? ''))
/**
 * 这一批是按什么取的。
 *
 * 用户自己填过方向 → 说清是那个方向；没填 → 说"按你的画像"，
 * 并给出画像里那个专业名作为**提示**（提示，不是断言：真正用的是后端那条规则）。
 */
const asked = computed(() => session.intel?.topic?.trim() ?? '')
const askedLabel = computed(() =>
  asked.value ? `按「${asked.value}」取回` : '按你画像里的专业与方向取回',
)

/* ── 翻页 ─────────────────────────────────────────────────────────── */
const at = ref(0)
const current = computed<IntelItem | null>(() => flat.value[at.value] ?? null)
const total = computed(() => flat.value.length)
const kindOf = (item: IntelItem) => groups.value.find((g) => g.items.includes(item))?.label ?? ''

/** 每个类别从第几条开始 —— 类别那一行点一下就跳过去 */
const kindStarts = computed(() => {
  let cursor = 0
  return groups.value.map((g) => {
    const start = cursor
    cursor += g.items.length
    return { kind: g.kind, label: g.label, count: g.items.length, start }
  })
})

function go(next: number) {
  if (!total.value) return
  at.value = Math.max(0, Math.min(total.value - 1, next))
}

/** 键盘左右键翻页：一次看一条的东西，不该只能用鼠标翻 */
function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') go(at.value - 1)
  if (e.key === 'ArrowRight') go(at.value + 1)
}

/* ── 这一条怎么读 ─────────────────────────────────────────────────── */
const reading = computed(() =>
  current.value ? readIntelText(current.value.text ?? '', current.value.title ?? '') : null,
)

const shareRow = computed(() =>
  (reading.value?.fields ?? []).find((f) => /对口职业|相关职业/.test(f.label)) ?? null,
)
const shares = computed(() => (shareRow.value ? readShares(shareRow.value.value).slice(0, 6) : []))
const maxShare = computed(() => Math.max(...shares.value.map((s) => s.percent ?? 0), 1))

/**
 * 一长串名字才拆成小签。
 *
 * 顿号在原文里不一定是分隔符 —— "农、林、牧、渔业"是行业分类里的**一个**大类，
 * 拆开就成了四个小签，那是把正确的原文读错。所以条件收紧：
 * 段数 2–6、每段 ≤8 字，不满足就整句留着。
 */
const chipsOf = (field: IntelField): string[] => {
  if (!/[、,]/.test(field.value)) return []
  const parts = readList(field.value)
  if (parts.length < 2 || parts.length > 6) return []
  if (parts.some((p) => p.length > 8)) return []
  return parts
}

const isShareRow = (label: string) => /对口职业|相关职业/.test(label)
const plainFields = computed(() =>
  (reading.value?.fields ?? []).filter((f) => !isShareRow(f.label) && !chipsOf(f).length),
)
const chipFields = computed(() =>
  (reading.value?.fields ?? []).filter((f) => !isShareRow(f.label) && chipsOf(f).length),
)

/**
 * "拿去问主理"要问的那一句。
 *
 * 按类别写，因为三类情报能问出三件不同的事：专业问"先试哪个职业"、
 * 职业问"我现在差哪一条"、校友案例问"他第一步做了什么"。
 * 句子里带上标题的关键词，编排器这一轮才真的会为它去取数。
 */
function askText(item: IntelItem): string {
  const name = item.title || item.kind_label || '这条'
  if (item.kind === 'speciality') return `「${name}」这个专业对口的职业里，我先试哪个？`
  if (item.kind === 'occupation') return `「${name}」要求什么，我现在差哪一条？`
  if (item.kind === 'career_case' || item.kind === 'occucase') {
    return `「${name}」这样的人，第一步做了什么？`
  }
  return `「${name}」这条和我有什么关系？`
}

/* ── 方向与取数 ───────────────────────────────────────────────────── */
const draft = ref('')

/**
 * 空的时候给三个能点的方向。
 *
 * 为什么需要它：主题是从画像推的，而**新用户还没有画像** —— 于是第一次打开
 * 面板会是一条都没有。那不是"没数据"，那是"还差你一句话"。
 * 与其摆一句"没取到"，不如把"给他一个起点"这件事做成一次点击：
 * 点一下，八条带来源的公开事实立刻铺开，同时他也懂了——
 * 这个面板是**按方向**取东西的。
 *
 * 三个方向的选法：一个工科、一个商科、一个文科，覆盖面最广的那几类。
 * 不做成"热门搜索"：那是在替用户决定他关心什么。
 */
const STARTERS = ['计算机', '会计', '汉语言文学']

function fetchNow() {
  void session.loadIntel(true, draft.value.trim() || undefined)
  draft.value = ''
  at.value = 0
}

function startWith(topic: string) {
  draft.value = ''
  void session.loadIntel(true, topic)
  at.value = 0
}

onMounted(async () => {
  await session.loadIntel()
  await nextTick()
  /* 从对话里的引用跳进来时停在**那一条**上；否则从头开始 */
  const focus = session.intelFocus
  if (focus) {
    const hit = flat.value.findIndex((i) => i.id === focus)
    at.value = hit >= 0 ? hit : 0
    session.intelFocus = ''
  }
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Overlay
    title="外部情报"
    :subtitle="
      total
        ? `${total} 条 · ${askedLabel} · ${stamp}`
        : `正在${askedLabel.replace('取回', '找')}和你有关的公开信息`
    "
    from="market"
    size="wide"
    tone="fact"
    @close="session.closeOverlay()"
  >
    <div class="intel">
      <!-- 工具条：换方向 / 再取一次 -->
      <header class="tools">
        <label class="tools__topic">
          <span class="label">按这个方向去取</span>
          <input
            v-model="draft"
            type="text"
            :placeholder="asked || '填一个专业名，比如：计算机'"
            aria-label="按什么方向取外部情报"
            @keydown.enter="fetchNow"
          >
        </label>
        <button class="btn primary" type="button" :disabled="session.intelBusy" @click="fetchNow">
          {{ session.intelBusy ? '正在取…' : '现在去取一次' }}
        </button>
      </header>
      <!--
        主题从哪来，写在脸上：用户想换一批，就知道该去改画像，而不是反复点"去取一次"。
      -->
      <p v-if="!asked" class="label tools__from">
        主题来自你画像里的专业与方向 —— 补一条，下一批就跟着变。
      </p>

      <!-- 一条都没有：说清为什么，以及怎么才有 -->
      <section v-if="!total" class="empty">
        <h3 class="empty__t editorial">
          {{ session.intelBusy ? '正在去公开渠道找…' : '这次没取到和你方向相关的公开信息。' }}
        </h3>
        <p class="empty__d">
          它按你填的方向去学职平台这类公开页面读：专业对口的职业、这些职业要求什么、
          走过这条路的人后来怎么样。方向越具体，回来的东西越挨着 ——
          填一个专业名（比如"计算机"）就能试。
        </p>
        <p v-if="session.intelError" class="label empty__err">{{ session.intelError }}</p>

        <!-- 没有方向时，给他一个起点：点一下就有东西看，而不是一句"没取到" -->
        <div v-if="!session.intelBusy" class="empty__starters">
          <span class="label">手边还没想好查什么？先点一个</span>
          <ul>
            <li v-for="t in STARTERS" :key="t">
              <button type="button" @click="startWith(t)">{{ t }}</button>
            </li>
          </ul>
        </div>
      </section>

      <template v-else-if="current">
        <!-- 类别：一条链的顺序。点一下跳到那一类的第一条 -->
        <nav class="kinds" aria-label="按类别跳">
          <button
            v-for="k in kindStarts"
            :key="k.kind"
            class="kind"
            type="button"
            :class="{ 'kind--on': k.kind === current.kind }"
            :style="{ '--kind': toneOfKind(k.kind) }"
            @click="go(k.start)"
          >
            {{ k.label }} <b>{{ k.count }}</b>
          </button>
          <span class="rule" />
          <span class="label kinds__at">第 {{ at + 1 }} / {{ total }} 条</span>
        </nav>

        <!-- 一条情报的全文。翻页时整块换掉，不做长滚动 -->
        <article :key="current.id" class="card">
          <header class="card__head">
            <span class="card__kind" :style="{ '--kind': toneOfKind(current.kind) }">
              {{ kindOf(current) }}
            </span>
            <h3 class="card__t">{{ current.title || kindOf(current) }}</h3>
          </header>

          <p v-if="reading?.intro" class="card__intro">{{ reading.intro }}</p>

          <dl v-if="plainFields.length" class="facts">
            <div v-for="field in plainFields" :key="field.label" class="facts__row">
              <dt class="label">{{ field.label }}</dt>
              <dd>{{ field.value }}</dd>
            </div>
          </dl>

          <!-- 对口职业：原文里唯一自带数字的一段，画成条 -->
          <div v-if="shares.length" class="shares">
            <span class="label shares__k">{{ shareRow?.label }}</span>
            <ul>
              <li v-for="share in shares" :key="share.name">
                <span class="shares__n">{{ share.name }}</span>
                <span class="shares__track">
                  <i
                    :style="{
                      width: `${Math.max(6, ((share.percent ?? 0) / maxShare) * 100)}%`,
                      background: toneOfKind(current.kind),
                    }"
                  />
                </span>
                <span class="mono shares__p">
                  {{ share.percent === null ? '—' : share.percent + '%' }}
                </span>
              </li>
            </ul>
          </div>

          <div v-for="field in chipFields" :key="field.label" class="chips">
            <span class="label">{{ field.label }}</span>
            <ul>
              <li v-for="name in chipsOf(field)" :key="name">{{ name }}</li>
            </ul>
          </div>

          <p v-for="(line, i) in reading?.loose ?? []" :key="i" class="card__loose">{{ line }}</p>

          <footer class="card__foot">
            <span class="label card__src">{{ current.source_name || '公开渠道' }}</span>
            <span class="label card__at">{{ readFetched(current.fetched_at ?? '') }}</span>
            <button class="card__why label" type="button" @click="session.openIntelItem(current)">
              看它的依据
            </button>
            <a
              v-if="current.source_url"
              class="card__link"
              :href="current.source_url"
              target="_blank"
              rel="noopener noreferrer"
            >
              打开原页面 ↗
            </a>
          </footer>
        </article>

        <!-- 翻页 + 把这一条交给 AI -->
        <footer class="pager">
          <button class="pg" type="button" :disabled="at === 0" @click="go(at - 1)">
            ← 上一条
          </button>

          <button class="ask" type="button" @click="session.askAboutIntel(askText(current))">
            拿这条去问主理
          </button>

          <button class="pg" type="button" :disabled="at >= total - 1" @click="go(at + 1)">
            下一条 →
          </button>
        </footer>
      </template>
    </div>
  </Overlay>
</template>

<style scoped>
/*
 * 这一页是**一张纸**。条目之间不再各套一个盒子 —— 一次只显示一条，
 * 盒子的边界反而会让人以为"下面还有"。
 */
.intel {
  /*
   * 四行固定：工具条 / 类别 / **这一条** / 翻页。
   *
   * 中间那一行是 `minmax(0, 1fr)` 且自己滚 —— 这样"翻页"永远在纸上待着。
   * 上一版让整块一起长，长条目（会计学的简介四百字）会把翻页顶到视野外面，
   * 于是"用按钮翻，不要长页"这件事在最需要它的那一条上恰好失效。
   */
  display: grid; gap: var(--s4);
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  flex: 1 1 auto;
  min-height: 0;
  padding: var(--s5);
  background: var(--c-paper);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--e-4), var(--inner-hi);
}

/* ── 工具条 ─────────────────────────────────────────────────────── */
.tools { display: flex; align-items: flex-end; gap: var(--s3); }
.tools__topic { display: grid; gap: 4px; flex: 1; min-width: 0; }
.tools__topic input {
  height: 38px; padding: 0 var(--s4);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-sm);
  background: var(--n-1); color: var(--ink-1);
  font-size: var(--t-sm);
  transition: border-color var(--dur-micro) var(--ease-out);
}
.tools__topic input:hover { border-color: var(--line-3); }
.tools__topic input:focus-visible { outline: none; border-color: var(--accent); }
.tools__from { margin-top: calc(var(--s2) * -1); color: var(--ink-3); }

/* ── 空态 ───────────────────────────────────────────────────────── */
.empty { display: grid; gap: var(--s2); }
.empty__t { font-size: var(--t-h3); }
.empty__d { font-size: var(--t-sm); color: var(--ink-2); line-height: 1.8; max-width: 62ch; }
.empty__err { color: var(--warn); }
.empty__starters { display: grid; gap: var(--s2); margin-top: var(--s2); }
.empty__starters ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--s2); }
.empty__starters button {
  min-height: 34px; padding: 6px 14px;
  border: var(--bw) solid var(--line-3); border-radius: var(--r-pill);
  background: var(--n-1); color: var(--ink-1);
  font-family: var(--font-editorial); font-size: var(--t-h4); line-height: 1.25;
  transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.empty__starters button:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

/* ── 类别跳转 ───────────────────────────────────────────────────── */
.kinds { display: flex; align-items: center; gap: var(--s2); }
.kind {
  display: inline-flex; align-items: baseline; gap: 5px;
  padding: 4px 10px 4px 9px;
  border-left: 3px solid var(--kind, var(--accent));
  border-radius: 0 var(--r-pill) var(--r-pill) 0;
  font-family: var(--font-editorial);
  font-size: var(--t-h4);
  color: var(--ink-2);
  transition: background var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out);
}
.kind:hover { background: var(--fill-hover); color: var(--ink-1); }
.kind--on { background: var(--fill-subtle); color: var(--ink-1); }
.kind b { font-family: var(--font-sans); font-size: var(--t-xs); font-weight: 500; color: var(--ink-3); }
.rule { flex: 1; height: 1px; background: var(--line-1); }
.kinds__at { color: var(--ink-3); white-space: nowrap; }

/* ── 这一条 ─────────────────────────────────────────────────────── */
.card {
  display: grid; gap: var(--s3);
  align-content: start;
  min-height: 0; overflow-y: auto;
  animation: page-in 260ms var(--ease-out) both;
}
@keyframes page-in {
  from { opacity: 0; transform: translateX(8px); }
  to { opacity: 1; transform: none; }
}
.card__head { display: flex; align-items: baseline; gap: var(--s3); }
.card__kind {
  flex: 0 0 auto;
  padding-left: 8px;
  border-left: 3px solid var(--kind, var(--accent));
  font-size: var(--t-xs); color: var(--ink-3);
}
.card__t { font-size: var(--t-h2); line-height: 1.35; }

/*
 * 正文：一次只显示一条，所以给足五行；再长就点"看它的依据"读全文。
 * 用确切行高（1.8 × 5）而不是 line-clamp —— 后者在 grid 子项上实测不稳。
 */
.card__intro {
  font-size: var(--t-body); color: var(--ink-2); line-height: 1.8;
  max-height: calc(1.8em * 5);
  overflow: hidden;
}

.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: var(--s2) var(--s4); margin: 0; }
.facts__row { display: grid; gap: 1px; }
.facts dt { color: var(--ink-3); }
.facts dd { margin: 0; font-size: var(--fs-small); color: var(--ink-1); font-variant-numeric: tabular-nums; line-height: 1.7; }

.shares { display: grid; gap: 6px; }
.shares__k { color: var(--ink-3); }
.shares ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; }
.shares li { display: grid; grid-template-columns: minmax(0, 220px) minmax(60px, 1fr) 42px; align-items: center; gap: var(--s3); }
.shares__n { font-size: var(--fs-small); color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shares__track { height: 7px; border-radius: 4px; background: var(--line-1); overflow: hidden; }
.shares__track i { display: block; height: 100%; border-radius: 4px; }
.shares__p { color: var(--ink-3); text-align: right; }

.chips { display: grid; gap: 5px; }
.chips ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 5px; }
.chips li {
  padding: 2px 9px; border-radius: var(--r-pill);
  border: 1px solid var(--line-1); background: var(--fill-subtle);
  font-size: var(--fs-label); color: var(--ink-2);
}

.card__loose { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7; }

.card__foot {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--s2);
  margin-top: var(--s1); padding-top: var(--s2);
  border-top: 1px solid var(--line-1);
}
.card__src { color: var(--ink-2); }
.card__at { color: var(--ink-3); }
.card__why { margin-left: auto; color: var(--ink-3); text-decoration: underline; text-underline-offset: 3px; }
.card__why:hover { color: var(--accent); }
.card__link { font-size: var(--fs-small); color: var(--accent); font-weight: 500; }
.card__link:hover { text-decoration: underline; text-underline-offset: 3px; }

/* ── 翻页 ───────────────────────────────────────────────────────── */
.pager {
  display: flex; align-items: center; gap: var(--s2);
  flex-wrap: wrap;
  padding-top: var(--s3);
  border-top: 1px solid var(--line-1);
}
.pg {
  min-height: 36px; padding: 6px var(--s4);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-sm);
  background: var(--n-1); color: var(--ink-2); font-size: var(--t-sm); line-height: 1.25;
  transition: border-color var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out);
}
.pg:hover:not(:disabled) { border-color: var(--ink-1); color: var(--ink-1); }
.pg:disabled { opacity: 0.4; cursor: not-allowed; }
/* 中间那颗是这一页最该被点的：把这条交给 AI */
.ask {
  flex: 1; min-height: 36px; padding: 6px var(--s4);
  border: var(--bw) solid var(--accent); border-radius: var(--r-sm);
  background: var(--accent); color: var(--accent-ink);
  font-family: var(--font-editorial); font-size: var(--t-h4); line-height: 1.25;
  transition: background var(--dur-micro) var(--ease-out);
}
.ask:hover { background: var(--accent-deep); }
.pager::after {
  content: "左右方向键也能翻";
  width: 100%; text-align: right;
  font-family: var(--font-sans); font-size: var(--t-xs); color: var(--ink-4);
}

@media (max-width: 900px) {
  .tools { flex-direction: column; align-items: stretch; }
  .kinds { flex-wrap: wrap; }
  .shares li { grid-template-columns: minmax(0, 1fr) 60px 42px; }
}
</style>
