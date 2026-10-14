/**
 * 把 before.json / after.json 汇总成改前→改后的对照表。
 *   node _tools/p0-tokens/summarize.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const load = (t) => { const p = path.join(HERE, `${t}.json`); return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null; };
const before = load('before');
const after = load('after');
const ROUTES = ['portal', 'chat', 'profile', 'report', 'plan'];
const WIDTHS = [1280, 390];
const pad = (s, n) => String(s ?? '—').padEnd(n);
const num = (s, n = 6) => String(s ?? '—').padStart(n);

const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4; };
const h2r = (h) => { const s = (h || '').replace('#', ''); return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16)); };
const lum = (h) => { const [r, g, b] = h2r(h); return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); };
const cr = (a, b) => { const l1 = lum(a), l2 = lum(b); const hi = Math.max(l1, l2), lo = Math.min(l1, l2); return ((hi + 0.05) / (lo + 0.05)).toFixed(3); };
const firstColor = (tok) => { const m = /#[0-9a-f]{6}/i.exec(tok || ''); return m ? m[0] : null; };
const pct = (v) => (v === undefined ? '—' : v + '%');

/* ---------- 1. 分层判据表 ---------- */
function structureTable(snap) {
  if (!snap) return [];
  const t = snap.routes.chat['1280'].tokens;
  const paper = firstColor(t['c-surface']);
  const P = {
    '① L0 页底 → L1 纸面': [firstColor(t['c-bg']), paper],
    '② L2 局部面 → L1 纸面': [firstColor(t['c-surface-2']), paper],
    '③ 交互面 surface-3 → 纸面': [firstColor(t['c-surface-3']), paper],
    '④ 发丝线 --c-border → 纸面': [firstColor(t['c-border']), paper],
    '⑤ 强描边 --c-border-strong → 纸面': [firstColor(t['c-border-strong']), paper],
    '⑥ 控件边 --field-border → 纸面': [firstColor(t['field-border']), paper],
    '⑦ 发丝线 → 页底': [firstColor(t['c-border']), firstColor(t['c-bg'])],
    '⑧ 说明字 --c-text-3 → 纸面': [firstColor(t['c-text-3']), paper],
    '⑨ 旧刻度色 --c-text-4 → 纸面': [firstColor(t['c-text-4']), paper],
  };
  const out = [];
  for (const [k, [a, b]] of Object.entries(P)) if (a && b) out.push([k, cr(a, b), a, b]);
  return out;
}

/* ---------- 2. 屏幕像素的"层占比"（按命名色匹配，比"近白占比"可读） ---------- */
function layerShares(snap, route = null, width = null) {
  const keys = ['c-surface', 'c-bg', 'c-surface-2', 'c-surface-3', 'c-border'];
  const t = snap.routes.chat['1280'].tokens;
  const named = keys.map((k) => [k, firstColor(t[k])]);
  const acc = Object.fromEntries(named.map(([k]) => [k, []]));
  for (const r of (route ? [route] : ROUTES)) for (const w of (width ? [width] : WIDTHS)) {
    const m = snap.routes[r][w];
    for (const c of m.pixel.topColors) {
      for (const [k, hex] of named) if (hex === c.hex) acc[k].push(c.pct);
    }
  }
  return Object.fromEntries(Object.entries(acc).map(([k, arr]) => [k, arr.length ? +(arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(2) : 0]));
}

/* ---------- 3. 字号分布 ---------- */
function fontHist(snap) {
  const h = {}; let total = 0;
  for (const r of ROUTES) for (const w of WIDTHS) {
    const fs = snap.routes[r][w].fontSizes || {};
    for (const [k, v] of Object.entries(fs)) { h[k] = (h[k] || 0) + v; total += v; }
  }
  return { h, total };
}

/* ---------- 4. 12px 节点的文件归属（谁能改） ---------- */
const OOS = /^li\.p7-|^span\.p7-|^time\.p7-|^span\.confidence|^em\.p7-|^b\.mtr__|^span\.cf__|^text\./;
function fs12Attribution(snap) {
  const inScope = new Map(), outScope = new Map();
  for (const r of ROUTES) for (const w of WIDTHS) for (const item of (snap.routes[r][w].fontSizeBySel['12'] || [])) {
    const [sel, n] = item.split('×');
    const k = `${sel}`;
    const map = OOS.test(sel) ? outScope : inScope;
    map.set(k, (map.get(k) || 0) + Number(n));
  }
  const sum = (m) => [...m.values()].reduce((a, b) => a + b, 0);
  return { inScope, outScope, inTotal: sum(inScope), outTotal: sum(outScope) };
}

/* ---------- 输出 ---------- */
console.log('########## 1. 结构层判据（改前 → 改后） ##########');
const bt = structureTable(before), at = structureTable(after);
console.log(`${pad('关系', 36)} ${num('改前', 7)} ${num('改后', 7)}   色值`);
for (const [k, v, a1, b1] of bt) {
  const a = at.find((x) => x[0] === k);
  console.log(`${pad(k, 36)} ${num(v, 7)} ${num(a ? a[1] : '—', 7)}   ${a1} / ${b1}${a ? '  →  ' + a[2] + ' / ' + a[3] : ''}`);
}
if (before && after) {
  console.log('\n令牌数值改前→改后：');
  const tb = before.routes.chat['1280'].tokens, ta = after.routes.chat['1280'].tokens;
  for (const k of Object.keys(tb)) if (tb[k] !== ta[k]) console.log(`  --${pad(k, 16)} ${pad(tb[k], 42)} → ${ta[k]}`);
}

console.log('\n########## 2. 屏幕像素的层占比（5 路由 × 2 档平均） ##########');
console.log(`${pad('层', 26)} ${num('改前', 8)} ${num('改后', 8)}`);
const lb = before ? layerShares(before) : {}, la = after ? layerShares(after) : {};
const LNAME = { 'c-surface': 'L1 纸面（当前值）', 'c-bg': 'L0 页底', 'c-surface-2': 'L2 局部面', 'c-surface-3': '交互面', 'c-border': '结构线' };
for (const k of ['c-surface', 'c-bg', 'c-surface-2', 'c-surface-3', 'c-border']) {
  console.log(`${pad(LNAME[k], 26)} ${num(lb[k], 8)} ${num(la[k], 8)}`);
}
if (before && after) {
  console.log('\n各路由 nearWhite（=评审口径：加权亮度>0.965，注意 #f7f6f6 也算近白）：');
  for (const r of ROUTES) for (const w of WIDTHS) {
    console.log(`  ${pad(r, 8)}@${pad(w, 5)} 近白 ${num(before.routes[r][w].pixel.nearWhitePct, 6)}% → ${num(after.routes[r][w].pixel.nearWhitePct, 6)}%   纯白 ${num(before.routes[r][w].pixel.pureWhitePct, 6)}% → ${num(after.routes[r][w].pixel.pureWhitePct, 6)}%`);
  }
}

console.log('\n########## 3. 字号分布（5 路由 × 2 档合计，按可见文本节点数） ##########');
const hb = fontHist(before).h, ha = fontHist(after).h;
const totB = fontHist(before).total, totA = fontHist(after).total;
const keys = [...new Set([...Object.keys(hb), ...Object.keys(ha)])].map(Number).sort((a, b) => a - b);
console.log(`${pad('字号', 9)} ${num('改前节点', 9)} ${num('改前占比', 9)} ${num('改后节点', 9)} ${num('改后占比', 9)}`);
for (const k of keys) {
  const b = hb[k] || 0, a = ha[k] || 0;
  console.log(`${pad(k + 'px', 9)} ${num(b, 9)} ${num(((b / totB) * 100).toFixed(1) + '%', 9)} ${num(a, 9)} ${num(((a / totA) * 100).toFixed(1) + '%', 9)}`);
}
console.log(`合计 ${totB} → ${totA} 节点`);
console.log('\n12px 节点的文件归属（按选择器，合计 top14 覆盖数）：');
const ab = before ? fs12Attribution(before) : null, aa = after ? fs12Attribution(after) : null;
if (ab && aa) {
  console.log(`  本次写权限内（styles/*.css）: ${ab.inTotal} → ${aa.inTotal}`);
  console.log(`  写权限外（views/·components/ 的 scoped）: ${ab.outTotal} → ${aa.outTotal}`);
  console.log('  改后仍在 12px 的写权限外选择器：');
  for (const [k, n] of [...aa.outScope.entries()].sort((a, b) => b[1] - a[1]).slice(0, 16)) console.log(`    ${num(n, 4)}  ${k}`);
}

console.log('\n########## 4. 逐路由：字号/像素/侧栏/纸缘/凹槽/刻度/控件 ##########');
for (const label of ['before', 'after']) {
  const snap = label === 'before' ? before : after;
  if (!snap) continue;
  console.log(`\n===== ${label} =====`);
  for (const r of ROUTES) for (const w of WIDTHS) {
    const m = snap.routes[r][w];
    const fs = m.fontSizes || {}; const tot = Object.values(fs).reduce((a, b) => a + b, 0);
    const p = m.pixel || {};
    console.log(`${pad(r, 8)}@${pad(w, 5)} 12px=${num(fs['12'] || 0, 4)}(${num(((fs['12'] || 0) / tot * 100).toFixed(0), 3)}%) 14px=${num(fs['14'] || 0, 4)} 16px=${num(fs['16'] || 0, 3)} <12px=${num((m.sub12 || []).length, 2)} | 近白 ${num(p.nearWhitePct)}% 纯白 ${num(p.pureWhitePct)}% | 控件高度档=${JSON.stringify(m.controls.heights)}`);
    if (m.sidebarVsFloor) console.log(`         侧栏 内=${m.sidebarVsFloor.inside} 外=${m.sidebarVsFloor.outside} 差=${m.sidebarVsFloor.deltaRGB} 对比=${m.sidebarVsFloor.contrast} same=${m.sidebarVsFloor.sameColor}`);
    if (m.paperEdges) console.log(`         纸缘左最暗=${m.paperEdges.left.darkest.hex} (vs 纸 ${m.paperEdges.left.contrastVsPaper}) 上最暗=${m.paperEdges.top.darkest.hex} (vs 纸 ${m.paperEdges.top.contrastVsPaper})`);
    if (m.groove) console.log(`         凹槽 内=${m.groove.inside} 上方=${m.groove.above} 对比=${m.groove.contrast}`);
    const ticks = Array.isArray(m.chartTicks) ? (m.chartTicks.labels || m.chartTicks.filter((t) => t.fs === 12)) : (m.chartTicks && m.chartTicks.labels) || [];
    if (ticks.length) console.log(`         图表刻度 n=${ticks.length} ${ticks[0].color} on ${ticks[0].bg} = ${ticks[0].cr}:1`);
    if (m.letterSpacingOver && m.letterSpacingOver.length) console.log(`         字距越界: ${m.letterSpacingOver.slice(0, 2).join(' ; ')}`);
    if (m.positiveTracking && m.positiveTracking.length) console.log(`         中文正字距: ${m.positiveTracking.slice(0, 2).join(' ; ')}`);
    if (m.uaDefaultHeadings && m.uaDefaultHeadings.length) console.log(`         UA默认档 n=${m.uaDefaultHeadings.length}`);
  }
}

console.log('\n########## 5. 低对比文字（<4.5:1）与内容列宽度 ##########');
for (const label of ['before', 'after']) {
  const snap = label === 'before' ? before : after;
  if (!snap) continue;
  const set = new Set();
  for (const r of ROUTES) for (const w of WIDTHS) for (const t of (snap.routes[r][w].lowContrast || [])) set.add(`${t.cr}:1 ${t.fs}px ${t.color} on ${t.bg} ${t.tag}.${t.cls}`);
  console.log(` ${label}: ${set.size} 类`);
  [...set].slice(0, 6).forEach((s) => console.log('   ' + s));
  console.log(` ${label} 内容列 max-width：`);
  for (const r of ROUTES) {
    const c = snap.routes[r]['1280'].containers.filter((x) => x.present && ['.ws-page', '.ws-conversation', '.journey-page', '.assessment-page', '.dialogue-page'].includes(x.q));
    console.log(`   ${pad(r, 8)} ${c.map((x) => `${x.q}=${x.maxWidth}`).join('  ')}`);
  }
  console.log(` ${label} plan@1280 控件高度明细：${(snap.routes.plan['1280'].controls.heightBySel || []).slice(0, 8).join(' | ')}`);
}
