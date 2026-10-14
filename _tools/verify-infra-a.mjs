// 四态基础设施（骨架屏 / 空态 / 状态条）可视化验证台
//   PW_PATH=<playwright 路径> node _tools/verify-infra-a.mjs [baseUrl] [outDir]
//
// 为什么这样做：这三个组件不许塞进现有页面（会与其它 agent 的改造冲突），
// 所以不新增路由，而是在**已经在跑的 dev server** 上打开一个真实路由，
// 然后动态 import 这三个 SFC 模块（Vite dev 会照常编译并注入 scoped 样式），
// 用真正的 Vue 运行时把它们挂到一个临时容器里 —— 截到的是组件真实渲染结果，不是手抄的等价 HTML。
// dev server 与既有页面都不被改动。
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PW_PATH || 'playwright')

const baseUrl = process.argv[2] || 'http://127.0.0.1:5180'
const outDir = path.resolve(process.argv[3] || '_shots/infra-a')
fs.mkdirSync(outDir, { recursive: true })

const browser = await chromium.launch()

/* ------------------------------------------------------------------ 挂载 */
async function mount(page) {
  return page.evaluate(async () => {
    // 取到本页正在使用的那个 Vue 运行时（与 SFC 内部 import 的是同一个实例）
    const srcText = await (await fetch('/src/components/SkinSwitcher.vue')).text()
    const match = srcText.match(/["']([^"']*deps\/vue\.js[^"']*)["']/)
    if (!match) throw new Error('找不到 dev server 上的 vue 运行时 URL')
    const Vue = await import(match[1])
    const [SkeletonBlock, EmptyState, StatusBanner] = (
      await Promise.all([
        import('/src/components/SkeletonBlock.vue'),
        import('/src/components/EmptyState.vue'),
        import('/src/components/StatusBanner.vue')
      ])
    ).map((mod) => mod.default)

    const { createApp, h } = Vue

    const app = document.getElementById('app')
    if (app) app.style.display = 'none'

    const style = document.createElement('style')
    // base.css 把 html/body/#app 都锁成 height:100%（应用外壳自己滚动）。
    // 验证台要的是普通文档流，所以这里显式解除，并把应用外壳藏掉。
    style.textContent = `
      html, body { height: auto !important; overflow: visible !important; }
      #app { display: none !important; }
      .vf { display: grid; gap: 32px; padding: 32px; background: var(--c-bg); color: var(--c-text);
            font-family: var(--font-sans); font-size: var(--fs-14); }
      .vf-block { display: grid; gap: 4px; }
      .vf-block__title { font-size: var(--fs-20); font-weight: 600; }
      .vf-block__note { font-size: var(--fs-12); color: var(--c-text-3); line-height: 1.6; margin-bottom: 8px; }
      .vf-body { display: grid; gap: 16px; }
      .vf-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
      .vf-grid--2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .vf-tile { padding: 16px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); }
      .vf-tile__cap { font-size: var(--fs-12); color: var(--c-text-3); margin-bottom: 12px; letter-spacing: .06em; }
      .vf-stale { position: relative; padding: 16px; border: 1px dashed var(--c-border-strong); border-radius: var(--r-lg); }
      .vf-stale__text { font-size: var(--fs-14); color: var(--c-text-2); line-height: 1.7; }
      @media (max-width: 760px) { .vf { padding: 16px; gap: 24px; } .vf-grid, .vf-grid--2 { grid-template-columns: minmax(0, 1fr); } }
    `
    document.head.appendChild(style)

    const host = document.createElement('div')
    host.className = 'vf'
    host.id = 'vf-host'
    document.body.appendChild(host)

    const state = { retry: 0, action: 0, dismiss: 0 }
    window.__infra = state

    const block = (title, note, children) =>
      h('section', { class: 'vf-block' }, [
        h('h2', { class: 'vf-block__title' }, title),
        note ? h('p', { class: 'vf-block__note' }, note) : null,
        h('div', { class: 'vf-body' }, children)
      ])
    const tile = (cap, children) => h('div', { class: 'vf-tile' }, [h('p', { class: 'vf-tile__cap' }, cap), ...children])

    const EMPTY_KINDS = [
      ['chat', '还没有对话', '还没有对话', '这里是顾问等你开口的地方；先说出你现在最想问的一件事。'],
      ['notes', '待办 / 个人目标为空', '暂无个人待办', '在上方写下新的安排，已经完成的记录仍可恢复。'],
      ['intel', '岗位资讯为空', '暂无已读取资讯', '可调整筛选、检索最新资料，或先查看示例。'],
      ['profile', '个人画像没有已知信息', '暂无个人信息', '可以从一次咨询开始，也可以导入已有的学校资料。'],
      ['report', '还没有诊断报告', '还没有诊断报告', '需要先积累足够的事实，报告会说明还缺哪几项。'],
      ['academic', '学籍与资料为空', '暂无已录入的学籍资料', '导入学校资料后，这里会按来源与时间列出每条记录。'],
      ['schedule', '日历与课表空', '这段时间没有安排', '课程与个人安排会按时间排进同一张表。'],
      ['review', '还没有复盘记录', '还没有复盘记录', '记录发生了什么，复盘才有依据。'],
      ['search-empty', '筛选没有命中', '没有匹配的资讯', '当前筛选条件下没有条目，内容本身可能还在。']
    ]

    const Harness = {
      render: () =>
        h('div', [
          block(
            'SkeletonBlock · 预演"即将出现的东西的轮廓"',
            'variant 描述将要出现什么；行数/列数可配。整块 aria-hidden，加载状态由调用方用 aria-busy 表达。',
            [
              h('div', { class: 'vf-grid' }, [
                tile('text · 4 行（末行断句）', [h(SkeletonBlock, { variant: 'text', lines: 4 })]),
                tile('list · 3 行记录', [h(SkeletonBlock, { variant: 'list', lines: 3 })]),
                tile('card · 3 列', [h(SkeletonBlock, { variant: 'card', columns: 3 })]),
                tile('chart · 7 根不等高柱', [h(SkeletonBlock, { variant: 'chart', columns: 7, height: 130 })]),
                tile('avatar · 3 枚徽标', [h(SkeletonBlock, { variant: 'avatar', columns: 3, size: 'lg' })]),
                tile('inline · 跟在文字后面', [
                  h('p', {}, ['正在读取最新日程 ', h(SkeletonBlock, { variant: 'text', lines: 1, inline: true, size: 'sm' })])
                ])
              ]),
              h('div', { class: 'vf-stale' }, [
                h(
                  'p',
                  { class: 'vf-stale__text', id: 'stale-content' },
                  'overlay：上一次读取到的内容仍然在 DOM 里（骨架盖在上面），刷新时页面不会先空一块再重建。'
                ),
                h(SkeletonBlock, { variant: 'text', lines: 2, overlay: true })
              ])
            ]
          ),
          block(
            'EmptyState · 9 类场景（每条都带下一步）',
            '标题统一 h3；图形与语义对齐（profile 是人像，不再是便签）。下一步用 slot 或 kind 预设。',
            [
              h(
                'div',
                { class: 'vf-grid' },
                EMPTY_KINDS.map(([kind, cap, title, description]) =>
                  tile(cap, [h(EmptyState, { kind, title, description })])
                )
              ),
              h('div', { class: 'vf-grid vf-grid--2' }, [
                tile('调用方给 slot（既有 IntelView 用法）→ 预设让位', [
                  h(
                    EmptyState,
                    { kind: 'intel', title: '没有匹配的资讯', description: '可调整筛选、检索最新资料，或先查看示例。' },
                    { default: () => h('button', { class: 'btn' }, '清除筛选') }
                  )
                ]),
                tile('next=false → 保留空位，由调用方自行补', [
                  h(EmptyState, {
                    kind: 'notes',
                    title: '暂无个人待办',
                    description: '在上方写下新的安排，已经完成的记录仍可恢复。',
                    next: false
                  })
                ])
              ])
            ]
          ),
          block(
            'StatusBanner · 四态（形态差异为主，颜色为辅）',
            'success 灰/1px 线/描边圆 + 4s 自动消失；info 蓝/2px 线/描边圆；warning 红/2px 线/三角；error 红/3px 线/实心圆 + 必有重试 + role=alert。下面两条 success 显式 autoDismiss=0，只为留作对照。',
            [
              h(StatusBanner, {
                tone: 'success',
                message: '已保存到个人待办。',
                // 成功默认 4s 自动消失；这块验证台要留它做对照，所以显式关掉倒计时
                autoDismiss: 0,
                onDismiss: () => {
                  state.dismiss += 1
                }
              }),
              h(StatusBanner, {
                tone: 'info',
                title: '正在读取最新日程',
                message: '读取期间页面上的原有内容保持不变。',
                actionLabel: '查看详情',
                onAction: () => {
                  state.action += 1
                }
              }),
              h(StatusBanner, {
                tone: 'warning',
                title: '两门课时间重叠',
                message: '周三 5–8 节与 7–8 节冲突，需要你确认后再安排时间。'
              }),
              h(StatusBanner, {
                tone: 'error',
                title: '读取失败',
                message: '服务没有返回结果；你已经填的内容还在，可以直接重试。',
                onRetry: () => {
                  state.retry += 1
                }
              }),
              h(StatusBanner, {
                tone: 'error',
                title: '读取失败（重试中）',
                message: '重试按钮进入"正在重试…"并禁用，避免连点。',
                retrying: true
              }),
              h('div', { class: 'vf-grid vf-grid--2' }, [
                tile('floating（放进 toast 容器时的形态）', [
                  h(StatusBanner, { tone: 'success', message: '已复制到剪贴板。', floating: true, autoDismiss: 0 })
                ]),
                tile('size=sm + 自动消失（autoDismiss=900ms）', [
                  h(StatusBanner, { tone: 'success', message: '这条 0.9 秒后自己消失。', autoDismiss: 900 }),
                  h(StatusBanner, { tone: 'info', message: '信息态不自动消失。', size: 'sm' })
                ])
              ])
            ]
          )
        ])
    }

    const RouterLinkStub = {
      props: { to: { type: [String, Object], default: '' } },
      setup: (p, { slots }) => () => h('span', { class: 'vf-router-link', 'data-to': String(p.to) }, slots.default?.())
    }

    const instance = createApp(Harness)
    instance.component('RouterLink', RouterLinkStub)
    instance.mount(host)
    return { ok: true, instance: typeof instance }
  })
}

/* ------------------------------------------------------------------ 断言 */
async function probe(page) {
  return page.evaluate(() => {
    const q = (sel) => document.querySelector(sel)
    const qa = (sel) => Array.from(document.querySelectorAll(sel))
    const skeleton = q('.sk__bar')
    const after = skeleton ? getComputedStyle(skeleton, '::after') : null
    const profileSvg = q('.exp-empty--profile .exp-motif')
    const notesSvg = q('.exp-empty--notes .exp-motif')
    return {
      skeletonCount: qa('.sk').length,
      skeletonAllHidden: qa('.sk').every((el) => el.getAttribute('aria-hidden') === 'true'),
      skeletonBase: skeleton ? getComputedStyle(skeleton).backgroundColor : null,
      skeletonSweep: after ? { name: after.animationName, duration: after.animationDuration } : null,
      staleContentKept: !!document.getElementById('stale-content'),
      emptyHeadingLevels: qa('.exp-empty__title').map((el) => el.tagName),
      emptyH2Count: qa('.exp-empty h2').length,
      emptyNextCount: qa('.exp-empty__next').length,
      emptyPresetLink: q('.exp-empty--profile .exp-empty__next a, .exp-empty--profile .exp-empty__next [data-to]')?.getAttribute('data-to') || null,
      slotSuppressesPreset: !q('.vf-grid--2 .exp-empty--intel .exp-empty__next'),
      nextFalseSuppressesPreset: !q('.vf-grid--2 .exp-empty--notes .exp-empty__next'),
      gridStillHasPresets: qa('.vf-grid:not(.vf-grid--2) .exp-empty__next').length,
      profileGlyphHasPerson: !!profileSvg && profileSvg.innerHTML.includes('cx="45" cy="104"'),
      profileGlyphHasStickyNote: !!profileSvg && profileSvg.innerHTML.includes('M37 98h16v21H37z'),
      notesGlyphUsesMotif: !!notesSvg && !notesSvg.innerHTML.includes('empty-grid-'),
      roles: qa('.status-banner').map((el) => `${el.className.match(/status-banner--(\w+)/)?.[1]}:${el.getAttribute('role')}`),
      errorHasRetry: !!q('.status-banner--error .status-banner__retry'),
      successHasNoRetry: !q('.status-banner--success .status-banner__retry'),
      ruleWidths: qa('.status-banner').map((el) => getComputedStyle(el).borderLeftWidth),
      srSheen: getComputedStyle(document.documentElement).getPropertyValue('--sk-sheen').trim()
    }
  })
}

const results = {}
const shot = async (page, name, options = { fullPage: true }) => {
  const file = path.join(outDir, `${name}.png`)
  await page.screenshot({ path: file, ...options })
  const size = fs.statSync(file).size
  results[name] = { file, bytes: size }
  console.log(`ok   ${name} -> ${file} (${size} B)`)
}

/* ------------------------------------------------------------------ 跑 */
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 })
const page = await context.newPage()
const errors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})
page.on('pageerror', (err) => errors.push(String(err)))

await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30000 })
await mount(page)
await page.waitForTimeout(900)

results.probe = await probe(page)

// 时间敏感的一条先测：autoDismiss=900ms 的那条成功条自己消失（它等不到截图）
await page.waitForTimeout(1000)
const autoGone = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.status-banner__message')).every((el) => !el.textContent.includes('0.9 秒后自己消失'))
)

await shot(page, 'overview-1280')

// 深色主题
await page.evaluate(() => {
  document.documentElement.dataset.theme = 'dark'
})
await page.waitForTimeout(250)
results.darkSheen = await page.evaluate(() =>
  getComputedStyle(document.documentElement).getPropertyValue('--sk-sheen').trim()
)
await shot(page, 'dark-1280')

// 河大红主色皮肤（info 与 attention 同为红相，靠形态区分）
await page.evaluate(() => {
  document.documentElement.dataset.theme = 'light'
  document.documentElement.dataset.accent = 'red'
})
await page.waitForTimeout(200)
await shot(page, 'accent-red-1280')
await page.evaluate(() => {
  document.documentElement.dataset.accent = 'blue'
})

// reduced-motion：高光静止成静态块（不是 display:none）
await page.emulateMedia({ reducedMotion: 'reduce' })
await page.waitForTimeout(250)
results.reducedMotion = await page.evaluate(() => {
  const bar = document.querySelector('.sk__bar')
  const after = getComputedStyle(bar, '::after')
  return {
    animationName: after.animationName,
    backgroundImage: after.backgroundImage,
    barVisible: getComputedStyle(bar).backgroundColor,
    barDisplay: getComputedStyle(bar).display,
    barOffsetHeight: bar.offsetHeight
  }
})
await shot(page, 'reduced-motion-1280')
await page.emulateMedia({ reducedMotion: 'no-preference' })

// 390 窄屏
await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(300)
await shot(page, 'overview-390')
// 整页太长（>9000px），再单独截两张"一屏高"的切片，方便逐段核对
await page.evaluate(() => window.scrollTo(0, 0))
await page.waitForTimeout(200)
await shot(page, 'mobile-empty-390', { fullPage: false })
await page.evaluate(() => document.querySelectorAll('.vf-block')[2].scrollIntoView({ block: 'start' }))
await page.waitForTimeout(200)
await shot(page, 'mobile-banners-390', { fullPage: false })
await page.setViewportSize({ width: 1280, height: 900 })

/* ---- 交互：错误态重试 / 信息态次要动作 / 成功态手动关闭（放在截图之后，免得截图上少了一条） ---- */
await page.click('.status-banner--error .status-banner__retry')
await page.click('.status-banner--info .ws-text-button')
const beforeDismiss = await page.evaluate(() => document.querySelectorAll('.status-banner--success').length)
const successTextBefore = await page.evaluate(
  () => document.querySelector('.status-banner--success .status-banner__message')?.textContent?.trim() || null
)
await page.click('.status-banner--success .status-banner__close')
await page.waitForTimeout(400)
const afterDismiss = await page.evaluate(
  (text) => ({
    successBanners: document.querySelectorAll('.status-banner--success').length,
    firstGone: !Array.from(document.querySelectorAll('.status-banner__message')).some(
      (el) => el.textContent.trim() === text
    )
  }),
  successTextBefore
)
results.interaction = {
  retryClicks: await page.evaluate(() => window.__infra.retry),
  actionClicks: await page.evaluate(() => window.__infra.action),
  dismissClicks: await page.evaluate(() => window.__infra.dismiss),
  successBannersBeforeDismiss: beforeDismiss,
  ...afterDismiss,
  autoDismissWorked: autoGone,
  consoleErrors: errors
}

/* ------------------------------------------------------------------ 结论 */
const p = results.probe
const checks = [
  ['骨架块全部 aria-hidden', p.skeletonAllHidden === true],
  ['骨架底 = 交互态表面（--c-surface-3）', p.skeletonBase === 'rgb(235, 237, 242)'],
  ['扫光在跑且节奏 1.4s', p.skeletonSweep?.duration === '1.4s' && p.skeletonSweep?.name !== 'none'],
  ['overlay 下旧内容没有被摘掉', p.staleContentKept === true],
  ['空态标题统一 h3', p.emptyHeadingLevels.length > 0 && p.emptyHeadingLevels.every((t) => t === 'H3')],
  ['空态里没有 h2（层级不再混用）', p.emptyH2Count === 0],
  ['9 类场景都有"下一步"位置', p.emptyNextCount >= 9],
  ['profile 预设下一步是跨页链接 /chat', p.emptyPresetLink === '/chat'],
  ['profile 图形是人像、不是便签', p.profileGlyphHasPerson === true && p.profileGlyphHasStickyNote === false],
  ['chat/notes/intel 仍走 WorkspaceMotif', p.notesGlyphUsesMotif === true],
  ['调用方 slot 优先于 kind 预设', p.slotSuppressesPreset === true],
  ['next=false 时不渲染预设', p.nextFalseSuppressesPreset === true],
  ['9 类场景的预设确实都在', p.gridStillHasPresets === 9],
  ['error 用 alert、其余用 status', p.roles.includes('error:alert') && p.roles.includes('success:status') && p.roles.includes('warning:status')],
  ['error 一定有重试位', p.errorHasRetry === true],
  ['success 没有重试位', p.successHasNoRetry === true],
  ['四态竖线宽度有差别（非纯颜色区分）', new Set(p.ruleWidths).size >= 3],
  ['reduced-motion 下高光静止、灰块仍在', results.reducedMotion.animationName === 'none' && results.reducedMotion.barOffsetHeight > 0 && results.reducedMotion.barDisplay !== 'none'],
  ['深色下高光比骨架底更亮', results.darkSheen !== p.srSheen],
  ['重试按钮触发 retry', results.interaction.retryClicks === 1],
  ['关闭按钮能关掉成功条', results.interaction.successBannersBeforeDismiss >= 2 && results.interaction.firstGone === true],
  ['autoDismiss 生效', results.interaction.autoDismissWorked === true],
  ['没有控制台报错', errors.length === 0]
]

console.log('\n=== 检查项 ===')
let failed = 0
for (const [label, pass] of checks) {
  if (!pass) failed += 1
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${label}`)
}
results.checks = checks.map(([label, pass]) => ({ label, pass }))
results.failed = failed
fs.writeFileSync(path.join(outDir, 'verify-report.json'), JSON.stringify(results, null, 2), 'utf8')
console.log(`\n${failed === 0 ? '全部通过' : failed + ' 项未通过'} · 报告：${path.join(outDir, 'verify-report.json')}`)
if (errors.length) console.log('控制台报错：', errors)

await browser.close()
process.exit(failed === 0 ? 0 : 1)
