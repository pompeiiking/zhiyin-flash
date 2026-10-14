import fs from 'node:fs';
const s = fs.readFileSync('_src/views/intel.html', 'utf8');
for (const key of ['fit', 'when', 'kind', 'from']) {
  const set = new Map();
  for (const m of s.matchAll(new RegExp('data-' + key + '="([^"]+)"', 'g'))) set.set(m[1], (set.get(m[1]) || 0) + 1);
  console.log('data-' + key + ': ' + [...set.entries()].map(([k, v]) => k + ' ×' + v).join('  |  '));
}
console.log('\ndata-int-* hooks:');
for (const m of new Set([...s.matchAll(/data-int-[a-z]+/g)].map((x) => x[0]))) console.log('  ' + m);
console.log('\nids:');
console.log('  ' + [...s.matchAll(/id="([^"]+)"/g)].map((x) => x[1]).join(', '));
console.log('\nzoom layer counts: z--sum=' + (s.match(/z--sum/g) || []).length + ' z--mid=' + (s.match(/z--mid/g) || []).length + ' z--full=' + (s.match(/z--full/g) || []).length);
