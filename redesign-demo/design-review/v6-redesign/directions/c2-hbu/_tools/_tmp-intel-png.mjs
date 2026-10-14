import fs from 'node:fs';
for (const f of ['_shots/intel/1280-intel-blue-light-normal.png', '_shots/intel/390-intel-blue-light-normal.png']) {
  const b = fs.readFileSync(f);
  console.log(f + '  ' + b.readUInt32BE(16) + '×' + b.readUInt32BE(20));
}
console.log('\nshot-views.mjs args:');
const s = fs.readFileSync('_tools/shot-views.mjs', 'utf8');
for (const m of s.matchAll(/arg\('([^']+)'/g)) console.log('  --' + m[1]);
