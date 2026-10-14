// 取值辅助：算候选颜色的 WCAG 对比度，用来挑令牌数值（不参与交付度量）。
const srgb = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const lum = (hex) => {
  const h = hex.replace('#', '');
  return 0.2126 * srgb(parseInt(h.slice(0, 2), 16)) + 0.7152 * srgb(parseInt(h.slice(2, 4), 16)) + 0.0722 * srgb(parseInt(h.slice(4, 6), 16));
};
export const cr = (a, b) => { const l1 = lum(a), l2 = lum(b); const hi = Math.max(l1, l2), lo = Math.min(l1, l2); return (hi + 0.05) / (lo + 0.05); };

const FLOOR = '#e8eaef';   // 候选 L0 页底
const L2 = '#f0f1f4';      // 候选 L2 局部面
const PAPER = '#ffffff';
const DARKBG = '#1b1b1d';

const rows = [
  ['L0 页底候选 → 纸面 #fff', ['#f7f6f6', '#f0f1f4', '#eceef2', '#ebedf2', '#e8eaef', '#e6e8ee', '#e4e7ed']],
  ['L2 候选 → 纸面 #fff', ['#fafafa', '#f5f6f7', '#f2f3f6', '#f0f1f4', '#eef0f3', '#ebedf2']],
  ['发丝线候选 → 纸面 #fff', ['#e1e5ee', '#d8dee8', '#d4dae4', '#d0d6e0', '#ccd3de', '#c9d1dd', '#c8cfd9']],
  ['强描边候选 → 纸面 #fff', ['#cfd3d6', '#c3cbd7', '#b9c1cc', '#b0b9c7', '#adb6c3', '#a9b2bf', '#a2a4a6']],
  ['控件边候选 → 纸面 #fff', ['#a2a4a6', '#9aa4b1', '#94a0ae', '#8f959e', '#8a9099']],
];
for (const [label, hexes] of rows) {
  console.log(`--- ${label}`);
  for (const h of hexes) console.log(`  ${h}  on#fff=${cr(PAPER, h).toFixed(3)}  on${FLOOR}=${cr(FLOOR, h).toFixed(3)}  on${L2}=${cr(L2, h).toFixed(3)}`);
}
console.log('\n--- 组合校验（结构线压在页底必须也看得见）');
console.log('  发丝线 #ccd3de on 页底 =', cr(FLOOR, '#ccd3de').toFixed(3));
console.log('  强描边 #adb6c3 on 页底 =', cr(FLOOR, '#adb6c3').toFixed(3));
console.log('  控件边 #8f959e on 页底 =', cr(FLOOR, '#8f959e').toFixed(3));
console.log('\n--- 分层：三层之间的比值');
console.log('  0 页底 → 1 纸面  =', cr(FLOOR, PAPER).toFixed(3));
console.log('  0 页底 → 2 局部面 =', cr(FLOOR, L2).toFixed(3));
console.log('  2 局部面 → 1 纸面 =', cr(L2, PAPER).toFixed(3));
console.log('  交互面 #ebedf2 → 纸面 =', cr('#ebedf2', PAPER).toFixed(3));
console.log('  交互面 #ebedf2 → 局部面 =', cr('#ebedf2', L2).toFixed(3));
console.log('\n--- check-contrast.mjs 的必过项（阈值 4.5:1）复算');
const pairs = [
  ['c-text #1e232c / c-surface', '#1e232c', PAPER], ['c-text / c-bg', '#1e232c', FLOOR],
  ['c-text-2 #4b5157 / c-surface', '#4b5157', PAPER], ['c-text-2 / c-bg', '#4b5157', FLOOR],
  ['c-text-3 #61666b / c-surface', '#61666b', PAPER], ['c-text-3 / c-bg', '#61666b', FLOOR],
  ['c-text-3 / c-surface-2', '#61666b', L2], ['c-text-3 / c-surface-3', '#61666b', '#ebedf2'],
  ['c-primary #0058a7 / c-surface', '#0058a7', PAPER], ['c-primary / c-bg', '#0058a7', FLOOR],
  ['c-primary / c-primary-weak', '#0058a7', '#eef5fc'],
];
for (const [n, a, b] of pairs) { const v = cr(a, b); console.log(`  ${v >= 4.5 ? '过  ' : '破线'} ${v.toFixed(2).padStart(5)}  ${n}`); }
console.log('\n--- 深色主题下的新令牌');
for (const h of ['#6f7176', '#7a7c81', '#8f9196', '#5c5e63']) console.log(`  ${h} on ${DARKBG} = ${cr(DARKBG, h).toFixed(3)}`);
