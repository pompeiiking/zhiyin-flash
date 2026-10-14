// Independently measure the dominant colour of an image, in-browser (canvas), so no
// image library is needed. Reports the modal non-background colour and its share.
//   node _tools/sample-color.mjs <imageUrl> [--ignore-white]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const [, , imageUrl] = process.argv;
if (!imageUrl) {
  console.error("usage: node _tools/sample-color.mjs <imageUrl|localPath>");
  process.exit(1);
}

// A remote image cannot be read through a canvas (CORS taints / blocks it), so a
// local path is inlined as a data URL — the pixels are then same-origin and readable.
let src = imageUrl;
if (!/^https?:/.test(imageUrl)) {
  const ext = imageUrl.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg";
  src = `data:${ext};base64,${fs.readFileSync(imageUrl).toString("base64")}`;
}

const browser = await chromium.launch();
const page = await browser.newPage();

// Load the image into the page, then read its pixels through a canvas.
const result = await page.evaluate(async (src) => {
  const img = new Image();
  img.crossOrigin = "anonymous";
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("image failed to load"));
    img.src = src;
  });
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);

  const counts = new Map();
  let total = 0;
  for (let i = 0; i < data.length; i += 4) {
    const [r, g, b, a] = [data[i], data[i + 1], data[i + 2], data[i + 3]];
    if (a < 128) continue;
    // Skip near-white / near-transparent background.
    if (r > 240 && g > 240 && b > 240) continue;
    total++;
    const key = ((r << 16) | (g << 8) | b).toString(16).padStart(6, "0");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const top = [...counts.entries()].sort((x, y) => y[1] - x[1]).slice(0, 5);
  return {
    width: img.naturalWidth,
    height: img.naturalHeight,
    nonBackgroundPixels: total,
    top: top.map(([hex, n]) => ({
      hex: "#" + hex,
      share: +(n / total * 100).toFixed(2),
      rgb: [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)],
    })),
  };
}, imageUrl);

console.log(JSON.stringify(result, null, 2));
await browser.close();
