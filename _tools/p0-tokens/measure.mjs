/**
 * P0 度量脚本（可复跑）—— 结构量 / 字号阶梯 / 触控 / 视口宽度 / 图表刻度字。
 *
 *   node _tools/p0-tokens/measure.mjs before
 *   node _tools/p0-tokens/measure.mjs after
 *
 * 产物：
 *   _shots/p0-tokens/<tag>-<route>-<width>.png   5 路由 × 2 档 = 10 张
 *   _tools/p0-tokens/<tag>.json                  全部实测值（改前/改后同一套脚本）
 *
 * 口径说明（与 DESIGN-REVIEW-V7 的 probe.cjs 对齐，便于与评审数字互校）：
 *   · 文本节点清单：可见元素 × 直接子文本节点，fs = computed font-size（与 probe.cjs 同）
 *   · 近白占比 whitePct：l = (0.2126r+0.7152g+0.0722b)/255 > 0.965（与 probe.cjs 同公式）
 *     —— 它与"纯白 #ffffff 占比"不是同一个数（#f7f6f6 的 l=0.9655 也算近白）
 *   · 像素统计在 Node 里解码**全分辨率** PNG（probe.cjs 是画到 900px 宽的 canvas 上再统计，
 *     会重采样；所以我的绝对值可能与评审的差 1–2 个百分点，但同脚本改前/改后可直接比）
 *   · 结构量 structurePct：既不是近白（l>0.955）、也不是深色（l<0.25）、也不是彩色（sat>0.28）
 *     的像素占比 —— 描边、阴影、灰面都落在这个带里，"看不看得见"可以由它直接读出来
 */
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
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

const SHOTS = path.join(ROOT, '_shots', 'p0-tokens');
fs.mkdirSync(SHOTS, { recursive: true });

const ROUTES = [
  ['portal', '#/'],
  ['chat', '#/chat'],
  ['profile', '#/profile'],
  ['report', '#/report'],
  ['plan', '#/plan'],
];
const WIDTHS = [1280, 390];

/* ---------------------------------------------------------------- PNG 解码 */
function decodePng(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error('not a PNG');
  let pos = 8;
  let width = 0, height = 0, bitDepth = 0, colorType = 0, interlace = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const type = buf.toString('ascii', pos + 4, pos + 8);
    const data = buf.subarray(pos + 8, pos + 8 + len);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    pos += 12 + len;
  }
  if (bitDepth !== 8) throw new Error(`unsupported bit depth ${bitDepth}`);
  if (interlace !== 0) throw new Error('interlaced PNG unsupported');
  const bpp = colorType === 6 ? 4 : colorType === 2 ? 3 : 0;
  if (!bpp) throw new Error(`unsupported color type ${colorType}`);
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * bpp;
  const out = Buffer.alloc(height * stride);
  const paeth = (a, b, c) => {
    const p = a + b - c;
    const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
  };
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = raw.subarray(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
    const cur = out.subarray(y * stride, (y + 1) * stride);
    const prev = y > 0 ? out.subarray((y - 1) * stride, y * stride) : null;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? cur[x - bpp] : 0;
      const b = prev ? prev[x] : 0;
      const c = prev && x >= bpp ? prev[x - bpp] : 0;
      let v = src[x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) v += paeth(a, b, c);
      cur[x] = v & 0xff;
    }
  }
  return { width, height, bpp, data: out };
}

const px = (img, x, y) => {
  x = Math.max(0, Math.min(img.width - 1, Math.round(x)));
  y = Math.max(0, Math.min(img.height - 1, Math.round(y)));
  const i = (y * img.width + x) * img.bpp;
  return [img.data[i], img.data[i + 1], img.data[i + 2]];
};
const hexOf = ([r, g, b]) => '#' + [r, g, b].map((n) => n.toString(16).padStart(2, '0')).join('');
/* 与 probe.cjs 完全一致的"亮度"（加权平均，非 gamma） */
const flatLum = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
const satOf = ([r, g, b]) => { const mx = Math.max(r, g, b); return mx === 0 ? 0 : (mx - Math.min(r, g, b)) / mx; };

/* WCAG 相对亮度（gamma 正确），用于对比度比值 */
const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const cr = (a, b) => { const l1 = lum(a), l2 = lum(b); const hi = Math.max(l1, l2), lo = Math.min(l1, l2); return +((hi + 0.05) / (lo + 0.05)).toFixed(3); };
const hexToRgb = (h) => { const s = h.replace('#', ''); return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16)); };
const crHex = (a, b) => cr(hexToRgb(a), hexToRgb(b));

/* -------------------------------------------------- 页面内 DOM 度量（浏览器） */
const MEASURE = () => {
  const num = (v) => Math.round(parseFloat(v) * 100) / 100;
  const rgb = (s) => {
    const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(s || '');
    return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null;
  };
  const hex = (c) => (c ? '#' + [c.r, c.g, c.b].map((n) => Math.round(n).toString(16).padStart(2, '0')).join('') : null);
  const lum = (c) => { const f = (n) => { n /= 255; return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const effBg = (el) => {
    let n = el;
    while (n && n.nodeType === 1) {
      const c = rgb(getComputedStyle(n).backgroundColor);
      if (c && c.a >= 0.999) return c;
      if (c && c.a > 0) {
        let p = n.parentElement;
        while (p) {
          const pc = rgb(getComputedStyle(p).backgroundColor);
          if (pc && pc.a >= 0.999) return { r: c.r * c.a + pc.r * (1 - c.a), g: c.g * c.a + pc.g * (1 - c.a), b: c.b * c.a + pc.b * (1 - c.a), a: 1 };
          p = p.parentElement;
        }
        return c;
      }
      n = n.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  };
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

  const out = { url: location.href, viewport: { w: innerWidth, h: innerHeight }, docH: document.documentElement.scrollHeight };
  const all = [...document.querySelectorAll('body *')].filter(visible);

  /* ---- 令牌实际生效值（从 :root 读 computed） ---- */
  const cs = getComputedStyle(document.documentElement);
  out.tokens = {};
  for (const t of ['c-bg', 'c-surface', 'c-surface-2', 'c-surface-3', 'c-border', 'c-border-strong', 'c-text', 'c-text-2', 'c-text-3', 'c-text-4', 'c-primary', 'e-1', 'e-2', 'w-content', 'field-border']) {
    out.tokens[t] = cs.getPropertyValue('--' + t).trim();
  }

  /* ---- 1. 字号分布直方图 ---- */
  const texts = [];
  for (const el of all) {
    for (const n of el.childNodes) {
      if (n.nodeType !== 3) continue;
      const t = (n.textContent || '').trim();
      if (!t) continue;
      const s = getComputedStyle(el);
      const fs = num(s.fontSize);
      if (!(fs > 0)) continue;
      const fg = rgb(s.color), bg = effBg(el);
      texts.push({
        text: t.slice(0, 30), tag: el.tagName.toLowerCase(), cls: sig(el), fs,
        fw: s.fontWeight, ls: s.letterSpacing, color: hex(fg), bg: hex(bg),
        cr: fg && bg ? +((Math.max(lum(fg), lum(bg)) + 0.05) / (Math.min(lum(fg), lum(bg)) + 0.05)).toFixed(2) : null,
        y: Math.round(el.getBoundingClientRect().y),
      });
    }
  }
  out.textCount = texts.length;
  const hist = {}, bySel = {}, under = [];
  for (const t of texts) {
    hist[t.fs] = (hist[t.fs] || 0) + 1;
    const k = (bySel[t.fs] = bySel[t.fs] || {});
    k[t.cls] = (k[t.cls] || 0) + 1;
    if (t.fs < 12) under.push(t);
  }
  out.fontSizes = hist;
  out.fontSizeBySel = Object.fromEntries(Object.entries(bySel).map(([fs, m]) => [fs, Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 14).map(([sel, n]) => `${sel}×${n}`)]));
  out.sub12 = under;
  const fw = {};
  for (const t of texts) fw[t.fw] = (fw[t.fw] || 0) + 1;
  out.fontWeights = fw;

  /* ---- UA 默认档泄漏：标题/元素用了浏览器默认字号（没有任何 CSS 规则命中） ---- */
  const UA = { H1: 32, H2: 24, H3: 18.72, H4: 16, H5: 13.28, H6: 10.72 };
  out.uaDefaultHeadings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
    .filter(visible)
    .filter((h) => Math.abs(parseFloat(getComputedStyle(h).fontSize) - (UA[h.tagName] || -1)) < 0.05)
    .map((h) => ({ tag: h.tagName, fs: num(getComputedStyle(h).fontSize), text: (h.textContent || '').trim().slice(0, 24), cls: (h.className || '').toString().slice(0, 40) }));

  /* ---- 标题小于正文的检测：h* 的 fs 小于同容器内 p/li 的 fs ---- */
  out.headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(visible)
    .map((h) => ({ tag: h.tagName, fs: num(getComputedStyle(h).fontSize), text: (h.textContent || '').trim().slice(0, 24) }));

  /* ---- 2. 触控目标 <44px ----
     WCAG 2.5.8 对"句子内嵌的文本链接"有豁免，所以把控件与文本链接分开算：
     真正算违规的是 button / input / select / summary / [role=button] / .btn 这一类。 */
  const controls = [];
  const sel = 'button, a[href], input, select, textarea, summary, [role="button"]';
  for (const e of all) {
    if (!e.matches(sel)) continue;
    /* .sr-only 是"视觉隐藏但读屏可达"的输入（例如隐藏的 file input），
       它不是给手指点的目标，不能算进触控约束。 */
    if (/(^|\s)sr-only(\s|$)/.test((e.className || '').toString())) continue;
    const b = e.getBoundingClientRect();
    const cls = (e.className || '').toString();
    const isBtn = e.matches('button, input, select, textarea, summary, [role="button"]') || /\bbtn\b|btn--/.test(cls);
    controls.push({ tag: e.tagName.toLowerCase(), cls: sig(e), h: Math.round(b.height), w: Math.round(b.width), kind: isBtn ? 'button' : 'link', text: (e.textContent || '').trim().slice(0, 18) });
  }
  const tall = controls.filter((c) => c.h > 0);
  const btn = tall.filter((c) => c.kind === 'button');
  const link = tall.filter((c) => c.kind === 'link');
  out.controls = {
    total: tall.length,
    buttonCount: btn.length,
    under44: btn.filter((c) => c.h < 44).length,
    linkUnder44: link.filter((c) => c.h < 44).length,
    heights: tall.reduce((m, c) => ((m[c.h] = (m[c.h] || 0) + 1), m), {}),
    buttonHeights: btn.reduce((m, c) => ((m[c.h] = (m[c.h] || 0) + 1), m), {}),
    offenders: btn.filter((c) => c.h < 44)
      .sort((a, b) => b.h - a.h).map((c) => `${c.h}px ${c.tag}.${c.cls}`)
      .filter((v, i, arr) => arr.indexOf(v) === i).slice(0, 26),
    heightBySel: Object.entries(tall.reduce((m, c) => { const k = c.h + 'px ' + c.cls; m[k] = (m[k] || 0) + 1; return m; }, {}))
      .sort((a, b) => b[1] - a[1]).slice(0, 16).map(([k, n]) => `${k}×${n}`),
    sizesUnder44: [...new Set(btn.filter((c) => c.h < 44).map((c) => c.h))].sort((a, b) => b - a),
    linkSizesUnder44: [...new Set(link.filter((c) => c.h < 44).map((c) => c.h))].sort((a, b) => b - a),
  };

  /* ---- 3. 内容列最大宽度 ---- */
  out.containers = [];
  for (const q of ['.ws-page', '.ws-conversation', '.journey-page', '.assessment-page', '.dialogue-page', '.app__main', '.ws-chat-flow', '.ws-paper']) {
    const e = document.querySelector(q);
    if (!e || !visible(e)) { out.containers.push({ q, present: false }); continue; }
    const s = getComputedStyle(e);
    out.containers.push({ q, present: true, maxWidth: s.maxWidth, width: Math.round(e.getBoundingClientRect().width), border: s.borderTopWidth + ' ' + s.borderTopStyle, bg: hex(rgb(s.backgroundColor)), shadow: s.boxShadow === 'none' ? 'none' : s.boxShadow.slice(0, 60) });
  }

  /* ---- 4. 字距越界（≥20px 且 < -0.02em） ---- */
  out.letterSpacingOver = [];
  for (const e of all) {
    const s = getComputedStyle(e);
    const fs = parseFloat(s.fontSize), ls = parseFloat(s.letterSpacing);
    if (!isFinite(ls) || ls === 0 || !(fs >= 20)) continue;
    if (ls / fs < -0.0201) out.letterSpacingOver.push(`${sig(e)} fs=${fs} ls=${s.letterSpacing} (${(ls / fs).toFixed(4)}em)`);
  }
  out.letterSpacingOver = [...new Set(out.letterSpacingOver)].slice(0, 12);
  /* 中文正字距（品牌字 / 中文标签） */
  out.positiveTracking = [];
  for (const e of all) {
    const s = getComputedStyle(e);
    const ls = parseFloat(s.letterSpacing);
    if (!isFinite(ls) || ls <= 0) continue;
    const own = [...e.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).map((n) => n.textContent.trim()).join('');
    const hasCjk = /[\u4e00-\u9fff]/.test(own);
    if (hasCjk && (e.matches('strong,b,.desk-brand *,.ws-brand *') || e.closest('.desk-brand,.ws-brand'))) {
      out.positiveTracking.push(`${sig(e)} ls=${s.letterSpacing} "${own.slice(0, 8)}"`);
    }
  }
  out.positiveTracking = [...new Set(out.positiveTracking)].slice(0, 12);

  /* ---- 5. 低对比文字（P0-4 等） ---- */
  out.lowContrast = texts.filter((t) => t.cr !== null && t.cr < 4.5 && !(t.fs >= 24 && t.cr >= 3))
    .sort((a, b) => a.cr - b.cr).slice(0, 26);
  const tickOf = (e) => {
    const s = getComputedStyle(e), fg = rgb(s.color), bg = effBg(e);
    return { text: (e.textContent || '').trim(), fs: num(s.fontSize), color: hex(fg), bg: hex(bg), cr: +((Math.max(lum(fg), lum(bg)) + 0.05) / (Math.min(lum(fg), lum(bg)) + 0.05)).toFixed(2) };
  };
  out.chartTicks = {
    labels: [...document.querySelectorAll('.chat-bars__grid i')].map(tickOf),
    gridlines: [...document.querySelectorAll('.chat-bars__grid span')].map(tickOf).slice(0, 2),
  };

  /* ---- 6. 关键元素矩形（给 Node 端做像素采样） ---- */
  const rectOf = (q) => { const e = document.querySelector(q); if (!e || !visible(e)) return null; const b = e.getBoundingClientRect(); return { x: Math.round(b.x), y: Math.round(b.y + scrollY), w: Math.round(b.width), h: Math.round(b.height) }; };
  const paperSel = ['.dialogue-page .exp-conversation-body > .ws-chat-flow', '.ws-chat-flow', '.ws-paper'].find((q) => rectOf(q)) || null;
  const paperRect = paperSel ? rectOf(paperSel) : null;
  out.rects = {
    sidebar: rectOf('.desk-sidebar'),
    main: rectOf('.app__main'),
    paper: paperRect,
    paperSel,
    surface2: rectOf('.dialogue-page .ws-composer') || rectOf('.ws-composer'),
    bookmarks: rectOf('.ws-bookmarks'),
  };
  out.computed = {
    sidebarBg: (() => { const e = document.querySelector('.desk-sidebar'); return e ? hex(rgb(getComputedStyle(e).backgroundColor)) : null; })(),
    sidebarBorder: (() => { const e = document.querySelector('.desk-sidebar'); if (!e) return null; const s = getComputedStyle(e); return `${s.borderTopWidth} ${s.borderTopStyle} ${s.borderTopColor}`; })(),
    mainBg: (() => { const e = document.querySelector('.app__main'); return e ? hex(rgb(getComputedStyle(e).backgroundColor)) : null; })(),
    bodyBg: hex(rgb(getComputedStyle(document.body).backgroundColor)),
    activeNavShadow: (() => { const e = document.querySelector(".desk-link[aria-current='page']"); return e ? getComputedStyle(e).boxShadow : null; })(),
    activeNavBg: (() => { const e = document.querySelector(".desk-link[aria-current='page']"); return e ? hex(rgb(getComputedStyle(e).backgroundColor)) : null; })(),
  };
  return out;
};

/* ------------------------------------------------------------ 主流程 */
(async () => {
  const browser = await chromium.launch();
  const results = { tag: TAG, generatedAt: new Date().toISOString(), base: BASE, routes: {} };
  for (const [name, hash] of ROUTES) {
    results.routes[name] = {};
    for (const w of WIDTHS) {
      const ctx = await browser.newContext({ viewport: { width: w, height: w === 1280 ? 900 : 844 }, deviceScaleFactor: 1, reducedMotion: 'no-preference' });
      const page = await ctx.newPage();
      await page.addInitScript(() => { try { localStorage.setItem('zhiyin.onboarded', '1'); } catch { /* ignore */ } });
      await page.goto(BASE + hash, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(1600);
      const shotPath = path.join(SHOTS, `${TAG}-${name}-${w}.png`);
      const buf = await page.screenshot({ path: shotPath, fullPage: true });
      let m;
      try { m = await page.evaluate(MEASURE); } catch (e) { m = { error: String(e).slice(0, 300) }; }
      if (m && !m.error) {
        const img = decodePng(buf);
        /* 像素配额 */
        let n = 0, nearWhite = 0, pureWhite = 0, structure = 0, dark = 0, colored = 0;
        const hist2 = new Map();
        for (let y = 0; y < img.height; y += 1) {
          for (let x = 0; x < img.width; x += 1) {
            const p = px(img, x, y);
            n++;
            const l = flatLum(p), s = satOf(p);
            const key = (p[0] << 16) | (p[1] << 8) | p[2];
            hist2.set(key, (hist2.get(key) || 0) + 1);
            if (l > 0.965) nearWhite++;
            if (p[0] === 255 && p[1] === 255 && p[2] === 255) pureWhite++;
            if (s > 0.28) colored++;
            else if (l < 0.25) dark++;
            else if (l <= 0.955) structure++;
          }
        }
        const pct = (v) => +((v / n) * 100).toFixed(2);
        m.pixel = {
          sampled: n, size: `${img.width}x${img.height}`,
          nearWhitePct: pct(nearWhite), pureWhitePct: pct(pureWhite),
          structurePct: pct(structure), coloredPct: pct(colored), darkPct: pct(dark),
          topColors: [...hist2.entries()].sort((a, b) => b[1] - a[1]).slice(0, 9)
            .map(([k, v]) => ({ hex: '#' + k.toString(16).padStart(6, '0'), pct: pct(v) })),
        };
        /* 侧栏内部 vs 页面底（同色问题） */
        const sb = m.rects.sidebar;
        if (sb && sb.w > 20) {
          const inner = px(img, sb.x + 8, sb.y + Math.round(sb.h * 0.5));
          const outer = px(img, sb.x - 8, sb.y + Math.round(sb.h * 0.5));
          const gap = m.rects.main ? px(img, m.rects.main.x - 6, sb.y + Math.round(sb.h * 0.5)) : null;
          m.sidebarVsFloor = {
            insideAt: `${sb.x + 8},${sb.y + Math.round(sb.h * 0.5)}`, inside: hexOf(inner),
            outside: hexOf(outer), gapBetween: gap ? hexOf(gap) : null,
            deltaRGB: Math.max(...[0, 1, 2].map((i) => Math.abs(inner[i] - outer[i]))),
            contrast: cr(inner, outer),
            sameColor: hexOf(inner) === hexOf(outer),
          };
        } else m.sidebarVsFloor = null;
        /* 纸面左缘/上缘的阴影带：在纸面外侧找最暗像素 */
        const pap = m.rects.paper;
        if (pap) {
          const scan = (x0, x1, y0, y1, axis) => {
            let best = null;
            if (axis === 'x') {
              const y = y0 + Math.min(50, Math.round((y1 - y0) / 2));
              for (let x = x0 - 1; x >= x0 - 14; x--) { const p = px(img, x, y); const l = lum(p); if (!best || l < best.l) best = { l, hex: hexOf(p), at: `${x},${y}` }; }
              const paperPx = px(img, x0 + 6, y);
              return { darkest: best, paper: hexOf(paperPx), contrastVsPaper: cr(hexToRgb(best.hex), paperPx) };
            }
            const x = x0 + Math.min(120, Math.round((x1 - x0) / 2));
            for (let y = y0 - 1; y >= y0 - 14; y--) { const p = px(img, x, y); const l = lum(p); if (!best || l < best.l) best = { l, hex: hexOf(p), at: `${x},${y}` }; }
            const paperPx = px(img, x, y0 + 6);
            return { darkest: best, paper: hexOf(paperPx), contrastVsPaper: cr(hexToRgb(best.hex), paperPx) };
          };
          m.paperEdges = {
            rect: pap, sel: m.rects.paperSel,
            left: scan(pap.x, 0, pap.y, pap.y + pap.h, 'x'),
            top: scan(pap.x, pap.x + pap.w, pap.y, 0, 'y'),
          };
        } else m.paperEdges = null;
        /* 凹槽（composer）与其上方纸面的像素差 */
        const s2 = m.rects.surface2;
        if (s2) {
          const inside = px(img, s2.x + Math.round(s2.w / 2), s2.y + Math.round(s2.h / 2));
          const above = px(img, s2.x + Math.round(s2.w / 2), s2.y - 6);
          m.groove = { rect: s2, inside: hexOf(inside), above: hexOf(above), contrast: cr(inside, above), insetTop: px(img, s2.x + Math.round(s2.w / 2), s2.y + 1) };
        } else m.groove = null;
      }
      m.shot = `_shots/p0-tokens/${TAG}-${name}-${w}.png`;
      results.routes[name][w] = m;
      await ctx.close();
      console.log(`  ${TAG} ${name}@${w} ok`);
    }
  }
  await browser.close();
  const dest = path.join(HERE, `${TAG}.json`);
  fs.writeFileSync(dest, JSON.stringify(results, null, 1));
  console.log('WROTE', dest);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
