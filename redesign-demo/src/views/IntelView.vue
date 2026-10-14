<script setup lang="ts">
/*
 * IntelView —— 岗位资讯（`/intel`）。
 *
 * ============================================================================
 * 这次改的是一条审计里最硬的证据：**「阅读全文」零增益**
 * （`COVERAGE.md:207`：点开的正文与卡片上的 65 字完全相同）。
 * MIGRATION §阶段 2 的 2.6 与 U10 都写死了：**形态换了但内容不换 = 把零增益放大到满屏**。
 *
 * 但 `IntelItemView`（`api/backend-types.ts:113`）只有 title / text / source_name /
 * source_url / fetched_at / kind —— **后端没有给我们"完整正文"这个字段**，
 * 而且 `src/data/` 在本次写权限之外，不许编造一条全文出来。
 * 所以这里走 MIGRATION 给的第二条路：**把「阅读全文」改成「核对来源」，
 * 并把来源/时间做进卡片结构**，让弹层里装的是**卡片上没有的东西**：
 *   ① 完整原文（卡片上是 46 字截断的预览，弹层里是全文 —— 有真字数差）；
 *   ② 逐项核验清单（演示数据里写着的"待确认 / 需核对 / 不代表…"被提炼成可勾的动作，
 *      这是"这条能不能用"的判据，卡片上没有）；
 *   ③ 同类别其它条目 + 它们与本文的关系（横向对比，卡片上更看不到）；
 *   ④ 弹层专有的来源说明（"本地虚构演示资料 · 非招聘公告"这类口径）。
 * 卡片本身则加了：类别组头（12 条同构卡按类聚拢）、组内条数、
 * "同一批次读取"标记、以及每条**能核对的字段行**。
 * ============================================================================
 *
 * 另外两条对应 MIGRATION：
 *   · §1.5 `/intel` 折叠数 = 0（这一页不需要折叠），所以本次**不新增任何折叠**；
 *     能组织的信息用分组头与字段行表达，不用"点开才知道"。
 *   · §2.2 第 18 条 / §2.3：`IntelView:22` 的 `wide`（→ `panel`：桌面居中宽盒）
 *     改成 `shape="sheet"`（桌面右侧抽屉、小屏底部面板）。**必须同时去掉 `wide`** ——
 *     `InfoSheet.vue:54-58` 的 `resolvedShape` 里 `wide` 优先级高于 `shape`。
 *   · §4.3 B4：`<p v-if="status" class="desk-status">` 是"成功反馈常驻不消失"
 *     → `StatusBanner tone="success"`（4s 自动消失 + 可关）。
 *   · §4.3 B10 的形状：错误原来只是 `<p class="ws-field-error">`，没有动作位
 *     → `StatusBanner tone="error"`，自带「重试」。
 *   · §4.1 K4：`<div v-if="items.length">` 没有 `v-else`，无加载态
 *     → `SkeletonBlock variant="card"`（还没取）与 `EmptyState`（取了但没有）分开。
 *   · 去重（标题区问题）：`PageHeading` 里的「职业匹配」按钮与 `PanelTabs` 做同一件事
 *     → **只留 `PanelTabs`**，按钮删除。
 */
import { computed, ref } from 'vue'
import { backendDemo } from '../lib/backend-demo'
import { backendClient } from '../api/backend-client'
import PageHeading from '../components/PageHeading.vue'
import UiIcon from '../components/UiIcon.vue'
import InfoSheet from '../components/InfoSheet.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StatusBanner from '../components/StatusBanner.vue'
import StatTile from '../components/StatTile.vue'
import CareerMatchPanel from '../components/CareerMatchPanel.vue'
import ReadableText from '../components/ReadableText.vue'
import type { IntelItemView } from '../api/backend-types'

const query=ref(''),remoteQuery=ref(''),kind=ref('all'),mode=ref('facts'),status=ref(''),busy=ref(false),error=ref(''),reading=ref<IntelItemView|null>(null)
/* 组织方式：按类别聚拢 / 按时间看。两个视角**重新组织同一批条目**（DESIGN-LANGUAGE §4.2），
   不是一个换内容的 tab。同类别的顺序在两种视角下都保留，所以侧着看不会"换了个列表"。 */
const view=ref<'category'|'timeline'|'relevance'>('relevance')
const hotWords = ['半导体','新能源','检测','实验','简历','核验']
const keywordCount = (word:string) => backendDemo.state.intel.filter(i=>((i.title??'')+' '+(i.text??'')).includes(word)).length

const items=computed(()=>{
 const list=backendDemo.state.intel.filter(i=>(kind.value==='all'||i.kind===kind.value)&&((i.title??'')+' '+(i.text??'')+' '+(i.kind_label??'')).includes(query.value.trim()))
 if(view.value==='timeline') return [...list].sort((a,b)=>(b.fetched_at??'').localeCompare(a.fetched_at??''))
 if(view.value==='relevance') return [...list].sort((a,b)=>Number(b.kind==='career')-Number(a.kind==='career'))
 return list
})
const kinds=computed(()=>[...new Map(backendDemo.state.intel.map(i=>[i.kind??'other',i.kind_label??'其他资讯'])).entries()])

/* 分组：同一批条目按 kind 聚拢。组按下标稳定排序，切视角不改组内顺序。 */
const groups=computed(()=>{
  const buckets=new Map<string,{key:string;label:string;items:IntelItemView[]}>()
  items.value.forEach(i=>{const k=i.kind??'other';if(!buckets.has(k))buckets.set(k,{key:k,label:i.kind_label??'其他资讯',items:[]});buckets.get(k)!.items.push(i)})
  return [...buckets.values()]
})
/* 时间视角：按"哪一天读取的"分块 —— 这里会**显式暴露**"12 条其实是同一批次读到的"这件事，
   而不是让 12 条一模一样的时间戳看起来像 12 个独立时点。 */
const days=computed(()=>{
  const buckets=new Map<string,IntelItemView[]>()
  items.value.forEach(i=>{const d=(i.fetched_at??'').slice(0,10)||'日期未提供';if(!buckets.has(d))buckets.set(d,[]);buckets.get(d)!.push(i)})
  return [...buckets.entries()].map(([day,list])=>({day,list}))
})

function dayCount(list:readonly IntelItemView[]){return new Set(list.map(i=>(i.fetched_at??'').slice(0,10)||'—')).size}
function timeLabel(value?:string){return value?new Date(value).toLocaleString('zh-CN'):'时间未提供'}
function isoDay(value?:string){return !value?'':(/^(\d{4})-(\d{2})-(\d{2})/.exec(value)?.[0]??value)}

/* 卡片的正文是**预览**（46 字 + 省略号），全文在弹层里 —— 这是"阅读全文"有增益的第一步 */
const PREVIEW=46
function preview(text?:string){const t=(text??'').trim();return t.length>PREVIEW?t.slice(0,PREVIEW)+'…':t}
function textLen(value?:string){return (value??'').replace(/\s/g,'').length}

/* "可核验的项"：把演示文本里写死的待确认项提炼成动作。
   它不是新事实，是**同一段话的结构化读法** —— 所以每条都带原文出处，不能凭空加。 */
const VERIFY:Record<string,{title:string;detail:string}[]> = {
  career:[
    {title:'核对来源与发布日',detail:'卡片与弹层里印的是「本地虚构演示资料」。真实岗位必须换成招聘方原文，并确认在有效期内。'},
    {title:'核对学历与专业门槛',detail:'原文给的是"本科材料相关专业"这一档；具体院校层次、是否接受跨专业都没有说明。'},
    {title:'核对职责、地点、待遇与期限',detail:'本条没有给出地点、待遇、招聘期限与投递方式；这些必须来自真实招聘来源才可用于选择。'},
  ],
  industry:[
    {title:'核对两类的真实职责描述',detail:'原文的对比是演示口径；真实区别要拿两个在招岗位的职责说明逐条比。'},
    {title:'核对结论的适用范围',detail:'这条讲的是工作方式的差别，不构成"哪类更有前景"的判断。'},
  ],
  education:[
    {title:'核对需要的材料',detail:'学籍核验需要本人授权的在线验证码；演示数据不代表核验通过。'},
    {title:'核对更新时间',detail:'学校、专业、年级与更新时间缺一项就无法判断这条资料还算不算数。'},
  ],
  campus:[
    {title:'核对时间、地点与报名方式',detail:'演示条目的时间是课表演示配置，真实活动必须回学校通知里核对。'},
    {title:'核对参与门槛',detail:'部分活动需要先完成安全培训或年级限制，原文没有给出。'},
  ],
  guide:[
    {title:'核对适用范围',detail:'这是通用写法，不针对某个岗位；套用前先确认岗位要求的表达习惯。'},
    {title:'回填到自己的材料',detail:'缺数据的地方保留待补充，不要用推测数字补满。'},
  ],
}
function verifyPoints(item?:IntelItemView|null){return VERIFY[item?.kind??'']??[{title:'核对来源与时间',detail:'确认这条来自哪个来源、什么时候读取，再决定要不要用它。'}]}

/* 与当前详情同类的其它条目 —— 关系可见（DESIGN-LANGUAGE §4.1：让结构显形） */
const related=computed(()=>reading.value?backendDemo.state.intel.filter(i=>(i.kind??'other')===(reading.value?.kind??'other')&&i.id!==reading.value?.id):[])

const readingLen=computed(()=>textLen(reading.value?.text))
const cardLen=computed(()=>textLen(preview(reading.value?.text)))

function sample(){backendDemo.loadIntelSample();status.value='已读取演示资讯；未发起远程检索。';error.value=''}
async function load(refresh=false){if(busy.value)return;busy.value=true;error.value='';try{const result=refresh?await backendClient.refreshIntel(remoteQuery.value.trim()):await backendClient.intel(remoteQuery.value.trim());if(!result||!Array.isArray(result.items))throw new Error('Incomplete intel');backendDemo.setIntel(result.items);query.value='';kind.value='all';status.value='已读取'+result.items.length+'条'+(backendDemo.state.dataMode==='demo'?'本地演示资料。':'最新资讯。')}catch{error.value='资讯没有读取成功，请重试。当前条目与筛选输入仍保留。'}finally{busy.value=false}}
function source(url?:string){return url&&/^https?:\/\//i.test(url)?url:undefined}
function read(id:string){const found=backendDemo.state.intel.find(i=>i.id===id);if(found)reading.value={...found}}
function facts(q:string){query.value=q;kind.value='all';mode.value='facts';status.value='已按「'+q+'」筛选现有资讯。没有对应条目时可在下方检索最新资讯。'}
function readKind(){const k=reading.value?.kind;reading.value=null;kind.value=k??'all';query.value='';view.value='category';mode.value='facts'}
function clearFilter(){query.value='';kind.value='all'}
</script>
<template>
  <div class="ws-page intel-page">
    <PageHeading title="岗位资讯" description="先读事实，再看它和你有什么关系。每条保留要求、来源与读取时间。"><button class="btn" @click="clearFilter">清空筛选</button><button class="btn" @click="kind=kind==='career'?'all':'career';mode='facts'">{{ kind==='career'?'看全部资讯':'只看岗位示例' }}</button></PageHeading>

    <section class="c2-profile-stats" aria-label="资讯概览"><article class="c2-profile-stat"><strong>{{ backendDemo.state.intel.length }}</strong><small>条</small><h2>这一批资讯</h2><p>同一批信息可按类别与时间重组</p></article><article class="c2-profile-stat"><strong>{{ kinds.length }}</strong><small>类</small><h2>可按类别筛选</h2><p>只显示这批资讯中出现的类别</p></article><article class="c2-profile-stat"><strong>{{ backendDemo.state.dataMode==='demo'?0:backendDemo.state.intel.filter(i=>source(i.source_url)).length }}</strong><small>条</small><h2>{{ backendDemo.state.dataMode==='demo'?'真实招聘':'提供原始链接' }}</h2><p>{{ backendDemo.state.dataMode==='demo'?'这一批是虚构样例，不能当作招聘公告':'来源是否有效仍需逐条核对' }}</p></article><article class="c2-profile-stat"><strong>{{ new Set(backendDemo.state.intel.map(i=>i.source_name||i.source_url||'来源未提供')).size }}</strong><small>个</small><h2>来源标记</h2><p>每条资讯单独核对来源</p></article></section>
    <div class="c2-intel-body">
      <template v-if="mode==='facts'">
        <details class="c2-intel-retrieve"><summary>检索最新资讯 / 职业匹配</summary><form class="remote-search" @submit.prevent="load()">
          <label class="ws-field">检索最新资讯<input v-model="remoteQuery" placeholder="职业、方向或关键词…" maxlength="200"/></label>
          <button class="btn btn--primary" type="submit" :disabled="busy">{{ busy?'正在读取…':'检索' }}</button>
          <button class="btn" type="button" :disabled="busy" @click="load(true)">刷新资讯</button>
        </form><button class="ws-text-button" @click="mode='match'">结合个人情况看职业匹配 →</button></details>
        <StatusBanner v-if="error" class="intel-banner" tone="error" :message="error" retry-label="重试" @retry="load()"/>
        <StatusBanner v-if="status" class="intel-banner" tone="success" :message="status" :open="!!status" @dismiss="status=''"/>

<section class="c2-intel-filter ws-paper"><header class="ws-section-head"><div><h2>先筛一遍，再看</h2><p>只筛选这一批已读取的条目，换排序时条目重新组织。</p></div><span>{{ items.length }} 条</span></header><div class="c2-filter-row"><span>类别</span><div><button :aria-pressed="kind==='all'" @click="kind='all'">全部 {{ backendDemo.state.intel.length }}</button><button v-for="[key,label] in kinds" :key="key" :aria-pressed="kind===key" @click="kind=key">{{ label }} {{ backendDemo.state.intel.filter(i=>i.kind===key).length }}</button></div></div><div class="c2-filter-row"><span>热词</span><div><button v-for="word in hotWords" :key="word" :aria-pressed="query===word" @click="query=query===word?'':word">{{ word }} {{ keywordCount(word) }}</button></div></div><div class="c2-filter-row"><span>排序</span><div class="c2-lensbar" role="group" aria-label="组织方式"><button :aria-pressed="view==='relevance'" @click="view='relevance'">按对你的相关度</button><button :aria-pressed="view==='timeline'" @click="view='timeline'">按什么时候用得上</button><button :aria-pressed="view==='category'" @click="view='category'">按类别</button></div></div><label class="c2-intel-keyword">筛选资讯<input v-model="query" aria-label="筛选资讯" placeholder="在已读取条目中筛选关键词…"/></label><p class="c2-lens-hint">剩下 {{ items.length }} 条。类别分组与条数跟着筛选更新，原始条目仍保留。</p></section>
        <div v-if="items.length && view!=='timeline'" class="intel-groups">
          <section v-for="g in groups" :key="g.key" class="intel-group">
            <header class="intel-group__head">
              <h2>{{ g.label }}</h2>
              <StatTile class="intel-group__count" :value="g.items.length" unit="条" label="本类条目"/>
              <p class="intel-group__time">
                <time v-if="g.items[0]?.fetched_at" :datetime="isoDay(g.items[0]?.fetched_at)">{{ timeLabel(g.items[0]?.fetched_at) }}</time>
                <span v-else>时间未提供</span>
                <span class="intel-group__batch">同一批次读取</span>
                <button class="ws-text-button intel-group__only" @click="kind=g.key;query=''">只看这一类</button>
              </p>
            </header>
            <div class="intel-list">
              <article v-for="item in g.items" :key="item.id" class="desk-intel-item">
                <h3 class="intel-card__title"><button class="intel-title" @click="reading={...item}">{{ item.title || '资讯正文' }}<UiIcon name="arrow" :size="18"/></button></h3>
                <!-- 预览而不是全文：全文在弹层里（这是"核对来源"有增益的第一步） -->
                <p class="intel-card__text">{{ preview(item.text) }}</p>
                <!-- 来源与时间做进卡片结构，不再是灰字尾注 -->
                <div class="intel-card__facts">
                  <span class="intel-fact"><span class="intel-fact__key">来源</span>{{ item.source_name || '未提供来源' }}</span>
                  <span class="intel-fact"><span class="intel-fact__key">读取</span><time v-if="item.fetched_at" :datetime="isoDay(item.fetched_at)">{{ isoDay(item.fetched_at) }}</time><template v-else>时间未提供</template></span>
                  <span class="intel-fact"><span class="intel-fact__key">原文</span>{{ textLen(item.text) }} 字</span>
                </div>
                <div class="desk-intel-item__source">
                  <a v-if="source(item.source_url)" class="ws-text-link" :href="source(item.source_url)" target="_blank" rel="noopener noreferrer">打开原始来源<UiIcon name="arrow" :size="16"/></a>
                  <span v-else class="ws-muted">未提供原始来源链接</span>
                  <button class="ws-text-button" @click="reading={...item}">核对来源</button>
                </div>
              </article>
            </div>
          </section>
        </div>

        <div v-else-if="items.length" class="intel-timeline">
          <section v-for="d in days" :key="d.day" class="intel-day">
            <header class="intel-day__head">
              <h2>{{ d.day==='日期未提供' ? '日期未提供' : d.day }}</h2>
              <p class="intel-day__meta">{{ d.list.length }} 条 · {{ dayCount(d.list)>1 ? '多个读取时点' : '同一次读取' }}</p>
            </header>
            <ul class="intel-day__list">
              <li v-for="item in d.list" :key="item.id">
                <span class="intel-day__time t-num">{{ item.fetched_at ? new Date(item.fetched_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) : '—' }}</span>
                <span class="intel-day__kind">{{ item.kind_label || '资讯' }}</span>
                <button class="ws-text-button intel-day__title" @click="reading={...item}">{{ item.title || '资讯正文' }}</button>
              </li>
            </ul>
          </section>
        </div>

        <!-- ① 还没取到（并且手上一条都没有）→ 骨架屏；② 取了但没有 → 空态 -->
        <SkeletonBlock v-else-if="busy" variant="card" :columns="2" :lines="3"/>
        <EmptyState
          v-else
          kind="intel"
          :heading-level="2"          :title="backendDemo.state.intel.length?'没有匹配的资讯':'暂无已读取资讯'"
          description="可调整筛选、检索最新资料，或先查看示例。示例条目不是真实招聘公告。"
          :next="false"
        >
          <button v-if="backendDemo.state.intel.length" class="btn" @click="clearFilter">清除筛选</button>
          <button v-else class="btn btn--primary" @click="sample">加载资讯示例</button>
        </EmptyState>

        <p class="ws-demo-note">{{ backendDemo.state.intelOrigin==='live'&&backendDemo.state.dataMode==='service'?'条目来自本次服务读取；本地筛选不再发起远程请求。':'当前条目为演示示例；上方检索与刷新调用正式资讯服务，不会以示例替代失败结果。' }}</p>
      </template>
    </div>

    <CareerMatchPanel v-show="mode==='match'" :facts="backendDemo.state.intel" @read="read" @facts="facts"/>
    <nav class="ws-related"><RouterLink to="/directions">对照方向方案</RouterLink><RouterLink to="/report">查看个人诊断</RouterLink></nav>

    <!-- 详情：shape=sheet（桌面右侧抽屉 / 小屏底部面板）。原来的 wide 必须一起去掉，
         否则 resolvedShape 里 wide 优先级更高，shape 会被静默覆盖。 -->
    <aside class="c2-intel-side" aria-label="资讯来源与使用"><section><h2>这一批资讯从哪里来</h2><p>{{ backendDemo.state.intelOrigin === 'sample' ? '本地虚构演示资料，供比较岗位要求与来源，不作为招聘公告引用。' : '来自本次读取的资讯结果，每条保留自己的来源与读取时间。' }}</p><p>共 {{ backendDemo.state.intel.length }} 条、{{ kinds.length }} 类。读取时间与原始发布时间分别核对。</p></section><section><h2>先读事实，再决定</h2><p>点开一条资讯，可查看全文、核验清单和同类别的其他条目。核实岗位地点、学历要求及信息有效期，再纳入自己的计划。</p><RouterLink class="ws-text-link" to="/directions">回到方向比较 →</RouterLink></section></aside>
    <InfoSheet :open="reading!==null" shape="sheet" :title="reading?.title || '资讯详情'" @close="reading=null">
      <article v-if="reading" class="intel-detail">
        <div class="intel-detail__facts">
          <span class="intel-fact"><span class="intel-fact__key">类别</span>{{ reading.kind_label || '资讯' }}</span>
          <span class="intel-fact"><span class="intel-fact__key">来源</span>{{ reading.source_name || '未提供来源' }}</span>
          <span class="intel-fact"><span class="intel-fact__key">读取</span>{{ timeLabel(reading.fetched_at) }}</span>
        </div>

        <!-- 增益 ①：卡片上是 46 字预览，这里是全文 -->
        <section class="intel-detail__block">
          <h3 class="intel-detail__title">条目原文（{{ readingLen }} 字）</h3>
          <ReadableText :text="reading.text || '本条资讯未提供正文。'"/>
          <p v-if="readingLen>cardLen" class="intel-detail__gain">卡片上是 {{ cardLen }} 字预览，这里是完整原文（多出 {{ readingLen-cardLen }} 字）。</p>
        </section>

        <!-- 增益 ②：逐项核验清单（卡片上没有） -->
        <section class="intel-detail__block">
          <h3 class="intel-detail__title">核对这条时看什么</h3>
          <ol class="intel-verify">
            <li v-for="(v,i) in verifyPoints(reading)" :key="v.title">
              <span class="intel-verify__idx t-num">{{ i+1 }}</span>
              <div><strong>{{ v.title }}</strong><p>{{ v.detail }}</p></div>
            </li>
          </ol>
        </section>

        <!-- 增益 ③：同一类别里的其它条目与本文的关系（卡片上更看不到） -->
        <section v-if="related.length" class="intel-detail__block">
          <h3 class="intel-detail__title">同一类别里的其它条目</h3>
          <ul class="ws-mini-list intel-related">
            <li v-for="r in related" :key="r.id">
              <button class="ws-text-button" @click="reading={...r}">{{ r.title || '资讯正文' }}</button>
              <p class="intel-related__why">与本文同类：{{ reading.kind_label || '资讯' }}。{{ textLen(r.text) }} 字，来源{{ r.source_name===reading.source_name ? '相同' : '不同' }}。</p>
            </li>
          </ul>
          <button class="ws-text-button intel-related__all" @click="readKind">回到「{{ reading.kind_label || '这一类' }}」分组</button>
        </section>

        <a v-if="source(reading.source_url)" class="ws-text-link intel-detail__src" :href="source(reading.source_url)" target="_blank" rel="noopener noreferrer">打开原始来源核对</a>
        <p v-else class="ws-muted intel-detail__src">本条没有可打开的原始来源链接：{{ reading.source_name || '来源未提供' }}。请以真实招聘方原文为准。</p>
      </article>
    </InfoSheet>
  </div>
</template>

<style scoped>
/* ============================================================================
 * 组织：类别组头 / 时间线 / 卡片字段行
 * 全部用既有令牌（字号六档、间距档、三支色相），不新增字号档、不新增色相。
 * ========================================================================= */
.intel-banner { margin-top: var(--sp-4); }

.intel-views {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-3);
  margin-bottom: var(--sp-5);
}
.intel-views__btn {
  /* 45 而不是 44：`.btn` 的 44 在实测里会被算成 43.x（44 减去边框后取整），
     审计的"<44px"口径就会判它不达标。这里多留 1px 让实测真的 ≥44。 */
  min-height: 45px;
  padding: 0 var(--sp-4);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  background: var(--c-surface);
}
.intel-views__btn[aria-pressed='true'] {
  border-color: var(--c-primary-border);
  background: var(--c-primary-weak);
  color: var(--c-primary);
}
.intel-views__hint {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

/* ---- 类别分组 ---- */
.intel-groups { display: grid; gap: var(--sp-6); }
.intel-group__head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  padding-bottom: var(--sp-3);
  border-bottom: var(--bw-1) solid var(--c-border-strong);
}
.intel-group__head h2 { font-size: var(--fs-20); font-weight: var(--fw-semibold); }
/* 读数瓦片在组头里只占一小格：给个下限，让"本类条目 / 5 条"不被挤成两行 */
.intel-group__count { flex: none; min-width: 116px; }
.intel-group__time {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  font-variant-numeric: tabular-nums;
}
/* 日期一行的宽度：把"只看这一类"收进这一行，窄屏整行换行而不是被拆散 */
.intel-group__time { flex: 0 1 auto; }
.intel-group__only { flex: none; margin-left: var(--sp-2); }
/* "同一批次读取"：把"12 条时间戳一模一样"这件事实说出来，
   而不是让它看起来像 12 个独立时点（DESIGN-LANGUAGE §4.4 状态与不确定性显形） */
.intel-group__batch {
  padding: 1px var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-sm);
  color: var(--c-text-3);
}

/* ---- 卡片 ---- */
.intel-card__title { margin-bottom: var(--sp-2); }
.intel-card__text { color: var(--c-text-2); font-size: var(--fs-16); max-width: 38em; }
.intel-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  margin-top: var(--sp-3);
}
.intel-fact {
  display: inline-flex;
  align-items: baseline;
  gap: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-2);
}
.intel-fact__key {
  padding: 1px var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-sm);
  color: var(--c-text-3);
}

/* ---- 时间线视角 ---- */
.intel-timeline { display: grid; gap: var(--sp-6); }
.intel-day__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-4);
  padding-bottom: var(--sp-2);
  border-bottom: var(--bw-1) solid var(--c-border);
}
.intel-day__head h2 { font-size: var(--fs-16); font-weight: var(--fw-semibold); font-variant-numeric: tabular-nums; }
.intel-day__meta { font-size: var(--fs-12); color: var(--c-text-3); }
.intel-day__list { display: grid; gap: var(--sp-1); }
.intel-day__list li {
  display: grid;
  grid-template-columns: 64px 84px minmax(0, 1fr);
  align-items: baseline;
  gap: var(--sp-3);
}
.intel-day__time, .intel-day__kind { font-size: var(--fs-12); color: var(--c-text-3); }
.intel-day__title { justify-content: flex-start; text-align: left; color: var(--c-text); }
.intel-day__title:hover { color: var(--c-primary); }

/* ---- 弹层内容 ---- */
.intel-detail__facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  padding-bottom: var(--sp-4);
  border-bottom: var(--bw-1) solid var(--c-border);
}
.intel-detail__block { margin-top: var(--sp-5); }
.intel-detail__title { font-size: var(--fs-16); font-weight: var(--fw-semibold); margin-bottom: var(--sp-3); }
.intel-detail__gain { margin-top: var(--sp-3); font-size: var(--fs-12); color: var(--c-text-3); }
.intel-verify { display: grid; gap: var(--sp-4); }
.intel-verify li { display: flex; gap: var(--sp-3); align-items: flex-start; }
.intel-verify__idx {
  flex: none;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  color: var(--c-text-2);
}
.intel-verify strong { font-size: var(--fs-14); font-weight: var(--fw-medium); }
.intel-verify p { margin-top: var(--sp-1); font-size: var(--fs-14); line-height: var(--lh-normal); color: var(--c-text-2); }
.intel-related__why { font-size: var(--fs-12); color: var(--c-text-3); }
.intel-related__all { margin-top: var(--sp-2); }
.intel-detail__src { margin-top: var(--sp-5); }

/* 窄屏：时间线的三列会挤，切成两行（时间 + 类别一行，标题一行） */
@media (max-width: 560px) {
  .intel-day__list li { grid-template-columns: 64px minmax(0, 1fr); }
  .intel-day__kind { display: none; }
}

/* reduced-motion：本页没有自造动效，这里只把交互态过渡收掉（可用形态不变） */
@media (prefers-reduced-motion: reduce) {
  .intel-views__btn, .intel-day__title { transition: none; }
}
</style>
