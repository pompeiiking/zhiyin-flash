import fs from 'node:fs';
const s = fs.readFileSync('_src/views/intel.html', 'utf8');
const lines = s.split('\n');
let line = 1;
const bad = [];
// 逐个标签扫：标签区内 `"` 的个数必须等于 2×`=` 的个数（即全部引号都是 ="...")
for (const m of s.matchAll(/<[a-zA-Z][^>]*>/g)) {
  const tag = m[0];
  const start = m.index;
  line = s.slice(0, start).split('\n').length;
  const eq = (tag.match(/="/g) || []).length;
  const q = (tag.match(/"/g) || []).length;
  if (q !== eq * 2) {
    bad.push({ line, q, eq, tag: tag.slice(0, 180) });
  }
}
console.log('引号数不自洽的标签：' + bad.length + ' 个');
for (const b of bad) console.log('  line ' + b.line + '  "×' + b.q + '  ="×' + b.eq + '\n    ' + b.tag + '\n');
