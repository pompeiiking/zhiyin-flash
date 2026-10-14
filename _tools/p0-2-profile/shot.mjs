/**
 * 截图：profile 页 1280 / 390 各一张整页。
 *   node _tools/p0-2-profile/shot.mjs before
 *   node _tools/p0-2-profile/shot.mjs after
 * 产物：_shots/p0-2-profile/<tag>-profile-<w>.png
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const PW = process.env.PW_PATH || path.join(process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright');
const { chromium } = require(PW);
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5180/';
const TAG = process.argv[2] || 'run';
const SHOTS = path.join(ROOT, '_shots', 'p0-2-profile');
fs.mkdirSync(SHOTS, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  for (const w of [1280, 390]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 1280 ? 900 : 844 }, deviceScaleFactor: 1, reducedMotion: 'no-preference' });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.setItem('zhiyin.onboarded', '1'); } catch { /* ignore */ } });
    await page.goto(BASE + '#/profile', { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(1600);
    const dest = path.join(SHOTS, `${TAG}-profile-${w}.png`);
    await page.screenshot({ path: dest, fullPage: true });
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    console.log(`  ${TAG} ${dest}  docH=${h}`);
    await ctx.close();
  }
  await browser.close();
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
