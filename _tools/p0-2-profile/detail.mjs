/**
 * 细节对照截图（用浏览器裁剪，避免自己解码 PNG）：
 *   node _tools/p0-2-profile/detail.mjs <tag>
 * 产物：_shots/p0-2-profile/detail-<tag>-<name>.png
 *
 * 偏移量固定写死，所以"改前/改后"取到的是**同一段页面**（页面整体变长时也一致，
 * 因为偏移是从文档顶部算的）。
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

/* [名字, 页面 y, 高, 宽档] */
const REGIONS = [
  ['rows', 2050, 700, 1280],   // A 段：字段名 + 来源/时间/关系/动作 这一排
  ['concl', 2760, 700, 1280],  // B 段：判断 + 依赖边
  ['rows-390', 1500, 700, 390],
  ['concl-390', 3300, 700, 390],
];

(async () => {
  const browser = await chromium.launch();
  for (const [name, y, h, w] of REGIONS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 1280 ? 900 : 844 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.setItem('zhiyin.onboarded', '1'); } catch { /* ignore */ } });
    await page.goto(BASE + '#/profile', { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(1600);
    const dest = path.join(SHOTS, `detail-${TAG}-${name}.png`);
    await page.screenshot({ path: dest, clip: { x: 0, y, width: w, height: h }, fullPage: true });
    console.log(`  ${TAG} ${name} y=${y} -> ${dest}`);
    await ctx.close();
  }
  await browser.close();
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
