<script setup lang="ts">
import { computed, ref } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { bindChsiTask, type BindResult } from '@/ai/registry'
import { importAcademic, importAcademicFiles, type AcademicImportAck } from '@/api/client'
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

/*
 * 导入表单：**给文件**或**给原文** —— 不登录、不授权、不经手任何凭据。
 *
 * 主路是传文件（那是用户手上真正有的东西：教务系统导出的 csv / json / 整页 html）。
 * 粘贴留着，因为"整页复制"是最省事的一条：导出走不通的时候，它一直是可用的。
 * 但粘贴区默认收起来 —— 两条路都铺开，会让"这一步要做几件事"看起来是两件。
 */
const school = ref('')
const term = ref('')
const coursesText = ref('')
const gradesText = ref('')
const coursesFile = ref<File | null>(null)
const gradesFile = ref<File | null>(null)
const pasteOpen = ref({ courses: false, grades: false })
/** 正在拖进来的那一栏（只用来给那栏加高亮，拖过别处就清掉） */
const dragging = ref<'' | 'courses' | 'grades'>('')
const importing = ref(false)
const importError = ref('')
const importResult = ref<AcademicImportAck | null>(null)

const fileCount = computed(() => (coursesFile.value ? 1 : 0) + (gradesFile.value ? 1 : 0))
const importReady = computed(
  () =>
    fileCount.value > 0 ||
    coursesText.value.trim().length > 0 ||
    gradesText.value.trim().length > 0,
)

/** 按钮文案说清**这次会导什么**：几个文件，还是一段粘贴的原文。 */
const importLabel = computed(() =>
  fileCount.value ? `导入这 ${fileCount.value} 个文件` : '导入粘贴的原文',
)

/**
 * 同一栏只留一个来源。
 *
 * 选了文件就清掉那一栏里粘的原文，反之亦然 —— 两份内容同时在时，"哪一份算数"
 * 没有诚实的答案，而猜一个的代价是用户看到一份他不认识的数据被导进去。
 */
function setFile(slot: 'courses' | 'grades', file: File | null) {
  if (slot === 'courses') {
    coursesFile.value = file
    if (file) coursesText.value = ''
  } else {
    gradesFile.value = file
    if (file) gradesText.value = ''
  }
  importError.value = ''
}

function pickFile(event: Event, slot: 'courses' | 'grades') {
  const input = event.target as HTMLInputElement
  setFile(slot, input.files?.[0] ?? null)
  // 清空 input：同一份文件连选两次（第一次没读对）时 change 才会再触发
  input.value = ''
}

function onDragOver(event: DragEvent, slot: 'courses' | 'grades') {
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  dragging.value = slot
}

function onDragLeave(slot: 'courses' | 'grades') {
  if (dragging.value === slot) dragging.value = ''
}

function onDrop(event: DragEvent, slot: 'courses' | 'grades') {
  event.preventDefault()
  dragging.value = ''
  setFile(slot, event.dataTransfer?.files?.[0] ?? null)
}

/** 在那一栏里手动输入/粘贴时，把同栏的文件让掉（见 `setFile` 的注释） */
function onTyped(slot: 'courses' | 'grades') {
  const text = slot === 'courses' ? coursesText.value : gradesText.value
  if (text.trim()) setFile(slot, null)
}

/** 文件大小：只给"这是不是一份正常的导出"用的一个量级，不追求精确 */
function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 粘贴即导入。
 *
 * 用户贴进来的那一刻，他要的结果其实已经确定了：把这段东西变成课表。
 * 还要他再找一个「导入」按钮点一下，中间那一步只会让人怀疑"我是不是没贴上"。
 * 所以贴完稍等一下自动跑；只在一段内容明显够长（不是误触）时触发，
 * 顺序也是先课表后成绩，避免两个框各触发一次。
 *
 * **选文件不自动跑**：一份一份选是常态（课表和成绩各一个文件），
 * 选完第一个就自动提交，会让第二个文件永远没机会被选上。
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
    // 有文件就走上传（编码与二进制格式都由后端处理）；纯粘贴走原来那条 JSON 接口
    importResult.value = fileCount.value
      ? await importAcademicFiles(uploadForm())
      : await importAcademic({
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

/**
 * 组装 multipart 表单。
 *
 * 两栏的内容都带上（`courses_text` 与 `courses_file` 可能只有一个有值）——
 * "哪一栏有东西"由用户当时的选择决定，前端不替后端做过滤。
 * 文件名由 `courses_file` 的 filename 带过去，后端出错时才能点名"是课表.json 这份"。
 */
function uploadForm(): FormData {
  const form = new FormData()
  if (coursesFile.value) form.append('courses_file', coursesFile.value, coursesFile.value.name)
  if (gradesFile.value) form.append('grades_file', gradesFile.value, gradesFile.value.name)
  form.append('courses_text', coursesText.value)
  form.append('grades_text', gradesText.value)
  form.append('school', school.value.trim())
  form.append('term', term.value.trim())
  return form
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
  coursesFile.value = null
  gradesFile.value = null
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
 * 读法的中文名。
 *
 * 后端回执里的 `source` 是 `qz` / `table` / `json` 这种代号（那是溯源用的机器值）。
 * 直接摆在界面上等于让用户读我们的内部编号 —— 这里是给人看的那一版。
 */
const SOURCE_LABEL: Record<string, string> = {
  qz: '教务系统页面',
  zf: '教务系统页面',
  table: '表格文本',
  json: 'JSON',
}

/** 后端没给 source（或给了个我们还不认识的值）时，就照实说"原始内容"，不编一个读法。 */
function sourceLabel(source: string | undefined): string {
  return (source && SOURCE_LABEL[source]) || '原始内容'
}

/**
 * 导入回执的正文行。
 *
 * 序号**跟着实际有几行走**，不写死在模板里：只导了课表时，从前那版会显示
 * "1 课表 / 3 写进画像"—— 中间那个 2 因为条件渲染整行消失，于是序号看起来像缺了一条。
 */
const resultRows = computed(() => {
  const result = importResult.value
  if (!result) return []
  const rows: { key: string; label: string; detail: string; src: string }[] = []
  if (result.courses) {
    rows.push({
      key: 'courses',
      label: '课表',
      detail: `${result.term || '本学期'} · ${result.courses} 门课`,
      src: '课表',
    })
  }
  if (result.grades) {
    rows.push({
      key: 'grades',
      label: '成绩单',
      detail: `${result.grades} 门成绩`,
      src: '成绩单',
    })
  }
  if (result.wrote_profile?.length) {
    rows.push({
      key: 'profile',
      label: '写进画像',
      detail: `${result.wrote_profile.join(' / ')} 已标记为已拿到 —— 采集清单跟着更新`,
      src: '画像 · 摘要',
    })
  }
  return rows
})

/** 读的时候发现、但不足以拒绝的那几条（例如有课没读出上课时间） */
const resultNotes = computed(() => importResult.value?.notes ?? [])

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
        : '传教务系统的课表/成绩文件，或整页复制粘贴 · 不用登录、不用授权'
    "
    from="collect"
    @close="close"
  >
    <!-- 导入那一面是**两栏**（课表 / 成绩单），所以它比核验那一面宽一档 -->
    <div class="bind" :class="{ 'bind--wide': mode === 'academic' }">
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
          <span class="tabs__d">传文件或粘贴 · 不碰账号</span>
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
              它们在<b>你学校的教务系统</b>里。那套系统没有对外的数据通道，
              我们不去替你登录 —— 你自己导出一份传上来，我们负责读懂它；
              你校内账号的密码一次都不经过任何人。
            </p>
          </section>

          <!--
            三步走成**一行**（窄屏自动折行）。

            此前是三条各占两行的大条目，占掉近 200px，把真正的动作（选文件、
            那颗导入按钮）挤到了折叠线以下 —— 讲清怎么拿数据不该以"看不见操作"为代价。
          -->
          <ol class="rail">
            <li><span class="rail__n mono">1</span>打开学校的课表页 / 成绩页</li>
            <li><span class="rail__n mono">2</span>导出一份，或整页 Ctrl+A 复制</li>
            <li><span class="rail__n mono">3</span>传到下面，课表归课表、成绩归成绩</li>
          </ol>

          <form class="form" novalidate @submit.prevent="doImport">
            <!--
              两栏**平级**：课表与成绩单互不依赖，没有"先弄哪个"的先后。
              每一栏自己收一份东西（文件或粘贴的原文），所以两栏长得一样、行为也一样。
            -->
            <div class="slots">
              <section class="slot" :class="{ 'is-filled': !!coursesFile }">
                <header class="slot__head">
                  <h4 class="slot__t">课表</h4>
                  <span class="label slot__hint">
                    {{ coursesFile ? '已选好' : '课表页整页复制，或导出文件' }}
                  </span>
                  <button
                    v-if="coursesFile"
                    class="label slot__x"
                    type="button"
                    @click="setFile('courses', null)"
                  >
                    移除
                  </button>
                </header>

                <label
                  class="drop"
                  :class="{ 'is-filled': !!coursesFile, 'is-over': dragging === 'courses' }"
                  @dragover="onDragOver($event, 'courses')"
                  @dragleave="onDragLeave('courses')"
                  @drop="onDrop($event, 'courses')"
                >
                  <input
                    type="file"
                    accept=".txt,.csv,.html,.htm,.json"
                    @change="pickFile($event, 'courses')"
                  >
                  <svg class="drop__icon" viewBox="0 0 34 40" aria-hidden="true">
                    <path
                      d="M3 3.6h19l9 9v23.8a1.6 1.6 0 0 1-1.6 1.6H3a1.6 1.6 0 0 1-1.6-1.6V5.2A1.6 1.6 0 0 1 3 3.6Z"
                      fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"
                    />
                    <path
                      d="M22 3.6v9h9" fill="none" stroke="currentColor" stroke-width="1.7"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M9 23h16M9 29h11" stroke="currentColor" stroke-width="1.7"
                      stroke-linecap="round"
                    />
                  </svg>
                  <template v-if="coursesFile">
                    <span class="drop__name mono">{{ coursesFile.name }}</span>
                    <span class="label drop__meta">{{ fileSize(coursesFile.size) }} · 点一下换一份</span>
                  </template>
                  <template v-else>
                    <span class="drop__t">把文件拖到这里，或点一下选文件</span>
                    <span class="label drop__meta">.json · .csv · .txt · .html</span>
                  </template>
                </label>

                <button
                  class="disclose slot__paste"
                  type="button"
                  :aria-expanded="pasteOpen.courses"
                  @click="pasteOpen.courses = !pasteOpen.courses"
                >
                  <span class="caret" aria-hidden="true">›</span>
                  {{ coursesFile ? '改用整页复制粘贴' : '没有文件？直接粘贴原文' }}
                </button>
                <textarea
                  v-if="pasteOpen.courses"
                  v-model="coursesText"
                  name="jw-courses"
                  rows="6"
                  spellcheck="false"
                  placeholder="在课表页 Ctrl+A 全选复制，粘贴到这里"
                  @input="onTyped('courses')"
                  @paste="onPasted"
                />
              </section>

              <section class="slot" :class="{ 'is-filled': !!gradesFile }">
                <header class="slot__head">
                  <h4 class="slot__t">成绩单</h4>
                  <span class="label slot__hint">
                    {{ gradesFile ? '已选好' : '成绩页整页复制，或导出文件' }}
                  </span>
                  <button
                    v-if="gradesFile"
                    class="label slot__x"
                    type="button"
                    @click="setFile('grades', null)"
                  >
                    移除
                  </button>
                </header>

                <label
                  class="drop"
                  :class="{ 'is-filled': !!gradesFile, 'is-over': dragging === 'grades' }"
                  @dragover="onDragOver($event, 'grades')"
                  @dragleave="onDragLeave('grades')"
                  @drop="onDrop($event, 'grades')"
                >
                  <input
                    type="file"
                    accept=".txt,.csv,.html,.htm,.json"
                    @change="pickFile($event, 'grades')"
                  >
                  <svg class="drop__icon" viewBox="0 0 34 40" aria-hidden="true">
                    <path
                      d="M3 3.6h19l9 9v23.8a1.6 1.6 0 0 1-1.6 1.6H3a1.6 1.6 0 0 1-1.6-1.6V5.2A1.6 1.6 0 0 1 3 3.6Z"
                      fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"
                    />
                    <path
                      d="M22 3.6v9h9" fill="none" stroke="currentColor" stroke-width="1.7"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M9 23h16M9 29h11" stroke="currentColor" stroke-width="1.7"
                      stroke-linecap="round"
                    />
                  </svg>
                  <template v-if="gradesFile">
                    <span class="drop__name mono">{{ gradesFile.name }}</span>
                    <span class="label drop__meta">{{ fileSize(gradesFile.size) }} · 点一下换一份</span>
                  </template>
                  <template v-else>
                    <span class="drop__t">把文件拖到这里，或点一下选文件</span>
                    <span class="label drop__meta">.json · .csv · .txt · .html</span>
                  </template>
                </label>

                <button
                  class="disclose slot__paste"
                  type="button"
                  :aria-expanded="pasteOpen.grades"
                  @click="pasteOpen.grades = !pasteOpen.grades"
                >
                  <span class="caret" aria-hidden="true">›</span>
                  {{ gradesFile ? '改用整页复制粘贴' : '没有文件？直接粘贴原文' }}
                </button>
                <textarea
                  v-if="pasteOpen.grades"
                  v-model="gradesText"
                  name="jw-grades"
                  rows="5"
                  spellcheck="false"
                  placeholder="在成绩页全选复制，粘贴到这里"
                  @input="onTyped('grades')"
                  @paste="onPasted"
                />
              </section>
            </div>

            <!--
              学校与学期**并成一行**、紧挨着：它们是同一件小事（这份数据属于哪一学期），
              又是选填 —— 各占半行铺满整幅会让人以为必须填。
            -->
            <div class="meta">
              <label class="meta__f">
                <span class="label">学校（可留空）</span>
                <input v-model="school" type="text" autocomplete="off" placeholder="例如 某某大学">
              </label>
              <label class="meta__f">
                <span class="label">学期（可留空）</span>
                <input v-model="term" type="text" autocomplete="off" placeholder="多数情况能从原文读到">
              </label>
            </div>

            <!--
              读不出来的原话直接摆出来（后端会写清"改哪里"）。
              它不缩成一句"导入失败"：失败的原因正是用户要动手改的那一处。
            -->
            <p v-if="importError" class="alert" role="alert">{{ importError }}</p>
            <p v-else-if="autoHint || importing" class="label field__auto">
              {{ autoHint || '正在读你传上来的内容…' }}
            </p>

            <div class="actions">
              <button class="btn primary" type="submit" :disabled="!importReady || importing">
                {{ importing ? '正在读…' : importLabel }}
              </button>
              <span class="label promise">
                读不出来会说清是哪里不对：缺表头 / 版式不认识 / 传的是二进制文件。
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
            <p class="label result__how">
              这次导入读的是「{{ sourceLabel(importResult.source) }}」
            </p>

            <ol class="steps">
              <li v-for="(row, i) in resultRows" :key="row.key">
                <span class="steps__n mono">{{ i + 1 }}</span>
                <span class="steps__label">{{ row.label }}</span>
                <span class="steps__detail">{{ row.detail }}</span>
                <span class="label steps__src">{{ row.src }}</span>
              </li>
              <li v-for="(note, i) in resultNotes" :key="`note-${i}`" class="steps--empty">
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
  display: flex; flex-direction: column; gap: var(--s4);
  background: var(--n-1);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--e-4);
}
/* 导入那一面：两栏数据槽要的是宽度，不是更长的行 */
.bind--wide { width: min(880px, 100%); }

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

/*
 * 两栏数据槽。
 *
 * 它们是这一屏的主体，所以给它俩最大的面积：并排、等高、各自把一个**投放口**
 * 摆在正中。此前那两栏是"一个文本框 + 一行虚线的小字"，看起来像两种不同的东西；
 * 现在两栏一模一样 —— 课表与成绩单本来就是平行的两份数据。
 */
/*
 * `align-items: start`：两栏各自高。
 *
 * 默认的 stretch 会把另一栏也拉高 —— 一栏点开粘贴区，旁边那栏底下就空出一大块，
 * 看起来像"这块还没画完"。各自贴着自己的内容收尾才对。
 */
.slots {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: var(--s3);
}

.slot {
  display: flex; flex-direction: column; gap: var(--s2);
  padding: var(--s3) var(--s3) var(--s3);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-md);
  background: var(--n-1);
  transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
/*
 * 选好文件的那一栏：**只换边框色**，不换底色、不加阴影。
 * 底色一换，两栏就不再平级了（"这栏重要、那栏不重要"），而它俩本来就一样重要。
 */
.slot.is-filled { border-color: var(--accent); }

.slot__head { display: flex; align-items: baseline; gap: var(--s2); }
.slot__t { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.slot__hint { color: var(--ink-faint); }
.slot__x { margin-left: auto; color: var(--ink-3); }
.slot__x:hover { color: var(--warn); text-decoration: underline; }

/*
 * 投放口。
 *
 * 原生 `<input type="file">` 在每个浏览器里长得都不一样（还带着一个几十年前的
 * 灰按钮），所以把它藏起来、整张卡可点；**藏而不删**：它仍是可聚焦的控件，
 * 焦点环由 `.drop:focus-within` 画在卡片上 —— 键盘用户看得见自己在哪。
 */
.drop {
  position: relative;
  display: grid; place-items: center; gap: 4px;
  min-height: 112px; padding: var(--s3) var(--s2);
  border: 1.5px dashed var(--line-3); border-radius: var(--r-sm);
  background: var(--fill-subtle);
  text-align: center;
  cursor: pointer;
  transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.drop:hover { border-color: var(--line-4); background: var(--fill-hover); }
/* 拖到这一栏上面：边框变实线（"就是这儿"），比换色更快读懂 */
.drop.is-over { border-style: solid; border-color: var(--accent); background: var(--accent-soft); }
.drop.is-filled { border-style: solid; border-color: var(--line-3); background: transparent; }
.drop:focus-within { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.drop input[type="file"] {
  position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
.drop__icon { width: 30px; height: 35px; color: var(--ink-3); }
.drop.is-filled .drop__icon { color: var(--accent); }
.drop__t { font-size: var(--fs-small); color: var(--ink-2); }
.drop__meta { color: var(--ink-faint); }
/* 文件名：等宽，长名字折行而不是撑破卡片 */
.drop__name { font-size: var(--t-xs); color: var(--ink-1); overflow-wrap: anywhere; }

/* 粘贴是备选：一条不抢眼的文字开关，点开才展开输入框 */
.slot__paste { align-self: flex-start; }

.slot textarea {
  width: 100%; padding: var(--s3);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-sm);
  background: var(--n-1);
  font-family: var(--font-mono); font-size: 12px; line-height: 1.6;
  resize: vertical; min-height: 96px;
  white-space: pre; overflow-wrap: normal; overflow-x: auto;
}
.slot textarea:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

/* 学校 / 学期：一行两格，选填 */
.meta { display: flex; flex-wrap: wrap; gap: var(--s3); }
.meta__f { display: grid; gap: 5px; flex: 1 1 210px; max-width: 320px; }
.meta__f input {
  height: 38px; padding: 0 var(--s3);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-sm);
  background: var(--n-1); font-size: var(--fs-small);
  letter-spacing: normal; font-family: var(--font-sans);
}
.meta__f input:hover { border-color: var(--line-3); }
.meta__f input:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

/* 读不出来的原话：左侧一条警示线，不铺满整块橙 —— 这是提示，不是警报屏 */
.alert {
  padding: var(--s2) var(--s3) var(--s2) var(--s3);
  border-left: 3px solid var(--warn);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
  background: var(--mk-orange-soft);
  font-size: var(--fs-small); line-height: 1.72; color: var(--ink-1);
}

/*
 * 三步的窄条：一颗浅底胶囊一步。
 *
 * 编号留在胶囊里（这是个真的序列，不是装饰），但每一步只有一行 —— 一行的说明
 * 足够让人照做，两行的说明会把这颗导入按钮挤出屏幕。
 */
.rail { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--s2) var(--s2); }
.rail li {
  display: inline-flex; align-items: baseline; gap: 6px;
  padding: 5px var(--s3);
  border: var(--bw) solid var(--line-1); border-radius: var(--r-pill);
  background: var(--fill-subtle);
  font-size: var(--fs-small); color: var(--ink-2);
}
.rail__n { color: var(--accent); font-weight: 600; }

.actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s3); }
/*
 * 没东西可导时的按钮：**看起来就是"现在点不了"**。
 *
 * 此前 disabled 只有行为、没有样子 —— 一颗实心绿的按钮点下去什么都不发生，
 * 用户会以为是自己点错了地方。
 */
.actions .btn.primary:disabled { opacity: 0.42; box-shadow: none; transform: none; }
.actions .btn.primary:disabled:hover { opacity: 0.42; transform: none; }
.link { color: var(--accent); font-size: var(--fs-small); }
.link:hover { text-decoration: underline; }
.promise { color: var(--ink-3); line-height: 1.7; flex: 1 1 340px; max-width: 62ch; }

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

/* 窄屏：两栏并排会各自挤成一条窄缝，改成一上一下 */
@media (max-width: 720px) {
  .bind { padding: var(--s4) var(--s4) var(--s5); gap: var(--s4); }
  .slots { grid-template-columns: minmax(0, 1fr); }
  .meta__f { max-width: none; }
}
</style>
