<script setup lang="ts">
import { computed, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { bindChsiTask, type BindResult } from '@/ai/registry'
import { importAcademic, type AcademicImportAck } from '@/api/client'
import { useSessionStore } from '@/stores/session'

/**
 * 学信网核验 —— 这是采集环节的"第一口气"。
 *
 * 真数据走的是学信网的官方通道：**在线验证码**。
 * 学生在学信档案里自己申请一份《教育部学籍在线验证报告》，
 * 得到一串码；我们拿这串码去学信网官方验证页核验，读回学籍。
 *
 * 所以这个浮层不是"授权按钮"，是一张表单 —— 而且必须先说清楚：
 *   · 去哪里拿码、长什么样（不然用户会去找"学信网登录"）；
 *   · 我们不要你的学信网账号密码（这是用户最该确认的一件事）；
 *   · 能拿到什么、拿不到什么（学信网没有课程表与成绩单，别让人误会）。
 */
const session = useSessionStore()

/**
 * 两条平行的路，界面上必须分开 —— 它们的性质完全不同：
 *
 *   学信网：官方验证码通道，不碰账号密码 → 学籍
 *   课表与成绩：学生自己从教务系统导出（整页复制 / Excel / JSON）后导入
 *
 * 合成一个"授权"按钮会让人以为两条路一样 —— 而第二条**根本不需要授权**：
 * 数据是他自己的，我们只是把它读懂。
 */
const mode = ref<'chsi' | 'academic'>(session.bindMode)

const code = ref('')
const submitted = ref('')
const frame = ref<InstanceType<typeof AiFrame> | null>(null)

/* 导入表单：贴进来说行 —— 不登录、不授权、不经手任何凭据 */
const school = ref('')
const term = ref('')
const coursesText = ref('')
const gradesText = ref('')
const importing = ref(false)
const importError = ref('')
const importResult = ref<AcademicImportAck | null>(null)
/** 选过文件之后把那行字换掉 —— 原生文件名框是这一屏最丑的东西 */
const picked = ref<{ courses: string; grades: string }>({ courses: '', grades: '' })

const importReady = computed(
  () => coursesText.value.trim().length > 0 || gradesText.value.trim().length > 0,
)

/**
 * 粘贴即导入。
 *
 * 用户贴进来的那一刻，他要的结果其实已经确定了：把这段东西变成课表。
 * 还要他再找一个「导入」按钮点一下，中间那一步只会让人怀疑"我是不是没贴上"。
 * 所以贴完稍等一下自动跑；只在一段内容明显够长（不是误触）时触发，
 * 顺序也是先课表后成绩，避免两个框各触发一次。
 */
let autoTimer: ReturnType<typeof setTimeout> | null = null
const autoHint = ref('')

function onPasted() {
  if (autoTimer) clearTimeout(autoTimer)
  autoTimer = setTimeout(async () => {
    if (importing.value) return
    const courses = coursesText.value.trim()
    const grades = gradesText.value.trim()
    const ready = courses.length >= 20 || grades.length >= 20
    if (!ready) return
    autoHint.value = '认出来了，正在生成…'
    await doImport()
    autoHint.value = ''
  }, 700)
}

/** 学信网验证页自己用的格式：12 位数字，或 A / X 开头 + 15 位字母数字 */
const CODE_SHAPE = /^(\d{12}|[AX][A-Z0-9]{15})$/

const cleaned = computed(() => code.value.replace(/[\s\-_]/g, '').toUpperCase())
const shapeOk = computed(() => CODE_SHAPE.test(cleaned.value))
const running = computed(() => !!submitted.value)

/** 任务绑定的是"提交那一刻"的码 —— 否则用户改了输入框会悄悄改掉正在跑的这次核验 */
const task = () => bindChsiTask(submitted.value) as never

function verify() {
  if (!shapeOk.value) return
  submitted.value = cleaned.value
}

async function doImport() {
  if (!importReady.value || importing.value) return
  importing.value = true
  importError.value = ''
  try {
    importResult.value = await importAcademic({
      courses: coursesText.value,
      grades: gradesText.value,
      school: school.value.trim(),
      term: term.value.trim(),
    })
    // 画像与快照都在后端改了，前端这份是挂载时拉的快照 —— 不重拉就是旧数据
    await session.loadBackend()
    session.bindAcademic()
  } catch (cause) {
    // 读不出来时后端会说清"改哪里"，原样显示，不吞成一句"导入失败"
    importError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    importing.value = false
  }
}

/** 文件读进来填进输入框：这一步在浏览器里做，不需要上传接口 */
function readFile(event: Event, target: 'courses' | 'grades') {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  picked.value[target] = file.name
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result ?? '')
    if (target === 'courses') coursesText.value = text
    else gradesText.value = text
  }
  reader.readAsText(file, 'utf-8')
}

function reset() {
  submitted.value = ''
  code.value = ''
}

function resetAcademic() {
  importResult.value = null
  importError.value = ''
  coursesText.value = ''
  gradesText.value = ''
}

async function finish() {
  // 画像是在后端被改的，前端这份是挂载时拉的快照 ——
  // 不重新拉一次，用户关掉浮层看到的还是旧画像。
  await session.loadBackend()
  session.bindChsi()
  session.closeOverlay()
}

async function finishAcademic() {
  await session.loadBackend()
  session.closeOverlay()
}

/**
 * 直接关掉（没点"知道了"）也要刷新。
 *
 * 报告一核验完，后端就已经写进画像、采集清单也跟着变了 ——
 * 前端不刷新的话，用户关掉浮层会看到一份**过期的清单**：
 * 明明补上了 8 条，画布上还写着"还差 14 条"。
 */
async function close() {
  await session.loadBackend()
  session.closeOverlay()
}
</script>

<template>
  <Overlay
    :title="mode === 'chsi' ? '核验学信网学籍' : '导入课表与成绩单'"
    :subtitle="
      mode === 'chsi'
        ? '用学信档案的在线验证码 · 不要账号密码'
        : '把教务系统的课表/成绩复制进来 · 不用登录、不用授权'
    "
    from="collect"
    @close="close"
  >
    <div class="bind">
      <!--
        两条路并列，但性质写清楚：左边那条不需要密码，右边那条需要。
        用户有权在点之前就知道自己在给什么。
      -->
      <nav class="tabs" aria-label="数据来源">
        <button
          class="tabs__b"
          type="button"
          :class="{ 'is-on': mode === 'chsi' }"
          @click="mode = 'chsi'"
        >
          <span class="tabs__t">学信网 · 学籍</span>
          <span class="tabs__d">官方验证码 · 不用密码</span>
        </button>
        <button
          class="tabs__b"
          type="button"
          :class="{ 'is-on': mode === 'academic' }"
          @click="mode = 'academic'"
        >
          <span class="tabs__t">课表与成绩 · 自己导入</span>
          <span class="tabs__d">复制粘贴 · 不碰账号</span>
        </button>
      </nav>

      <!-- 第一步：拿到码。表单之前先把"去哪拿"讲清楚。 -->
      <template v-if="mode === 'chsi' && !running">
        <section class="lead">
          <h3 class="lead__t editorial">学籍这件事，不用你手填。</h3>
          <p class="lead__d">
            学信网有一条官方核验通道：你在学信档案里申请一份
            《教育部学籍在线验证报告》，把报告上的<b>在线验证码</b>填进下面这一栏，
            我们拿去官方验证页核验，读回学籍写进画像。
          </p>
        </section>

        <!--
          三步各占一行。写成"小标题 + 说明"两行会把提交框挤出可视区（窄屏尤甚），
          而那颗输入框才是这一步唯一的动作 —— 讲清去哪拿，不能把动作挤出屏幕。
        -->
        <ol class="howto">
          <li>
            <span class="howto__n mono">1</span>
            <span class="howto__t">登录<b>学信档案</b>（本人实人认证，由学信网完成）</span>
          </li>
          <li>
            <span class="howto__n mono">2</span>
            <span class="howto__t">在线验证报告 → 申请《教育部学籍在线验证报告》</span>
          </li>
          <li>
            <span class="howto__n mono">3</span>
            <span class="howto__t">复制报告上的验证码，填到<b>下面这一栏</b></span>
          </li>
        </ol>

        <form class="form" novalidate @submit.prevent="verify">
          <label class="field">
            <span class="label">在线验证码（12 位数字，或以 A / X 开头的 16 位码）</span>
            <input
              v-model="code"
              type="text"
              name="chsi-code"
              autocomplete="off"
              spellcheck="false"
              placeholder="例如 123456789012"
              :aria-invalid="code.length > 0 && !shapeOk"
            >
          </label>
          <p v-if="code.length > 0 && !shapeOk" class="field__err" role="alert">
            这串码看起来不对：应为 12 位数字，或以 A / X 开头的 16 位码。
          </p>

          <div class="actions">
            <button class="btn primary" type="submit" :disabled="!shapeOk">核验并写入画像</button>
            <a
              class="link"
              href="https://my.chsi.com.cn/archive/index.jsp"
              target="_blank"
              rel="noreferrer"
            >去学信档案申请 →</a>
          </div>

          <p class="label promise">
            我们只凭这串码读一次报告，不索取、不保存你的学信网账号密码；
            报告过期后需要重新申请一串新码。
          </p>
        </form>
      </template>

      <!-- 第二步：核验。进度、结果、失败都在这一段里。 -->
      <template v-else-if="mode === 'chsi'">
        <AiFrame ref="frame" :task="task">
          <template #default="{ data }">
            <div class="result">
              <h3 class="lead__t editorial">核验通过，学籍已经写进画像。</h3>

              <ol class="steps">
                <li v-for="(s, i) in (data as BindResult).steps" :key="s.id" :class="{ 'steps--empty': s.got === 0 }">
                  <span class="steps__n mono">{{ i + 1 }}</span>
                  <span class="steps__label">{{ s.label }}</span>
                  <span class="steps__detail">{{ s.detail }}</span>
                  <span class="label steps__src">{{ s.source }}</span>
                </li>
              </ol>

              <div v-if="(data as BindResult).lifted.length" class="lift">
                <span class="label">写进画像的信息</span>
                <div v-for="l in (data as BindResult).lifted" :key="l.dim" class="lift__row">
                  <span class="lift__dim">{{ l.dim }}</span>
                  <span class="mono lift__num">{{ l.to.toFixed(2) }}</span>
                  <span class="lift__why">{{ l.because }}</span>
                </div>
              </div>

              <footer class="actions">
                <button class="btn primary" type="button" @click="finish">知道了</button>
                <button class="btn ghost" type="button" @click="reset">换一串码重新核验</button>
              </footer>
            </div>
          </template>
        </AiFrame>

        <!-- 失败时除了"重算"，还要能退回改码 —— 码写错是最常见的失败 -->
        <button
          v-if="frame?.state === 'error'"
          class="btn ghost back"
          type="button"
          @click="reset"
        >改验证码</button>
      </template>

      <!-- ── 课表与成绩：自己导入。不登录、不授权、不经手任何凭据 ─────── -->
      <template v-else>
        <template v-if="!importResult">
          <section class="lead">
            <h3 class="lead__t editorial">课表和成绩，学信网里没有。</h3>
            <p class="lead__d">
              它们在<b>你学校的教务系统</b>里。那套系统没有对外开放的数据通道，
              所以我们不去替你登录 —— 你自己导出一份，贴进来，我们负责读懂它。
              这样你校内账号的密码一次都不需要经过任何人。
            </p>
          </section>

          <ol class="howto">
            <li>
              <span class="howto__n mono">1</span>
              <div>
                <span class="howto__t">打开你学校的课表页 / 成绩页</span>
                <span class="howto__d">登录学校教务系统，进到"我的课表"或"成绩查询"。</span>
              </div>
            </li>
            <li>
              <span class="howto__n mono">2</span>
              <div>
                <span class="howto__t">Ctrl+A 全选、Ctrl+C 复制</span>
                <span class="howto__d">
                  整页复制最省事。也可以导出 Excel 后连<b>表头那一行</b>一起复制
                  （表头要有「课程名称」）。
                </span>
              </div>
            </li>
            <li>
              <span class="howto__n mono">3</span>
              <div>
                <span class="howto__t">贴到下面，各贴各的</span>
                <span class="howto__d">课表贴课表、成绩贴成绩；只导一份也行，另一份以后再说。</span>
              </div>
            </li>
          </ol>

          <form class="form" novalidate @submit.prevent="doImport">
            <div class="grid">
              <label class="field">
                <span class="label">学校（可留空）</span>
                <input v-model="school" type="text" autocomplete="off" placeholder="例如 某某大学">
              </label>
              <label class="field">
                <span class="label">学期（可留空）</span>
                <input v-model="term" type="text" autocomplete="off" placeholder="多数情况能从原文读到">
              </label>
            </div>

            <label class="field field--wide">
              <span class="label">课表</span>
              <textarea
                v-model="coursesText"
                name="jw-courses"
                rows="6"
                spellcheck="false"
                placeholder="在课表页 Ctrl+A 全选复制，粘贴到这里"
                @paste="onPasted"
              />
              <label class="pick">
                <input type="file" accept=".txt,.csv,.html,.htm,.json" @change="readFile($event, 'courses')">
                <span class="pick__t">{{ picked.courses ? `已选：${picked.courses}` : '或选一个文件' }}</span>
                <span class="label pick__hint">txt / csv / html / json</span>
              </label>
            </label>

            <label class="field field--wide">
              <span class="label">成绩单</span>
              <textarea
                v-model="gradesText"
                name="jw-grades"
                rows="5"
                spellcheck="false"
                placeholder="在成绩页全选复制，粘贴到这里"
                @paste="onPasted"
              />
              <label class="pick">
                <input type="file" accept=".txt,.csv,.html,.htm" @change="readFile($event, 'grades')">
                <span class="pick__t">{{ picked.grades ? `已选：${picked.grades}` : '或选一个文件' }}</span>
                <span class="label pick__hint">txt / csv / html</span>
              </label>
            </label>

            <p v-if="importError" class="field__err" role="alert">{{ importError }}</p>
            <p v-else-if="autoHint || importing" class="label field__auto">{{ autoHint || '正在读你贴进来的内容…' }}</p>

            <div class="actions">
              <button class="btn primary" type="submit" :disabled="!importReady || importing">
                {{ importing ? '正在读…' : '导入' }}
              </button>
              <span class="label promise">
                读得到就读，读不出来会说清是哪里不对（缺表头 / 只复制了表头 / 版式不认识）。
              </span>
            </div>
          </form>
        </template>

        <template v-else>
          <div class="result">
            <h3 class="lead__t editorial">导入完成。</h3>
            <!--
              读取方式说一次就够：一次导入可能同时读了课表与成绩，
              但"按哪种版式读的"是这次导入的属性，不是每一行的属性 ——
              贴在每一行上会让人以为两段内容各用了一种读法。
            -->
            <p class="label result__how">这次导入按「{{ importResult.source }}」版式读取</p>

            <ol class="steps">
              <li v-if="importResult.courses">
                <span class="steps__n mono">1</span>
                <span class="steps__label">课表</span>
                <span class="steps__detail">
                  {{ importResult.term || '本学期' }} · {{ importResult.courses }} 门课
                </span>
                <span class="label steps__src">课表</span>
              </li>
              <li v-if="importResult.grades">
                <span class="steps__n mono">2</span>
                <span class="steps__label">成绩单</span>
                <span class="steps__detail">{{ importResult.grades }} 门成绩</span>
                <span class="label steps__src">成绩单</span>
              </li>
              <li v-if="importResult.wrote_profile?.length">
                <span class="steps__n mono">3</span>
                <span class="steps__label">写进画像</span>
                <span class="steps__detail">
                  {{ importResult.wrote_profile?.join(' / ') }} 已标记为已拿到 —— 采集清单跟着更新
                </span>
                <span class="label steps__src">画像 · 摘要</span>
              </li>
              <li v-for="(note, i) in importResult.notes ?? []" :key="i" class="steps--empty">
                <span class="steps__n mono">!</span>
                <span class="steps__label">要留意的</span>
                <span class="steps__detail">{{ note }}</span>
                <span class="label steps__src">导入解析</span>
              </li>
            </ol>

            <footer class="actions">
              <button class="btn primary" type="button" @click="finishAcademic">知道了</button>
              <button class="btn ghost" type="button" @click="resetAcademic">再导一份</button>
            </footer>
          </div>
        </template>
      </template>
    </div>
  </Overlay>
</template>

<style scoped>
/*
 * 底板已经拿掉（见 Overlay.vue），所以这一张自己出纸：
 *
 * 它是一个**表单**：填验证码 / 贴课表。内容是一列，铺满 1180px 只会让每行太长 ——
 * 收窄到 760px 居中，高度跟着内容走、最多占满舞台。这样它读起来是"浮在中间的一张纸"，
 * 而不是"整页的一层底"。
 */
.bind {
  align-self: center;
  width: min(760px, 100%);
  max-height: 100%;
  overflow: auto;
  padding: var(--s5) var(--s6) var(--s6);
  display: flex; flex-direction: column; gap: var(--s5);
  background: var(--n-1);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--e-4);
}

/* 两条路并列：左边不用密码、右边要密码 —— 差别必须在点击之前就看出来 */
.tabs { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); }
.tabs__b {
  display: grid; gap: 2px; text-align: left; align-content: center;
  /* 两个页签**等高**：文案长短不一，不等高的话并排看就像没对齐 */
  min-height: 62px;
  padding: var(--s3) var(--s4);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-md);
  background: var(--n-1);
  transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.tabs__b:hover { border-color: var(--line-4); }
.tabs__b.is-on { border-color: var(--accent); background: var(--accent-soft); }
.tabs__t { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.tabs__b.is-on .tabs__t { color: var(--accent); }
.tabs__d { font-size: var(--fs-small); color: var(--ink-3); }

/* 教务系统那条路的边界：先摆条件，再要凭据 */
.terms { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.terms li {
  font-size: var(--fs-small); line-height: 1.7; color: var(--ink-2);
  padding: var(--s2) var(--s3); border-left: 3px solid var(--line-3);
}
.terms b { color: var(--ink-1); }

.lead { display: flex; flex-direction: column; gap: var(--s2); }
.lead__t { font-size: var(--t-h4); line-height: 1.42; }
.lead__d { font-size: var(--fs-small); line-height: 1.78; color: var(--ink-2); max-width: 54ch; }
.lead__d b { color: var(--ink-1); font-weight: 600; }

.howto { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.howto li {
  display: grid; grid-template-columns: 22px minmax(0, 1fr);
  gap: var(--s3); align-items: baseline;
  padding: var(--s3) var(--s4) var(--s3) var(--s2);
  border-left: 3px solid var(--accent);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}
.howto li:nth-child(odd) { background: var(--fill-subtle); }
.howto__n { color: var(--accent); }
.howto__t { display: block; font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.howto__d { display: block; font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7; margin-top: 2px; }

.form { display: flex; flex-direction: column; gap: var(--s3); padding-top: var(--s3); border-top: 1px solid var(--line-1); }
.field { display: grid; gap: 6px; max-width: 420px; }
.field input {
  height: 44px; padding: 0 var(--s4);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--n-1);
  font-family: var(--font-mono);
  font-size: var(--t-body);
  letter-spacing: 0.14em;
  transition: border-color var(--dur-micro) var(--ease-out), box-shadow var(--dur-micro) var(--ease-out);
}
.field input:hover { border-color: var(--line-3); }
.field input:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.field input[aria-invalid="true"] { border-color: var(--warn); }
.field__err { font-size: var(--fs-small); color: var(--warn); }
.field__auto { color: var(--accent); }

/* 导入表单：学校与学期并排，两块粘贴区各占一行 */
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); max-width: 560px; }
.grid .field { max-width: none; }
.grid input {
  height: 40px; padding: 0 var(--s3);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-sm);
  background: var(--n-1); font-size: var(--fs-small);
  letter-spacing: normal; font-family: var(--font-sans);
}
.grid input:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

.field--wide { max-width: 640px; }
.field textarea {
  padding: var(--s3);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-sm);
  background: var(--n-1);
  font-family: var(--font-mono); font-size: 12px; line-height: 1.6;
  resize: vertical; min-height: 96px;
  white-space: pre; overflow-wrap: normal; overflow-x: auto;
}
.field textarea:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
/*
 * 传文件那一格。
 *
 * 之前直接用原生 `<input type="file">` —— 每个浏览器长得都不一样、带着
 * 一个几十年前的灰色按钮，是这一屏最丑的地方。现在把它藏起来，
 * 外面套一张虚线卡片：点整张卡都能选文件，选完显示文件名。
 */
.pick {
  display: flex; align-items: center; gap: var(--s2);
  padding: 9px var(--s3);
  border: 1px dashed var(--line-3); border-radius: var(--r-sm);
  background: var(--fill-subtle);
  cursor: pointer;
  transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.pick:hover { border-color: var(--accent); background: var(--accent-soft); }
.pick input[type="file"] { display: none; }
.pick__t { font-size: var(--fs-small); color: var(--ink-2); }
.pick__hint { color: var(--ink-faint); margin-left: auto; }

.actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s3); }
.link { color: var(--accent); font-size: var(--fs-small); }
.link:hover { text-decoration: underline; }
.promise { color: var(--ink-3); line-height: 1.7; max-width: 56ch; }

/* ── 结果 ─────────────────────────────────────────────────────── */
.result { display: flex; flex-direction: column; gap: var(--s5); }
.result__how { color: var(--ink-3); }
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.steps li {
  display: grid; grid-template-columns: 22px 92px minmax(0, 1fr) auto;
  align-items: baseline; gap: var(--s3);
  padding: var(--s3) var(--s4) var(--s3) var(--s2);
  border-left: 3px solid var(--mk-green);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}
.steps li:nth-child(odd) { background: var(--fill-subtle); }
/* got=0 的那一步不是"完成了 0 条"，是"这里没有数据源" —— 用虚线边框区分开 */
.steps--empty { border-left-style: dashed; border-left-color: var(--line-3); }
.steps--empty .steps__n,
.steps--empty .steps__label { color: var(--ink-3); }
.steps__n { color: var(--mk-green); }
.steps__label { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.steps__detail { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7; }
.steps__src { color: var(--ink-3); white-space: nowrap; }

.lift { display: flex; flex-direction: column; gap: var(--s2); padding-top: var(--s3); border-top: 1px solid var(--line-1); }
.lift__row { display: grid; grid-template-columns: 80px 56px minmax(0, 1fr); align-items: baseline; gap: var(--s3); }
.lift__dim { font-size: var(--fs-small); color: var(--ink-1); }
.lift__num { color: var(--mk-green); }
.lift__why { font-size: var(--fs-small); color: var(--ink-2); }

.back { align-self: flex-start; }
</style>
