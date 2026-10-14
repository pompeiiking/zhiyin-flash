/* =============================================================================
 * c2-hbu 一次性拆分脚本（已执行，保留供复核）
 * -----------------------------------------------------------------------------
 * 背景：c2-hbu 原来是"单页样张"（只有对话页），由 build.mjs 从
 *       directions/c-companion/index.html 换 <style> 层生成。
 *       现在要把它扩成"覆盖全部学生端界面"的多视图原型，需要：
 *         · 每个视图一个片段文件（写域互斥 → 可并行施工）
 *         · 一份共享外壳（导航 / 顶栏 / 演示台 / 移动底栏）
 *         · 一份共享行为脚本（路由 + 头像 + 三轴 + 各种交互）
 *       所以先把现有 index.html 拆到 _src/ 下，再改 build.mjs 从 _src/ 组装。
 *
 * 关键约束：**拆分必须是可逆的**。
 *   拆完立刻用新 build.mjs 重组一次，产物必须与拆分前的 index.html 逐字节相同。
 *   做不到这一点，后面 20 个视图的施工就没有安全网。
 *
 * 用法：node _tools/extract.mjs
 * ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
const SRC = path.join(DIR, 'index.html');
const OUT = path.join(DIR, '_src');

const html = fs.readFileSync(SRC, 'utf8');

function at(needle, from = 0) {
  const i = html.indexOf(needle, from);
  if (i < 0) throw new Error('找不到锚点：' + JSON.stringify(needle.slice(0, 60)));
  if (html.indexOf(needle, i + 1) >= 0) throw new Error('锚点不唯一：' + JSON.stringify(needle.slice(0, 60)));
  return i;
}

const iStyleOpen = at('<style>');
const iStyleClose = at('</style>');
const iChat = at('<div class="main__scroll" id="mainScroll">');
const iMainClose = at('  </main>');
const iScript = at('<script>');
const iScriptClose = at('</script>');

const pieces = {
  // <head> 里 <style> 之前的一切（含 doctype / html 属性 / meta / title）
  'shell/head.html': html.slice(0, iStyleOpen),
  // <style> 之后到主区内容之前：</head><body> + 品牌条 + .app + 导航 + 顶栏 + <main>
  'shell/body-a.html': html.slice(iStyleClose, iChat),
  // 当前唯一的视图：对话页主区
  'views/chat.html': html.slice(iChat, iMainClose),
  // </main> 之后到 <script> 之前：scrim + 移动底栏 + </div><!-- /app -->
  'shell/body-b.html': html.slice(iMainClose, iScript),
  // 行为脚本
  'app.js': html.slice(iScript + '<script>'.length, iScriptClose),
  // 收尾
  'shell/tail.html': html.slice(iScriptClose),
};

const styleInner = html.slice(iStyleOpen + '<style>'.length, iStyleClose);
const c2css = fs.readFileSync(path.join(HERE, 'c2.css'), 'utf8');
if (styleInner.trim() !== c2css.trim()) {
  throw new Error('index.html 的 <style> 与 _tools/c2.css 不一致 —— 拆分前先跑一次 build.mjs');
}
console.log('[ok] <style> 与 _tools/c2.css 一致（' + c2css.length + ' 字符）');

for (const [rel, content] of Object.entries(pieces)) {
  const p = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content, 'utf8');
  console.log(`[ok] ${rel.padEnd(22)} ${(Buffer.byteLength(content, 'utf8') / 1024).toFixed(1)} KB`);
}

/* 自检：按 build.mjs 的组装顺序拼回来，必须与 SRC 逐字节相同 */
const rebuilt =
  pieces['shell/head.html'] +
  '<style>' + styleInner + // body-a 以 </style> 开头
  pieces['shell/body-a.html'] +
  pieces['views/chat.html'] +
  pieces['shell/body-b.html'] +
  '<script>' +
  pieces['app.js'] +
  pieces['shell/tail.html'];
if (rebuilt !== html) {
  let i = 0;
  while (i < rebuilt.length && rebuilt[i] === html[i]) i++;
  throw new Error(
    '拆分自检失败：重建 ' + rebuilt.length + ' 字符 vs 原 ' + html.length +
    ' 字符，首个不同处在第 ' + i + ' 字符\n  重建: ' + JSON.stringify(rebuilt.slice(i - 40, i + 40)) +
    '\n  原稿: ' + JSON.stringify(html.slice(i - 40, i + 40)));
}
console.log('[ok] 分片按序拼回 = 原 index.html 逐字节相同（' + Buffer.byteLength(rebuilt, 'utf8') + ' 字节）');
