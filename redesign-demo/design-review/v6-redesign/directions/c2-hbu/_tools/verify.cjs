/* =============================================================================
 * c2-hbu 样张验证脚本（零依赖，只借 Playwright）
 *   1. 截图到 shots/
 *   2. 交互断言（卡组切换 / 依据展开 0→Npx / 头像三态 / 输入聚焦与空输入禁用 /
 *      行动卡状态 / 移动抽屉 / 桌面导航折叠 / 后续问题写入输入区）
 *   3. 主题切换覆盖核对（逐条读计算值，蓝 vs 红 diff）
 *   4. 对比度实测（在浏览器里把前景色合成到"有效背景"上算 WCAG 比值）
 *   5. 1280 / 1024 / 390 的 scrollWidth == clientWidth
 *
 * 用法：node _tools/verify.cjs
 * ========================================================================== */
const path = require('path');
const fs = require('fs');
const zlib = require('zlib');
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));

const DIR = path.resolve(__dirname, '..');
const FILE = 'file:///' + path.join(DIR, 'index.html').replace(/\\/g, '/');
const SHOTS = path.join(DIR, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

const wait = ms => new Promise(r => setTimeout(r, ms));
const problems = [];
const notes = [];
function check(ok, msg) { console.log((ok ? '  [ok] ' : '  [FAIL] ') + msg); if (!ok) problems.push(msg); }

/* ---- 真·实测：把文字调成 transparent，再截 1×1 像素读**渲染出来的底色** -----
   为什么不用"沿祖先合成 computedStyle"：渐变底与 backdrop-filter 在 computedStyle 里
   看不出来（background-image 不是 color），合成结果会偏保守甚至错。直接读像素最硬。 */
function decode1x1(buf) {
  let off = 8, idat = [], w = 0, h = 0;
  while (off < buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('ascii', off + 4, off + 8);
    const data = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IHDR') { w = data.readUInt32BE(0); h = data.readUInt32BE(4); }
    if (type === 'IDAT') idat.push(data);
    off += 12 + len;
    if (type === 'IEND') break;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  /* 第一行第一像素：任何 filter 类型在无左/上邻居时都等于原值 */
  return { r: raw[1], g: raw[2], b: raw[3], w, h };
}
function srgbLum(c) {
  const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
}
function ratioOf(a, b) { const l1 = srgbLum(a), l2 = srgbLum(b), hi = Math.max(l1, l2), lo = Math.min(l1, l2); return (hi + 0.05) / (lo + 0.05); }
function parseRgb(s) {
  const m = String(s).match(/rgba?\(([^)]+)\)/); if (!m) return null;
  const p = m[1].split(/[,\s\/]+/).filter(Boolean).map(Number);
  return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
}

/* 逐个元素：滚动到视口 → 记下计算色 → 把文字调透明 → 截 1×1 → 还原 */
async function pixelContrast(page, probes) {
  const out = [];
  for (const [label, sel] of probes) {
    const info = await page.evaluate((s) => {
      const el = document.querySelector(s);
      if (!el) return null;
      el.scrollIntoView({ block: 'center' });
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return null;
      const cs = getComputedStyle(el);
      const color = cs.color, fs = parseFloat(cs.fontSize), fw = parseInt(cs.fontWeight, 10) || 400;
      const prev = el.style.color;
      el.style.color = 'transparent';
      el.setAttribute('data-probe-prev', prev);
      return {
        color, fs, fw,
        x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
        vw: window.innerWidth, vh: window.innerHeight
      };
    }, sel);
    if (!info) { out.push({ label, sel, ratio: null, why: '元素不可见/不存在' }); continue; }
    let bg = null;
    if (info.x >= 0 && info.y >= 0 && info.x < info.vw && info.y < info.vh) {
      try {
        const png = await page.screenshot({ clip: { x: info.x, y: info.y, width: 1, height: 1 } });
        bg = decode1x1(png);
      } catch (e) { /* 视口外，跳过 */ }
    }
    await page.evaluate((s) => {
      const el = document.querySelector(s);
      if (el) { el.style.color = el.getAttribute('data-probe-prev') || ''; el.removeAttribute('data-probe-prev'); }
    }, sel);
    const fg = parseRgb(info.color);
    if (!bg || !fg) { out.push({ label, sel, ratio: null, why: '取色失败' }); continue; }
    const fgc = fg.a < 1 ? { r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a) } : fg;
    out.push({
      label, sel, ratio: ratioOf(fgc, bg), fs: info.fs, fw: info.fw,
      fg: info.color, bg: `rgb(${bg.r},${bg.g},${bg.b})`
    });
  }
  return out;
}

/* 需要实测的"文字/背景"组合（每条都是页面里真实存在的组合） */
const PROBES = [
  ['对话头标题', '.conv-head__title'],
  ['会话标签', '.conv-head__meta .tag'],
  ['演示数据徽标（注意色）', '.tag--demo'],
  ['主理名字', '.agent__name'],
  ['主理职责', '.agent__role'],
  ['主理状态胶囊', '.agent__state'],
  ['演示提示', '.agent__hint'],
  ['用户消息正文', '.bubble p'],
  ['用户消息时间', '.bubble__meta'],
  ['交接-谁交给谁', '.handoff__who'],
  ['交接-原因', '.handoff__why'],
  ['交接-依据', '.handoff__from'],
  ['顾问名', '.who__name'],
  ['顾问角色', '.who__role'],
  ['结论大字', '.lead__text'],
  ['结论小字', '.lead__sub'],
  ['结论标签', '.lead__label'],
  ['卡组标签', '.mats__label'],
  ['卡组位置', '.mats__pos'],
  ['选中 tab', '.tab[aria-selected="true"]'],
  ['依据正文', '.ev__text'],
  ['依据来源行', '.ev__src'],
  ['依据来源徽标', '.ev__src b'],
  ['卡脚说明', '.panel__foot'],
  ['说明段', '.note p'],
  ['行动卡 kicker', '.action__kicker'],
  ['行动卡标题', '.action__title'],
  ['时长药丸', '.pill--time'],
  ['普通药丸', '.pill'],
  ['主按钮', '.btn--primary'],
  ['次按钮', '.btn--ghost'],
  ['后续问题', '.followbtn'],
  ['后续问题序号', '.followbtn__n'],
  ['输入提示行', '.composer__hint'],
  ['输入键盘提示', '.box__foot'],
  ['发送按钮', '.box__send'],
  ['输入占位文字', '.box__field textarea'],
  ['rail 标题', '.rail__title'],
  ['rail 卡标题', '.railcard__t'],
  ['rail 卡说明', '.railcard__d'],
  ['rail 卡入口', '.railcard__foot'],
  ['rail 计数', '.railcard__n'],
  ['rail 注解', '.railnote'],
  ['演示台标签', '.demo__lb'],
  ['演示台选中片', '.segb[aria-pressed="true"]'],
  ['演示台说明', '.demo__note'],
  ['导航品牌名', '.nav__name'],
  ['导航副标', '.nav__sub'],
  ['导航分组标签', '.nav__label'],
  ['导航选中项', '.nav__item--on'],
  ['导航徽标', '.nav__badge'],
  ['导航普通项', '.nav__item'],
  ['搜索占位', '.search input'],
  ['账号名', '.topbar__me>span:not(.topbar__me-av)'],
  ['账号/导航头像字母', '.topbar__me-av'],
  ['图表题注', '.chart__unit'],
  ['图表行名', '.row__name'],
  ['图表数值', '.row__value'],
  ['图表刻度', '.chart__ticks span']
];

(async () => {
  const browser = await chromium.launch();
  const allConsole = [];

  async function newPage(w, h, opts = {}) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h },
      deviceScaleFactor: 2,
      reducedMotion: opts.reducedMotion ? 'reduce' : 'no-preference',
      isMobile: w < 500, hasTouch: w < 500
    });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error') allConsole.push(`${w}px: ${m.text()}`); });
    page.on('pageerror', e => allConsole.push(`${w}px pageerror: ${e.message}`));
    await page.goto(FILE, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    await page.addStyleTag({ content: 'input::placeholder,textarea::placeholder{color:transparent !important}' });
    await wait(700);
    return { ctx, page };
  }
  async function setDemo(page, accent, theme, style) {
    await page.evaluate(([a, t, s]) => {
      document.querySelector(`.segb[data-set="accent"][data-val="${a}"]`).click();
      document.querySelector(`.segb[data-set="theme"][data-val="${t}"]`).click();
      document.querySelector(`.segb[data-set="style"][data-val="${s}"]`).click();
    }, [accent, theme, style]);
    await wait(450);
  }

  /* =====================================================================
   * A. 截图
   * ================================================================== */
  console.log('\n=== A. 截图 ===');
  {
    const { ctx, page } = await newPage(1280, 900);
    await setDemo(page, 'blue', 'light', 'normal');
    await page.screenshot({ path: path.join(SHOTS, '1280-blue.png') });
    console.log('  [shot] 1280-blue.png');

    await setDemo(page, 'red', 'light', 'normal');
    await page.screenshot({ path: path.join(SHOTS, '1280-red.png') });
    console.log('  [shot] 1280-red.png');

    await setDemo(page, 'blue', 'dark', 'normal');
    await page.screenshot({ path: path.join(SHOTS, '1280-dark.png') });
    console.log('  [shot] 1280-dark.png');

    /* 追加：滚到行动卡 + 数据卡，展示按钮 / 图表 / 进度 / 徽标 */
    await setDemo(page, 'blue', 'light', 'normal');
    await page.click('#tab-data');
    await wait(500);
    await page.evaluate(() => { document.getElementById('mainScroll').scrollTop = 620; });
    await wait(400);
    await page.screenshot({ path: path.join(SHOTS, '1280-blue-lower.png') });
    console.log('  [shot] 1280-blue-lower.png');

    await setDemo(page, 'red', 'light', 'normal');
    await page.evaluate(() => { document.getElementById('mainScroll').scrollTop = 620; });
    await wait(400);
    await page.screenshot({ path: path.join(SHOTS, '1280-red-lower.png') });
    console.log('  [shot] 1280-red-lower.png');

    /* 数据卡特写 */
    await setDemo(page, 'blue', 'light', 'normal');
    await page.evaluate(() => { document.getElementById('mainScroll').scrollTop = 0; });
    await page.click('#tab-data');
    await wait(600);
    await page.locator('.card').screenshot({ path: path.join(SHOTS, 'data-card.png') });
    console.log('  [shot] data-card.png');

    /* 依据展开特写 */
    await page.click('#tab-ev');
    await wait(300);
    await page.click('#evToggle');
    await wait(700);
    await page.locator('.card').screenshot({ path: path.join(SHOTS, 'evidence-expanded.png') });
    console.log('  [shot] evidence-expanded.png');
    await page.click('#evToggle');
    await wait(600);

    /* 头像三态。本轮需求方要求"两个尺寸都要可读"，所以两档各拍一遍：
       · 96px = 会话头部大头像（.avatar--lg / .avatar 的默认档）
       · 40px = 消息里的小头像（.avatar--sm 的默认档）—— 卡通头像最容易翻车的一档 */
    const shootAvatar = async (sel, size, tag) => {
      await page.evaluate(([s, v]) => {
        document.querySelectorAll(s).forEach(e => e.style.setProperty('--av-size', v));
      }, [sel, size]);
      for (const st of ['idle', 'thinking', 'speaking']) {
        await page.click(`[data-presence="${st}"]`);
        await wait(900);
        /* 眨眼是 6.4s 一次、只占 0.35s 的窄窗。直接截有一半概率截到"半闭眼"，
           那不是"待命/思考长什么样"，是动画的一帧。这里把**眨眼**这条动画停掉
           （只停眨眼，呼吸光晕、六点轨道照旧，它们本来就是状态的语义），
           保证拍到的是"静态表情"本身而不是运气。 */
        await page.addStyleTag({ content: '.avatar__eye{animation:none !important;transform:none !important}' });
        await wait(220);
        const name = tag === 'lg' ? `avatar-${st}.png` : `avatar-40px-${st}.png`;
        await page.locator(sel).first().screenshot({ path: path.join(SHOTS, name) });
        console.log(`  [shot] ${name}  (${size}，已停掉眨眼，拍到的是静态表情)`);
        await page.evaluate(() => {
          document.querySelectorAll('style').forEach(s => { if (/avatar__eye\{animation:none/.test(s.textContent || '')) s.remove(); });
        });
      }
      await page.evaluate((s) => {
        document.querySelectorAll(s).forEach(e => e.style.removeProperty('--av-size'));
      }, sel);
    };
    await shootAvatar('.agent .avatar', '96px', 'lg');
    await shootAvatar('.turn-host .avatar', '40px', 'sm');

    /* 用户气泡：改前（渐变）↔ 改后（纯色）对照。
       "改前"是把 c-companion 那条 linear-gradient(180deg,--c-primary-weak,--c-surface)
       临时贴回去 —— 这样 before/after 的**唯一变量**就是填充方式，圆角、内边距、
       字号、边框、文案全都一样，对照里看到的差别只来自渐变本身。 */
    const BUBBLE_SHOT = async (tag) => {
      await page.locator('.bubble').screenshot({ path: path.join(SHOTS, `bubble-${tag}.png`) });
      console.log(`  [shot] bubble-${tag}.png`);
    };
    const bubbleOld = `linear-gradient(180deg,var(--c-primary-weak),var(--c-surface))`;
    await setDemo(page, 'blue', 'light', 'normal');
    await page.evaluate((bg) => { document.querySelector('.bubble').style.background = bg; }, bubbleOld);
    await wait(300);
    await BUBBLE_SHOT('before-blue-light');
    await page.evaluate(() => { document.querySelector('.bubble').style.background = ''; });
    await wait(300);
    await BUBBLE_SHOT('after-blue-light');
    await setDemo(page, 'red', 'light', 'normal');
    await page.evaluate((bg) => { document.querySelector('.bubble').style.background = bg; }, bubbleOld);
    await wait(300);
    await BUBBLE_SHOT('before-red-light');
    await page.evaluate(() => { document.querySelector('.bubble').style.background = ''; });
    await wait(300);
    await BUBBLE_SHOT('after-red-light');
    await setDemo(page, 'blue', 'dark', 'normal');
    await page.evaluate((bg) => { document.querySelector('.bubble').style.background = bg; }, bubbleOld);
    await wait(300);
    await BUBBLE_SHOT('before-blue-dark');
    await page.evaluate(() => { document.querySelector('.bubble').style.background = ''; });
    await wait(300);
    await BUBBLE_SHOT('after-blue-dark');
    await setDemo(page, 'red', 'dark', 'normal');
    await page.evaluate((bg) => { document.querySelector('.bubble').style.background = bg; }, bubbleOld);
    await wait(300);
    await BUBBLE_SHOT('before-red-dark');
    await page.evaluate(() => { document.querySelector('.bubble').style.background = ''; });
    await wait(300);
    await BUBBLE_SHOT('after-red-dark');

    /* 紧凑密度 + 深色红（额外存档，便于逐项核对密度与深色红） */
    await setDemo(page, 'red', 'dark', 'dense');
    await page.screenshot({ path: path.join(SHOTS, '1280-dark-red-dense.png') });
    console.log('  [shot] 1280-dark-red-dense.png');
    await ctx.close();
  }

  {
    const { ctx, page } = await newPage(390, 844);
    await setDemo(page, 'blue', 'light', 'normal');
    await page.screenshot({ path: path.join(SHOTS, '390-blue.png') });
    console.log('  [shot] 390-blue.png');
    await setDemo(page, 'red', 'light', 'normal');
    await page.screenshot({ path: path.join(SHOTS, '390-red.png') });
    console.log('  [shot] 390-red.png');

    /* 移动端：抽屉打开态（证明导航在 390 上是白灰抽屉，不是深蓝） */
    await page.click('#burger');
    await wait(600);
    await page.screenshot({ path: path.join(SHOTS, '390-drawer.png') });
    console.log('  [shot] 390-drawer.png');

    /* 移动端：数据卡（窄屏刻度仍对齐，数值回到条尾） */
    await page.mouse.click(352, 420);   /* 点遮罩右侧（抽屉 84vw 盖住了中心点）*/
    await wait(500);
    await page.click('#tab-data');
    await wait(500);
    await page.locator('.card').scrollIntoViewIfNeeded();
    await wait(300);
    await page.locator('.card').screenshot({ path: path.join(SHOTS, '390-data-card.png') });
    console.log('  [shot] 390-data-card.png');
    await ctx.close();
  }

  /* =====================================================================
   * B. 交互断言（1280）
   * ================================================================== */
  console.log('\n=== B. 交互断言 ===');
  {
    const { ctx, page } = await newPage(1280, 900);

    /* B1 卡组切换 */
    const before = await page.getAttribute('#panel-ev', 'data-active');
    await page.click('#tab-data');
    await wait(500);
    const st = await page.evaluate(() => ({
      ev: document.getElementById('panel-ev').getAttribute('data-active'),
      data: document.getElementById('panel-data').getAttribute('data-active'),
      dataVisible: document.getElementById('panel-data').getBoundingClientRect().height > 0,
      pos: document.getElementById('posNow').textContent,
      sel: document.getElementById('tab-data').getAttribute('aria-selected'),
      tabindex: document.getElementById('tab-ev').tabIndex
    }));
    check(before === 'true' && st.ev === null && st.data === 'true' && st.dataVisible && st.pos === '2' && st.sel === 'true' && st.tabindex === -1,
      `B1 卡组切换：默认依据卡 → 点"数据对比"后面板真的换了（pos=${st.pos}，可见=${st.dataVisible}，旧 tab tabindex=${st.tabindex}）`);

    /* B2 方向键 */
    await page.focus('#tab-ev');
    await page.keyboard.press('ArrowRight');
    await wait(400);
    const kb = await page.evaluate(() => ({
      sel: document.getElementById('tab-data').getAttribute('aria-selected'),
      focused: document.activeElement && document.activeElement.id
    }));
    check(kb.sel === 'true' && kb.focused === 'tab-data', `B2 方向键切卡：ArrowRight 从"支持依据"到"数据对比"（焦点=${kb.focused}）`);
    await page.keyboard.press('End');
    await wait(300);
    check(await page.getAttribute('#tab-method', 'aria-selected') === 'true', 'B2b 方向键 Home/End：End 跳到"方法依据"');

    /* B3 依据展开 0 → N px */
    await page.click('#tab-ev');
    await wait(500);
    const h0 = await page.evaluate(() => document.getElementById('evMore').getBoundingClientRect().height);
    await page.click('#evToggle');
    await wait(800);
    const h1 = await page.evaluate(() => ({
      h: document.getElementById('evMore').getBoundingClientRect().height,
      open: document.getElementById('evMore').getAttribute('data-open'),
      aria: document.getElementById('evToggle').getAttribute('aria-expanded'),
      label: document.querySelector('#evToggle [data-label]').textContent,
      items: document.querySelectorAll('#evMore .ev__item').length
    }));
    check(h0 === 0 && h1.h > 40 && h1.open === 'true' && h1.aria === 'true' && h1.items === 2,
      `B3 依据展开：${h0}px → ${Math.round(h1.h)}px（真展开，不是换块；内置 ${h1.items} 条；按钮文案="${h1.label}"）`);
    await page.click('#evToggle');
    await wait(700);
    const h2 = await page.evaluate(() => document.getElementById('evMore').getBoundingClientRect().height);
    check(h2 === 0, `B3b 依据收起：回到 ${h2}px`);

    /* B4 头像三态 */
    const states = [];
    for (const s of ['idle', 'thinking', 'speaking']) {
      await page.click(`[data-presence="${s}"]`);
      await wait(350);
      states.push(await page.evaluate(() => ({
        attr: document.documentElement.getAttribute('data-state'),
        stA: getComputedStyle(document.documentElement).getPropertyValue('--st-a').trim(),
        text: document.getElementById('stateText').textContent,
        pressed: document.querySelector('[data-presence][aria-pressed="true"]').getAttribute('data-presence')
      })));
    }
    const uniqA = new Set(states.map(s => s.stA));
    check(states.every(s => s.attr === s.pressed) && uniqA.size === 3 && states[1].text === '正在想',
      `B4 头像三态：data-state 与按钮同步，三态色温各不相同（${[...uniqA].join(' / ')}），状态文字="${states[1].text}"`);

    /* B5 输入区：聚焦态 + 空输入禁用 */
    const b5a = await page.evaluate(() => ({
      focus: document.getElementById('box').getAttribute('data-focused'),
      dis: document.getElementById('send').getAttribute('aria-disabled')
    }));
    await page.click('#msg');
    await wait(300);
    const b5b = await page.evaluate(() => document.getElementById('box').getAttribute('data-focused'));
    await page.fill('#msg', '那如果我想先做材料检测的实习，顺序要怎么调？');
    await wait(300);
    const b5c = await page.getAttribute('#send', 'aria-disabled');
    await page.fill('#msg', '');
    await wait(300);
    const b5d = await page.getAttribute('#send', 'aria-disabled');
    check(b5a.focus === 'false' && b5a.dis === 'true' && b5b === 'true' && b5c === 'false' && b5d === 'true',
      `B5 输入区：未聚焦=${b5a.focus}/空输入禁用=${b5a.dis} → 聚焦=${b5b} → 有字可用=${b5c} → 清空又禁用=${b5d}`);

    /* B6 行动卡状态 */
    const b6a = await page.evaluate(() => ({
      done: document.getElementById('addTask').getAttribute('data-done'),
      label: document.querySelector('#addTask [data-label]').textContent
    }));
    await page.click('#addTask');
    await wait(400);
    const b6b = await page.evaluate(() => ({
      done: document.getElementById('addTask').getAttribute('data-done'),
      label: document.querySelector('#addTask [data-label]').textContent,
      bg: getComputedStyle(document.getElementById('addTask')).backgroundImage
    }));
    await page.click('#addTask');
    await wait(400);
    const b6c = await page.getAttribute('#addTask', 'data-done');
    check(b6a.done === 'false' && b6b.done === 'true' && /已加入/.test(b6b.label) && b6c === 'false',
      `B6 行动卡：${b6a.label} → ${b6b.label} → 再点回 ${b6c}`);

    /* B7 后续问题写入输入区 + Enter 发送 / Shift+Enter 换行 */
    await page.click('.followbtn');
    await wait(300);
    const typed = await page.inputValue('#msg');
    check(typed.length > 6, `B7 后续问题点击写入输入区：「${typed.slice(0, 18)}…」`);
    await page.focus('#msg');
    await page.keyboard.press('Shift+Enter');
    await wait(200);
    const afterShift = await page.inputValue('#msg');
    check(afterShift.includes('\n'), 'B7b Shift+Enter 换行（不发送）');
    await page.keyboard.press('Enter');
    await wait(300);
    const afterEnter = await page.inputValue('#msg');
    check(afterEnter === '' && await page.getAttribute('#send', 'aria-disabled') === 'true',
      'B7c Enter 发送后清空输入区，发送键回到禁用');

    /* B8 桌面导航折叠 */
    const g0 = await page.evaluate(() => getComputedStyle(document.getElementById('app')).gridTemplateColumns);
    await page.click('#navToggle');
    await wait(500);
    const g1 = await page.evaluate(() => ({
      cols: getComputedStyle(document.getElementById('app')).gridTemplateColumns,
      nav: document.getElementById('app').getAttribute('data-nav'),
      aria: document.getElementById('navToggle').getAttribute('aria-expanded')
    }));
    check(g0 !== g1.cols && g1.nav === 'mini' && g1.aria === 'false', `B8 导航折叠：${g0} → ${g1.cols}（aria-expanded=${g1.aria}）`);
    await page.click('#navToggle');
    await wait(400);

    /* B9 无横向溢出（1280 / 1024） */
    for (const w of [1280, 1400, 1024]) {
      await page.setViewportSize({ width: w, height: 900 });
      await wait(500);
      const m = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
      check(m.s === m.c, `B9 ${w}px：scrollWidth(${m.s}) == clientWidth(${m.c})`);
    }

    /* B10 控制台干净 */
    check(allConsole.length === 0, `B10 控制台无报错${allConsole.length ? '：' + JSON.stringify(allConsole) : ''}`);
    await ctx.close();
  }

  /* ---- 390：移动抽屉 + 无横向溢出 ---------------------------------------- */
  {
    const { ctx, page } = await newPage(390, 844);
    const m0 = await page.evaluate(() => ({
      s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth,
      bodyS: document.body.scrollWidth,
      drawer: document.getElementById('app').getAttribute('data-drawer'),
      navX: document.getElementById('sidenav').getBoundingClientRect().left
    }));
    check(m0.s === m0.c && m0.bodyS <= m0.c, `B11 390px：scrollWidth(${m0.s}) == clientWidth(${m0.c})，body(${m0.bodyS})`);
    await page.click('#burger');
    await wait(600);
    const d1 = await page.evaluate(() => ({
      drawer: document.getElementById('app').getAttribute('data-drawer'),
      aria: document.getElementById('burger').getAttribute('aria-expanded'),
      navX: Math.round(document.getElementById('sidenav').getBoundingClientRect().left),
      navBg: getComputedStyle(document.getElementById('sidenav')).backgroundImage,
      scrim: getComputedStyle(document.getElementById('scrim')).opacity
    }));
    check(d1.drawer === 'open' && d1.aria === 'true' && d1.navX === 0 && parseFloat(d1.scrim) > 0.9,
      `B12 移动抽屉：closed(${m0.navX}px) → open(${d1.navX}px)，遮罩 opacity=${d1.scrim}`);
    /* 抽屉里点导航项后关闭（Esc） */
    await page.keyboard.press('Escape');
    await wait(500);
    check(await page.getAttribute('#app', 'data-drawer') === 'closed', 'B12b Esc 关闭抽屉');
    const m1 = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
    check(m1.s === m1.c, `B11b 抽屉开合后仍无横向溢出（${m1.s} == ${m1.c}）`);
    check(allConsole.length === 0, 'B10b 390px 控制台无报错');
    await ctx.close();
  }

  /* =====================================================================
   * B13 / B14 · 本轮两条意见的"结构级"断言
   *   B13 用户气泡：四组组合下都必须是纯色（backgroundImage === 'none'）
   *   B14 卡通头像：非正圆、无腮红/表情符号、动效幅度不超线
   * ================================================================== */
  console.log('\n=== B13/B14 本轮两条意见的断言 ===');
  const bubbleRows = [];
  {
    const { ctx, page } = await newPage(1280, 900);

    /* B13 气泡纯色：四组组合逐组读 background-image */
    for (const [accent, theme] of [['blue', 'light'], ['red', 'light'], ['blue', 'dark'], ['red', 'dark']]) {
      await setDemo(page, accent, theme, 'normal');
      await wait(320);
      bubbleRows.push(await page.evaluate(([a, t]) => {
        const el = document.querySelector('.bubble');
        const cs = getComputedStyle(el);
        return { k: `${a}/${t}`, img: cs.backgroundImage, bg: cs.backgroundColor, line: cs.borderTopColor };
      }, [accent, theme]));
    }
    check(bubbleRows.every(r => r.img === 'none'),
      'B13 用户气泡：蓝浅 / 红浅 / 蓝深 / 红深 四组 background-image 全为 none（纯色）—— ' +
      bubbleRows.map(r => `${r.k}=${r.bg}`).join(' | '));
    const uniqBg = new Set(bubbleRows.map(r => r.bg));
    check(uniqBg.size >= 2, `B13b 气泡底随主题/主色真的分开（${[...uniqBg].join(' / ')}）`);

    /* B14 卡通头像的形体红线：非正圆 + 没有腮红/星星/心形/音符 + 幅度 */
    await setDemo(page, 'blue', 'light', 'normal');
    await page.click('[data-presence="thinking"]');
    await wait(400);
    const av = await page.evaluate(() => {
      const svg = document.querySelector('.agent .avatar svg');
      const body = svg.querySelector('rect');
      const rx = parseFloat(body.getAttribute('rx')), w = parseFloat(body.getAttribute('width'));
      const html = svg.outerHTML;
      /* 旧版"玻璃"的三件套：radialGradient / 镜面高光椭圆 / 边缘受光白描边 */
      const glass = {
        radial: /<radialGradient/i.test(html),
        specular: /rx="2[01]" ry="1[01]"/.test(html) || /opacity="\.34"/.test(html) || /opacity="\.40"/.test(html),
        rim: /--face-rim/.test(html)
      };
      const icons = /腮红|星星|心形|音符|⭐|★|❤|♪/.test(html);
      const halo = getComputedStyle(document.querySelector('.avatar__halo')).animationName;
      const face = getComputedStyle(document.querySelector('.avatar__face')).transform;
      return { rx, w, ratio: rx / w, glass, icons, halo, face, ellipses: svg.querySelectorAll('ellipse').length };
    });
    check(av.ratio < 0.5 && av.rx > 0,
      `B14 头像仍是非正圆：圆角方块 rx=${av.rx}/${av.w} = ${av.ratio.toFixed(2)}（< 0.5 = 不是正圆）`);
    check(!av.glass.radial && !av.glass.rim,
      `B14b 去了玻璃材质：radialGradient=${av.glass.radial}、边缘受光描边=${av.glass.rim}`);
    check(!av.icons && av.ellipses === 4,
      `B14c 没有腮红/星星/心形/音符，椭圆件只剩 4 个眼白（旧版 5 个 = 2 眼白 + 2 腮红 + 1 镜面高光）`);
    check(av.halo === 'haloBreathe',
      `B14d 动效沿用原来的克制幅度：光晕仍是 ${av.halo}（1.0→1.12），没有换成更跳的曲线`);
    check(/matrix/.test(av.face),
      `B14e 思考态只做"脸收 .96 + 上移 1px"：transform=${av.face}`);
    await ctx.close();
  }

  /* =====================================================================
   * C. 主题切换覆盖核对（蓝 vs 红，浅色；再抽查深色）
   * ================================================================== */
  console.log('\n=== C. 主题切换覆盖核对 ===');
  const COVER = [
    ['按钮 · 主按钮底', '.btn--primary', 'backgroundImage'],
    ['按钮 · 发送键底', '.box__send', 'backgroundImage'],
    ['按钮 · 品牌方块', '.nav__mark', 'backgroundImage'],
    ['选中态 · 导航当前项竖线', '.nav__item--on', '::before:backgroundColor'],
    ['选中态 · 当前 tab 圆点', '.tab[aria-selected="true"]', '::after:backgroundColor'],
    ['选中态 · 主理状态按钮边', '.statebtn[aria-pressed="true"]', 'borderTopColor'],
    ['选中态 · 学生气泡边（主色边）', '.bubble', 'borderTopColor'],
    ['选中态 · 输入区聚焦边框（置位后）', '.box', 'borderTopColor'],
    ['焦点环 · --c-focus', ':root', 'focus'],
    ['图表 · 领先条渐变', '.row--top .row__bar', 'backgroundImage'],
    ['图表 · 普通条渐变', '.row:not(.row--top) .row__bar', 'backgroundImage'],
    ['图表 · 领先数值色', '.row--top .row__value', 'color'],
    ['图表 · 徽标底', '.row__badge', 'backgroundColor'],
    ['图表 · 徽标字', '.row__badge', 'color'],
    ['进度 · 画像进度条', '.meter i.on', 'backgroundImage'],
    ['徽标 · 导航计数徽标底', '.nav__badge', 'backgroundColor'],
    ['徽标 · 导航计数徽标字', '.nav__badge', 'color'],
    ['徽标 · 演示台选中片字', '.segb[aria-pressed="true"]', 'color'],
    ['徽标 · 原型小标签字', '.demo__tag', 'color'],
    ['强调字 · 结论标签', '.lead__label', 'color'],
    ['强调字 · rail 入口', '.railcard__foot', 'color'],
    ['强调字 · 时长药丸', '.pill--time', 'color'],
    ['头像 · 渐变起点', '#heroAvatar stop[data-grad-a]', 'stopColor'],
    ['头像 · 待命/思考/说话雾', '.agent__state', 'backgroundColor'],
    ['身份 · 品牌条（应不变）', '.brandstripe', 'backgroundImage'],
    ['中性 · 正文色（应不变）', '.note p', 'color'],
    ['中性 · 图表刻度字（应不变）', '.chart__ticks span', 'color']
  ];

  async function readCover(page) {
    return page.evaluate((rows) => {
      const root = document.documentElement;
      const out = {};
      for (const [label, sel, prop] of rows) {
        if (prop === 'focus') { out[label] = getComputedStyle(root).getPropertyValue('--c-focus').trim(); continue; }
        let el = document.querySelector(sel);
        if (!el) { out[label] = '(缺)'; continue; }
        if (prop.startsWith('::before:')) { out[label] = getComputedStyle(el, '::before')[prop.slice(9)]; continue; }
        if (prop.startsWith('::after:')) { out[label] = getComputedStyle(el, '::after')[prop.slice(8)]; continue; }
        out[label] = getComputedStyle(el)[prop];
      }
      return out;
    }, COVER);
  }

  {
    const { ctx, page } = await newPage(1280, 900);
    await page.click('#tab-data');
    await wait(400);
    const readWithState = async (accent, theme) => {
      await setDemo(page, accent, theme, 'normal');
      await page.click('#tab-data');
      await page.click('#msg');           /* 让输入区处于聚焦态，才读得到聚焦边框 */
      await wait(300);
      return readCover(page);
    };
    const blue = await readWithState('blue', 'light');
    const red = await readWithState('red', 'light');
    const blueDark = await readWithState('blue', 'dark');
    const redDark = await readWithState('red', 'dark');

    let changed = 0;
    const shouldNotChange = new Set(['身份 · 品牌条（应不变）', '中性 · 正文色（应不变）', '中性 · 图表刻度字（应不变）']);
    console.log('  浅色：蓝 → 红');
    for (const [label] of COVER) {
      const a = blue[label], b = red[label];
      const diff = a !== b;
      if (shouldNotChange.has(label)) {
        check(!diff, `C ${label}：两套 accent 下保持同一支（${a}）`);
      } else {
        if (diff) changed++;
        check(diff, `C ${label}：${a} → ${b}`);
      }
    }
    console.log(`  → 浅色下 ${changed}/${COVER.length - shouldNotChange.size} 项随 accent 变化`);
    const darkChanged = COVER.filter(([l]) => !shouldNotChange.has(l) && blueDark[l] !== redDark[l]).length;
    check(darkChanged === COVER.length - shouldNotChange.size, `C 深色下同样覆盖：${darkChanged}/${COVER.length - shouldNotChange.size} 项随 accent 变化`);

    /* hover 态也是主色出现的地方（后续问题的序号 / 边框 / 箭头） */
    const hoverOf = async (accent) => {
      await setDemo(page, accent, 'light', 'normal');
      await page.hover('.followbtn');
      await wait(350);
      return page.evaluate(() => {
        const b = document.querySelector('.followbtn');
        return {
          n: getComputedStyle(b.querySelector('.followbtn__n')).color,
          border: getComputedStyle(b).borderTopColor,
          arrow: getComputedStyle(b.querySelector('.followbtn__arrow')).color,
          bg: getComputedStyle(b.querySelector('.followbtn__n')).backgroundColor
        };
      });
    };
    const hb = await hoverOf('blue'), hr = await hoverOf('red');
    check(JSON.stringify(hb) !== JSON.stringify(hr),
      `C hover 态（后续问题）：蓝 ${JSON.stringify(hb)} → 红 ${JSON.stringify(hr)}`);

    /* 密度：文字间距真的变了（不是只改一个值） */
    await setDemo(page, 'blue', 'light', 'normal');
    const dens0 = await page.evaluate(() => {
      const a = document.querySelector('.action'), b = document.querySelector('.column');
      return { pad: getComputedStyle(a).padding, gap: getComputedStyle(b).rowGap, lh: getComputedStyle(document.querySelector('.note p')).lineHeight, r: getComputedStyle(a).borderRadius };
    });
    await setDemo(page, 'blue', 'light', 'dense');
    const dens1 = await page.evaluate(() => {
      const a = document.querySelector('.action'), b = document.querySelector('.column');
      return { pad: getComputedStyle(a).padding, gap: getComputedStyle(b).rowGap, lh: getComputedStyle(document.querySelector('.note p')).lineHeight, r: getComputedStyle(a).borderRadius };
    });
    check(JSON.stringify(dens0) !== JSON.stringify(dens1),
      `C 密度：常规 ${JSON.stringify(dens0)} → 紧凑 ${JSON.stringify(dens1)}`);

    /* 跟随系统真的跟随 */
    await page.emulateMedia({ colorScheme: 'dark' });
    await setDemo(page, 'blue', 'auto', 'normal');
    const autoDark = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    await page.emulateMedia({ colorScheme: 'light' });
    await wait(200);
    const autoLight = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    check(autoDark === 'dark' && autoLight === 'light', `C 跟随系统：系统深色→data-theme=${autoDark}；系统浅色→${autoLight}`);
    await ctx.close();
  }

  /* =====================================================================
   * D. 对比度实测（四套组合：蓝浅 / 红浅 / 蓝深 / 红深）
   * ================================================================== */
  console.log('\n=== D. 对比度实测（把文字调透明后截 1×1 像素读渲染底色；门禁 4.5:1）===');
  {
    const { ctx, page } = await newPage(1280, 900);
    /* 量对比度时先冻住所有过渡与动画：否则把 color 调成 transparent 会走完 190ms 过渡，
       截到的是"半透明文字"，量出来的是假的低对比。 */
    await page.addStyleTag({ content: '*,*::before,*::after{transition:none !important;animation:none !important}' });
    const report = {};
    const CHART_PROBES = [['图表题注', '.chart__unit'], ['图表行名', '.row__name'], ['图表数值（普通行）', '.row:not(.row--top) .row__cell .row__value'],
      ['图表数值（领先行）', '.row--top .row__cell .row__value'], ['图表刻度', '.chart__ticks span'], ['图表徽标', '.row__badge']];
    for (const [accent, theme] of [['blue', 'light'], ['red', 'light'], ['blue', 'dark'], ['red', 'dark']]) {
      await setDemo(page, accent, theme, 'normal');
      /* 发送键在空输入时是禁用态（opacity .42）。禁用控件不受 WCAG 对比度约束，
         但门禁要看的是"可用时的样子"，所以这里先让它可用再量。 */
      await page.fill('#msg', '测', { force: true }).catch(() => {});
      await page.click('#tab-ev');
      await wait(350);
      const pass1 = await pixelContrast(page, PROBES);
      await page.click('#tab-data');
      await wait(350);
      const pass2 = await pixelContrast(page, CHART_PROBES);
      await page.fill('#msg', '').catch(() => {});

      const rows = pass1.concat(pass2);
      report[`${accent}-${theme}`] = rows;
      const ok = rows.filter(r => r.ratio != null);
      const min = ok.reduce((m, r) => Math.min(m, r.ratio), 99);
      const low = ok.filter(r => r.ratio < 4.5);
      console.log(`\n  ── ${accent} / ${theme} ── 共实测 ${ok.length} 组，最低 ${min.toFixed(2)}:1`);
      for (const r of ok.slice().sort((a, b) => a.ratio - b.ratio).slice(0, 8)) {
        console.log(`     ${r.ratio.toFixed(2)}:1  ${String(r.label).padEnd(16, ' ')} ${r.fs}px/${r.fw}  fg=${r.fg} bg=${r.bg}`);
      }
      const bad = low.filter(r => !(r.fs >= 24 || (r.fs >= 18.66 && r.fw >= 700)));
      check(bad.length === 0, `D ${accent}/${theme}：全部正文档 ≥4.5:1（实测最低 ${min.toFixed(2)}:1）${bad.length ? ' —— 不达标：' + JSON.stringify(bad) : ''}`);
      if (low.length) notes.push(`${accent}/${theme} 低于 4.5 但属大字放宽：` + low.map(r => `${r.label} ${r.ratio.toFixed(2)}:1(${r.fs}px/${r.fw})`).join('、'));
    }
    fs.writeFileSync(path.join(DIR, '_tools', 'contrast-report.json'), JSON.stringify(report, null, 1), 'utf8');

    /* ---- 用户气泡纯色底的对比度专表（交付说明里的那张表就是这段输出）--------
       量法同 PROBES：把文字 color 调成 transparent、冻住过渡、截 1×1 像素读
       **渲染出来的**底色，再和计算出的前景色算 WCAG 比值。 */
    const ME_BUBBLE = [['用户消息正文', '.bubble p'], ['用户消息时间', '.bubble__meta']];
    console.log('\n  ── 用户气泡（纯色底）对比度实测表 ──');
    console.log('     组合            元素          比值      字号/字重   fg → bg');
    const table = {};
    let allOk = true, worst = 99, worstAt = '';
    for (const key of ['blue-light', 'red-light', 'blue-dark', 'red-dark']) {
      table[key] = [];
      for (const [label, sel] of ME_BUBBLE) {
        const r = (report[key] || []).find(x => x.label === label);
        if (!r || r.ratio == null) { console.log(`     ${key.padEnd(14)} ${label.padEnd(12)} 取色失败`); allOk = false; continue; }
        table[key].push({ label, ratio: r.ratio, fg: r.fg, bg: r.bg, fs: r.fs, fw: r.fw });
        if (r.ratio < worst) { worst = r.ratio; worstAt = `${key} / ${label}`; }
        if (r.ratio < 4.5) allOk = false;
        console.log(`     ${key.padEnd(14)} ${label.padEnd(12)} ${r.ratio.toFixed(2)}:1   ${r.fs}px/${r.fw}   ${r.fg} → ${r.bg}`);
      }
    }
    check(allOk, `D-me 用户气泡四组组合全部 ≥4.5:1（最低 ${worst.toFixed(2)}:1 @ ${worstAt}）`);
    fs.writeFileSync(path.join(DIR, '_tools', 'me-bubble-contrast.json'), JSON.stringify(table, null, 1), 'utf8');
    fs.writeFileSync(path.join(DIR, '_tools', 'bubble-bg.json'), JSON.stringify(bubbleRows, null, 1), 'utf8');
    await ctx.close();
  }

  /* ---- reduced-motion：只归零时长，不隐藏层 ------------------------------ */
  console.log('\n=== E. prefers-reduced-motion ===');
  {
    const { ctx, page } = await newPage(1280, 900, { reducedMotion: true });
    await page.click('#tab-data');
    await wait(500);
    const r = await page.evaluate(() => {
      const halo = document.querySelector('.avatar__halo');
      const ring = document.querySelector('.avatar__ring');
      const whoosh = document.querySelector('.avatar__whoosh');
      const eye = document.querySelector('.avatar__eye');
      const bar = document.querySelector('.row__bar');
      return {
        haloDisplay: getComputedStyle(halo).display,
        haloOpacity: getComputedStyle(halo).opacity,
        haloAnim: getComputedStyle(halo).animationName,
        eyeAnim: getComputedStyle(eye).animationName,
        whooshOpacity: getComputedStyle(whoosh).opacity,
        panelAnim: getComputedStyle(document.getElementById('panel-ev')).animationName,
        barClip: getComputedStyle(bar).clipPath,
        barH: bar.getBoundingClientRect().height,
        dur: getComputedStyle(document.querySelector('.nav__item')).transitionDuration
      };
    });
    check(r.haloDisplay !== 'none' && parseFloat(r.haloOpacity) > 0 && r.haloAnim === 'none' && r.eyeAnim === 'none' && r.panelAnim === 'none',
      `E reduced-motion：动画归零（halo animation=${r.haloAnim}）但层还在（halo display=${r.haloDisplay} opacity=${r.haloOpacity}；whoosh opacity=${r.whooshOpacity}）`);
    check(parseFloat(r.barH) >= 10 && !/inset\(0px 0px/.test(r.barClip), `E 条形仍是完整长度（高 ${r.barH}px，clip=${r.barClip}）`);
    check(r.dur === '0.001s', `E 过渡时长归零：${r.dur}`);
    await page.screenshot({ path: path.join(SHOTS, '1280-reduced.png') });
    console.log('  [shot] 1280-reduced.png');
    await ctx.close();
  }

  await browser.close();

  console.log('\n=== 汇总 ===');
  if (notes.length) { console.log('大字放宽说明：'); notes.forEach(n => console.log('  · ' + n)); }
  if (problems.length) {
    console.log(`\n问题 ${problems.length} 条：`);
    problems.forEach(p => console.log('  ✗ ' + p));
    process.exitCode = 1;
  } else {
    console.log('全部断言通过：无横向溢出、无控制台报错、交互与主题覆盖逐条核过。');
  }
})();
