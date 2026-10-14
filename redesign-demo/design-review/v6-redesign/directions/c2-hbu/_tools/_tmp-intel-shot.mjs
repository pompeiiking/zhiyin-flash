/* 临时：只在开发时看几处局部截图（跑完即删，不进仓库） */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(
  process.env.LOCALAPPDATA, 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'
));

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
const URL_ = pathToFileURL(path.join(DIR, '_shots', 'preview-intel.html')).href + '#/intel';
const OUT = path.join(DIR, '_shots', 'intel');

const browser = await chromium.launch();

async function shots(width, tag) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(URL_, { waitUntil: 'load' });
  await page.waitForTimeout(500);
  const targets = [
    ['.lens__item.int-card', 1, 'card'],
    ['section.sec[aria-labelledby="intFilterT"]', 0, 'filter'],
    ['aside.pg-doc__side', 0, 'side'],
  ];
  for (const [sel, idx, name] of targets) {
    const els = await page.$$(sel);
    if (!els[idx]) { console.log('缺 ' + sel); continue; }
    const file = path.join(OUT, `tmp-${tag}-${name}.png`);
    await els[idx].screenshot({ path: file });
    console.log('写出 ' + path.basename(file));
  }
  await page.close();
}

await shots(1280, '1280');
await shots(390, '390');
await browser.close();
