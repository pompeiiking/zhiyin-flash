#!/usr/bin/env node
/**
 * 生成「大一到大四」页里那条操作路径用的界面截图。
 *
 * 为什么用真截图而不是设计稿：评审要看的是"产品用起来长什么样"，
 * 截图和跑起来的界面是同一份东西，改坏了截图就会跟着变 —— 设计稿不会。
 *
 * 用法：
 *   1. 另开一个终端跑 `npm run dev`（默认 http://127.0.0.1:5273）
 *   2. node scripts/shots.mjs
 * 可选：node scripts/shots.mjs --url http://127.0.0.1:5273 --width 1600 --height 1100
 *
 * 只用系统里已有的 Chrome / Edge，不装 puppeteer —— 少一个依赖，少一处会过期的东西。
 */

import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')
const OUT_DIR = join(ROOT, 'public', 'shots')

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

const BASE = arg('url', 'http://127.0.0.1:5273').replace(/\/$/, '')
const WIDTH = Number(arg('width', '1600'))
const HEIGHT = Number(arg('height', '1100'))

/** 截图清单：与 src/views/PathView.vue 里的 PATH、以及皮肤轴一一对应 */
const SHOTS = [
  { file: 'portal.png', hash: '#/' },
  /*
   * prefers-reduced-motion 这条路径必须有一张点名的截图。
   * 教训：皮肤轴的截图曾经只覆盖 4 种颜色组合，"减少动效"这条路径没人拍 ——
   * 于是门户在减少动效下整页绘制成纯白（DOM 完好、零报错），很久没被发现。
   *
   * 注：2026-10-11 起，**全部截图都带 `--force-prefers-reduced-motion`**
   * （原因见下面 spawn 参数里的长注释：只有它能让入场动画落到终点）。
   * 所以这一条现在与 `portal.png` 同路径 —— 保留它是为了**点名**：
   * 门户在减少动效下不许变白屏，这条判据必须在截图清单里看得见。
   */
  { file: 'portal-reduced.png', hash: '#/', flags: ['--force-prefers-reduced-motion'] },
  /*
   * 风格轴的两端各拍一张。教训：这条轴曾经"看起来像有、其实看不出"——
   * 只改卡片内距，全屏像素平均差 2.3 灰阶。现在密度改的是间距阶梯 + 行高 + 字号，
   * 这两张就是"它真的看得出"的证据（也防止以后有人把它改回去）。
   */
  { file: 'style-soft.png', hash: '#/home?style=soft' },
  { file: 'style-dense.png', hash: '#/home?style=dense' },
  { file: 'skin-dark-portal.png', hash: '#/?theme=dark' },
  { file: 'chat.png', hash: '#/chat?as=mid' },
  { file: 'chat-collected.png', hash: '#/chat?as=mid&collected=2' },
  /*
   * 裸链接（不带 ?as=）：验证"链接一定能打开"。
   * 这两张是回归证据 —— 曾经未登录打开内页会被弹回门户，评审看到的就是"链接坏了"。
   */
  { file: 'link-bare-chat.png', hash: '#/chat' },
  { file: 'link-bare-report.png', hash: '#/report' },
  /* 坏地址必须渲染成 404 页，不能是"外壳在、中间空白" —— 曾经就是这样，且控制台无报错 */
  { file: 'not-found.png', hash: '#/nope-does-not-exist' },
  { file: 'profile.png', hash: '#/profile?as=mid' },
  { file: 'report.png', hash: '#/report?as=mid' },
  { file: 'report-directions.png', hash: '#/report?as=mid&dir=d1' },
  { file: 'plan.png', hash: '#/plan?as=mid' },
  { file: 'review.png', hash: '#/review?as=mid' },
  { file: 'home.png', hash: '#/home?as=mid' },
  { file: 'nav-float.png', hash: '#/home?as=mid&float=1' },
  { file: 'home-freshman.png', hash: '#/home?as=mid&grade=freshman' },
  { file: 'path.png', hash: '#/path?as=mid' },
  { file: 'spec.png', hash: '#/spec' },
  // 皮肤：同一个页面，四套外观（浅/深 × 蓝/河大红，外加紧凑与柔和各一张）
  { file: 'skin-dark.png', hash: '#/home?as=mid&theme=dark' },
  { file: 'skin-dark-report.png', hash: '#/report?as=mid&theme=dark' },
  { file: 'skin-red.png', hash: '#/home?as=mid&accent=red' },
  { file: 'skin-dark-red.png', hash: '#/chat?as=mid&theme=dark&accent=red' },
  { file: 'skin-soft.png', hash: '#/report?as=mid&style=soft' },
  { file: 'skin-dense.png', hash: '#/plan?as=mid&style=dense' },
]

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean)

const browser = CANDIDATES.find((p) => existsSync(p))
if (!browser) {
  console.error('没找到 Chrome / Edge。设一个 CHROME_PATH 环境变量再跑。')
  process.exit(1)
}

mkdirSync(OUT_DIR, { recursive: true })
console.log(`浏览器：${browser}`)
console.log(`输出到：${OUT_DIR}\n`)

let failed = 0

for (const s of SHOTS) {
  const out = join(OUT_DIR, s.file)
  rmSync(out, { force: true })

  const url = `${BASE}/${s.hash}`
  const res = spawnSync(
    browser,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--no-first-run',
      '--disable-extensions',
      '--hide-scrollbars',
      '--force-device-scale-factor=1',
      `--window-size=${WIDTH},${HEIGHT}`,
      // 给 Vue 挂载 + 字体 + 过渡留时间
      '--virtual-time-budget=5000',
      /*
       * **让入场动画落到终点再拍**（2026-10-11 接手者补）。
       *
       * 实测缺陷：只有 `--virtual-time-budget` 时，`.stagger` 的入场动画会被冻在某一刻，
       * 于是最后一个条目以接近 0 的透明度被拍进交付图 ——
       * 例：`home.png` 里第 3 个任务项所在的一整条（y 880–959）**一个暗像素都没有**，
       * 而同一条用真实时间拍（CDP 等 3 秒）是 2715 个。而且它**不稳定**：
       * 同样参数连拍两次，一次 0、一次 1487。
       *
       * 为什么用 `--force-prefers-reduced-motion` 而不是加长 budget：
       * budget 从 5000 加到 20000 完全没用（动画时钟不跟着走）。
       * base.css 的 reduced-motion 分支把 `.stagger > * { animation: none }`，
       * 而入场动画的**终点**就是元素的自然状态（opacity 1 / translate 0），
       * 所以这样拍到的就是"动画跑完之后"的样子 —— 与真实浏览器的稳定态逐像素一致，
       * 且每次结果可复现。截图要的是"这一页长什么样"，不是"动画播到一半长什么样"。
       */
      '--force-prefers-reduced-motion',
      // 每张可以带自己的开关（例如 --force-prefers-reduced-motion）
      ...(s.flags ?? []),
      `--screenshot=${out}`,
      url,
    ],
    // 不捕获 stdout：headless Chrome 在受限环境下会因为管道报 EPERM
    { stdio: 'ignore' },
  )

  const ok = existsSync(out) && statSync(out).size > 0
  if (ok) {
    const kb = Math.round(statSync(out).size / 1024)
    console.log(`  ✓ ${s.file.padEnd(24)} ${kb} KB   ${url}`)
  } else {
    failed += 1
    console.log(`  ✗ ${s.file.padEnd(24)} 失败（exit ${res.status}）   ${url}`)
  }
}

console.log('')
if (failed) {
  console.error(`${failed} 张没生成。确认 dev server 起着（${BASE}）再跑一次。`)
  process.exit(1)
}
console.log(`全部 ${SHOTS.length} 张已生成。打开 #/path 就能看到它们嵌在操作路径里。`)
