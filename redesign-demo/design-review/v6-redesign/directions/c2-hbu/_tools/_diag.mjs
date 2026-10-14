/* 一次性诊断（作者自用，不属交付物）：找出把 .pg 撑到 1240px 的那个元素。
   用法：node _tools/_diag.mjs <preview文件> <视图key> */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
const FILE = pathToFileURL(path.resolve(DIR, process.argv[2])).href;
const VIEW = process.argv[3] || 'tools';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(`${FILE}#/${VIEW}`, { waitUntil: 'load' });
await page.waitForTimeout(400);

const out = await page.evaluate(() => {
  const root = document.querySelector('.main > .main__scroll[data-active="true"]');
  const bad = [];
  root.querySelectorAll('*').forEach((el) => {
    const sw = el.scrollWidth;
    const cw = el.clientWidth;
    if (cw > 0 && sw > cw + 1) {
      // 只记"自己撑宽的"：先看子元素里有没有同样宽的
      let pushed = false;
      for (const c of el.children) if (c.scrollWidth >= sw - 1 && c.clientWidth > 0) pushed = true;
      if (!pushed) {
        bad.push({
          tag: el.tagName.toLowerCase(),
          cls: String(el.className).slice(0, 60),
          sw, cw,
          minW: getComputedStyle(el).minWidth,
          w: Math.round(el.getBoundingClientRect().width),
          text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
        });
      }
    }
  });
  return {
    root: { sw: root.scrollWidth, cw: root.clientWidth },
    worst: bad.slice(0, 20),
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.close();
