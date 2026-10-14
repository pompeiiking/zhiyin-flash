/* 方向 C「陪伴感」样张截图脚本（零依赖，只借 Playwright）
   用法：node shoot.js
   产出：shots/1280.png、shots/390.png
   另外做三件检查：横向溢出、控制台报错、prefers-reduced-motion 下的静态形态。 */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA,
  'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));

const DIR = __dirname;
const FILE = 'file:///' + path.join(DIR, 'index.html').replace(/\\/g, '/');
const SHOTS = path.join(DIR, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const problems = [];

  async function shot(name, width, height, opts = {}) {
    const ctx = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 2,
      reducedMotion: opts.reducedMotion ? 'reduce' : 'no-preference',
      isMobile: width < 500,
      hasTouch: width < 500
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    page.on('pageerror', e => errs.push('pageerror: ' + e.message));

    await page.goto(FILE, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    await wait(900);

    // 先在最前面的"支持依据"卡上展开其余 2 条，再切到别的卡
    if (opts.expandEvidence) {
      await page.click('#evToggle');
      await wait(700);
    }
    // 演示默认切到"数据对比"，让截图同时展示卡组可切与图表
    if (opts.tab) {
      await page.click('#tab-' + opts.tab);
      await wait(700);
    }
    // 聚焦输入区，展示聚焦态
    if (opts.focusInput) {
      await page.click('#msg');
      await wait(500);
    }

    const metrics = await page.evaluate(() => {
      const de = document.documentElement;
      const over = [];
      document.querySelectorAll('body *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width <= 0) return;
        // 抽屉是故意停在画布左侧外面的，不算溢出；只看"向右越界"
        if (el.closest('.nav')) return;
        if (r.right > de.clientWidth + 1 || r.left < -1) {
          over.push({ tag: el.tagName, cls: el.className && String(el.className).slice(0, 48),
                      left: Math.round(r.left), right: Math.round(r.right) });
        }
      });
      return {
        docScrollW: de.scrollWidth,
        clientW: de.clientWidth,
        bodyScrollW: document.body.scrollWidth,
        overflowing: over.slice(0, 8),
        avatarRendered: !!document.querySelector('#heroAvatar svg'),
        state: de.getAttribute('data-state')
      };
    });

    if (metrics.docScrollW > metrics.clientW + 1) {
      problems.push(`${name}: 横向溢出 scrollWidth=${metrics.docScrollW} > clientWidth=${metrics.clientW}`);
    }
    if (metrics.overflowing.length) {
      problems.push(`${name}: 越界元素 ${JSON.stringify(metrics.overflowing)}`);
    }
    if (errs.length) problems.push(`${name}: 控制台 ${JSON.stringify(errs)}`);
    if (!metrics.avatarRendered) problems.push(`${name}: 头像 SVG 未渲染`);

    await page.screenshot({ path: path.join(SHOTS, name + '.png'), fullPage: !!opts.fullPage });
    console.log(`[ok] ${name}  scrollW=${metrics.docScrollW} clientW=${metrics.clientW} state=${metrics.state}`);
    await ctx.close();
    return metrics;
  }

  // 1280：桌面，展示"数据对比"卡
  await shot('1280', 1280, 900, { tab: 'data', fullPage: false });
  // 1280 整页（含输入区）
  await shot('1280-full', 1280, 900, { tab: 'data', fullPage: true });
  // 1280：支持依据卡 + 展开其余 2 条
  await shot('1280-evidence', 1280, 900, { tab: 'ev', expandEvidence: true, fullPage: true });
  // 1280：方法卡 + 展开全文
  await shot('1280-method', 1280, 900, { tab: 'method', fullPage: true });
  // 390：移动（默认"支持依据"卡 + 展开 4 条 + 输入区聚焦态）
  await shot('390', 390, 844, { tab: 'ev', expandEvidence: true, focusInput: true, fullPage: false });
  await shot('390-full', 390, 844, { tab: 'ev', expandEvidence: true, fullPage: true });
  // 390：数据卡（窄屏下刻度仍要对齐）
  await shot('390-data', 390, 844, { tab: 'data', fullPage: true });
  // 静态形态（reduced-motion 降级后必须仍然完整）
  await shot('1280-reduced', 1280, 900, { tab: 'data', reducedMotion: true });
  await shot('390-reduced', 390, 844, { tab: 'data', reducedMotion: true, fullPage: true });

  await browser.close();

  if (problems.length) {
    console.log('\n=== 问题 ===');
    problems.forEach(p => console.log(' - ' + p));
    process.exitCode = 1;
  } else {
    console.log('\n没有发现问题：无横向溢出、无控制台报错、头像已渲染。');
  }
})();
