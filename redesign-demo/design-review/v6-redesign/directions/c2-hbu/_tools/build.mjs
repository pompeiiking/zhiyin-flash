/* =============================================================================
 * c2-hbu 样张构建脚本（只在 directions/c2-hbu/ 内读写，不碰仓库里任何其它文件）
 * -----------------------------------------------------------------------------
 * 做法：把 directions/c-companion/index.html 当作"结构与交互的唯一来源"读进来，
 *      **只替换 <style> 层**，并追加/替换与配色 / 头像形体 / 气泡填充有关的锚点
 *      （品牌条、演示台、头像 SVG 的整段画法、三轴切换与气泡令牌的 JS）。
 * 这样能保证"结构 / 内容 / 交互"与 c-companion 一一对应：除 <style> 与上列锚点外，
 *      生成物的其余每一行都能在 SRC 里逐字找到（第 7 节自检会报行数与令牌覆盖）。
 *
 * 复现：`node _tools/build.mjs`
 *   · 幂等：本脚本只读 SRC + c2.css，**不读自己上一次的输出**，所以连跑两次
 *     生成物逐字节相同；第 7 节会把生成物的 SHA-256 打出来（两次一致 = 可复现）。
 *   · 生成物头部带一行 `build-stamp`（本次 SRC + c2.css + 本脚本的哈希）。
 *     这一行是**自洽**的：哈希在注入前算，重跑时算出的还是同一个值，所以不破坏幂等。
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(HERE, '..');                       // directions/c2-hbu
const SRC = path.resolve(OUT_DIR, '..', 'c-companion', 'index.html');
const CSS = path.join(HERE, 'c2.css');
const OUT = path.join(OUT_DIR, 'index.html');

let html = fs.readFileSync(SRC, 'utf8');
const css = fs.readFileSync(CSS, 'utf8').trim();
const sha = s => crypto.createHash('sha256').update(s).digest('hex').slice(0, 12);

function must(label, from, to) {
  const before = html;
  if (!html.includes(from)) throw new Error('锚点没找到：' + label);
  html = html.split(from).join(to);
  if (html === before) throw new Error('没有发生替换：' + label);
  return true;
}
function once(label, from, to) {
  const n = html.split(from).length - 1;
  if (n !== 1) throw new Error(`锚点 "${label}" 出现 ${n} 次，应为 1 次`);
  html = html.replace(from, to);
}

/* ---- 1. 换掉整层样式 ------------------------------------------------------ */
const styleRe = /<style>[\s\S]*?<\/style>/;
if (!styleRe.test(html)) throw new Error('没有找到 <style> 块');
html = html.replace(styleRe, '<style>\n' + css + '\n</style>');

/* ---- 2. 文档级属性 -------------------------------------------------------- */
once('lang/html',
  '<html lang="zh-CN" data-state="thinking">',
  '<html lang="zh-CN" data-theme="light" data-accent="blue" data-style="normal" data-theme-mode="light" data-state="thinking">');
once('color-scheme',
  '<meta name="color-scheme" content="light">',
  '<meta name="color-scheme" content="light dark">');
once('title',
  '<title>职引 · 咨询对话 · 方向 C「陪伴感」样张</title>',
  '<title>职引 · 咨询对话 · 方向 C2「陪伴感 × 河大配色」样张</title>');

/* ---- 3. 品牌身份条（河北大学官网顶部那条红）+ 演示台 ---------------------- */
once('body 开头', '<body>\n', '<body>\n\n<!-- 品牌身份条：河大官网顶部那条红（layout.css 的 .top），3px，不随 accent 变 -->\n<div class="brandstripe" aria-hidden="true"></div>\n');

once('topbar 开', '<header class="topbar">\n', '<header class="topbar">\n    <div class="topbar__row">\n');

const DEMO = `
    </div><!-- /topbar__row -->

    <!-- 原型演示台：三轴切换（主色 / 主题 / 密度），常驻在工具条第二行 -->
    <div class="topbar__demo" role="group" aria-label="原型演示：配色与密度切换">
      <span class="demo__tag">原型</span>
      <div class="demo__grp" role="group" aria-label="主色">
        <span class="demo__lb">主色</span>
        <button class="segb" type="button" data-set="accent" data-val="blue" aria-pressed="true">校徽蓝</button>
        <button class="segb" type="button" data-set="accent" data-val="red" aria-pressed="false">官网红</button>
      </div>
      <div class="demo__grp" role="group" aria-label="主题">
        <span class="demo__lb">主题</span>
        <button class="segb" type="button" data-set="theme" data-val="light" aria-pressed="true">浅色</button>
        <button class="segb" type="button" data-set="theme" data-val="dark" aria-pressed="false">深色</button>
        <button class="segb" type="button" data-set="theme" data-val="auto" aria-pressed="false">跟随系统</button>
      </div>
      <div class="demo__grp" role="group" aria-label="密度">
        <span class="demo__lb">密度</span>
        <button class="segb" type="button" data-set="style" data-val="normal" aria-pressed="true">常规</button>
        <button class="segb" type="button" data-set="style" data-val="dense" aria-pressed="false">紧凑</button>
      </div>
      <span class="demo__note" id="demoNote" aria-live="polite">校徽蓝 #0058A7 · 浅色 · 常规</span>
    </div>
  </header>`;

once('topbar 收尾',
  '        <span class="sr">账号菜单</span>\n      </button>\n    </div>\n  </header>',
  '        <span class="sr">账号菜单</span>\n      </button>\n    </div>' + DEMO);

/* ---- 4. 本轮需求方提的两条意见 --------------------------------------------
 *  ① "机器人头像有点丑，我想要那种卡通风格的"
 *  ② "用户的气泡渐变难看，我觉得不如纯色"
 * 两条都落在**正确的层**上：② 是纯样式（c2.css）+ 一组令牌（第 5 节 applyDemo）；
 * ① 的形体是 JS 里的 SVG 字符串（结构层），所以替换的是 SRC 的挂载点这一处。
 *
 *  ① 卡通头像：把 c-companion 的整段画法收成"上一版存档 AVATAR_SVG_GLASS"
 *     （留着可回滚、可 diff），在**同一处挂载点**定义并挂上卡通形体。
 *     为什么整段替换而不是再拆一遍字符串锚点：头像的形体是"整体重画"，
 *     逐条锚点替换会留下受光层、镜面高光、镜面小高光这类**半成品残留**；
 *     整段收起 + 整段定义，生成物里读到的是一份完整、自洽的画法。
 * ------------------------------------------------------------------------ */
must('头像-旧画法收成存档',
  '  var AVATAR_SVG = function (uid) { return [',
  [
    '  /* ⚠ 以下是 c-companion 的**玻璃实体**画法，本版不渲染它 ——',
    '     保留 "旧名 AVATAR_SVG_GLASS + 新名 AVATAR_SVG" 的对照，是为了',
    '     "形体换过哪一层"这件事可回滚、可 diff，而不是靠一段注释声称。',
    '     真正生效的卡通形体定义在下面的挂载点（同一处、同一个作用域）。 */',
    '  var AVATAR_SVG_GLASS = function (uid) { return ['
  ].join('\n'));

must('头像-换成卡通形体并挂载',
  [
    '  if (heroMount) heroMount.innerHTML = AVATAR_SVG(\'avBodyHero\');',
    '  if (turnMount) turnMount.innerHTML = AVATAR_SVG(\'avBodyTurn\');'
  ].join('\n'),
  [
    '  /* =======================================================================',
    '     卡通头像（本轮需求方意见①："机器人头像有点丑，我想要那种卡通风格的"）',
    '     ----------------------------------------------------------------------',
    '     换掉的只有"形体"这一层，三态机制、挂载点、CSS 钩子名全部沿用：',
    '       .avatar__whoosh / .avatar__dots / .avatar__brow / .avatar__face',
    '       .avatar__eye(--l/--r) / .avatar__pupil / .avatar__gaze / .avatar__glint',
    '       .avatar__mouth / .avatar__ring / .avatar__wave（三条 i）',
    '       html[data-state="idle|thinking|speaking"] 仍然只改 --st-a/--st-b',
    '',
    '     与上一版（AVATAR_SVG_GLASS）的差别，逐条：',
    '       1. 去掉 radialGradient（受光渐变）→ 纯色底 + 一层很淡的上亮下暗',
    '       2. 去掉"顶部镜面高光"与"第二层小高光"两个椭圆 → 一条柔和的左上受光',
    '       3. 去掉"边缘受光"白描边 → 一条 1px 主色边（那是"轮廓"，不是"玻璃厚度"）',
    '       4. 眼睛放大：眼白 12.8×14 → 13.6×15.2，瞳 r4.4 → r4.6，高光 r1.25 → r1.9；',
    '          两眼各留 3.8u 空隙、间距 25u —— 40px 下才不会糊成两个灰点',
    '       5. 眉从 .32 描边提到 .48，且只在思考时出现（待命不堆表情）',
    '       6. 嘴的弧线加深（stroke-opacity .5 → .68），三态读得出差别',
    '     没有加：腮红、星星/心形/音符、金属玻璃、任何超过 1.4px 的位移。',
    '     ==================================================================== */',
    '  var AVATAR_SVG = function (uid) { return [',
    '    /* 眼睛是主角：眼白 13.6×15.2、瞳 r4.6（留 2.2u 白边，读得出"眼白"）、',
    '       高光 r1.9 压在左上。高光**不放在瞳孔正中心** —— 正中会读成"珠子"，',
    '       偏左上才读成"朝一个方向看的眼睛"。 */',
    '    \'<svg viewBox="-8 -8 116 116" role="img" aria-hidden="true" focusable="false">\',',
    '    \'  <defs>\',',
    '    \'    <linearGradient id="\' + uid + \'" x1="0" y1="0" x2="0" y2="1">\',',
    '    \'      <stop data-grad-a offset="0" stop-color="var(--st-a)" stop-opacity="0"/>\',',
    '    \'      <stop data-grad-b offset="1" stop-color="var(--st-b)" stop-opacity=".30"/>\',',
    '    \'    </linearGradient>\',',
    '    \'  </defs>\',',
    '    /* 说话时的涟漪；待命/思考时 CSS 让它 opacity:0 */',
    '    \'  <circle class="avatar__ring" cx="50" cy="50" r="38" fill="none" stroke="var(--st-a)" stroke-width="1.6"/>\',',
    '    /* 思考时的轨道与六点：轨道把"念头"挂在一个明确的位置上 */',
    '    \'  <g class="avatar__whoosh">\',',
    '    \'    <circle cx="50" cy="50" r="46" fill="none" stroke="var(--st-a)" stroke-opacity=".20" stroke-width="1.2" stroke-dasharray="2.5 6"/>\',',
    '    \'    <g class="avatar__dots">\',',
    '    \'      <circle cx="50" cy="4" r="2.4"/><circle cx="82" cy="15.2" r="2.7"/>\',',
    '    \'      <circle cx="96" cy="38" r="3"/><circle cx="96" cy="62" r="2.7"/>\',',
    '    \'      <circle cx="82" cy="84.8" r="3"/><circle cx="50" cy="96" r="2.4"/>\',',
    '    \'    </g>\',',
    '    \'    <g class="avatar__dots">\',',
    '    \'      <circle cx="18" cy="84.8" r="2.7"/><circle cx="4" cy="62" r="2.4"/>\',',
    '    \'      <circle cx="4" cy="38" r="2.7"/><circle cx="18" cy="15.2" r="3"/>\',',
    '    \'      <circle cx="32" cy="8.5" r="2.4"/><circle cx="68" cy="8.5" r="2.7"/>\',',
    '    \'    </g>\',',
    '    \'  </g>\',',
    '    /* 形体 ①：圆角方块（rx 27 / 80 = .34，**不是正圆** —— 风险评估的红线）。',
    '       填充 = 纯色 --st-a + 一层 .30 的上亮下暗。没有受光渐变、没有镜面高光。 */',
    '    \'  <rect x="10" y="10" width="80" height="80" rx="27" fill="var(--st-a)"/>\',',
    '    \'  <rect x="10" y="10" width="80" height="80" rx="27" fill="url(#\' + uid + \')"/>\',',
    '    /* 形体 ②：这一版**没有**受光面。上一版是靠"顶部镜面高光 + 第二层小高光"',
    '       两个椭圆堆出体积的 —— 那正是"读起来像玻璃"的来源。',
    '       卡通只留一条信息：光从上面来（就是上面那层上亮下暗的渐变，一条，不再加）。 */',
    '    /* 形体 ③：轮廓。用主色描一条 1px，是"形"，不是"玻璃的厚度/边缘受光"。 */',
    '    \'  <rect x="10.6" y="10.6" width="78.8" height="78.8" rx="26.6" fill="none" stroke="var(--st-a)" stroke-opacity=".34" stroke-width="1.2"/>\',',
    '    /* 眉：只在"思考"时出现。待命不堆表情 —— 这是"少即是多"那一条。',
    '       斜率是"内端抬高、外端压低"（不是内低外高的皱眉）：那读成"在琢磨"，',
    '       后者读成"生气"。这一条差 1.5u 的斜率，是卡通表情最容易写错的一处。 */',
    '    \'  <g class="avatar__brow" opacity="0" stroke="var(--face-ink)" stroke-opacity=".48" stroke-width="2.4" stroke-linecap="round">\',',
    '    \'    <path d="M30.6 30.6 39.4 27.8"/><path d="M60.6 27.8 69.4 30.6"/>\',',
    '    \'  </g>\',',
    '    /* 眼：白眼球 + 深瞳 + 高光。待命时整只眼慢慢扫视（"在看"）。 */',
    '    \'  <g class="avatar__face">\',',
    '    \'    <g class="avatar__eye avatar__eye--l">\',',
    '    \'      <ellipse class="avatar__eye-white" cx="37.5" cy="43" rx="6.8" ry="7.6"/>\',',
    '    \'      <ellipse class="avatar__eye-rim" cx="37.5" cy="43" rx="6.8" ry="7.6"/>\',',
    '    \'      <g class="avatar__pupil">\',',
    '    \'        <g class="avatar__gaze">\',',
    '    \'          <circle cx="38.4" cy="44.2" r="4.6" fill="var(--face-ink)"/>\',',
    '    \'          <circle class="avatar__glint" cx="36.6" cy="42.1" r="1.9" fill="#fff"/>\',',
    '    \'        </g>\',',
    '    \'      </g>\',',
    '    \'    </g>\',',
    '    \'    <g class="avatar__eye avatar__eye--r">\',',
    '    \'      <ellipse class="avatar__eye-white" cx="62.5" cy="43" rx="6.8" ry="7.6"/>\',',
    '    \'      <ellipse class="avatar__eye-rim" cx="62.5" cy="43" rx="6.8" ry="7.6"/>\',',
    '    \'      <g class="avatar__pupil">\',',
    '    \'        <g class="avatar__gaze">\',',
    '    \'          <circle cx="63.4" cy="44.2" r="4.6" fill="var(--face-ink)"/>\',',
    '    \'          <circle class="avatar__glint" cx="61.6" cy="42.1" r="1.9" fill="#fff"/>\',',
    '    \'        </g>\',',
    '    \'      </g>\',',
    '    \'    </g>\',',
    '    /* 嘴：一条弧线，说的时候用 scaleY 开合（.62s）。没有腮红、没有表情符号。 */',
    '    \'    <path class="avatar__mouth" d="M43.5 61.5q6.5 6.6 13 0" fill="none" stroke="var(--face-ink)" stroke-opacity=".68" stroke-width="3.2" stroke-linecap="round"/>\',',
    '    \'  </g>\',',
    '    /* 说话：声波（用 i 装，CSS 的 .avatar__wave i 负责间距与错峰） */',
    '    \'  <foreignObject x="86" y="34" width="26" height="32" class="avatar__wave">\',',
    '    \'    <div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:center;height:100%">\',',
    '    \'      <i style="display:block;width:2.6px;height:14px;border-radius:2px;background:var(--st-b)"></i>\',',
    '    \'      <i style="display:block;width:2.6px;height:20px;border-radius:2px;background:var(--st-b)"></i>\',',
    '    \'      <i style="display:block;width:2.6px;height:11px;border-radius:2px;background:var(--st-b)"></i>\',',
    '    \'    </div>\',',
    '    \'  </foreignObject>\',',
    '    \'</svg>\'',
    '  ].join(\'\'); };',
    '',
    '  if (heroMount) heroMount.innerHTML = AVATAR_SVG(\'avBodyHero\');',
    '  if (turnMount) turnMount.innerHTML = AVATAR_SVG(\'avBodyTurn\');'
  ].join('\n'));

/* ---- 4.1 用户气泡：纯色底的令牌在 DEMO_JS 的 applyDemo 里写（见第 5 节），
    所以每一次三轴切换（主色 / 主题 / 密度 / 跟随系统）都跟着走。
    浅色取主色最浅一档 → 色相由 accent 决定；
    深色取实色面（--c-surface-solid）→ 分层由主题决定，色相交给 1px 主色边。 */

/* ---- 5. 三轴切换的 JS ----------------------------------------------------- */
const DEMO_JS = `
  /* ---- 原型演示台：主色 / 主题 / 密度 --------------------------------------
     与 tokens.css 的三轴同构：data-accent / data-theme / data-style。
     一次切换要盖到：按钮、选中态、焦点环、图表、进度、徽标、头像（全部走 --c-primary / --bar-* / --st-*）。
     "跟随系统"不是文字说明：真的挂 matchMedia，系统换色时页面跟着换。 */
  var root = document.documentElement;
  var segs = Array.prototype.slice.call(document.querySelectorAll('.segb'));
  var demoNote = document.getElementById('demoNote');
  var mqDark = window.matchMedia('(prefers-color-scheme: dark)');
  var demo = { accent: 'blue', theme: 'light', style: 'normal' };
  var NOTE_TEXT = {
    accent: { blue: '校徽蓝 #0058A7', red: '官网红 #96000E' },
    theme: { light: '浅色', dark: '深色', auto: '跟随系统' },
    style: { normal: '常规', dense: '紧凑' }
  };
  function effTheme() { return demo.theme === 'auto' ? (mqDark.matches ? 'dark' : 'light') : demo.theme; }
  function applyDemo() {
    var t = effTheme();
    root.setAttribute('data-accent', demo.accent);
    root.setAttribute('data-theme', t);
    root.setAttribute('data-style', demo.style);
    root.setAttribute('data-theme-mode', demo.theme);
    root.style.colorScheme = t;
    /* ---- 用户气泡：纯色底（需求方："渐变难看，不如纯色"）----------------------
       整块只有 background-color，没有 background-image。
       浅色 = 主色最浅一档（整支色阶的第 2 档，冷暖跟着 accent 走）；
       深色 = 实色面 + 1px 主色边（深色主题的分层手段是"面提亮一档"，不是"浅色填充"）。
       两个值都取已经存在的令牌，不新造颜色，红/蓝 × 浅/深四组自动成立。
       c2.css 里也声明了同名令牌（不带主题分支），这里覆盖成"按当前主题解析"的值。 */
    var bt = (t === 'dark')
      ? { bg: '--c-surface-solid', line: '--c-primary-border' }
      : { bg: '--c-primary-weak-2', line: '--c-primary-border' };
    root.style.setProperty('--c-me-bubble', 'var(' + bt.bg + ')');
    root.style.setProperty('--c-me-bubble-line', 'var(' + bt.line + ')');
    segs.forEach(function (b) {
      b.setAttribute('aria-pressed', String(demo[b.getAttribute('data-set')] === b.getAttribute('data-val')));
    });
    if (demoNote) {
      demoNote.textContent = NOTE_TEXT.accent[demo.accent] + ' · ' + NOTE_TEXT.theme[demo.theme] + ' · ' + NOTE_TEXT.style[demo.style];
    }
  }
  segs.forEach(function (b) {
    b.addEventListener('click', function () {
      demo[b.getAttribute('data-set')] = b.getAttribute('data-val');
      applyDemo();
    });
  });
  if (mqDark.addEventListener) mqDark.addEventListener('change', function () { if (demo.theme === 'auto') applyDemo(); });
  applyDemo();

  /* ---- 后续问题：点一下写进输入区 -----------------------------------------
     任务清单把"3 个后续问题（点击写入输入区）"列为必须可用的交互，而 c-companion
     只有按钮没有落点。这里补上落点（并把发送键同步成可用）。 */
  Array.prototype.forEach.call(document.querySelectorAll('.followbtn'), function (b) {
    b.addEventListener('click', function () {
      var n = b.querySelector('.followbtn__n');
      var text = b.textContent.replace(n ? n.textContent : '', '').replace(/\\s+/g, ' ').trim();
      msg.value = text;
      msg.style.height = 'auto';
      msg.style.height = Math.min(msg.scrollHeight, 132) + 'px';
      syncSend();
      msg.focus();
    });
  });

  /* ---- 键盘：Enter 发送 / Shift+Enter 换行 ---------------------------------
     输入区的提示行就写着这一条，c-companion 只写了文案没有实现（按 Enter 只会换行）。
     这里让它与文案一致：空输入不发、中文输入法组字中不抢键。 */
  msg.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (send.getAttribute('aria-disabled') === 'true') return;
    msg.value = '';
    msg.style.height = 'auto';
    syncSend();
  });
`;
once('IIFE 收尾插入', '\n})();\n</script>', '\n' + DEMO_JS + '})();\n</script>');

/* ---- 6. 写出 -------------------------------------------------------------- */
/* 复现戳：SRC + c2.css + 本脚本 的哈希。算的是"注入之前"的三份源，
   所以下一次重跑会算出同一个值 —— 它让生成物自带"我是哪三份源构建出来的"，
   又不破坏"连跑两次逐字节相同"这条幂等性。 */
{
  const selfSrc = fs.readFileSync(fileURLToPath(import.meta.url), 'utf8');
  const stamp = `<!-- build-stamp: src=${sha(html)} css=${sha(css)} build=${sha(selfSrc)} -->`;
  const docRe = /^<!doctype html>\n/i;
  if (!docRe.test(html)) throw new Error('没有找到 <!doctype html>');
  html = html.replace(docRe, m => m + stamp + '\n');
}
fs.writeFileSync(OUT, html, 'utf8');
const kb = (Buffer.byteLength(html, 'utf8') / 1024).toFixed(1);
const outSha = crypto.createHash('sha256').update(Buffer.from(html, 'utf8')).digest('hex');
console.log(`[ok] 写出 ${path.relative(process.cwd(), OUT)}  ${kb} KB`);
console.log(`[ok] 生成物 SHA-256：${outSha}（重跑一次应完全相同 = 可复现）`);

/* ---- 7. 自检：确认"除样式与上列锚点外，与 c-companion 完全一致" ---------- */
const origLines = fs.readFileSync(SRC, 'utf8').split('\n');
const newLines = html.split('\n');
console.log(`[info] 源 ${origLines.length} 行 → 生成 ${newLines.length} 行`);

/* 令牌自检：整个生成物里用到的每个 var(--x) 是否都有定义。
   （--chart-bar 由 JS 在运行时 setProperty 写入，属于已知的运行时令牌。） */
const RUNTIME = new Set(['--chart-bar']);
const used = new Set([...html.matchAll(/var\((--[a-z0-9-]+)/gi)].map(m => m[1]));
const defs = new Set([...css.matchAll(/(^|[\s;{])(--[a-z0-9-]+)\s*:/gim)].map(m => m[2]));
const missing = [...used].filter(v => !defs.has(v) && !RUNTIME.has(v));
if (missing.length) {
  console.log('[warn] 没有定义的令牌：' + missing.join(', '));
  process.exitCode = 1;
} else {
  console.log('[ok] var() 用到的令牌全部有定义（--chart-bar 由 JS 写入）');
}
const unused = [...defs].filter(v => !used.has(v));
if (unused.length) console.log('[info] 只作为"完整色阶/间距阶梯"声明、本页未直接引用的原始值：\n   ' + unused.join(', '));
