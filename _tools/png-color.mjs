// Decode an 8-bit RGB/RGBA non-interlaced PNG and report its dominant colour.
// Written because the browser could not read these assets through a canvas (CORS)
// and a data-URL round trip failed; Node + zlib needs no extra dependency.
//   node _tools/png-color.mjs <file.png>
import fs from "node:fs";
import zlib from "node:zlib";

const file = process.argv[2];
if (!file) {
  console.error("usage: node _tools/png-color.mjs <file.png>");
  process.exit(1);
}

const buf = fs.readFileSync(file);
if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error("not a PNG");

let pos = 8;
let width = 0, height = 0, bitDepth = 0, colorType = 0, interlace = 0;
const idat = [];
while (pos < buf.length) {
  const len = buf.readUInt32BE(pos);
  const type = buf.toString("ascii", pos + 4, pos + 8);
  const data = buf.subarray(pos + 8, pos + 8 + len);
  if (type === "IHDR") {
    width = data.readUInt32BE(0);
    height = data.readUInt32BE(4);
    bitDepth = data[8];
    colorType = data[9];
    interlace = data[12];
  } else if (type === "IDAT") idat.push(data);
  else if (type === "IEND") break;
  pos += 12 + len;
}

if (bitDepth !== 8) throw new Error(`unsupported bit depth ${bitDepth}`);
if (interlace !== 0) throw new Error("interlaced PNG unsupported");
const bpp = colorType === 6 ? 4 : colorType === 2 ? 3 : 0;
if (!bpp) throw new Error(`unsupported color type ${colorType}`);

const raw = zlib.inflateSync(Buffer.concat(idat));
const stride = width * bpp;
const out = Buffer.alloc(height * stride);

const paeth = (a, b, c) => {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
};

for (let y = 0; y < height; y++) {
  const filter = raw[y * (stride + 1)];
  const src = raw.subarray(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
  const cur = out.subarray(y * stride, (y + 1) * stride);
  const prev = y > 0 ? out.subarray((y - 1) * stride, y * stride) : null;
  for (let x = 0; x < stride; x++) {
    const a = x >= bpp ? cur[x - bpp] : 0;
    const b = prev ? prev[x] : 0;
    const c = prev && x >= bpp ? prev[x - bpp] : 0;
    let v = src[x];
    if (filter === 1) v += a;
    else if (filter === 2) v += b;
    else if (filter === 3) v += (a + b) >> 1;
    else if (filter === 4) v += paeth(a, b, c);
    cur[x] = v & 0xff;
  }
}

const counts = new Map();
let considered = 0;
for (let i = 0; i < out.length; i += bpp) {
  const r = out[i], g = out[i + 1], b = out[i + 2];
  const a = bpp === 4 ? out[i + 3] : 255;
  if (a < 128) continue;
  if (r > 240 && g > 240 && b > 240) continue; // skip white background
  considered++;
  const key = (r << 16) | (g << 8) | b;
  counts.set(key, (counts.get(key) ?? 0) + 1);
}

const top = [...counts.entries()].sort((x, y) => y[1] - x[1]).slice(0, 5);
console.log(JSON.stringify({
  file,
  size: `${width}x${height}`,
  colorType,
  nonBackgroundPixels: considered,
  top: top.map(([k, n]) => ({
    hex: "#" + k.toString(16).padStart(6, "0"),
    rgb: [(k >> 16) & 255, (k >> 8) & 255, k & 255],
    share: +((n / considered) * 100).toFixed(2),
  })),
}, null, 2));
