// Renders one 256 x 256 PNG per X3D scene with X_ITE in headless Chromium, for SimReady SR.002.
//   node thumbnails.mjs X_ITE_DIST_DIR SCENES_DIR OUT_DIR [settle_ms]
// The picture is of the scene as authored, from its first Viewpoint, a moment after load. It is rendered at
// 1024 x 1024, cropped to a square around everything that differs from the corner colour (the authored Viewpoints of
// single pieces frame a whole board and leave the piece a few pixels wide), and scaled to 256. Prints one JSON line per
// scene (file, png, bytes, console errors) and a last line with the X_ITE and Chromium versions.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const [XITE, SCENES, OUT, SETTLE = '2500'] = process.argv.slice(2);
const TYPES = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.x3d': 'model/x3d+xml', '.html': 'text/html',
  '.css': 'text/css', '.png': 'image/png', '.wasm': 'application/wasm', '.json': 'application/json', '.woff2': 'font/woff2' };
const PAGE = `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#000}x3d-canvas{display:block;width:1024px;height:1024px}</style>
<script src="/x_ite/x_ite.min.js"></script><x3d-canvas id="c" splashScreen="false" notifications="false" timings="false" contextMenu="false"></x3d-canvas>`;
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (u === '/page.html') { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(PAGE); }
  const root = u.startsWith('/x_ite/') ? [XITE, u.slice(7)] : u.startsWith('/scenes/') ? [SCENES, u.slice(8)] : null;
  const f = root && path.resolve(root[0], root[1]);
  if (!f || !f.startsWith(path.resolve(root[0])) || !fs.existsSync(f) || !fs.statSync(f).isFile()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const walk = d => fs.readdirSync(d, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(d, e.name)) : e.name.endsWith('.x3d') ? [path.join(d, e.name)] : []);
const browser = await chromium.launch();
let version = null;
for (const file of walk(SCENES).sort()) {
  const rel = path.relative(SCENES, file);
  const page = await browser.newPage({ viewport: { width: 1024, height: 1024 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  await page.goto(base + '/page.html');
  await page.waitForFunction(() => window.X3D && document.getElementById('c').browser);
  await page.evaluate(async url => {
    const b = document.getElementById('c').browser;
    await b.loadURL(new X3D.MFString(url));
  }, '/scenes/' + rel.split(path.sep).map(encodeURIComponent).join('/'));
  await page.waitForTimeout(Number(SETTLE));
  version ??= await page.evaluate(() => document.getElementById('c').browser.version);
  const big = await page.screenshot({ clip: { x: 0, y: 0, width: 1024, height: 1024 }, timeout: 120000 });
  const out = await page.evaluate(async b64 => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const n = img.width, c = Object.assign(document.createElement('canvas'), { width: n, height: n }), g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, n, n).data, bg = [d[0], d[1], d[2]];
    let x0 = n, y0 = n, x1 = -1, y1 = -1, px = 0;
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      const i = 4 * (y * n + x);
      if (Math.abs(d[i] - bg[0]) + Math.abs(d[i + 1] - bg[1]) + Math.abs(d[i + 2] - bg[2]) > 24) { px++; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    }
    let side = n, cx = n / 2, cy = n / 2;
    if (px) { side = Math.min(n, Math.max(64, Math.ceil(Math.max(x1 - x0, y1 - y0) * 1.25))); cx = (x0 + x1) / 2; cy = (y0 + y1) / 2; }
    const sx = Math.max(0, Math.min(n - side, Math.round(cx - side / 2))), sy = Math.max(0, Math.min(n - side, Math.round(cy - side / 2)));
    const t = Object.assign(document.createElement('canvas'), { width: 256, height: 256 }), h = t.getContext('2d');
    h.imageSmoothingQuality = 'high'; h.drawImage(c, sx, sy, side, side, 0, 0, 256, 256);
    const e = h.getImageData(0, 0, 256, 256).data; let drawn = 0;
    for (let i = 0; i < e.length; i += 4) if (Math.abs(e[i] - bg[0]) + Math.abs(e[i + 1] - bg[1]) + Math.abs(e[i + 2] - bg[2]) > 24) drawn++;
    return { png: t.toDataURL('image/png').split(',')[1], crop: [sx, sy, side], drawn };
  }, big.toString('base64'));
  const png = path.join(OUT, rel.replace(/\.x3d$/, '.png'));
  fs.mkdirSync(path.dirname(png), { recursive: true });
  fs.writeFileSync(png, Buffer.from(out.png, 'base64'));
  console.log(JSON.stringify({ file: rel, png: path.relative(OUT, png), bytes: fs.statSync(png).size, crop_of_1024: out.crop, drawn_pixels_of_65536: out.drawn, console_errors: errors }));
  await page.close();
}
console.log(JSON.stringify({ x_ite: version, chromium: browser.version(), settle_ms: Number(SETTLE), size: '256x256' }));
await browser.close();
server.close();
