/* =============================================================================
 * 一次性迁移：把面包屑统一成「分组 › 当前页」
 * -----------------------------------------------------------------------------
 * 背景：BRIEF 写的是"分组 › 页面"，但样板页（profile.html）当时写成了
 *   `咨询对话 › 了解自己 › 个人画像` —— 第一段是**同级页面**，不是分组。
 *   于是 13 个视图各自照抄，全站都错成"你从哪个页面来的"而不是"你在哪一层"。
 *   （再一次印证：样板页会传播，样板页错了就是全站错。）
 *
 * 统一后的形态：
 *   分组段 = 指向该分组**第一页**的链接（一个"回到这一段"的入口，而不是假层级）
 *   当前页段 = 纯文本
 *   若当前页就是该组第一页，则分组段不链接（指向自己没有意义）
 *
 * 用法：node _tools/fix-crumbs.mjs            # 干跑，只报要改什么
 *       node _tools/fix-crumbs.mjs --write    # 真的写
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, '..', '_src');
const WRITE = process.argv.includes('--write');
const registry = JSON.parse(fs.readFileSync(path.join(SRC, 'views.json'), 'utf8'));
const keys = Object.keys(registry).filter((k) => !k.startsWith('_'));

/** 分组 → 该组第一页的 key（按 views.json 的登记顺序） */
const groupFirst = {};
for (const k of keys) {
  const g = registry[k].group;
  if (g && !groupFirst[g]) groupFirst[g] = k;
}

const CHEV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';

let changed = 0;
for (const key of keys) {
  if (key === 'chat') continue; // 对话页是已批准的基线，不动它的标记
  const file = path.join(SRC, 'views', `${key}.html`);
  if (!fs.existsSync(file)) continue;
  const src = fs.readFileSync(file, 'utf8');
  const m = src.match(/([ \t]*)<p class="crumb">[\s\S]*?<\/p>/);
  if (!m) { console.log(`[skip] ${key}：没有面包屑`); continue; }

  const indent = m[1];
  const group = registry[key].group;
  const title = registry[key].title;
  const first = groupFirst[group];
  const groupPart = first && first !== key
    ? `<a href="#/${first}">${group}</a>`
    : `<span>${group}</span>`;
  const block = `${indent}<p class="crumb">\n`
    + `${indent}  ${groupPart}\n`
    + `${indent}  ${CHEV}\n`
    + `${indent}  <span>${title}</span>\n`
    + `${indent}</p>`;

  if (src.includes(block)) { console.log(`[ok]   ${key}：已经是统一形态`); continue; }
  changed++;
  console.log(`[改]   ${key}：${group} › ${title}` + (first !== key ? `（分组段 → #/${first}）` : ''));
  if (WRITE) fs.writeFileSync(file, src.replace(/([ \t]*)<p class="crumb">[\s\S]*?<\/p>/, block), 'utf8');
}

console.log(`\n${changed} 个视图需要改。` + (WRITE ? ' 已写入。' : ' 这是干跑；加 --write 才写。'));
