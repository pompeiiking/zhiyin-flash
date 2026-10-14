// Read files out of an Electron .asar archive.
//   node _tools/asar.mjs <archive> <pathRegex> [--out <dir>] [--dump <bytes>]
import fs from "node:fs";

const [, , archivePath, pattern = ".", ...rest] = process.argv;
const val = (flag) => {
  const i = rest.indexOf(flag);
  return i >= 0 ? rest[i + 1] : null;
};
const outDir = val("--out");
const dumpLimit = Number(val("--dump") ?? 0);
const re = new RegExp(pattern, "i");

const fd = fs.openSync(archivePath, "r");
const head = Buffer.alloc(16);
fs.readSync(fd, head, 0, 16, 0);

let header, jsonSize, jsonStart;
for (const start of [16, 8]) {
  for (const field of [12, 8, 4]) {
    const size = head.readUInt32LE(field);
    if (!size || size > 64 * 1024 * 1024) continue;
    const buf = Buffer.alloc(size);
    fs.readSync(fd, buf, 0, size, start);
    const text = buf.toString("utf8").trim();
    if (!text.startsWith("{")) continue;
    try { header = JSON.parse(text); jsonSize = size; jsonStart = start; break; } catch {}
  }
  if (header) break;
}
if (!header) { console.error("header JSON not found"); process.exit(1); }
const dataOffset = jsonStart + Math.ceil(jsonSize / 4) * 4;

const all = [];
(function walk(node, prefix) {
  if (!node.files) return;
  for (const [name, child] of Object.entries(node.files)) {
    const p = prefix ? `${prefix}/${name}` : name;
    if (child.files) walk(child, p);
    else all.push({ path: p, size: child.size, offset: child.offset, unpacked: !!child.unpacked });
  }
})(header, "");

const hits = all.filter((f) => re.test(f.path));
console.error(`archive files: ${all.length}, matches: ${hits.length}`);
for (const h of hits) console.error(`  ${h.path} (${h.size})${h.unpacked ? " [unpacked]" : ""}`);

if (outDir) {
  for (const h of hits) {
    if (h.unpacked) continue;
    const buf = Buffer.alloc(h.size);
    fs.readSync(fd, buf, 0, h.size, dataOffset + Number(h.offset));
    const dest = `${outDir}/${h.path.replace(/^dsh\/node_modules\//, "").replace(/\//g, "__")}`;
    fs.writeFileSync(dest, buf);
    console.log(`wrote ${dest}`);
  }
}

for (const h of hits) {
  if (h.unpacked || !dumpLimit) continue;
  const len = Math.min(h.size, dumpLimit);
  const buf = Buffer.alloc(len);
  fs.readSync(fd, buf, 0, len, dataOffset + Number(h.offset));
  console.log(`\n===== ${h.path} (first ${len}/${h.size} bytes) =====`);
  console.log(buf.toString("utf8"));
}
fs.closeSync(fd);
