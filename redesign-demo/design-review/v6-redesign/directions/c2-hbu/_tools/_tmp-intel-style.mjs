/* 临时：量几处计算样式（跑完即删） */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));
const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(pathToFileURL(path.join(DIR, '_shots', 'preview-intel.html')).href + '#/intel', { waitUntil: 'load' });
await page.waitForTimeout(400);

const out = await page.evaluate(() => {
  const pick = (sel, props) => {
    const el = document.querySelector(sel);
    if (!el) return sel + ' → 找不到';
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return sel + '  [' + Math.round(r.width) + '×' + Math.round(r.height) + ']  '
      + props.map((p) => p + '=' + cs[p]).join('  ');
  };
  return [
    pick('.int-match', ['backgroundColor', 'boxShadow', 'borderTopColor', 'borderTopWidth']),
    pick('.int-fact', ['backgroundColor', 'padding']),
    pick('.int-kind', ['backgroundColor', 'borderRadius', 'borderColor', 'color']),
    pick('.int-fact__top .pill', ['backgroundColor', 'borderColor', 'color']),
    pick('.int-src', ['backgroundColor', 'borderRadius', 'borderColor', 'whiteSpace']),
    pick('.int-src .src__k', ['whiteSpace', 'color', 'fontWeight']),
    pick('.int-zoom .zoom__body', ['backgroundColor', 'borderLeftColor', 'borderLeftWidth', 'color']),
    pick('.int-zoom .zoombar', ['backgroundColor', 'borderRadius']),
    pick('.int-filter__k', ['color', 'fontSize', 'paddingTop']),
    pick('.int-hot', ['borderStyle', 'borderRadius']),
    pick('.int-sort', ['backgroundColor', 'borderRadius', 'display']),
    pick('.int-filter__echo', ['backgroundColor', 'borderStyle', 'color']),
    pick('.int-scope li', ['color', 'fontSize', 'paddingLeft']),
    pick('.lensbtn', ['minHeight', 'height']),
    pick('.chipbtn', ['minHeight', 'height']),
    pick('.zoombtn', ['minHeight', 'height']),
    pick('.chipf', ['minHeight', 'height']),
    /* 字号/字重清单：确认只用 5 档字号、4 档字重 */
    (() => {
      const sizes = {}, weights = {};
      document.querySelectorAll('.main > .main__scroll[data-view="intel"] *').forEach((el) => {
        const cs = getComputedStyle(el);
        if (!el.textContent || !el.textContent.trim()) return;
        if (el.children.length && !Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) return;
        sizes[cs.fontSize] = (sizes[cs.fontSize] || 0) + 1;
        weights[cs.fontWeight] = (weights[cs.fontWeight] || 0) + 1;
      });
      return 'intel 文字节点 fontSize=' + JSON.stringify(sizes) + '  fontWeight=' + JSON.stringify(weights);
    })(),
  ];
});
out.forEach((l) => console.log(l));
await browser.close();
