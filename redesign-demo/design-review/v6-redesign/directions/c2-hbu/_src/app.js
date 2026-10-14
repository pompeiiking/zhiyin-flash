
(function () {
  'use strict';

  /* ---------------------------------------------------------------------------
     主理头像：一只"鹅卵石"伙伴。
     三态不是三张图，是同一张 SVG 上不同部件的启用 ——
     待命（眼睛会扫视）／思考（眼睛上抬 + 三点绕行）／说话（嘴开合 + 声波）。
     颜色由 CSS 变量 --st-a/--st-b 驱动，跟着 html[data-state] 整页换色温。
     ------------------------------------------------------------------------ */
  /* ⚠ 以下是 c-companion 的**玻璃实体**画法，本版不渲染它 ——
     保留 "旧名 AVATAR_SVG_GLASS + 新名 AVATAR_SVG" 的对照，是为了
     "形体换过哪一层"这件事可回滚、可 diff，而不是靠一段注释声称。
     真正生效的卡通形体定义在下面的挂载点（同一处、同一个作用域）。 */
  var AVATAR_SVG_GLASS = function (uid) { return [
    /* viewBox 留了余量：思考时那三点绕到身体之外，
       被裁掉就会变成脸上两块脏东西，而不是"正在想"。 */
    '<svg viewBox="-8 -8 116 116" role="img" aria-hidden="true" focusable="false">',
    '  <defs>',
    '    <radialGradient id="' + uid + '" cx="34%" cy="24%" r="92%">',
    '      <stop data-grad-a offset="0" stop-color="var(--st-a)"/>',
    '      <stop data-grad-b offset="1" stop-color="var(--st-b)"/>',
    '    </radialGradient>',
    '  </defs>',
    /* 说话时的涟漪；待命/思考时 CSS 让它 opacity:0 */
    '  <circle class="avatar__ring" cx="50" cy="50" r="38" fill="none" stroke="var(--st-a)" stroke-width="1.6"/>',
    /* 思考时的轨道与六点：轨道把"念头"挂在一个明确的位置上，呼吸感够用 */
    '  <g class="avatar__whoosh">',
    '    <circle cx="50" cy="50" r="46" fill="none" stroke="var(--st-a)" stroke-opacity=".20" stroke-width="1.2" stroke-dasharray="2.5 6"/>',
    '    <g class="avatar__dots">',
    '      <circle cx="50" cy="4" r="2.4"/><circle cx="82" cy="15.2" r="2.7"/>',
    '      <circle cx="96" cy="38" r="3"/><circle cx="96" cy="62" r="2.7"/>',
    '      <circle cx="82" cy="84.8" r="3"/><circle cx="50" cy="96" r="2.4"/>',
    '    </g>',
    '    <g class="avatar__dots">',
    '      <circle cx="18" cy="84.8" r="2.7"/><circle cx="4" cy="62" r="2.4"/>',
    '      <circle cx="4" cy="38" r="2.7"/><circle cx="18" cy="15.2" r="3"/>',
    '      <circle cx="32" cy="8.5" r="2.4"/><circle cx="68" cy="8.5" r="2.7"/>',
    '    </g>',
    '  </g>',
    /* 主体：圆角方块（superellipse 观感），比正圆更有"实体感" */
    '  <rect x="10" y="10" width="80" height="80" rx="27" fill="url(#' + uid + ')"/>',
    /* 顶部高光：给它一个受光面，避免变成一块平的色块 */
    '  <ellipse cx="38" cy="27" rx="20" ry="11" fill="#fff" opacity=".22"/>',
    /* 眉：只在"思考"时出现，轻一点——它不该抢眼睛 */
    '  <g class="avatar__brow" opacity="0" stroke="#2C2320" stroke-opacity=".32" stroke-width="2.2" stroke-linecap="round">',
    '    <path d="M30 30.5 39 29.2"/><path d="M61 29.2 70 30.5"/>',
    '  </g>',
    /* 眼 + 瞳 + 高光 */
    '  <g class="avatar__face">',
    '    <g class="avatar__eye avatar__eye--l">',
    '      <ellipse cx="37.5" cy="44" rx="6.4" ry="7" fill="#FFF7F1" opacity=".96"/>',
    '      <g class="avatar__pupil">',
    '        <g class="avatar__gaze">',
    '          <circle cx="38.1" cy="45" r="3.4" fill="#2C2320"/>',
    '          <circle class="avatar__glint" cx="36.8" cy="43.3" r="1.25" fill="#fff"/>',
    '        </g>',
    '      </g>',
    '    </g>',
    '    <g class="avatar__eye avatar__eye--r">',
    '      <ellipse cx="62.5" cy="44" rx="6.4" ry="7" fill="#FFF7F1" opacity=".96"/>',
    '      <g class="avatar__pupil">',
    '        <g class="avatar__gaze">',
    '          <circle cx="63.1" cy="45" r="3.4" fill="#2C2320"/>',
    '          <circle class="avatar__glint" cx="61.8" cy="43.3" r="1.25" fill="#fff"/>',
    '        </g>',
    '      </g>',
    '    </g>',
    /* 嘴：说的时候用 scaleY 做开合，底形就是一条自信的弧线 */
    '    <path class="avatar__mouth" d="M43.5 60.4q6.5 6.4 13 0" fill="none" stroke="#2C2320" stroke-opacity=".6" stroke-width="3" stroke-linecap="round"/>',
    /* 脸颊上的两点腮红：这是"温度"最便宜也最有效的一笔 */
    '    <ellipse cx="25" cy="62" rx="5.2" ry="3.2" fill="#B0552F" opacity=".15"/>',
    '    <ellipse cx="75" cy="62" rx="5.2" ry="3.2" fill="#B0552F" opacity=".15"/>',
    '  </g>',
    /* 说话：声波（用 i 装，方便错峰） */
    '  <foreignObject x="86" y="34" width="26" height="32" class="avatar__wave">',
    '    <div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:center;gap:3px;height:100%">',
    '      <i style="display:block;width:2.6px;height:14px;border-radius:2px;background:var(--st-b);transform-origin:center"></i>',
    '      <i style="display:block;width:2.6px;height:20px;border-radius:2px;background:var(--st-b);transform-origin:center"></i>',
    '      <i style="display:block;width:2.6px;height:11px;border-radius:2px;background:var(--st-b);transform-origin:center"></i>',
    '    </div>',
    '  </foreignObject>',
    '</svg>'
  ].join(''); };

  var heroMount = document.getElementById('heroAvatar');
  var turnMount = document.getElementById('turnAvatar');
  /* =======================================================================
     卡通头像（本轮需求方意见①："机器人头像有点丑，我想要那种卡通风格的"）
     ----------------------------------------------------------------------
     换掉的只有"形体"这一层，三态机制、挂载点、CSS 钩子名全部沿用：
       .avatar__whoosh / .avatar__dots / .avatar__brow / .avatar__face
       .avatar__eye(--l/--r) / .avatar__pupil / .avatar__gaze / .avatar__glint
       .avatar__mouth / .avatar__ring / .avatar__wave（三条 i）
       html[data-state="idle|thinking|speaking"] 仍然只改 --st-a/--st-b

     与上一版（AVATAR_SVG_GLASS）的差别，逐条：
       1. 去掉 radialGradient（受光渐变）→ 纯色底 + 一层很淡的上亮下暗
       2. 去掉"顶部镜面高光"与"第二层小高光"两个椭圆 → 一条柔和的左上受光
       3. 去掉"边缘受光"白描边 → 一条 1px 主色边（那是"轮廓"，不是"玻璃厚度"）
       4. 眼睛放大：眼白 12.8×14 → 13.6×15.2，瞳 r4.4 → r4.6，高光 r1.25 → r1.9；
          两眼各留 3.8u 空隙、间距 25u —— 40px 下才不会糊成两个灰点
       5. 眉从 .32 描边提到 .48，且只在思考时出现（待命不堆表情）
       6. 嘴的弧线加深（stroke-opacity .5 → .68），三态读得出差别
     没有加：腮红、星星/心形/音符、金属玻璃、任何超过 1.4px 的位移。
     ==================================================================== */
  var AVATAR_SVG = function (uid) { return [
    /* 眼睛是主角：眼白 13.6×15.2、瞳 r4.6（留 2.2u 白边，读得出"眼白"）、
       高光 r1.9 压在左上。高光**不放在瞳孔正中心** —— 正中会读成"珠子"，
       偏左上才读成"朝一个方向看的眼睛"。 */
    '<svg viewBox="-8 -8 116 116" role="img" aria-hidden="true" focusable="false">',
    '  <defs>',
    '    <linearGradient id="' + uid + '" x1="0" y1="0" x2="0" y2="1">',
    '      <stop data-grad-a offset="0" stop-color="var(--st-a)" stop-opacity="0"/>',
    '      <stop data-grad-b offset="1" stop-color="var(--st-b)" stop-opacity=".30"/>',
    '    </linearGradient>',
    '  </defs>',
    /* 说话时的涟漪；待命/思考时 CSS 让它 opacity:0 */
    '  <circle class="avatar__ring" cx="50" cy="50" r="38" fill="none" stroke="var(--st-a)" stroke-width="1.6"/>',
    /* 思考时的轨道与六点：轨道把"念头"挂在一个明确的位置上 */
    '  <g class="avatar__whoosh">',
    '    <circle cx="50" cy="50" r="46" fill="none" stroke="var(--st-a)" stroke-opacity=".20" stroke-width="1.2" stroke-dasharray="2.5 6"/>',
    '    <g class="avatar__dots">',
    '      <circle cx="50" cy="4" r="2.4"/><circle cx="82" cy="15.2" r="2.7"/>',
    '      <circle cx="96" cy="38" r="3"/><circle cx="96" cy="62" r="2.7"/>',
    '      <circle cx="82" cy="84.8" r="3"/><circle cx="50" cy="96" r="2.4"/>',
    '    </g>',
    '    <g class="avatar__dots">',
    '      <circle cx="18" cy="84.8" r="2.7"/><circle cx="4" cy="62" r="2.4"/>',
    '      <circle cx="4" cy="38" r="2.7"/><circle cx="18" cy="15.2" r="3"/>',
    '      <circle cx="32" cy="8.5" r="2.4"/><circle cx="68" cy="8.5" r="2.7"/>',
    '    </g>',
    '  </g>',
    /* 形体 ①：圆角方块（rx 27 / 80 = .34，**不是正圆** —— 风险评估的红线）。
       填充 = 纯色 --st-a + 一层 .30 的上亮下暗。没有受光渐变、没有镜面高光。 */
    '  <rect x="10" y="10" width="80" height="80" rx="27" fill="var(--st-a)"/>',
    '  <rect x="10" y="10" width="80" height="80" rx="27" fill="url(#' + uid + ')"/>',
    /* 形体 ②：这一版**没有**受光面。上一版是靠"顶部镜面高光 + 第二层小高光"
       两个椭圆堆出体积的 —— 那正是"读起来像玻璃"的来源。
       卡通只留一条信息：光从上面来（就是上面那层上亮下暗的渐变，一条，不再加）。 */
    /* 形体 ③：轮廓。用主色描一条 1px，是"形"，不是"玻璃的厚度/边缘受光"。 */
    '  <rect x="10.6" y="10.6" width="78.8" height="78.8" rx="26.6" fill="none" stroke="var(--st-a)" stroke-opacity=".34" stroke-width="1.2"/>',
    /* 眉：只在"思考"时出现。待命不堆表情 —— 这是"少即是多"那一条。
       斜率是"内端抬高、外端压低"（不是内低外高的皱眉）：那读成"在琢磨"，
       后者读成"生气"。这一条差 1.5u 的斜率，是卡通表情最容易写错的一处。 */
    '  <g class="avatar__brow" opacity="0" stroke="var(--face-ink)" stroke-opacity=".48" stroke-width="2.4" stroke-linecap="round">',
    '    <path d="M30.6 30.6 39.4 27.8"/><path d="M60.6 27.8 69.4 30.6"/>',
    '  </g>',
    /* 眼：白眼球 + 深瞳 + 高光。待命时整只眼慢慢扫视（"在看"）。 */
    '  <g class="avatar__face">',
    '    <g class="avatar__eye avatar__eye--l">',
    '      <ellipse class="avatar__eye-white" cx="37.5" cy="43" rx="6.8" ry="7.6"/>',
    '      <ellipse class="avatar__eye-rim" cx="37.5" cy="43" rx="6.8" ry="7.6"/>',
    '      <g class="avatar__pupil">',
    '        <g class="avatar__gaze">',
    '          <circle cx="38.4" cy="44.2" r="4.6" fill="var(--face-ink)"/>',
    '          <circle class="avatar__glint" cx="36.6" cy="42.1" r="1.9" fill="#fff"/>',
    '        </g>',
    '      </g>',
    '    </g>',
    '    <g class="avatar__eye avatar__eye--r">',
    '      <ellipse class="avatar__eye-white" cx="62.5" cy="43" rx="6.8" ry="7.6"/>',
    '      <ellipse class="avatar__eye-rim" cx="62.5" cy="43" rx="6.8" ry="7.6"/>',
    '      <g class="avatar__pupil">',
    '        <g class="avatar__gaze">',
    '          <circle cx="63.4" cy="44.2" r="4.6" fill="var(--face-ink)"/>',
    '          <circle class="avatar__glint" cx="61.6" cy="42.1" r="1.9" fill="#fff"/>',
    '        </g>',
    '      </g>',
    '    </g>',
    /* 嘴：一条弧线，说的时候用 scaleY 开合（.62s）。没有腮红、没有表情符号。 */
    '    <path class="avatar__mouth" d="M43.5 61.5q6.5 6.6 13 0" fill="none" stroke="var(--face-ink)" stroke-opacity=".68" stroke-width="3.2" stroke-linecap="round"/>',
    '  </g>',
    /* 说话：声波（用 i 装，CSS 的 .avatar__wave i 负责间距与错峰） */
    '  <foreignObject x="86" y="34" width="26" height="32" class="avatar__wave">',
    '    <div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:center;height:100%">',
    '      <i style="display:block;width:2.6px;height:14px;border-radius:2px;background:var(--st-b)"></i>',
    '      <i style="display:block;width:2.6px;height:20px;border-radius:2px;background:var(--st-b)"></i>',
    '      <i style="display:block;width:2.6px;height:11px;border-radius:2px;background:var(--st-b)"></i>',
    '    </div>',
    '  </foreignObject>',
    '</svg>'
  ].join(''); };

  if (heroMount) heroMount.innerHTML = AVATAR_SVG('avBodyHero');
  if (turnMount) turnMount.innerHTML = AVATAR_SVG('avBodyTurn');

  /* ---- 状态切换（idle / thinking / speaking） ---- */
  var STATE_TEXT = { idle: '在场，等你开口', thinking: '正在想', speaking: '正在说' };
  var stateText = document.getElementById('stateText');
  var stateBtns = Array.prototype.slice.call(document.querySelectorAll('[data-presence]'));

  function setPresence(next) {
    document.documentElement.setAttribute('data-state', next);
    if (stateText) stateText.textContent = STATE_TEXT[next] || '';
    stateBtns.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-presence') === next));
    });
  }
  stateBtns.forEach(function (b) {
    b.addEventListener('click', function () { setPresence(b.getAttribute('data-presence')); });
  });
  setPresence('thinking');

  /* ---- 支撑材料卡组：真的能切 ---- */
  /* 注意：多视图版里全站只有一个文档，所以对话页的选择器必须**限定在对话视图内** ——
     否则别的视图只要用了 .tab/.panel 就会被这段脚本接管（见 _src/BRIEF.md 的命名纪律）。 */
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-view="chat"] .tab'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[data-view="chat"] .panel'));
  var posNow = document.getElementById('posNow');

  function selectTab(i) {
    tabs.forEach(function (t, k) {
      var on = k === i;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach(function (p, k) {
      /* 切走的面板不保留 data-active，重新进入时才会重播入场 */
      if (k === i) p.setAttribute('data-active', 'true');
      else p.removeAttribute('data-active');
    });
    if (posNow) posNow.textContent = String(i + 1);
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { selectTab(i); });
    t.addEventListener('keydown', function (e) {
      var next = null;
      if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
      else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = tabs.length - 1;
      if (next === null) return;
      e.preventDefault();
      selectTab(next);
      tabs[next].focus();
    });
  });
  selectTab(0);
  setChartBar();
  window.addEventListener('resize', setChartBar, { passive: true });

  /* ---- 依据：展开其余 2 条 ---- */
  var evMore = document.getElementById('evMore');
  var evToggle = document.getElementById('evToggle');
  if (evToggle && evMore) {
    evToggle.addEventListener('click', function () {
      var open = evMore.getAttribute('data-open') === 'true';
      evMore.setAttribute('data-open', String(!open));
      evToggle.setAttribute('aria-expanded', String(!open));
      var label = evToggle.querySelector('[data-label]');
      if (label) label.textContent = open ? '展开其余 2 条依据' : '收起依据';
    });
  }

  /* ---- 方法卡：展开全文 ---- */
  var methodFull = document.getElementById('methodFull');
  var methodToggle = document.getElementById('methodToggle');
  if (methodToggle && methodFull) {
    methodToggle.addEventListener('click', function () {
      var open = methodFull.getAttribute('data-open') === 'true';
      methodFull.setAttribute('data-open', String(!open));
      methodToggle.setAttribute('aria-expanded', String(!open));
      var label = methodToggle.querySelector('[data-label]');
      if (label) label.textContent = open ? '展开全文' : '收起全文';
    });
  }

  /* ---- 输入区：聚焦态 + 发送按钮可用性 ----
     这三行必须做空值保护：预览文件（build.mjs --only <key>）里不含对话页，
     这段不挡就会在 msg.addEventListener 抛异常，把整个 IIFE 打断 ——
     路由与视角重组引擎都在后面，作者会以为"引擎坏了"。 */
  var box = document.getElementById('box');
  var msg = document.getElementById('msg');
  var send = document.getElementById('send');

  function syncSend() {
    if (!msg || !send) return;
    var has = msg.value.trim().length > 0;
    send.setAttribute('aria-disabled', String(!has));
  }
  if (box && msg && send) {
    msg.addEventListener('focus', function () { box.setAttribute('data-focused', 'true'); });
    msg.addEventListener('blur', function () { box.setAttribute('data-focused', 'false'); });
    msg.addEventListener('input', function () {
      msg.style.height = 'auto';
      msg.style.height = Math.min(msg.scrollHeight, 132) + 'px';
      syncSend();
    });
    box.addEventListener('submit', function (e) {
      e.preventDefault();
      if (send.getAttribute('aria-disabled') === 'true') return;
      msg.value = '';
      msg.style.height = 'auto';
      syncSend();
    });
    syncSend();
  }

  /* 行动卡：加入今日行动的即时反馈 */
  var addTask = document.getElementById('addTask');
  if (addTask) {
    addTask.addEventListener('click', function () {
      var done = addTask.getAttribute('data-done') === 'true';
      addTask.setAttribute('data-done', String(!done));
      var label = addTask.querySelector('[data-label]');
      if (label) label.textContent = done ? '加入今日行动' : '已加入今日行动';
      var icon = addTask.querySelector('svg');
      if (icon) icon.innerHTML = done
        ? '<path d="M12 5v14M5 12h14"/>'
        : '<path d="M5 12.5 10 17.5 19 7"/>';
    });
  }

  /* ---- 数据卡：窄屏的数值标签要跟着自己那根条的末端走 ----
     条长是真实数值，任何时候都不为"给数字腾地方"而改写。
     桌面档没有这个问题（数值另有一列、竖向对齐），所以只在窄屏用到这个变量。 */
  var chartRows = document.getElementById('chartRows');
  function setChartBar() {
    if (!chartRows) return;
    var maxPct = 0;
    Array.prototype.forEach.call(chartRows.querySelectorAll('.row__bar'), function (bar) {
      var pct = parseFloat(bar.style.width) || 0;
      if (pct > maxPct) maxPct = pct;
    });
    chartRows.style.setProperty('--chart-bar', maxPct + '%');
  }

  /* ---- 导航折叠 / 移动端抽屉 ---- */
  var app = document.getElementById('app');
  var navToggle = document.getElementById('navToggle');
  var burger = document.getElementById('burger');
  var scrim = document.getElementById('scrim');

  if (navToggle) {
    navToggle.addEventListener('click', function () {
      var mini = app.getAttribute('data-nav') === 'mini';
      app.setAttribute('data-nav', mini ? 'full' : 'mini');
      navToggle.setAttribute('aria-expanded', String(mini));
      navToggle.title = mini ? '折叠导航' : '展开导航';
    });
  }
  function setDrawer(open) {
    app.setAttribute('data-drawer', open ? 'open' : 'closed');
    if (burger) burger.setAttribute('aria-expanded', String(open));
    if (scrim) {
      scrim.hidden = !open;
      scrim.style.opacity = open ? '1' : '';
    }
  }
  if (burger) burger.addEventListener('click', function () {
    setDrawer(app.getAttribute('data-drawer') !== 'open');
  });
  if (scrim) scrim.addEventListener('click', function () { setDrawer(false); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setDrawer(false);
  });

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
  Array.prototype.forEach.call(document.querySelectorAll('[data-view="chat"] .followbtn'), function (b) {
    b.addEventListener('click', function () {
      if (!msg || !send) return;
      var n = b.querySelector('.followbtn__n');
      var text = b.textContent.replace(n ? n.textContent : '', '').replace(/\s+/g, ' ').trim();
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
  if (msg && send) msg.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (send.getAttribute('aria-disabled') === 'true') return;
    msg.value = '';
    msg.style.height = 'auto';
    syncSend();
  });

  /* ===========================================================================
     多视图外壳：路由 / 全部界面目录 / 视角重组 / 粒度缩放 / 即时反馈
     ---------------------------------------------------------------------------
     为什么这些放在外壳而不是各视图自己写：
       · "同一批信息能被重新组织"（DESIGN-LANGUAGE §4.2）是全站的核心手法。
         每个页面各写一遍必然长出 20 种不一致的写法 —— 这正是上一轮
         "每做一个页面就多发明一套写法"的病灶（HANDOFF §4.2 共性问题 1）。
         所以引擎只有一份，各视图只负责给数据打标签。
       · 外壳与视图的契约写在 _src/BRIEF.md，视图作者只读那一份。
     ======================================================================== */

  var registry = [];
  try { registry = JSON.parse(document.getElementById('viewRegistry').textContent) || []; } catch (e) { registry = []; }
  var titleOf = {};
  registry.forEach(function (v) { titleOf[v.key] = v.title; });

  var DEFAULT_VIEW = 'chat';
  var activeView = null;
  var viewHooks = {};

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function viewKeyFromHash() {
    var m = /^#\/([a-zA-Z0-9_-]+)/.exec(location.hash || '');
    var key = m ? m[1] : DEFAULT_VIEW;
    if (titleOf[key]) return key;
    /* 认不出的地址 → 异常页（它自己也是一个视图），没有异常页就回默认视图 */
    return titleOf['notfound'] ? 'notfound' : DEFAULT_VIEW;
  }

  function showView(key, force) {
    if (!force && key === activeView) return;
    var target = document.querySelector('.main > .main__scroll[data-view="' + key + '"]');
    if (!target) { key = DEFAULT_VIEW; target = document.querySelector('.main > .main__scroll[data-view="' + key + '"]'); }
    if (!target) {
      /* 预览文件（build.mjs --only <key>）里只有作者那一个视图，没有 chat。
         这时退到文档里第一个视图 —— 否则 showView 直接 return，
         视角重组/粒度缩放引擎根本不会初始化，作者会以为引擎坏了。 */
      var first = document.querySelector('.main > .main__scroll[data-view]');
      if (first) { key = first.getAttribute('data-view'); target = first; }
    }
    if (!target) return;

    Array.prototype.forEach.call(document.querySelectorAll('.main > .main__scroll[data-view]'), function (el) {
      if (el === target) el.setAttribute('data-active', 'true');
      else el.removeAttribute('data-active');
    });
    activeView = key;
    document.documentElement.setAttribute('data-view', key);
    document.title = (titleOf[key] || key) + ' · 职引 · 全站界面样张';

    /* 导航高亮是路由状态，不写在标记里 */
    Array.prototype.forEach.call(document.querySelectorAll('[data-nav-to]'), function (el) {
      var on = el.getAttribute('data-nav-to') === key;
      if (el.classList.contains('nav__item')) el.classList.toggle('nav__item--on', on);
      if (on) el.setAttribute('aria-current', 'page');
      else el.removeAttribute('aria-current');
    });

    target.scrollTop = 0;
    setDrawer(false);
    closeIndex();
    syncIndexCurrent();
    initLens(target);
    initZoom(target);
    (viewHooks[key] || []).forEach(function (fn) { fn(); });
  }

  /* ---- 全部界面目录 -------------------------------------------------------- */
  var idxEl = document.getElementById('viewIndex');
  var idxBody = document.getElementById('idxBody');
  var idxBtn = document.getElementById('viewIndexBtn');
  var idxMore = document.getElementById('tabMore');
  var idxOpener = null;

  function buildIndex() {
    if (!idxBody || !registry.length) return;
    var order = [], byGroup = {};
    registry.forEach(function (v) {
      var g = v.group || '其它';
      if (!byGroup[g]) { byGroup[g] = []; order.push(g); }
      byGroup[g].push(v);
    });
    idxBody.innerHTML = order.map(function (g) {
      return '<div class="idx__grp"><p class="idx__glabel">' + esc(g) + '</p><div class="idx__list">' +
        byGroup[g].map(function (v) {
          return '<a class="idx__a" href="#/' + v.key + '" data-idx-link="' + v.key + '">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h13"/><path d="m13 7 5 5-5 5"/></svg>' +
            '<span>' + esc(v.title) + '</span><span class="idx__k">#/' + v.key + '</span></a>';
        }).join('') + '</div></div>';
    }).join('') +
      '<p class="idx__note">门户、登录、账号设置、提醒、工具页、使用指南、设计规范、异常页' +
      '不在学生导航里 —— 它们是直链可达的页面，占了导航位反而把学生的路带跑偏。' +
      '所以这份目录只出现在这里，不进左侧导航；要评审全部界面，从这里进。</p>';
    var n = document.getElementById('idxCount');
    if (n) n.textContent = String(registry.length);
  }

  function syncIndexCurrent() {
    if (!idxBody) return;
    Array.prototype.forEach.call(idxBody.querySelectorAll('[data-idx-link]'), function (a) {
      if (a.getAttribute('data-idx-link') === activeView) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }

  function openIndex() {
    if (!idxEl) return;
    idxEl.hidden = false;
    if (idxBtn) idxBtn.setAttribute('aria-expanded', 'true');
    if (idxMore) idxMore.setAttribute('aria-expanded', 'true');
    syncIndexCurrent();
    idxOpener = document.activeElement;
    var first = idxEl.querySelector('[aria-current="page"]') || idxEl.querySelector('.idx__a');
    if (first) first.focus();
  }
  function closeIndex() {
    if (!idxEl || idxEl.hidden) return;
    idxEl.hidden = true;
    if (idxBtn) idxBtn.setAttribute('aria-expanded', 'false');
    if (idxMore) idxMore.setAttribute('aria-expanded', 'false');
    if (idxOpener && idxOpener.focus && document.contains(idxOpener)) idxOpener.focus();
    idxOpener = null;
  }
  if (idxBtn) idxBtn.addEventListener('click', openIndex);
  if (idxMore) idxMore.addEventListener('click', openIndex);
  if (idxEl) {
    idxEl.addEventListener('click', function (e) {
      var t = e.target;
      if (t.closest && t.closest('[data-idx-close]')) { closeIndex(); return; }
      if (t.closest && t.closest('[data-idx-link]')) closeIndex();
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && idxEl && !idxEl.hidden) closeIndex();
  });

  /* ---- 视角重组 -------------------------------------------------------------
     同一批信息，按来源 / 时间 / 主题 / 对结论的贡献重新分组。
     分组头由引擎生成；组顺序由容器上的 data-order-<视角> 给定（不给就按首次出现顺序）。
     为什么值得为它写一个引擎：这是"数据不动、组织方式在动"的落点
     （DESIGN-LANGUAGE §4.2），也是本样张区别于"多视角做成 tab 换个列表"的地方 ——
     切换时条目是**被搬动的**，不是被换掉的。
     视图侧契约：
        <div class="lens" data-lens="topic" data-order-topic="实践|课程|证书"
             data-hint-topic="同样 12 条，按它回答的问题聚成 3 组">
          <div class="lensbar" role="tablist"><button class="lensbtn" data-lens-set="source">…</button>…</div>
          <p class="lens__hint" data-lens-hint aria-live="polite"></p>
          <div class="lens__items">
            <article class="lens__item" data-source="对话里说的" data-time="10-12"
                     data-topic="实践" data-weight="直接支撑">…</article>
          </div>
        </div>
     data-<视角> 的值是**分组名**而不是数值：四个视角共用一套引擎。 */
  function initLens(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.lens'), function (box) {
      if (box.getAttribute('data-lens-init') === 'true') return;
      box.setAttribute('data-lens-init', 'true');

      var items = Array.prototype.slice.call(box.querySelectorAll('.lens__item'));
      var btns = Array.prototype.slice.call(box.querySelectorAll('[data-lens-set]'));
      var hint = box.querySelector('[data-lens-hint]');
      var host = box.querySelector('.lens__items') || box;
      if (!items.length || !btns.length) return;

      function set(lens) {
        var before = new Map();
        items.forEach(function (el) { before.set(el, el.getBoundingClientRect().top); });

        var groups = [], map = {};
        items.forEach(function (el) {
          var k = el.getAttribute('data-' + lens) || '未归组';
          if (!map[k]) { map[k] = []; groups.push(k); }
          map[k].push(el);
        });
        var raw = box.getAttribute('data-order-' + lens);
        if (raw) {
          var order = raw.split('|').map(function (s) { return s.trim(); });
          groups.sort(function (a, b) {
            var ia = order.indexOf(a), ib = order.indexOf(b);
            return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
          });
        }

        Array.prototype.forEach.call(host.querySelectorAll('.lens__gh'), function (h) { h.remove(); });
        var frag = document.createDocumentFragment();
        groups.forEach(function (k, gi) {
          var h = document.createElement('p');
          h.className = 'lens__gh';
          if (gi > 0) h.setAttribute('data-gap', 'true');
          var gk = document.createElement('span');
          gk.className = 'lens__gk';
          gk.textContent = k;
          var gn = document.createElement('span');
          gn.className = 'lens__gn';
          gn.textContent = map[k].length + ' 条';
          h.appendChild(gk);
          h.appendChild(gn);
          frag.appendChild(h);
          map[k].forEach(function (el) { frag.appendChild(el); });
        });
        host.appendChild(frag);

        /* FLIP：让"被搬动"这件事看得见。这是本项目允许的动效类型 ——
           它回答"这里发生了什么"（同一批东西换了组织方式），不是进场装饰。 */
        var moved = 0;
        items.forEach(function (el) {
          var dy = before.get(el) - el.getBoundingClientRect().top;
          if (Math.abs(dy) < 1) return;
          moved++;
          el.style.transition = 'none';
          el.style.transform = 'translateY(' + dy + 'px)';
          requestAnimationFrame(function () {
            el.style.transition = 'transform var(--dur-4) var(--ease-out)';
            el.style.transform = '';
            setTimeout(function () { el.style.transition = ''; }, 480);
          });
        });

        box.setAttribute('data-lens', lens);
        box.setAttribute('data-lens-moved', String(moved));
        btns.forEach(function (b) {
          b.setAttribute('aria-selected', String(b.getAttribute('data-lens-set') === lens));
        });
        if (hint) {
          var t = box.getAttribute('data-hint-' + lens);
          hint.textContent = t || ('按' + lens + '归成 ' + groups.length + ' 组');
        }
      }

      btns.forEach(function (b) {
        b.addEventListener('click', function () { set(b.getAttribute('data-lens-set')); });
      });
      var initial = box.getAttribute('data-lens') || btns[0].getAttribute('data-lens-set');
      box.removeAttribute('data-lens');
      set(initial);
    });
  }

  /* ---- 粒度缩放：摘要 ↔ 细节 ↔ 原文 ---------------------------------------
     纯 CSS 实现（容器加 data-zoom，标记里用 .z--sum/.z--mid/.z--full 标层次），
     JS 只切属性 —— 所以 prefers-reduced-motion 下同一份内容仍然可读。
     契约：三层必须**同时写在标记里**（不是点开才有的折叠框）："连续缩放"与
     "把来源藏进一个折叠框"是两件事（DESIGN-LANGUAGE §4.3 与反例表）。 */
  function initZoom(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.zoom'), function (z) {
      if (z.getAttribute('data-zoom-init') === 'true') return;
      z.setAttribute('data-zoom-init', 'true');
      var btns = Array.prototype.slice.call(z.querySelectorAll('[data-zoom-set]'));
      if (!btns.length) return;
      function set(v) {
        z.setAttribute('data-zoom', v);
        btns.forEach(function (b) {
          b.setAttribute('aria-pressed', String(b.getAttribute('data-zoom-set') === v));
        });
      }
      btns.forEach(function (b) {
        b.addEventListener('click', function () { set(b.getAttribute('data-zoom-set')); });
      });
      set(z.getAttribute('data-zoom') || btns[0].getAttribute('data-zoom-set'));
    });
  }

  /* ---- 即时反馈 ------------------------------------------------------------
     反例表禁的是"装饰性动效"，不是"反馈"。勾掉一件事、保存一次设置、
     加入今日行动这类**状态变化**必须有落点，否则用户不知道发生了没有
     （HANDOFF §4.2 共性问题 2：勾掉一件事得到零反馈）。 */
  var toastHost = null;
  function toast(message, kind) {
    if (!toastHost) {
      toastHost = document.createElement('div');
      toastHost.className = 'toasts';
      toastHost.setAttribute('role', 'status');
      toastHost.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastHost);
    }
    var el = document.createElement('div');
    el.className = 'toast' + (kind ? ' toast--' + kind : '');
    el.textContent = message;
    toastHost.appendChild(el);
    requestAnimationFrame(function () { el.setAttribute('data-in', 'true'); });
    setTimeout(function () {
      el.removeAttribute('data-in');
      setTimeout(function () { el.remove(); }, 300);
    }, 2600);
  }

  /* ---- 对外契约（视图作者只用这一份） ------------------------------------- */
  window.C2 = {
    /** 该视图被显示时执行（已经在显示就立刻执行一次） */
    onView: function (key, fn) {
      (viewHooks[key] = viewHooks[key] || []).push(fn);
      if (activeView === key) fn();
    },
    show: function (key) { location.hash = '#/' + key; },
    lens: initLens,
    zoom: initZoom,
    toast: toast,
    esc: esc,
    view: function () { return activeView; }
  };

  window.addEventListener('hashchange', function () { showView(viewKeyFromHash()); });
  buildIndex();
  showView(viewKeyFromHash(), true);
})();
