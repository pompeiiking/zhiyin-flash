/**
 * 精确还原工具：把 StudentView.vue 临时换成"改前"版本测一次，再换回"改后"版本，
 * 全程用 SHA256 校验，任一步失败都会尝试还原并在退出码上体现。
 *
 *   node _tools/p0-2-profile/roundtrip.mjs <改前文件> <改后文件> <目标文件> <命令...>
 *
 * 例：node _tools/p0-2-profile/roundtrip.mjs _tools/p0-2-profile/StudentView.vue.orig \
 *        _tools/p0-2-profile/StudentView.vue.after redesign-demo/src/views/StudentView.vue \
 *        node _tools/p0-2-profile/blocks.mjs before
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';

const [orig, after, target, ...cmd] = process.argv.slice(2);
if (!orig || !after || !target || !cmd.length) {
  console.error('usage: roundtrip.mjs <beforeFile> <afterFile> <targetFile> <cmd...>');
  process.exit(2);
}
const sha = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex').toUpperCase();
const wait = (ms) => { const t = Date.now() + ms; while (Date.now() < t) { /* spin */ } };

const hOrig = sha(orig);
const hAfter = sha(after);
const hTarget = sha(target);
console.log('before 文件 :', hOrig);
console.log('after  文件 :', hAfter);
console.log('当前 target :', hTarget, hTarget === hAfter ? '(= after，正常)' : hTarget === hOrig ? '(= before，已在改前态)' : '(!! 与两者都不同)');

let code = 1;
try {
  fs.writeFileSync(target, fs.readFileSync(orig));
  console.log('已切到【改前】', sha(target) === hOrig ? 'OK 校验通过' : '!! 校验失败');
  wait(3000); // 等 vite 重新编译 + 浏览器端拿到的就一定是新模块
  const r = spawnSync(cmd[0], cmd.slice(1), { stdio: 'inherit', shell: process.platform === 'win32' });
  code = r.status ?? 1;
} finally {
  fs.writeFileSync(target, fs.readFileSync(after));
  const h = sha(target);
  console.log('已还原【改后】', h === hAfter ? 'OK 校验通过 ' + h : '!! 还原校验失败 ' + h);
  if (h !== hAfter) code = 3;
}
process.exit(code);
