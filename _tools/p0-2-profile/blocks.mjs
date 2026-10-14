/**
 * 逐区块高度对照：按"稳定的类名锚点"记录每块元素的 offsetTop/offsetHeight 与行高，
 * 改前/改后各跑一次，输出 JSON 供 diff。
 *   node _tools/p0-2-profile/blocks.mjs before
 *   node _tools/p0-2-profile/blocks.mjs after
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const PW = process.env.PW_PATH || path.join(process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright');
const { chromium } = require(PW);
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5180/';
const TAG = process.argv[2] || 'run';

const PROBE = () => {
  const sel = [
    '.p7', '.p7-meter', '.p7-block', '.p7-groups', '.p7-group', '.p7-group__head',
    '.p7-subfilter', '.p7-rows', '.p7-row', '.p7-row__hit', '.p7-row__label', '.p7-row__main',
    '.p7-row__meta', '.p7-concls', '.p7-concl', '.p7-concl__hit', '.p7-concl__label',
    '.p7-concl__brief', '.p7-concl__deps', '.p7-deps__list', '.p7-dep', '.p7-deps-note',
    '.p7-gaps', '.p7-gap', '.p7-meter__facts', '.p7-block__head', '.ws-context',
    '.profile-insights', '.page-heading', '.ws-heading', '.p7-affect',
  ];
  const out = [];
  for (const q of sel) {
    const els = [...document.querySelectorAll(q)];
    els.forEach((e, i) => {
      const s = getComputedStyle(e);
      out.push({
        q: q + (els.length > 1 ? `[${i}]` : ''),
        n: els.length,
        top: Math.round(e.getBoundingClientRect().top + scrollY),
        h: Math.round(e.getBoundingClientRect().height),
        fs: s.fontSize, lh: s.lineHeight,
        lines: Math.round(e.getBoundingClientRect().height / parseFloat(s.lineHeight || '1')),
      });
    });
  }
  return { docH: document.documentElement.scrollHeight, items: out };
};

(async () => {
  const browser = await chromium.launch();
  const res = {};
  for (const w of [1280, 390]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 1280 ? 900 : 844 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.setItem('zhiyin.onboarded', '1'); } catch { /* ignore */ } });
    await page.goto(BASE + '#/profile', { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(1600);
    res[w] = await page.evaluate(PROBE);
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(HERE, `blocks-${TAG}.json`), JSON.stringify(res, null, 1));
  console.log('WROTE', path.join(HERE, `blocks-${TAG}.json`), res['1280'].docH, res['390'].docH);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
