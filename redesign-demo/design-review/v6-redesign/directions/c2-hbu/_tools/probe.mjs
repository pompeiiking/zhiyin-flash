/* =============================================================================
 * c2-hbu DOM 探针（只读，不改任何东西）
 * -----------------------------------------------------------------------------
 * 为什么需要它：这个项目上一轮的教训之一是"拿估感当数据"（HANDOFF §9.5）。
 * 改视觉之前先量，改完之后再量。本探针只做"量"这件事，不做判定以外的事。
 *
 * 用法（在 directions/c2-hbu 下）：
 *   node _tools/probe.mjs --sel "#viewIndexBtn"                  看某个元素的盒与计算样式
 *   node _tools/probe.mjs --tap --view profile                   盘该视图里 <44px 的可点元素
 *   node _tools/probe.mjs --wrap --view report                   找溢出/被挤到换行的元素
 *   node _tools/probe.mjs --lens --view profile                  看视角重组每个视角的组数与搬动条数
 *   node _tools/probe.mjs --views --width 1280                   逐视图量：高度、横向溢出、可点数
 *
 * 参数：--view <key>（默认 chat） --width（默认 1280） --height（默认 900）
 *       --accent/--theme/--style（默认 blue/light/normal） --reduce（开 prefers-reduced-motion）
 * ========================================================================== */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
/* --file：指向某个预览文件（并行施工时各量各的）
   node _tools/probe.mjs --file _shots/preview-report.html --views
   --url：改成量一个 http 地址（例如 _tools/serve.mjs 起的那份），用来确认
   "服务出去的那一份也能跑"，而不是只确认返回了 200 */
const iFile = process.argv.indexOf('--file');
const iUrl = process.argv.indexOf('--url');
const FILE_URL = iUrl >= 0
  ? process.argv[iUrl + 1]
  : pathToFileURL(
    iFile >= 0 ? path.resolve(DIR, process.argv[iFile + 1]) : path.join(DIR, 'index.html')
  ).href;

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return dflt;
  const next = process.argv[i + 1];
  if (next === undefined || next.startsWith('--')) return true;
  return next;
}
const VIEW = String(arg('view', 'chat'));
const WIDTH = Number(arg('width', 1280));
const HEIGHT = Number(arg('height', 900));
const ACCENT = String(arg('accent', 'blue'));
const THEME = String(arg('theme', 'light'));
const STYLE = String(arg('style', 'normal'));
const REDUCE = arg('reduce', false) === true;
const SEL = arg('sel', null);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });
await page.emulateMedia({ reducedMotion: REDUCE ? 'reduce' : 'no-preference' });

/* 页面里的 JS 异常一律抓下来。为什么要有这条：一个未捕获异常会把整个 IIFE 打断，
   后面的路由与引擎全都不跑，页面看起来"只是有点不对"。
   本项目吃过这个亏（app.js 的输入区代码在预览文件里空值报错）。 */
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') pageErrors.push('console.error: ' + m.text()); });

async function go(view) {
  await page.goto(`${FILE_URL}#/${view}`, { waitUntil: 'load' });
  /* 三轴走**真实的演示台按钮**（与 shot-views.mjs 一致）：手改 html 属性会漏掉
     applyDemo() 的其它副作用，量出来的计算样式与"人真的点过"不一样。 */
  await page.evaluate(([a, t, s]) => {
    const click = (set, val) => {
      const b = document.querySelector(`.segb[data-set="${set}"][data-val="${val}"]`);
      if (b) b.click();
    };
    click('accent', a);
    click('theme', t);
    click('style', s);
  }, [ACCENT, THEME, STYLE]);
  await page.waitForTimeout(500);
}

if (SEL) {
  await go(VIEW);
  const info = await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const keep = ['display', 'flexWrap', 'whiteSpace', 'width', 'height', 'padding', 'fontSize',
      'lineHeight', 'color', 'backgroundColor', 'gap', 'flex', 'maxWidth', 'minWidth', 'overflow', 'writingMode'];
    const styles = {};
    for (const k of keep) styles[k] = cs[k];
    return {
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      lines: el.getClientRects().length,
      text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
      styles,
    };
  }, SEL);
  console.log(info ? JSON.stringify(info, null, 2) : '找不到 ' + SEL);
}

if (arg('tap', false) === true) {
  await go(VIEW);
  const small = await page.evaluate(() => {
    /* ⚠ 必须用 root.querySelectorAll(sel) 而不是拼字符串：
       拼成 `'.main > ... ' + sel` 时，逗号列表里只有**第一个**选择器带上了祖先前缀，
       后面几个会匹配整个文档 —— 第一版就是这么把外壳和对话页的元素算进每个视图的。 */
    const root = document.querySelector('.main > .main__scroll[data-active="true"]');
    if (!root) return [];
    const sel = 'a[href], button, input, textarea, select, summary, label[for], [tabindex]:not([tabindex="-1"])';
    const out = [];
    root.querySelectorAll(sel).forEach((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const base = {
        tag: el.tagName.toLowerCase(),
        cls: String(el.className).slice(0, 46),
        text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 26),
        /* 正文里的行内链接按 WCAG 2.5.8 是豁免项（"句子内的目标"），不算触控缺陷 */
        inline: cs.display === 'inline' || cs.display === 'inline-block' && el.tagName === 'A',
      };
      if (r.width < 2 || r.height < 2) {
        out.push({ ...base, w: Math.round(r.width), h: Math.round(r.height), note: '零尺寸（sr-only 或当前隐藏）' });
        return;
      }
      if (r.width < 44 || r.height < 44) {
        out.push({ ...base, w: Math.round(r.width), h: Math.round(r.height) });
      }
    });
    return out;
  });
  const controls = small.filter((s) => !s.inline);
  const inline = small.filter((s) => s.inline);
  const zero = small.filter((s) => s.note);
  console.log(`[${VIEW} @${WIDTH}] <44px：控件 ${controls.length} 个 · 正文行内链接 ${inline.length} 个（WCAG 2.5.8 豁免）· 零尺寸 ${zero.length} 个`);
  for (const s of controls) console.log(`  控件  ${String(s.w).padStart(4)}×${String(s.h).padStart(3)}  ${s.tag}.${s.cls}  ${s.text}`);
  for (const s of inline.slice(0, 6)) console.log(`  行内  ${String(s.w).padStart(4)}×${String(s.h).padStart(3)}  ${s.tag}.${s.cls}  ${s.text}`);
  if (inline.length > 6) console.log(`  …还有 ${inline.length - 6} 个行内链接`);
  for (const s of zero) console.log(`  零尺寸 ${s.tag}.${s.cls}  ${s.text}  ${s.note}`);
}

if (arg('wrap', false) === true) {
  await go(VIEW);
  const bad = await page.evaluate(() => {
    const root = document.querySelector('.main > .main__scroll[data-active="true"]');
    const out = [];
    root.querySelectorAll('*').forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return;
      if (el.scrollWidth > el.clientWidth + 1 && cs.overflowX === 'visible' && el.tagName !== 'HTML') {
        out.push({ why: '内容比盒子宽', tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 44), sw: el.scrollWidth, cw: el.clientWidth });
      }
      if (el.getClientRects().length > 1 && cs.whiteSpace === 'nowrap' && cs.display !== 'inline') {
        out.push({ why: 'nowrap 却被折行', tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 44), lines: el.getClientRects().length });
      }
    });
    return out.slice(0, 40);
  });
  console.log(`[${VIEW} @${WIDTH}] 疑似溢出/折行 ${bad.length} 处`);
  bad.forEach((b) => console.log(`  ${b.why}  ${b.tag}.${b.cls}  ${b.sw ? b.sw + '>' + b.cw : 'lines=' + b.lines}`));
}

if (arg('lens', false) === true) {
  await go(VIEW);
  const info = await page.evaluate(async () => {
    const out = [];
    const boxes = Array.from(document.querySelectorAll('.main > .main__scroll[data-active="true"] .lens'));
    for (const box of boxes) {
      const btns = Array.from(box.querySelectorAll('[data-lens-set]'));
      const rows = [];
      for (const b of btns) {
        b.click();
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
        rows.push({
          lens: b.getAttribute('data-lens-set'),
          groups: Array.from(box.querySelectorAll('.lens__gk')).map((g) => g.textContent + '(' + (g.nextElementSibling ? '' : '') + ')'),
          groupN: box.querySelectorAll('.lens__gh').length,
          moved: box.getAttribute('data-lens-moved'),
          hint: (box.querySelector('[data-lens-hint]') || {}).textContent || '',
          firstThree: Array.from(box.querySelectorAll('.lens__item')).slice(0, 3).map((i) => (i.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 22)),
        });
      }
      out.push({ items: box.querySelectorAll('.lens__item').length, rows });
    }
    return out;
  });
  console.log(`[${VIEW}] .lens 容器 ${info.length} 个`);
  console.log(JSON.stringify(info, null, 2));
}

if (arg('shell', false) === true) {
  /* 外壳级验收：目录面板 + 侧栏 + 底栏 + **每个界面是否真的能路由过去**。
     "所有界面都做"这句话的可点性证明就是这一条：目录里 21 个条目逐个点过去，
     看 html[data-view] 是否真的变成那一个。 */
  await page.goto(FILE_URL, { waitUntil: 'load' });
  const shell = await page.evaluate(async () => {
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const btn = document.getElementById('viewIndexBtn');
    if (btn) btn.click();
    await wait(60);
    const panel = document.getElementById('viewIndex');
    return {
      indexOpens: panel ? !panel.hidden : false,
      indexLinks: Array.from(document.querySelectorAll('#idxBody [data-idx-link]')).map((a) => a.getAttribute('data-idx-link')),
      idxCount: (document.getElementById('idxCount') || {}).textContent,
      navItems: Array.from(document.querySelectorAll('.nav__item')).map((a) => a.getAttribute('data-nav-to')),
      tabbarItems: Array.from(document.querySelectorAll('.tabbar a, .tabbar button')).length,
      registry: JSON.parse(document.getElementById('viewRegistry').textContent).map((v) => v.key),
    };
  });
  console.log(`[外壳 @${WIDTH}] 目录按钮能开=${shell.indexOpens} · 目录条目 ${shell.indexLinks.length}（计数显示 ${shell.idxCount}）`
    + ` · 侧栏 ${shell.navItems.length} 项 · 底栏 ${shell.tabbarItems} 项 · 登记表 ${shell.registry.length} 个`);

  const want = shell.registry;
  const notInIndex = want.filter((k) => !shell.indexLinks.includes(k));
  const extra = shell.indexLinks.filter((k) => !want.includes(k));
  if (notInIndex.length) console.log(`  [FAIL] 登记了但目录里没有：${notInIndex.join(', ')}`);
  if (extra.length) console.log(`  [FAIL] 目录里有但没登记：${extra.join(', ')}`);

  /* 逐个走一遍：改 hash → 等路由 → 读 html[data-view] */
  const bad = [];
  for (const key of want) {
    await page.evaluate((k) => { window.location.hash = '#/' + k; }, key);
    await page.waitForTimeout(90);
    const active = await page.evaluate(() => ({
      view: document.documentElement.getAttribute('data-view'),
      shown: document.querySelectorAll('.main > .main__scroll[data-active="true"]').length,
      navOn: (document.querySelector('.nav__item--on') || {}).getAttribute
        ? document.querySelector('.nav__item--on').getAttribute('data-nav-to') : null,
      title: document.title,
    }));
    const ok = active.view === key && active.shown === 1;
    console.log(`  ${ok ? '[ok]  ' : '[FAIL]'} #/${key.padEnd(13)} → 视图=${active.view} 可见数=${active.shown} 侧栏高亮=${active.navOn}`
      + `  title="${active.title}"`);
    if (!ok) bad.push(key);
  }
  console.log(bad.length ? `\n[FAIL] ${bad.length} 个界面路由不过去：${bad.join(', ')}` : '\n[ok] 全部界面都能路由过去');
  if (bad.length) process.exitCode = 1;
}

if (arg('views', false) === true) {
  await page.goto(FILE_URL, { waitUntil: 'load' });
  const keys = await page.evaluate(() =>
    Array.from(document.querySelectorAll('.main > .main__scroll[data-view]')).map((el) => el.getAttribute('data-view'))
  );
  console.log(`视图 ${keys.length} 个 @${WIDTH}`);
  for (const key of keys) {
    await go(key);
    const m = await page.evaluate(() => {
      const root = document.querySelector('.main > .main__scroll[data-active="true"]');
      const tap = [];
      root.querySelectorAll('a[href], button, input, textarea, select, summary').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width > 1 && r.height > 1 && (r.width < 44 || r.height < 44)) tap.push(`${Math.round(r.width)}×${Math.round(r.height)}`);
      });
      return {
        h: Math.round(root.scrollHeight),
        over: root.scrollWidth > root.clientWidth + 1 ? root.scrollWidth + '>' + root.clientWidth : 'ok',
        small: tap.length,
        smallList: tap.slice(0, 6).join(' '),
        title: document.title,
        hasLens: root.querySelectorAll('.lens').length,
        folded: root.querySelectorAll('details').length,
      };
    });
    console.log(`  ${key.padEnd(13)} h=${String(m.h).padStart(6)}  overflow=${m.over.padEnd(10)} <44px=${String(m.small).padStart(3)}  lens=${m.hasLens} fold=${m.folded}  ${m.smallList}`);
  }
}

await browser.close();

if (pageErrors.length) {
  console.log(`\n[FAIL] 页面 JS 报了 ${pageErrors.length} 条错误（会打断路由与引擎，必须修）：`);
  [...new Set(pageErrors)].forEach((e) => console.log('  ' + e));
  process.exitCode = 1;
} else {
  console.log('\n[ok] 页面无 JS 异常');
}
