/* =============================================================================
 * c2-hbu 视图盘点（只读）
 * -----------------------------------------------------------------------------
 * 用途：多作者并行施工时，一眼看清每个视图的"落地程度"，以及结构是否完好。
 *   node _tools/inspect.mjs
 * 报告每个视图：行数 / 根元素 / div 配平 / 分区数与折叠数 / 视角重组数 /
 *               自有前缀类数 / 是否缺 css、缺 js / 是否还在 views.json 里
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, '..', '_src');
const registry = JSON.parse(fs.readFileSync(path.join(SRC, 'views.json'), 'utf8'));
const keys = Object.keys(registry).filter((k) => !k.startsWith('_'));
const has = (dir, file) => fs.existsSync(path.join(SRC, dir, file));

const counts = (s, re) => (s.match(re) || []).length;
const rows = [];
const problems = [];

for (const key of keys) {
  const vPath = path.join(SRC, 'views', `${key}.html`);
  if (!fs.existsSync(vPath)) {
    rows.push({ key, view: '缺', css: has('css', key + '.css') ? 'OK' : '--', js: has('js', key + '.js') ? 'OK' : '--' });
    continue;
  }
  const s = fs.readFileSync(vPath, 'utf8');
  const open = counts(s, /<div\b/g);
  const close = counts(s, /<\/div>/g);
  const root = counts(s, /<div class="main__scroll"/g);
  const stats = {
    key,
    lines: s.split('\n').length,
    root,
    div: `${open}/${close}`,
    balanced: open === close,
    sec: counts(s, /class="sec[ "]/g),
    lens: counts(s, /class="lens"/g),
    zoom: counts(s, /class="zoom"/g),
    fold: counts(s, /<details\b/g),
    src: counts(s, /class="src[ "]/g),
    conf: counts(s, /class="conf[ "]/g),
    demo: /tag--demo/.test(s),
    own: counts(s, new RegExp(`class="${key.slice(0, 3)}-`, 'g')),
    css: has('css', key + '.css') ? 'OK' : '--',
    js: has('js', key + '.js') ? 'OK' : '--',
  };
  rows.push(stats);

  if (root !== 1) problems.push(`${key}: 根元素 .main__scroll 出现 ${root} 次（应为 1）`);
  if (open !== close) problems.push(`${key}: <div> ${open} 个 / </div> ${close} 个，不配平`);
  if (!stats.demo) problems.push(`${key}: 页头没有 tag--demo 演示数据标记`);
  if (!has('css', key + '.css') && key !== 'chat') problems.push(`${key}: 没有 _src/css/${key}.css（自有类会没有样式）`);
}

const pad = (v, n) => String(v).padEnd(n);
console.log(pad('view', 13) + pad('行数', 7) + pad('根', 4) + pad('div 配平', 12) + pad('sec', 5) + pad('lens', 6) +
  pad('zoom', 6) + pad('fold', 6) + pad('src', 5) + pad('conf', 6) + pad('own类', 7) + pad('css', 6) + 'js');
for (const r of rows) {
  if (r.view === '缺') {
    console.log(pad(r.key, 13) + pad('—', 7) + pad('—', 4) + pad('—', 12) + pad('—', 5) + pad('—', 6) + pad('—', 6) +
      pad('—', 6) + pad('—', 5) + pad('—', 6) + pad('—', 7) + pad(r.css, 6) + r.js + '   ← 还没写');
    continue;
  }
  console.log(pad(r.key, 13) + pad(r.lines, 7) + pad(r.root, 4) + pad(r.div + (r.balanced ? '' : ' ✗'), 12) +
    pad(r.sec, 5) + pad(r.lens, 6) + pad(r.zoom, 6) + pad(r.fold, 6) + pad(r.src, 5) + pad(r.conf, 6) +
    pad(r.own, 7) + pad(r.css, 6) + r.js);
}

const missing = keys.filter((k) => !fs.existsSync(path.join(SRC, 'views', `${k}.html`)));
console.log(`\n视图 ${keys.length - missing.length}/${keys.length} 已落地` + (missing.length ? `；缺：${missing.join(', ')}` : ''));

/* ---- 面包屑校验：必须是「分组 › 页面」 ------------------------------------
   BRIEF 的口径是 `分组 › 页面`（回答"我在全站的什么位置"）。
   实测有页面写成 `兄弟页 › 分组 › 当前页` —— 第一个是同级页面，不是分组，
   读起来像"你从那里来的"，而不是"你在哪一层"。这里逐页对一遍。 */
const crumbProblems = [];
for (const key of keys) {
  const vPath = path.join(SRC, 'views', `${key}.html`);
  if (!fs.existsSync(vPath)) continue;
  const s = fs.readFileSync(vPath, 'utf8');
  const m = s.match(/<p class="crumb">([\s\S]*?)<\/p>/);
  if (!m) { crumbProblems.push(`${key}: 没有面包屑`); continue; }
  const chain = m[1]
    .replace(/<svg[\s\S]*?<\/svg>/g, ' › ')
    .replace(/<[^>]+>/g, '')
    .split('›').map((x) => x.replace(/\s+/g, ' ').trim()).filter(Boolean);
  const wantGroup = registry[key].group;
  const wantTitle = registry[key].title;
  if (chain.length > 2) crumbProblems.push(`${key}: 面包屑多了同级页面 —— ${chain.join(' › ')}（应为 ${wantGroup} › ${wantTitle}）`);
  else if (chain[chain.length - 1] !== wantTitle) crumbProblems.push(`${key}: 末段不是页面名 —— ${chain.join(' › ')}（应为 ${wantTitle}）`);
  else if (chain.length === 2 && chain[0] !== wantGroup) crumbProblems.push(`${key}: 首段不是分组 —— ${chain.join(' › ')}（分组应为 ${wantGroup}）`);
}
if (crumbProblems.length) {
  console.log(`\n面包屑 ${crumbProblems.length} 处与「分组 › 页面」不符：`);
  for (const c of crumbProblems) console.log('  · ' + c);
}

if (problems.length) {
  console.log(`\n${problems.length} 条结构问题：`);
  for (const p of problems) console.log('  · ' + p);
  process.exitCode = 1;
} else {
  console.log('结构自检全过。');
}
