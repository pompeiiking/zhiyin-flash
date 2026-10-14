/* 方向 A 截图 + 硬检查（一次性脚本，产物只写进本目录 shots/） */
const path = require('path');
const fs = require('fs');
const PW = process.env.PW_PATH;
const { chromium } = require(PW);

const DIR = __dirname;
const SHOTS = path.join(DIR, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });
const URL = 'file:///' + path.join(DIR, 'index.html').replace(/\\/g, '/') + '?v=' + Date.now();

(async () => {
  const browser = await chromium.launch();

  async function shoot(name, width, height, dsf) {
    const ctx = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: dsf,
      reducedMotion: 'no-preference',
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
    page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
    await page.goto(URL, { waitUntil: 'load' });
    await page.waitForTimeout(400);

    const probe = await page.evaluate(() => {
      const de = document.documentElement;
      const overflowing = [...document.querySelectorAll('body *')]
        .filter((el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && (r.right > window.innerWidth + 1 || r.left < -1);
        })
        .slice(0, 8)
        .map((el) => el.tagName + '.' + (el.className || '').toString().slice(0, 40) + ' @' + Math.round(el.getBoundingClientRect().right));
      const box = (s) => {
        const el = document.querySelector(s);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) };
      };
      return {
        scrollW: de.scrollWidth,
        clientW: de.clientWidth,
        bodyScrollW: document.body.scrollWidth,
        docH: de.scrollHeight,
        innerW: window.innerWidth,
        innerH: window.innerHeight,
        overflowing,
        tabbar: getComputedStyle(document.querySelector('.tabbar')).display,
        aside: getComputedStyle(document.querySelector('.aside')).display,
        rail: getComputedStyle(document.querySelector('.rail')).display,
        boxes: {
          main: box('.main'), workspace: box('.workspace'), panel: box('.panel'),
          chathead: box('.chathead'), flow: box('.flow'), composer: box('.composer'),
          tabbar: box('.tabbar'),
        },
        flowScrollable: (() => { const f = document.querySelector('.flow'); return f.scrollHeight - f.clientHeight; })(),
      };
    });

    await page.screenshot({ path: path.join(SHOTS, name), fullPage: false });
    await ctx.close();
    return { name, probe, errs };
  }

  const a = await shoot('1280.png', 1280, 900, 2);
  const b = await shoot('390.png', 390, 844, 3);
  /* 第三张：390 全流程（按内容实际高度定视口，把一屏放不下的卡组 / 行动卡 / 后续问题一并留证） */
  async function shootTall() {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto(URL, { waitUntil: 'load' });
    await page.waitForTimeout(300);
    const need = await page.evaluate(() => {
      const thread = document.querySelector('.thread');
      const cs = getComputedStyle(thread);
      const content = thread.scrollHeight + parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
      return Math.ceil(content + 75 + 129 + 54 + 24); // 头部 + 输入区 + 底栏 + 余量
    });
    await page.setViewportSize({ width: 390, height: need });
    await page.waitForTimeout(500);
    const probe = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      docH: document.documentElement.scrollHeight,
      innerH: window.innerHeight,
      overflowing: [...document.querySelectorAll('body *')].filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.right > window.innerWidth + 1 || r.left < -1);
      }).slice(0, 6).map((el) => el.tagName + '.' + (el.className || '').toString().slice(0, 36)),
      flowScrollable: (() => { const f = document.querySelector('.flow'); return f.scrollHeight - f.clientHeight; })(),
      composerBottom: Math.round(document.querySelector('.composer').getBoundingClientRect().bottom),
      tabbarTop: Math.round(document.querySelector('.tabbar').getBoundingClientRect().top),
    }));
    await page.screenshot({ path: path.join(SHOTS, '390-fullflow.png'), fullPage: false });
    await ctx.close();
    return { name: '390-fullflow.png', probe, errs: [], height: need };
  }
  const c = await shootTall();

  /* 第四张：桌面数据卡与依据展开态（把卡的"仪表"细节留证） */
  async function shootDataCard() {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto(URL, { waitUntil: 'load' });
    await page.click('#tab-data');
    await page.waitForTimeout(900);
    await page.evaluate(() => {
      const el = document.querySelector('.cards');
      document.querySelector('.flow').scrollTop = el.offsetTop - 60;
    });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(SHOTS, '1280-datacard.png'), fullPage: false });
    await ctx.close();
    return 'ok';
  }
  await shootDataCard();

  /* 交互自检（在 1280 上跑） */
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: 'load' });
  const inter = {};

  // 卡片切换
  await page.click('#tab-data');
  await page.waitForTimeout(500);
  inter.dataSelected = await page.getAttribute('#tab-data', 'aria-selected');
  inter.dataVisible = await page.isVisible('#pl-data');
  inter.evHidden = await page.isHidden('#pl-ev');
  inter.barWidths = await page.$$eval('.gauge__bar', (els) => els.map((e) => getComputedStyle(e).width));
  inter.ariaLabel = await page.getAttribute('.gauge__rows', 'aria-label');
  await page.click('#tab-method');
  await page.waitForTimeout(300);
  inter.methodVisible = await page.isVisible('#pl-method');

  // 依据展开
  await page.click('#tab-ev');
  await page.waitForTimeout(200);
  inter.evRestBefore = await page.isHidden('#evRest');
  await page.click('#evMore');
  await page.waitForTimeout(200);
  inter.evRestAfter = await page.isVisible('#evRest');
  inter.evCount = await page.$$eval('#pl-ev .ev', (e) => e.length);
  inter.evMoreText = await page.textContent('#evMoreText');

  // 方法展开
  await page.click('#tab-method');
  await page.click('#methodMore');
  await page.waitForTimeout(150);
  inter.methodFullVisible = await page.isVisible('#methodFull');

  // 输入区聚焦态
  await page.click('#draft');
  await page.waitForTimeout(200);
  inter.slotFocus = await page.$eval('#slot', (e) => e.classList.contains('is-focus'));
  inter.slotBorder = await page.$eval('#slot', (e) => getComputedStyle(e).borderColor);
  await page.type('#draft', '我想先看看省内机会');
  inter.sendEnabled = await page.getAttribute('#send', 'aria-disabled');

  // 后续问题 → 输入框
  await page.click('.chip[data-send]');
  await page.waitForTimeout(150);
  inter.draftAfterChip = await page.inputValue('#draft');

  // 行动卡
  await page.click('#addPlan');
  await page.waitForTimeout(200);
  inter.actionAdded = await page.$eval('#actionCard', (e) => e.classList.contains('is-added'));
  inter.actionBtnText = (await page.textContent('#addPlan')).trim();

  // 折叠导航
  await page.click('#railToggle');
  await page.waitForTimeout(250);
  inter.railMini = await page.getAttribute('#shell', 'data-rail');

  // 焦点环（键盘）
  await page.keyboard.press('Tab');
  inter.focusRing = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el) return null;
    const s = getComputedStyle(el);
    return { tag: el.tagName, cls: (el.className || '').toString().slice(0, 30), boxShadow: s.boxShadow.slice(0, 90) };
  });
  await ctx.close();

  /* reduced-motion 自检 */
  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 860 }, reducedMotion: 'reduce' });
  const p2 = await ctx2.newPage();
  await p2.goto(URL, { waitUntil: 'load' });
  await p2.click('#tab-data');
  await p2.waitForTimeout(120);
  const rm = {
    barWidths: await p2.$$eval('.gauge__bar', (els) => els.map((e) => getComputedStyle(e).width)),
    plateAnimation: await p2.$eval('#pl-data', (e) => getComputedStyle(e).animationName),
    composerBlur: await p2.$eval('.composer', (e) => getComputedStyle(e).backdropFilter),
    actionTransition: await p2.$eval('.action', (e) => getComputedStyle(e).transitionDuration),
  };
  await ctx2.close();

  await browser.close();
  console.log(JSON.stringify({ shots: [a, b, c], inter, rm }, null, 2));
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
