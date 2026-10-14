/* =============================================================================
 * c2-hbu 本地静态服务（零依赖）
 * -----------------------------------------------------------------------------
 * 用途：样张本来是设计成"双击 index.html 直接开"的（单文件、离线、无外部依赖）。
 *      但如果遇到「双击不开 / 编辑器或预览器打不开 / file:// 被策略拦」，
 *      起一个本地 http 服务是最可靠的兜底路径。
 *
 * 用法：node _tools/serve.mjs [端口]        # 默认 5188
 *      然后浏览器打开 http://127.0.0.1:5188/index.html
 *      hash 路由照常：#/profile、#/report、#/spec …
 *
 * 说明：只读地服务本目录（directions/c2-hbu），不做目录穿越，不写任何文件。
 * ========================================================================== */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIR = path.resolve(HERE, '..');
const PORT = Number(process.argv[2] || 5188);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8'
};

http
  .createServer((req, res) => {
    let rel = decodeURIComponent((req.url || '/').split('#')[0].split('?')[0]);
    if (rel === '/' || rel === '') rel = '/index.html';
    const file = path.resolve(DIR, '.' + rel);
    if (!file.startsWith(DIR + path.sep) && file !== path.join(DIR, 'index.html')) {
      res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('403 只能读本目录内的文件');
      return;
    }
    fs.readFile(file, (err, buf) => {
      if (err) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end('404 ' + rel);
        return;
      }
      res.writeHead(200, {
        'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
        'Cache-Control': 'no-store'
      });
      res.end(buf);
    });
  })
  .listen(PORT, '127.0.0.1', () => {
    console.log('[ok] http://127.0.0.1:' + PORT + '/index.html');
    console.log('[ok] 直接进某个界面：http://127.0.0.1:' + PORT + '/index.html#/profile');
    console.log('[ok] 服务目录：' + DIR);
  });
