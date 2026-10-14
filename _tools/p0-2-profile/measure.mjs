/**
 * P0-2（StudentView.vue 字号结构）度量脚本 —— 可复跑，改前/改后同一套口径。
 *
 *   node _tools/p0-2-profile/measure.mjs before
 *   node _tools/p0-2-profile/measure.mjs after
 *
 * 口径与 _tools/p0-tokens/measure.mjs 的 profile 段**完全一致**（同一份 MEASURE 取数逻辑），
 * 便于与该轮的数字互校：
 *   · 文本节点 = 可见元素 × 直接子文本节点，fs = computed font-size
 *   · 可见 = display!==none && visibility!==hidden && opacity!=0 && rect.w>0 && rect.h>0
 *     （注意：这只排除 display:none；v-show 隐藏的元素不在 DOM 布局里，所以也被排除）
 *   · 页面高度 = document.documentElement.scrollHeight（全页截图高度）
 *   · 触控 <44px = button/input/select/textarea/summary/[role=button]/带 .btn 的真实控件，
 *     a[href] 单列为 link（WCAG 2.5.8 对句子内嵌文本链接有豁免）
 *
 * 额外产物（本任务需要）：
 *   · 逐选择器的 12px 节点数 + 样例文本 —— 用来判定"正文 / 标注"
 *   · 视口内可见的 12px 节点数（不滚动就到位的那些）
 *
 * 产物：_shots/p0-2-profile/<tag>-profile-<w>.png 与 _tools/p0-2-profile/<tag>.json
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const TAG = process.argv[2] || 'run';
const PW =
  process.env.PW_PATH ||
  path.join(process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright');
const { chromium } = require(PW);
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5180/';
const ROUTE = process.env.ROUTE || '#/profile';

const SHOTS = path.join(ROOT, '_shots', 'p0-2-profile');
fs.mkdirSync(SHOTS, { recursive: true });

const MEASURE = () => {
  const num = (v) => Math.round(parseFloat(v) * 100) / 100;
  const sig = (el) => {
    const cls = (el.className || '').toString().trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.');
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
  };
  const visible = (e) => {
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    const b = e.getBoundingClientRect();
    return b.width > 0 && b.height > 0;
  };
  const all = [...document.querySelectorAll('body *')].filter(visible);

  const texts = [];
  for (const el of all) {
    for (const n of el.childNodes) {
      if (n.nodeType !== 3) continue;
      const t = (n.textContent || '').trim();
      if (!t) continue;
      const s = getComputedStyle(el);
      const fs = num(s.fontSize);
      if (!(fs > 0)) continue;
      const b = el.getBoundingClientRect();
      texts.push({
        text: t.replace(/\s+/g, ' ').slice(0, 40),
        tag: el.tagName.toLowerCase(),
        cls: sig(el),
        full: `${el.tagName.toLowerCase()}${(el.className || '').toString().trim() ? '.' + (el.className || '').toString().trim().split(/\s+/).filter(Boolean).join('.') : ''}`,
        fs,
        fw: s.fontWeight,
        ls: s.letterSpacing,
        lh: s.lineHeight,
        inViewport: b.y < innerHeight && b.y + b.height > 0,
        chars: t.length,
        y: Math.round(b.y + scrollY),
      });
    }
  }

  const hist = {};
  for (const t of texts) hist[t.fs] = (hist[t.fs] || 0) + 1;

  const bySel = {};
  for (const t of texts) {
    const k = bySel[t.fs] = bySel[t.fs] || {};
    k[t.cls] = (k[t.cls] || 0) + 1;
  }

  const detail12 = texts
    .filter((t) => t.fs === 12)
    .reduce((m, t) => {
      const e = (m[t.cls] = m[t.cls] || { sel: t.cls, n: 0, inViewport: 0, samples: [], chars: [] });
      e.n++;
      if (t.inViewport) e.inViewport++;
      if (e.samples.length < 4) e.samples.push(t.text);
      if (e.chars.length < 40) e.chars.push(t.chars);
      return m;
    }, {});
  const detail12Arr = Object.values(detail12).sort((a, b) => b.n - a.n);
  for (const e of detail12Arr) e.maxChars = Math.max(...e.chars);

  /* 触控 */
  const controls = [];
  const sel = 'button, a[href], input, select, textarea, summary, [role="button"]';
  for (const e of all) {
    if (!e.matches(sel)) continue;
    if (/(^|\s)sr-only(\s|$)/.test((e.className || '').toString())) continue;
    const b = e.getBoundingClientRect();
    const cls = (e.className || '').toString();
    const isBtn = e.matches('button, input, select, textarea, summary, [role="button"]') || /\bbtn\b|btn--/.test(cls);
    controls.push({ tag: e.tagName.toLowerCase(), cls: sig(e), h: Math.round(b.height), w: Math.round(b.width), kind: isBtn ? 'button' : 'link', text: (e.textContent || '').trim().slice(0, 20) });
  }
  const tall = controls.filter((c) => c.h > 0);
  const btn = tall.filter((c) => c.kind === 'button');
  const link = tall.filter((c) => c.kind === 'link');

  /* 字距越界：≥20px 且 < -0.02em；以及正字距（中文） */
  const lsOver = [];
  const lsPositive = [];
  for (const e of all) {
    const s = getComputedStyle(e);
    const fs = parseFloat(s.fontSize), ls = parseFloat(s.letterSpacing);
    if (!isFinite(ls) || ls === 0) continue;
    const own = [...e.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).map((n) => n.textContent.trim()).join('');
    if (!own) continue;
    if (ls < 0) {
      const em = ls / fs;
      if (em < -0.0201) lsOver.push(`${sig(e)} fs=${fs} ls=${s.letterSpacing} (${em.toFixed(4)}em) "${own.slice(0, 14)}"`);
      else if (fs < 20) lsOver.push(`负字距用在 ${fs}px：${sig(e)} ls=${s.letterSpacing} "${own.slice(0, 14)}"`);
    } else if (/[\u4e00-\u9fff]/.test(own)) {
      lsPositive.push(`${sig(e)} fs=${fs} ls=${s.letterSpacing} "${own.slice(0, 14)}"`);
    }
  }

  /* 行距与字号反相关：列出所有 12/14/16/20px 的 line-height 倍数 */
  const lhByFs = {};
  for (const t of texts) {
    const lh = parseFloat(t.lh);
    if (!isFinite(lh)) continue;
    const k = t.fs;
    lhByFs[k] = lhByFs[k] || {};
    const r = (lh / t.fs).toFixed(2);
    lhByFs[k][r] = lhByFs[k][r] || { n: 0, sample: `${t.cls} lh=${t.lh}` };
    lhByFs[k][r].n++;
  }

  return {
    url: location.href,
    viewport: { w: innerWidth, h: innerHeight },
    docH: document.documentElement.scrollHeight,
    bodyH: document.body.scrollHeight,
    textCount: texts.length,
    hist,
    pct: Object.fromEntries(Object.entries(hist).map(([k, v]) => [k, +((v / texts.length) * 100).toFixed(2)])),
    sub12: texts.filter((t) => t.fs < 12).length,
    bySel: Object.fromEntries(
      Object.entries(bySel).map(([fs, m]) => [fs, Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 18).map(([s, n]) => `${s}×${n}`)]),
    ),
    detail12: detail12Arr,
    controls: {
      total: tall.length,
      buttonCount: btn.length,
      under44: btn.filter((c) => c.h < 44).length,
      under44List: btn.filter((c) => c.h < 44).map((c) => `${c.h}px ${c.tag}.${c.cls} "${c.text}"`),
      linkUnder44: link.filter((c) => c.h < 44).length,
      linkUnder44List: link.filter((c) => c.h < 44).map((c) => `${c.h}px ${c.tag}.${c.cls} "${c.text}"`),
      buttonHeights: btn.reduce((m, c) => ((m[c.h] = (m[c.h] || 0) + 1), m), {}),
      heightBySel: Object.entries(tall.reduce((m, c) => { const k = c.h + 'px ' + c.cls; m[k] = (m[k] || 0) + 1; return m; }, {}))
        .sort((a, b) => b[1] - a[1]).slice(0, 18).map(([k, n]) => `${k}×${n}`),
    },
    lsOver: [...new Set(lsOver)],
    lsPositive: [...new Set(lsPositive)],
    lhByFs,
    uaDefaultHeadings: [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(visible)
      .filter((h) => [32, 24, 18.72, 16, 13.28, 10.72].some((v) => Math.abs(parseFloat(getComputedStyle(h).fontSize) - v) < 0.05))
      .map((h) => ({ tag: h.tagName, fs: num(getComputedStyle(h).fontSize), text: (h.textContent || '').trim().slice(0, 24) })),
  };
};

(async () => {
  const browser = await chromium.launch();
  const out = { tag: TAG, generatedAt: new Date().toISOString(), base: BASE, route: ROUTE, widths: {} };
  for (const w of [1280, 390]) {
    /* REDUCED=1 时以 prefers-reduced-motion: reduce 跑一遍，用来验证本任务没影响降级分支 */
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 1280 ? 900 : 844 }, deviceScaleFactor: 1, reducedMotion: process.env.REDUCED ? 'reduce' : 'no-preference' });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.setItem('zhiyin.onboarded', '1'); } catch { /* ignore */ } });
    await page.goto(BASE + ROUTE, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(1600);
    await page.screenshot({ path: path.join(SHOTS, `${TAG}-profile-${w}.png`), fullPage: true });
    const m = await page.evaluate(MEASURE);
    out.widths[w] = m;
    console.log(`  ${TAG} profile@${w} docH=${m.docH} text=${m.textCount} 12px=${m.hist[12] || 0}(${m.pct[12] || 0}%) under44=${m.controls.under44}`);
    await ctx.close();
  }
  await browser.close();
  const dest = path.join(HERE, `${TAG}.json`);
  fs.writeFileSync(dest, JSON.stringify(out, null, 1));
  console.log('WROTE', dest);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
