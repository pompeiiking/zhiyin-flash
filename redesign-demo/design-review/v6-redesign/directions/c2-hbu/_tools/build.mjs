/* =============================================================================
 * c2-hbu 样张构建脚本（v2：多视图版）
 * -----------------------------------------------------------------------------
 * v1 的做法是"读 c-companion/index.html，只换 <style> 层"，所以它只能产出
 * **一个视图**。现在这份样张要覆盖学生端全部界面，v1 的结构不够用了，改成：
 *
 *   _tools/c2.css        ← 样式基线（已批准，本脚本只读不改）
 *   _src/css/*.css       ← 追加样式层，按文件名排序拼接
 *   _src/shell/head.html ← <style> 之前的一切
 *   _src/shell/body-a.html ← <style> 之后、主区内容之前（品牌条 + 导航 + 顶栏 + <main>）
 *   _src/views/*.html    ← 每个视图的主区内容（自动包成 <section class="view">）
 *   _src/shell/body-b.html ← </main> 之后、<script> 之前（scrim + 移动底栏）
 *   _src/app.js          ← 外壳行为（路由 / 三轴 / 头像 / 导航）
 *   _src/js/*.js         ← 各视图自己的行为，按文件名排序拼接
 *   _src/shell/tail.html ← </script> 起
 *
 * 幂等：只读 _src/ 与 c2.css，不读自己上一次的输出 → 连跑两次逐字节相同。
 *
 * 门禁（非 --strict 时为告警，--strict 时退出码 1）：
 *   1. 视图必须有 _src/views.json 里的登记，登记了必须有文件
 *   2. 全文档 id 不得重复（多视图同处一个文档，这是最容易踩的坑）
 *   3. href="#/xxx" 必须指向存在的视图
 *   4. var(--x) 用到的令牌必须有定义
 *   5. 每个视图片段必须非空且以 .main__scroll 或 .main__fixed 起头
 *
 * 用法：
 *   node _tools/build.mjs            # 组装 + 告警
 *   node _tools/build.mjs --strict   # 全部告警升级为失败（交付前跑这个）
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
const SRC = path.join(DIR, '_src');
const STRICT = process.argv.includes('--strict');

/* ---- 预览模式（并行施工的关键） -------------------------------------------
   多个视图作者同时跑 `build.mjs` 会互相踩同一个 index.html。
   所以作者用 `--only <key>`：只把自己那一个视图+完整外壳+全部样式装成一个
   独立文件写进 _shots/preview-<key>.html，各写各的，互不干扰。
   交付时再跑不带参数的完整构建。 */
const argv = process.argv.slice(2);
const onlyIdx = argv.indexOf('--only');
const ONLY = onlyIdx >= 0 ? argv[onlyIdx + 1] : null;
const OUT = ONLY
  ? path.join(DIR, '_shots', `preview-${ONLY}.html`)
  : path.join(DIR, 'index.html');

const problems = [];
const notes = [];
const warn = (m) => problems.push(m);
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');

const read = (p) => fs.readFileSync(p, 'utf8');
function listOrEmpty(dir, ext) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => f.endsWith(ext)).sort();
}

/* ---- 1. 样式层 ------------------------------------------------------------ */
const BASE_CSS = read(path.join(HERE, 'c2.css'));
const layerFiles = listOrEmpty(path.join(SRC, 'css'), '.css');
const layers = layerFiles.map((f) => ({ file: f, css: read(path.join(SRC, 'css', f)).trim() }));
const css = [BASE_CSS.trim(), ...layers.map((l) => l.css)].join('\n\n');

/* ---- 2. 视图 -------------------------------------------------------------- */
const REG_PATH = path.join(SRC, 'views.json');
if (!fs.existsSync(REG_PATH)) throw new Error('缺 _src/views.json（视图登记表）');
const registry = JSON.parse(read(REG_PATH));
const viewFiles = listOrEmpty(path.join(SRC, 'views'), '.html');
const viewKeys = viewFiles.map((f) => f.replace(/\.html$/, ''));
/* views.json 里以 _ 开头的键是说明（_doc），不是视图 */
const registered = Object.keys(registry).filter((k) => !k.startsWith('_'));

/* 预览模式：只装这一个视图。缺别的视图不算问题（它们还没写完）。 */
if (ONLY && !viewKeys.includes(ONLY)) throw new Error(`--only ${ONLY}：没有 _src/views/${ONLY}.html`);
const buildKeys = ONLY ? [ONLY] : viewKeys;
if (!ONLY) {
  for (const k of registered) if (!viewKeys.includes(k)) warn(`views.json 登记了 "${k}" 但没有 _src/views/${k}.html`);
}
for (const k of viewKeys) if (!registered.includes(k)) warn(`_src/views/${k}.html 没有在 views.json 里登记`);
if (!viewKeys.includes('chat')) throw new Error('对话页（views/chat.html）是基线，不能缺');

/* 视图不套包裹层：每个视图片段本身就是单一滚动根（.main__scroll），
   把 data-view / data-active 注入它的根元素即可 —— 这样对话页的标记一行都不用改，
   也不必用 display:contents 去接父级布局（那在部分引擎里会把元素从无障碍树里摘掉）。 */
const sections = buildKeys.map((key) => {
  const html = read(path.join(SRC, 'views', `${key}.html`)).trimEnd();
  if (!html.trim()) warn(`视图 ${key} 片段为空`);
  const rootRe = /<div class="main__scroll"([^>]*)>/;
  const m = html.match(rootRe);
  if (!m) {
    warn(`视图 ${key} 片段找不到根元素 <div class="main__scroll" ...>`);
    return `\n    <!-- ===== 视图：${key} ===== -->\n` + html;
  }
  const active = key === 'chat' || key === ONLY ? ' data-active="true"' : '';
  const injected = `<div class="main__scroll" data-view="${key}"${active}${m[1]}>`;
  return `\n    <!-- ===== 视图：${key}（${registry[key] ? registry[key].title : '未登记'}）===== -->\n`
    + html.replace(rootRe, injected);
}).join('\n');

/* ---- 3. 外壳 + 行为 ------------------------------------------------------- */
const shell = (n) => read(path.join(SRC, 'shell', n));
const jsFiles = listOrEmpty(path.join(SRC, 'js'), '.js');
const viewJs = jsFiles.map((f) => `\n/* ---- _src/js/${f} ---- */\n` + read(path.join(SRC, 'js', f)).trim() + '\n');

/* 视图登记表注入外壳：目录面板与 <title> 都读这一份，避免在标记里硬编码第二份清单 */
const registryJson = JSON.stringify(
  viewKeys.map((k) => ({ key: k, ...(registry[k] || { title: k }), exists: true })),
  null, 0
);
const bodyA = shell('body-a.html').replace(
  '<!--VIEW-REGISTRY-->',
  `<script type="application/json" id="viewRegistry">${registryJson}</script>`
);

let html =
  shell('head.html') +
  '<style>\n' + css + '\n</style>' +
  bodyA +
  sections + '\n' +
  shell('body-b.html') +
  '<script>\n' +
  read(path.join(SRC, 'app.js')).trimEnd() +
  '\n' + viewJs.join('') +
  '\n' + shell('tail.html');

/* ---- 4. 门禁：全文档 id 唯一 ----------------------------------------------
   只扫 <script> 之前的标记部分：脚本里 AVATAR_SVG 的模板串也写着 id="' + uid + '"，
   那是运行时生成的 SVG，不是文档里的重复 id（第一版扫全文，报了一次假警）。 */
{
  const markup = html.split('<script>')[0];
  const ids = [...markup.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  const seen = new Map();
  for (const id of ids) seen.set(id, (seen.get(id) || 0) + 1);
  const dup = [...seen].filter(([, n]) => n > 1).map(([id, n]) => `${id}×${n}`);
  if (dup.length) warn(`id 重复（多视图同处一个文档时最危险）：${dup.join(', ')}`);
}

/* ---- 5. 门禁：视图链接必须存在 --------------------------------------------
   预览模式下别的视图还没写完，链接指向不存在的视图是**正常的**，不报警。 */
if (!ONLY) {
  const targets = [...html.matchAll(/href="#\/([a-zA-Z0-9_-]+)"/g)].map((m) => m[1]);
  const missing = [...new Set(targets)].filter((t) => !viewKeys.includes(t));
  if (missing.length) warn(`导航指向不存在的视图：${missing.join(', ')}`);
  const unlinked = viewKeys.filter((k) => !targets.includes(k) && k !== 'chat' && !registry[k]?.offNav);
  if (unlinked.length) notes.push(`没有入口的视图（门户/登录/异常页等可以没有）：${unlinked.join(', ')}`);
}

/* ---- 6. 门禁：令牌 -------------------------------------------------------- */
{
  const RUNTIME = new Set(['--chart-bar']);
  const used = new Set([...html.matchAll(/var\((--[a-z0-9-]+)/gi)].map((m) => m[1]));
  const defs = new Set([...css.matchAll(/(^|[\s;{])(--[a-z0-9-]+)\s*:/gim)].map((m) => m[2]));
  const missing = [...used].filter((v) => !defs.has(v) && !RUNTIME.has(v));
  if (missing.length) warn(`用到的令牌没有定义：${missing.join(', ')}`);
  notes.push(`令牌：用到 ${used.size} 个，定义 ${defs.size} 个`);
}

/* ---- 7. 门禁：跨视图样式撞车 ----------------------------------------------
   为什么单独加这一条：本项目出现过 4 次"规范被后加载文件覆盖"（HANDOFF §9.4），
   而原工程的 check-classes.mjs 对 BEM 修饰符式撞车抓不到。
   多视图共用一份拼接后的样式表时，这个风险更高：A 视图和 B 视图各自定义同名类，
   后加载的那个会**全局**生效 —— 哪怕两边都以为自己"只改了自己的页面"。
   判定：每个视图 css 里出现的类名，若同时出现在别的层里，就是一处真冲突。 */
{
  const layerOf = (name, text) => ({ name, text });
  const all = [layerOf('c2.css(基线)', BASE_CSS), ...layers.map((l) => layerOf(l.file, l.css))];

  /* 只统计"全局定义"：选择器的**主体**是裸类（没有祖先组合、没有属性限定、没有伪类之外的修饰）。
     · `.btn{…}`            → 全局定义 .btn（危险）
     · `.pf-act .btn{…}`    → 上下文覆盖，不算（有祖先组合）
     · `.lens__item[data-dim="true"]{…}` → 限定作用域，不算（有属性）
     · `@media` 里的规则要先剥掉包装再切块，否则整段媒体查询里的类会漏掉。 */
  function globalClasses(text) {
    const out = new Set();
    const bare = text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/@[^{;]+\{/g, '');
    for (const block of bare.split('}')) {
      const head = block.split('{')[0];
      if (!head) continue;
      for (const selRaw of head.split(',')) {
        let sel = selRaw.trim();
        if (!sel || sel.startsWith('@')) continue;
        sel = sel.replace(/::?[a-zA-Z-]+(\([^)]*\))?/g, '').trim(); // 去伪类/伪元素
        if (!sel || sel.includes('[')) continue;                    // 属性限定 → 不算全局
        if (/[\s>+~]/.test(sel)) continue;                          // 有祖先/兄弟组合 → 不算全局
        const m = sel.match(/^\.([a-zA-Z][a-zA-Z0-9_-]*)$/);
        if (m) out.add(m[1]);
      }
    }
    return out;
  }

  const owners = new Map();
  for (const layer of all) {
    for (const c of globalClasses(layer.text)) {
      if (!owners.has(c)) owners.set(c, []);
      owners.get(c).push(layer.name);
    }
  }
  const sharedLayers = new Set(['c2.css(基线)', ...layers.filter((l) => /^(00|10)-/.test(l.file)).map((l) => l.file)]);
  const crossView = [];
  const overrideShared = [];
  for (const [cls, files] of owners) {
    const viewFiles = files.filter((f) => !sharedLayers.has(f));
    if (viewFiles.length > 1) crossView.push(`.${cls}（${viewFiles.join(' + ')}）`);
    else if (viewFiles.length === 1 && files.length > 1) overrideShared.push(`.${cls}（${viewFiles[0]} 覆盖了共享层）`);
  }
  if (crossView.length) {
    warn(`两个视图全局定义了同一个类（后加载的会覆盖前一个）：${crossView.slice(0, 12).join('、')}`
      + (crossView.length > 12 ? ` 等 ${crossView.length} 处` : ''));
  }
  if (overrideShared.length) {
    notes.push(`视图层全局重定义了共享层的类：${overrideShared.slice(0, 10).join('、')}`
      + (overrideShared.length > 10 ? ` 等 ${overrideShared.length} 处` : ''));
  }
}

/* ---- 8. 写出 -------------------------------------------------------------- */
const stamp = [
  '<!-- build-stamp:',
  `views=${viewKeys.length}`,
  `css=${sha(css).slice(0, 12)}`,
  `base=${sha(BASE_CSS).slice(0, 12)}`,
  `chat=${sha(read(path.join(SRC, 'views', 'chat.html'))).slice(0, 12)}`,
  '-->'
].join(' ');
html = html.replace(/^<!doctype html>\n/i, (m) => m + stamp + '\n');
fs.writeFileSync(OUT, html, 'utf8');

const kb = (Buffer.byteLength(html, 'utf8') / 1024).toFixed(1);
console.log(`[ok] 写出 ${path.relative(process.cwd(), OUT)}  ${kb} KB · ${buildKeys.length} 个视图 · ${layers.length + 1} 层样式${ONLY ? '（预览模式：只装 --only ' + ONLY + '）' : ''}`);
console.log(`[ok] SHA-256 ${sha(Buffer.from(html, 'utf8'))}`);
console.log(`[ok] 视图：${viewKeys.join(', ')}`);
console.log(`[ok] 样式层：c2.css(基线) ${layers.map((l) => l.file).join(' ')}`);
for (const n of notes) console.log(`[info] ${n}`);
if (problems.length) {
  for (const p of problems) console.log(`[warn] ${p}`);
  console.log(`\n${problems.length} 条告警${STRICT ? '（--strict：失败）' : '（--strict 时会失败）'}`);
  if (STRICT) process.exitCode = 1;
} else {
  console.log('[ok] 门禁全过');
}
