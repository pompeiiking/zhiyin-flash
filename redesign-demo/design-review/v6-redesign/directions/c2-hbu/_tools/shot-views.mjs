/* =============================================================================
 * c2-hbu 视图截图工具
 * -----------------------------------------------------------------------------
 * 为什么自己写：现有截图工具都是打真实应用（127.0.0.1:5180 的 hash 路由），
 * 而本目录是**独立样张**（file:// 直开），而且需要"同一视图 × 主色 × 主题 × 密度 × 宽度"
 * 的组合截图 —— 这是三轴接线的验收手段，现成工具做不到。
 *
 * 用法（在 directions/c2-hbu 下）：
 *   node _tools/shot-views.mjs --out _shots/now --views all --widths 1280,390
 *   node _tools/shot-views.mjs --views chat --widths 1280 --accent blue,red --theme light,dark
 *
 * 参数：
 *   --out     输出目录（默认 _shots/now）
 *   --views   all 或逗号分隔的视图 key（对应 index.html 里 .view[data-view]）
 *   --widths  逗号分隔（默认 1280）
 *   --height  视口高（默认 900）
 *   --accent  blue,red（默认 blue）
 *   --theme   light,dark（默认 light）
 *   --style   normal,dense（默认 normal）
 *   --settle  每次导航后等待毫秒（默认 450）
 *   --full    整页截图（默认只截视口）
 *   --tag     文件名前缀（默认空）
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
/* --file：指向某个预览文件（多视图并行施工时各截各的） */
const iFile = process.argv.indexOf('--file');
const FILE_URL = pathToFileURL(
  iFile >= 0 ? path.resolve(DIR, process.argv[iFile + 1]) : path.join(DIR, 'index.html')
).href;

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return dflt;
  const next = process.argv[i + 1];
  if (next === undefined || next.startsWith('--')) return true;
  return next;
}
const OUT = path.join(DIR, String(arg('out', '_shots/now')));
const VIEWS_ARG = String(arg('views', 'all'));
const WIDTHS = String(arg('widths', '1280')).split(',').map(Number);
const HEIGHT = Number(arg('height', 900));
const ACCENTS = String(arg('accent', 'blue')).split(',');
const THEMES = String(arg('theme', 'light')).split(',');
const STYLES = String(arg('style', 'normal')).split(',');
const SETTLE = Number(arg('settle', 450));
const FULL = arg('full', false) === true;
const TAG = String(arg('tag', ''));

fs.mkdirSync(OUT, { recursive: true });

/* 视图清单：问页面自己（只认主区里的视图根，不认 <html data-view>） */
async function discoverViews(page) {
  await page.goto(FILE_URL, { waitUntil: 'load' });
  const list = await page.evaluate(() =>
    Array.from(document.querySelectorAll('.main > .main__scroll[data-view]')).map((el) =>
      el.getAttribute('data-view')
    )
  );
  return list.length ? list : ['chat'];
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: WIDTHS[0], height: HEIGHT } });
await page.emulateMedia({ reducedMotion: 'no-preference' });

const allViews = VIEWS_ARG === 'all' ? await discoverViews(page) : VIEWS_ARG.split(',');
const written = [];

for (const width of WIDTHS) {
  for (const theme of THEMES) {
    for (const accent of ACCENTS) {
      for (const style of STYLES) {
        for (const view of allViews) {
          await page.setViewportSize({ width, height: HEIGHT });
          await page.goto(`${FILE_URL}#/${view}`, { waitUntil: 'load' });
          /* 用**真实的演示台按钮**切三轴，而不是手改 html 属性：
             手改属性会漏掉 applyDemo() 的其它副作用（用户气泡令牌、demoNote 文案、
             aria-pressed 状态），截出来的图与人真的点过不一致 —— 第一版就是这么错的
             （深色图看起来还是浅色，因为 --bg-field 是 applyDemo 之外的另一条路径）。 */
          await page.evaluate(
            ([a, t, s]) => {
              const click = (set, val) => {
                const b = document.querySelector(`.segb[data-set="${set}"][data-val="${val}"]`);
                if (b) b.click();
              };
              click('accent', a);
              click('theme', t);
              click('style', s);
            },
            [accent, theme, style]
          );
          await page.waitForTimeout(SETTLE);
          const name = [TAG, String(width), view, accent, theme, style].filter(Boolean).join('-') + '.png';
          const file = path.join(OUT, name);
          await page.screenshot({ path: file, fullPage: FULL });
          const overflow = await page.evaluate(() => ({
            sw: document.documentElement.scrollWidth,
            cw: document.documentElement.clientWidth,
            hidden: document.querySelectorAll('.main > .main__scroll:not([data-active="true"])').length,
          }));
          written.push({ name, overflow: overflow.sw > overflow.cw ? `${overflow.sw}>${overflow.cw}` : 'ok' });
        }
      }
    }
  }
}
await browser.close();

const bad = written.filter((w) => w.overflow !== 'ok');
for (const w of written) console.log(`[ok] ${w.name.padEnd(46)} overflow=${w.overflow}`);
console.log(`\n${written.length} 张 → ${path.relative(DIR, OUT)}`);
if (bad.length) {
  console.log(`[FAIL] ${bad.length} 张横向溢出：` + bad.map((b) => b.name).join(', '));
  process.exitCode = 1;
}
