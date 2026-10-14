/**
 * 皮肤回归检查：我改的是第一、二层令牌，四种皮肤组合都必须还成立。
 *   node _tools/p0-tokens/skins.mjs
 * 产物：_shots/p0-tokens/skin-<combo>-<route>.png + 控制台里的对比度表
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const OUT = path.join(ROOT, '_shots', 'p0-tokens');
fs.mkdirSync(OUT, { recursive: true });
const PW = process.env.PW_PATH || path.join(process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright');
const { chromium } = require(PW);
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5180/';

const COMBOS = [
  ['light-blue-plain', { theme: 'light', accent: 'blue', style: 'plain' }],
  ['dark-blue-plain', { theme: 'dark', accent: 'blue', style: 'plain' }],
  ['light-red-plain', { theme: 'light', accent: 'red', style: 'plain' }],
  ['dark-red-soft', { theme: 'dark', accent: 'red', style: 'soft' }],
  ['light-blue-dense', { theme: 'light', accent: 'blue', style: 'dense' }],
];
const ROUTES = [['chat', '#/chat'], ['profile', '#/profile']];

const MEASURE = () => {
  const cs = getComputedStyle(document.documentElement);
  const get = (n) => cs.getPropertyValue('--' + n).trim();
  const firstHex = (v) => { const m = /#[0-9a-f]{6}/i.exec(v || ''); return m ? m[0] : null; };
  const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4; };
  const h2r = (h) => { const s = h.replace('#', ''); return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16)); };
  const lum = (h) => { const [r, g, b] = h2r(h); return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); };
  const cr = (a, b) => { const l1 = lum(a), l2 = lum(b); const hi = Math.max(l1, l2), lo = Math.min(l1, l2); return +((hi + 0.05) / (lo + 0.05)).toFixed(3); };
  const P = { paper: firstHex(get('c-surface')), floor: firstHex(get('c-bg')), l2: firstHex(get('c-surface-2')), border: firstHex(get('c-border')), borderStrong: firstHex(get('c-border-strong')), control: firstHex(get('c-border-control')), text3: firstHex(get('c-text-3')), text: firstHex(get('c-text')) };
  const pairs = {
    'L0→L1 页底/纸面': [P.floor, P.paper],
    'L2→L1 局部面/纸面': [P.l2, P.paper],
    '发丝线→纸面': [P.border, P.paper],
    '强描边→纸面': [P.borderStrong, P.paper],
    '控件边→纸面': [P.control, P.paper],
    '正文→纸面': [P.text, P.paper],
    '说明字→纸面': [P.text3, P.paper],
    '说明字→页底': [P.text3, P.floor],
  };
  const out = { attrs: [document.documentElement.dataset.theme, document.documentElement.dataset.accent, document.documentElement.dataset.style].join('/'), colors: P, ratios: {} };
  for (const [k, [a, b]] of Object.entries(pairs)) out.ratios[k] = a && b ? cr(a, b) : null;
  return out;
};

(async () => {
  const browser = await chromium.launch();
  const res = {};
  for (const [name, skin] of COMBOS) {
    res[name] = {};
    for (const [route, hash] of ROUTES) {
      const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      await page.addInitScript((s) => {
        try {
          localStorage.setItem('zhiyin.onboarded', '1');
          localStorage.setItem('zhiyin-demo-skin', JSON.stringify({ ...s, systemDark: false }));
        } catch { /* ignore */ }
      }, skin);
      await page.goto(BASE + hash, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(1200);
      res[name][route] = await page.evaluate(MEASURE);
      await page.screenshot({ path: path.join(OUT, `skin-${name}-${route}.png`) });
      await ctx.close();
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(HERE, 'skins.json'), JSON.stringify(res, null, 1));
  for (const [name, routes] of Object.entries(res)) {
    const r = routes.chat;
    console.log(`\n── ${name}  (data-* = ${r.attrs})`);
    console.log(`   ${JSON.stringify(r.colors)}`);
    for (const [k, v] of Object.entries(r.ratios)) {
      const min = k.startsWith('说明字') || k.startsWith('正文') ? 4.5 : k.startsWith('控件边') ? 3 : 1.1;
      console.log(`   ${v >= min ? '过  ' : '低  '} ${String(v).padStart(6)}  ${k}  (判据 ≥${min})`);
    }
  }
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
