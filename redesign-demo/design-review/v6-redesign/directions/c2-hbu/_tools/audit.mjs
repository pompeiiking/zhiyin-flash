/* =============================================================================
 * c2-hbu 合规审计（只读）
 * -----------------------------------------------------------------------------
 * 逐条把上游文档里"可判定的说法"变成测量：
 *   A. 四个落点（DESIGN-LANGUAGE §3/§4）——每个界面至少命中三个
 *   B. 反例表（§5）——淡入/位移进场/数字滚动/粒子/发光边框/自动轮播/图表生长
 *      · 静态：CSS 里的 @keyframes 与 JS 里的计时器/循环
 *      · 运行时：**不做任何交互**时页面上正在跑的动画（"一进页面把动画播一遍"就是这条抓）
 *   C. 判定清单（§6）可量化的部分：状态可见、组织方式可改、即时反馈、
 *      reduced-motion 降级、桌面与手机都成立
 *   D. 视觉纪律：字号只有 5 档 / 字重只有 4 档 / 触控目标 / 横向溢出
 *   E. 硬约束：20 区块覆盖、门户直达对话、演示数据标注、离线自足
 *
 * 用法：node _tools/audit.mjs [--json]
 * 退出码：有"违规"级发现时为 1（"需人工判断"级不影响退出码）
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));
const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
const SRC = path.join(DIR, '_src');
const JSON_OUT = process.argv.includes('--json');

const violations = [];
const warns = [];
const notes = [];
const v = (m) => violations.push(m);
const w = (m) => warns.push(m);

/* ============================ 静态检查 ============================ */
const cssPaths = [
  path.join(HERE, 'c2.css'),
  ...fs.readdirSync(path.join(SRC, 'css')).sort().map((f) => path.join(SRC, 'css', f))
];
const cssAll = cssPaths.map((p) => fs.readFileSync(p, 'utf8')).join('\n');
const jsPaths = [
  path.join(SRC, 'app.js'),
  ...fs.readdirSync(path.join(SRC, 'js')).sort().map((f) => path.join(SRC, 'js', f))
];
const jsAll = jsPaths.map((p) => fs.readFileSync(p, 'utf8')).join('\n');

/* 匹配禁用词之前必须先去掉注释：本项目大量注释在**解释为什么不做**数字滚动/淡入，
   不去注释就会把"我们不做 X"的说明当成"我们做了 X"（第一版就是这么误报的）。 */
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/[^\n]*/g, '$1 ');
const cssCode = stripComments(cssAll);
const jsCode = stripComments(jsAll);

/* 页面类型：四个落点是**数据页**的活法（DESIGN-LANGUAGE §3 明说"照对话页那套做不成立"，
   反过来也一样 —— 登录页与 404 页没有"组织权"可言）。所以按类型给不同门槛，
   而不是拿"每页都要三个落点"这一把尺子量全部 21 个页面。 */
const PAGE_KIND = {
  chat: 'dialogue',                    // 对话页：活 = 过程可见
  portal: 'entry', login: 'entry', settings: 'entry', reminders: 'entry',
  spec: 'doc', guide: 'doc', gallery: 'doc',
  tools: 'tool', notfound: 'state'
};
const REQUIRED_HITS = { data: 3, dialogue: 0, doc: 2, entry: 2, tool: 2, state: 2 };

/* A/B 允许的动效：它们回答"这里发生了什么"，不是进场装饰 */
const ALLOWED_KEYFRAMES = {
  // 主体在场（对话页的"活"= 过程可见）：头像三态
  haloBreathe: '主体在场（呼吸）', breathe: '主体在场（状态点呼吸）',
  blink: '主体在场（眨眼）', look: '主体在场（扫视）',
  talk: '主体在场（说话开合）', wave: '主体在场（声波）', orbit: '主体在场（思考绕行）',
  ripple: '主体在场（说话涟漪）',
  // 状态与加载
  skelSweep: '加载态（骨架屏扫光）',
  idxFade: '目录面板遮罩淡入（用户点开才发生）', idxIn: '目录面板入场（用户点开才发生）'
};
const SUSPECT_KEYFRAMES = {
  panelIn: '面板切换入场（用户点标签才发生）—— 允许，但要确认没有在页面加载时就播',
  grow: '图表条生长（clip-path）—— 反例表点名的"图表生长"，必须绑在用户动作上，不能一进页面就播'
};

{
  const names = [...cssAll.matchAll(/@keyframes\s+([a-zA-Z0-9_-]+)/g)].map((m) => m[1]);
  const uniq = [...new Set(names)];
  const unknown = uniq.filter((n) => !ALLOWED_KEYFRAMES[n] && !SUSPECT_KEYFRAMES[n]);
  if (unknown.length) w(`出现了未分类的 @keyframes：${unknown.join(', ')}（要人工确认它不是装饰性动效）`);
  notes.push(`@keyframes 共 ${uniq.length} 个：允许 ${uniq.filter((n) => ALLOWED_KEYFRAMES[n]).length} · 待确认 ${uniq.filter((n) => SUSPECT_KEYFRAMES[n]).length} · 未分类 ${unknown.length}`);
}

{
  // 粒子 / 发光 / 自动轮播 / 数字滚动：直接找实现
  const banned = [
    [/particle|粒子|confetti|sparkle/i, '粒子/彩带'],
    [/marquee|自动轮播|carousel|autoplay|autoSlide/i, '自动轮播'],
    [/setInterval\s*\(/i, 'setInterval（定时轮播/轮询的常见实现）'],
    [/useCountUp|countUp|数字滚动|odometer/i, '数字滚动']
  ];
  for (const [re, label] of banned) {
    const hit = re.test(cssCode) || re.test(jsCode);
    if (hit) w(`疑似${label}：在 CSS/JS（已去注释）里匹配到 ${re}`);
  }
  // 发光边框：box-shadow 带明显的 accent 光晕
  const glow = [...cssAll.matchAll(/box-shadow:[^;}]*?(?:glow|--sh-accent)[^;}]*/gi)];
  notes.push(`含 accent 光晕的 box-shadow：${glow.length} 处（焦点环与 select 高亮属允许项，逐条看）`);
}

{
  /* 已声明的例外：不是"悄悄放过"，而是**能在 spec 页里读到的例外**。
     逐个都写了为什么它是例外、以及出处。 */
  const EXCEPTIONS = {
    '15px': '侧栏品牌字「职」(.nav__mark) —— logo 字形不是界面文字；34×34 的方块里 15px 才撑得住。基线 c2.css:535'
  };
  const sizes = new Set();
  for (const m of cssCode.matchAll(/font-size:\s*([^;}]+)/g)) sizes.add(m[1].trim());
  const OK = /^(var\(--fs-(12|14|16|20|30)\)|inherit|0|1em|1rem)$/;
  const bad = [...sizes].filter((s) => !OK.test(s) && !EXCEPTIONS[s]);
  if (bad.length) w(`字号出现了 5 档之外的值：${bad.join(' · ')}`);
  const used = [...sizes].filter((s) => EXCEPTIONS[s]);
  notes.push(`font-size 出现 ${sizes.size} 种写法，五档之外${used.length ? '只有已声明例外：' + used.map((s) => s + '（' + EXCEPTIONS[s] + '）').join('；') : '无'}：${bad.length === 0 ? '是' : '否'}`);

  const weights = new Set();
  for (const m of cssCode.matchAll(/font-weight:\s*([^;}]+)/g)) weights.add(m[1].trim());
  const OKW = /^(var\(--fw-(regular|medium|semibold|bold)\)|normal|bold|inherit|400|500|600|700)$/;
  const badW = [...weights].filter((s) => !OKW.test(s));
  if (badW.length) w(`字重出现了 4 档之外的值：${badW.join(' · ')}`);
  notes.push(`font-weight 出现 ${weights.size} 种写法，全部用 --fw-* 四档：${badW.length === 0 ? '是' : '否'}`);
}

/* ============================ 运行时检查 ============================ */
const registry = JSON.parse(fs.readFileSync(path.join(SRC, 'views.json'), 'utf8'));
const keys = Object.keys(registry).filter((k) => !k.startsWith('_'));
const FILE_URL = pathToFileURL(path.join(DIR, 'index.html')).href;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const jsErrors = [];
page.on('pageerror', (e) => jsErrors.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') jsErrors.push('console.error: ' + m.text()); });

const matrix = [];
for (const key of keys) {
  const kind = PAGE_KIND[key] || 'data';
  await page.goto(FILE_URL + '#/' + key, { waitUntil: 'load' });
  await page.waitForTimeout(320);
  const m = await page.evaluate((kindArg) => {
    const root = document.querySelector('.main > .main__scroll[data-active="true"]');
    const q = (sel) => root.querySelectorAll(sel).length;
    const txt = (sel) => Array.from(root.querySelectorAll(sel));

    /* 落点判定。溯源一栏把 .sp-ref 也算上：spec 用"这条数值出自 c2.css 第 N 行"的
       引用 chip 做溯源，那是同一件事的另一种形态，不该因为类名不同就判它没做。 */
    const hit = {
      structure: q('.sec, .tbl, .kv, .cmp, .tl, .stats') > 0,
      organize: q('.lens') > 0,
      trace: q('.zoom') > 0 || q('.src') > 0 || q('.sp-ref') > 0,
      status: q('.conf') > 0 || q('.state') > 0 || q('.stale') > 0 || q('.callout') > 0
    };

    /* 对话页不看四个落点，看"过程可见"（DESIGN-LANGUAGE §3）：
       主体在场可切（三态）、交接是默认展开的说明、结论是一块立起来的、后续问题可点入输入区 */
    const dialogue = {
      presence: q('[data-presence]') >= 3,
      handoff: q('.handoff') > 0 && root.querySelector('.handoff').getBoundingClientRect().height > 40,
      conclusion: q('.lead') > 0,
      follow: q('.followbtn') > 0,
      composer: q('.box') > 0
    };

    /* 字号/字重实测：只看可见且有文字的节点 */
    const fsSet = {}, fwSet = {};
    txt('*').forEach((el) => {
      if (!el.textContent || !el.textContent.trim()) return;
      if (el.children.length) return;                 // 只看叶子，避免重复计
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') return;
      fsSet[Math.round(parseFloat(cs.fontSize))] = 1;
      fwSet[cs.fontWeight] = 1;
    });

    /* 触控：只算真正的控件（排除正文行内链接）。
       ⚠ `label[for]` 要不要算触控目标，取决于它**关联的那个控件**：
         · 控件本身 ≥36（例如输入框 280×40）→ 标签只是说明文字，点它是顺手聚焦，不算目标；
         · 控件很小或视觉隐藏（设置页的开关把 input 藏成 1×1，可见的就是那个标签）
           → **标签就是那个控件**，必须算。第一版一刀切地算所有 label，把登录页
           357×21 的字段标题也算成了触控缺陷（假阳性）。 */
    let smallCtl = 0;
    root.querySelectorAll('a[href], button, input, textarea, select, summary, label[for], [tabindex]:not([tabindex="-1"])')
      .forEach((el) => {
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        if (r.width < 2 || r.height < 2) return;
        if (cs.display === 'inline' && el.tagName === 'A') return;
        if (el.tagName === 'LABEL' && el.htmlFor) {
          let ctl = null;
          try { ctl = root.querySelector('#' + CSS.escape(el.htmlFor)); } catch (e) { ctl = null; }
          if (ctl && ctl.getBoundingClientRect().height >= 36) return;   // 标签只是说明文字
        }
        /* 反向情形：小控件被一个够大的 <label> **整块包着**（登录页的协议勾选框：
           20×20 的 checkbox 包在 min-height:44px 的 .lg-agree 里）。真目标是那个标签，
           控件本身只是它的可见形状 —— 不算触控缺陷。 */
        if (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') {
          const wrap = el.closest('label');
          if (wrap && wrap.getBoundingClientRect().height >= 36) return;
        }
        if (r.height < 36) smallCtl++;
      });

    /* 落点②是否真的能改：视角重组的按钮数 */
    const lensBtns = q('.lens [data-lens-set]');
    const lensItems = q('.lens .lens__item');

    /* 状态词表（品质差异是否被看见） */
    const confKinds = new Set();
    root.querySelectorAll('.conf').forEach((el) => {
      el.classList.forEach((c) => { if (c.startsWith('conf--')) confKinds.add(c); });
    });

    /* 后端契约字段是否显形（硬约束："后端有的功能前端也要有，字段以后端为准"）。
       对样张而言可检的形式就是这几个概念在页面上有没有落点：
         source（这条从哪来）/ confidence（有多结实）/ gaps（还缺什么）
         / needs_recompute（过期要重算）/ coverage（了解了几条） */
    const text = root.innerText || '';
    const contract = {
      src: q('.src'),
      verified: q('.conf--verified'),
      reported: q('.conf--reported'),
      inferred: q('.conf--inferred'),
      stale: q('.conf--stale, .stale'),
      conflict: q('.conf--conflict'),
      gap: (text.match(/还缺|缺口|待补充|还没聊到|待核对|没有成绩/g) || []).length,
      recompute: (text.match(/重算|过期|没重算/g) || []).length,
      coverage: (text.match(/已经了解|已知|覆盖率|已核对|\d+\s*\/\s*\d+/g) || []).length
    };

    return {
      hit, fsSet: Object.keys(fsSet).map(Number).sort((a, b) => a - b),
      fwSet: Object.keys(fwSet).sort(),
      smallCtl, lensBtns, lensItems,
      confKinds: [...confKinds],
      contract,
      sections: q('.sec'),
      dialogue,
      hasDemo: !!root.querySelector('.tag--demo'),
      /* 加载后正在跑的动画（未做任何交互） */
      running: document.getAnimations().filter((a) => a.playState === 'running')
        .map((a) => (a.animationName || '') + '@' + ((a.effect && a.effect.target && a.effect.target.className) || '?'))
    };
  }, kind);

  const hits = Object.values(m.hit).filter(Boolean).length;
  const need = REQUIRED_HITS[kind];
  if (kind === 'dialogue') {
    const d = Object.entries(m.dialogue);
    const okD = d.filter(([, x]) => x).length;
    if (okD < d.length) v(`${key}: 对话页"过程可见"缺项 —— ${d.filter(([, x]) => !x).map(([k]) => k).join(', ')}`);
    notes.push(`chat 作为对话页的判定（过程可见）：主体在场三态=${m.dialogue.presence} · 交接默认展开=${m.dialogue.handoff} · 结论块=${m.dialogue.conclusion} · 后续问题可点=${m.dialogue.follow} · 输入区=${m.dialogue.composer}`);
  } else if (hits < need) {
    v(`${key}（${kind}）：落点只命中 ${hits} 个（该类型门槛 ≥${need}）`);
  }
  if (!m.hasDemo) v(`${key}: 页头没有 tag--demo 演示数据标注`);
  if (kind === 'data') {
    /* 数据页的最低要求：每条信息写着从哪来（没有来源标注就是真缺口） */
    if (m.contract.src === 0) w(`${key}: 数据页没有任何 .src 来源标注（DESIGN-LANGUAGE §4.4 溯源）`);
    /* "品质差异要被看见"：不硬性要求逐条都挂 .conf —— 有些页面**同源同时间**，
       逐条标把握度等于编造差异（例如岗位资讯全部来自同一份虚构演示资料）。
       这种情况退回成提示，由报告里逐个交代。 */
    const confTotal = m.contract.verified + m.contract.reported + m.contract.inferred + m.contract.stale + m.contract.conflict;
    if (confTotal < 2) notes.push(`${key}: 逐条把握度只有 ${confTotal} 处 —— 若该页信息同源同时间，这是对的（不要编造差异）；否则应补`);
  }
  if (m.fsSet.some((s) => ![12, 14, 16, 20, 30].includes(s))) w(`${key}: 实测字号出现档位外的值 ${m.fsSet.join('/')}`);
  if (m.fwSet.some((s) => !['400', '500', '600', '700'].includes(s))) w(`${key}: 实测字重出现档位外的值 ${m.fwSet.join('/')}`);
  if (m.smallCtl > 0) w(`${key}: 有 ${m.smallCtl} 个控件高度 <36px`);
  if (m.running.length) {
    const susRun = m.running.map((x) => x.split('@')[0]).filter((n) => SUSPECT_KEYFRAMES[n]);
    if (susRun.length) w(`${key}: 加载后就在跑 ${[...new Set(susRun)].join(', ')}（进场/生长类）`);
  }
  matrix.push({ key, kind, ...m, hits, need });
}

/* 后端契约字段的覆盖（硬约束："后端有的功能前端也要有，字段以后端为准"） */
{
  const keys5 = ['src', 'verified', 'reported', 'inferred', 'stale', 'conflict', 'gap', 'recompute', 'coverage'];
  const totals = {};
  for (const k of keys5) totals[k] = 0;
  for (const r of matrix) for (const k of keys5) totals[k] += (r.contract[k] || 0);
  notes.push('后端契约字段在页面上的落点（全站合计）：' + keys5.map((k) => k + '=' + totals[k]).join(' · '));
  const missing = keys5.filter((k) => totals[k] === 0);
  if (missing.length) w(`有契约字段在全站都没有落点：${missing.join(', ')}（用户硬约束："后端有的功能前端也要有"）`);
  const viewsWithGap = matrix.filter((r) => r.contract.gap > 0).length;
  notes.push(`"缺口"被写出来的界面：${viewsWithGap}/${matrix.length} · "要重算"：${matrix.filter((r) => r.contract.recompute > 0).length}/${matrix.length} · "已了解/覆盖"：${matrix.filter((r) => r.contract.coverage > 0).length}/${matrix.length}`);
}

/* 未交互时正在跑的动画：分类 */
{
  const all = new Set();
  for (const row of matrix) for (const a of row.running) all.add(a.split('@')[0]);
  const sus = [...all].filter((n) => SUSPECT_KEYFRAMES[n]);
  notes.push(`页面加载后（未做任何交互）正在跑的动画：${[...all].join(', ') || '（无）'}`);
  const bad = [...all].filter((n) => n && !ALLOWED_KEYFRAMES[n] && !SUSPECT_KEYFRAMES[n]);
  if (bad.length) w(`加载后跑了未分类动画：${bad.join(', ')}`);
}

/* ============================ 全站对比度实测（--contrast） ============
   批准基线自带的 verify.cjs 用"把文字调透明再截 1×1 像素"的硬办法测对话页。
   这一层要把 21 个界面都盖住，所以用"沿祖先合成有效背景"的办法：
   本项目是平面材质（rgba 面 + 玻璃模糊），合成色对判 WCAG 1.4.3 足够准，
   而且能一次跑完 21 个界面。阈值：正文 4.5:1；大字（≥24px 或 ≥18.66px 且 ≥700）3:1。 */
if (process.argv.includes('--contrast')) {
  const rows = [];
  for (const key of keys) {
    await page.goto(FILE_URL + '#/' + key, { waitUntil: 'load' });
    await page.waitForTimeout(280);
    const bad = await page.evaluate(() => {
      const parse = (s) => {
        const m = String(s).match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const p = m[1].split(/[,\s\/]+/).filter(Boolean).map(Number);
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
      };
      const over = (fg, bg) => ({
        r: fg.r * fg.a + bg.r * (1 - fg.a),
        g: fg.g * fg.a + bg.g * (1 - fg.a),
        b: fg.b * fg.a + bg.b * (1 - fg.a),
        a: fg.a + bg.a * (1 - fg.a)
      });
      const bgOf = (el) => {
        const chain = [];
        for (let n = el; n; n = n.parentElement) chain.push(n);
        chain.reverse();
        let acc = { r: 255, g: 255, b: 255, a: 1 };
        for (const n of chain) {
          const cs = getComputedStyle(n);
          const c = parse(cs.backgroundColor);
          if (c && c.a > 0) {
            acc = over(c, acc);
            continue;
          }
          /* ⚠ 渐变底的 backgroundColor 是 transparent（第一版就漏了这条，
             于是主色按钮上的白字被算成"白底白字" = 7 处假违规）。
             取渐变的第一个色标当底色：本项目的主色按钮就是
             linear-gradient(180deg, --c-primary, --c-primary-hover)。 */
          const bi = cs.backgroundImage;
          if (bi && bi !== 'none' && bi.indexOf('gradient') >= 0) {
            const m = bi.match(/rgba?\([^)]+\)/);
            const g = m && parse(m[0]);
            if (g && g.a > 0) acc = over(g, acc);
          }
        }
        return acc;
      };
      const lum = (c) => {
        const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
      };
      const ratio = (a, b) => {
        const l1 = lum(a), l2 = lum(b);
        return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      };
      const root = document.querySelector('.main > .main__scroll[data-active="true"]');
      const out = [];
      root.querySelectorAll('*').forEach((el) => {
        if (el.children.length) return;                 // 只测叶子文字
        const t = (el.textContent || '').trim();
        if (!t) return;
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        const cs = getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.5) return;
        const fg0 = parse(cs.color);
        if (!fg0) return;
        const bg = bgOf(el);
        const fg = fg0.a < 1 ? over(fg0, bg) : fg0;
        const size = parseFloat(cs.fontSize);
        const weight = parseInt(cs.fontWeight, 10) || 400;
        const large = size >= 24 || (size >= 18.66 && weight >= 700);
        const need = large ? 3 : 4.5;
        const got = ratio(fg, bg);
        if (got < need) {
          out.push({
            need, got: Math.round(got * 100) / 100, size, weight,
            cls: String(el.className).slice(0, 40),
            text: t.replace(/\s+/g, ' ').slice(0, 26)
          });
        }
      });
      return out;
    });
    if (bad.length) rows.push({ key, bad });
  }
  console.log('=== 全站对比度实测（WCAG 1.4.3：正文 ≥4.5:1，大字 ≥3:1）===');
  if (!rows.length) console.log('  21 个界面、所有可见叶子文字全部达标 ✓');
  for (const r of rows) {
    console.log(`\n  ${r.key}：${r.bad.length} 处不达标`);
    r.bad.sort((a, b) => a.got - b.got).slice(0, 8).forEach((b) => {
      console.log(`    ${String(b.got).padStart(5)}:1（需 ${b.need}）  ${b.size}px/${b.weight}  ${b.cls}  「${b.text}」`);
    });
    if (r.bad.length > 8) console.log(`    …还有 ${r.bad.length - 8} 处`);
  }
  const total = rows.reduce((n, r) => n + r.bad.length, 0);
  console.log(`\n合计 ${total} 处不达标，涉及 ${rows.length}/${keys.length} 个界面`);
  if (total) process.exitCode = 1;
  await browser.close();
  process.exit(process.exitCode || 0);
}

/* ============================ 硬约束：门户直达对话 ============================ */
{
  await page.goto(FILE_URL + '#/portal', { waitUntil: 'load' });
  await page.waitForTimeout(250);
  const toChat = await page.evaluate(() =>
    !!document.querySelector('[data-view="portal"] a[href="#/chat"]')
  );
  if (!toChat) v('门户页没有直达对话页的入口（硬约束：从门户进入必须直达对话页）');
  else notes.push('门户页有直达 #/chat 的入口 ✓');
}

/* 反例表：数字滚动 / 自动轮播 —— 运行时看有没有持续变化的文本 */
{
  await page.goto(FILE_URL + '#/home', { waitUntil: 'load' });
  await page.waitForTimeout(250);
  const a = await page.evaluate(() => document.querySelector('[data-view="home"]').innerText.slice(0, 400));
  await page.waitForTimeout(1200);
  const b = await page.evaluate(() => document.querySelector('[data-view="home"]').innerText.slice(0, 400));
  if (a !== b) w('home 页在不做任何操作时文本自己在变（疑似数字滚动/自动轮播）');
  else notes.push('静置 1.2s 文本无变化（没有数字滚动/自动轮播）✓');
}

await browser.close();
if (jsErrors.length) v(`${jsErrors.length} 条页面 JS 异常：${[...new Set(jsErrors)].join(' | ')}`);

/* ============================ 汇总 ============================ */
if (JSON_OUT) {
  console.log(JSON.stringify({ matrix, violations, warns, notes }, null, 2));
} else {
  console.log('=== 落点矩阵（按页面类型定门槛：数据页 ≥3；文档/入口/工具/状态页 ≥2；对话页另判"过程可见"）===');
  console.log('view'.padEnd(14) + '类型'.padEnd(10) + '结构 组织 溯源 状态  命中/需  lens(按钮/条目)  实测字号        实测字重        <36控件');
  for (const r of matrix) {
    console.log(
      r.key.padEnd(14) +
      r.kind.padEnd(10) +
      [r.hit.structure, r.hit.organize, r.hit.trace, r.hit.status].map((x) => (x ? ' ✓  ' : ' ·  ')).join(' ') +
      '  ' + (r.hits + '/' + r.need).padEnd(8) +
      String(r.lensBtns + '/' + r.lensItems).padEnd(14) +
      r.fsSet.join('/').padEnd(15) +
      r.fwSet.join('/').padEnd(15) +
      r.smallCtl
    );
  }
  console.log('\n=== 提示 ===');
  for (const n of notes) console.log('  · ' + n);
  if (warns.length) { console.log('\n=== 需人工判断（不判为违规）==='); for (const x of warns) console.log('  ! ' + x); }
  console.log('\n=== 违规 ===');
  if (violations.length) for (const x of violations) console.log('  ✗ ' + x);
  else console.log('  （无）');
  console.log(`\n视图 ${matrix.length} 个 · 违规 ${violations.length} · 待人工判断 ${warns.length}`);
}
if (violations.length) process.exitCode = 1;
