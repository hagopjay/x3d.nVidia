// Render X3D scenes with X_ITE in headless Chrome and save PNG frames.
//
//   node tools/xite_render.mjs --xite <dir with x_ite.min.js> --root <scene dir> \
//        --out <png dir> --size 512 scene1.x3d scene2.x3d ...
//
// Prints one JSON line per scene: {scene, png, ms, rendererInfo, errors}.
// Uses Playwright with an existing Chrome (CHROME env, default /usr/bin/google-chrome).
// On Colab with x3dlab.graphics.enable() pass --gpu to use ANGLE/Vulkan.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
// Resolve playwright from the working directory (where node_modules lives),
// not from this script's folder.
const { chromium } = createRequire(path.join(process.cwd(), "noop.js"))("playwright");

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args.splice(i, 2)[1] : d; };
const flag = (k) => { const i = args.indexOf(k); if (i >= 0) { args.splice(i, 1); return true; } return false; };
const xite = path.resolve(opt("--xite", "node_modules/x_ite/dist"));
const root = path.resolve(opt("--root", "."));
const out = path.resolve(opt("--out", "frames"));
const size = Number(opt("--size", "512"));
const settle = Number(opt("--settle", "1500"));
const gpu = flag("--gpu");
const viewpoints = (opt("--viewpoints", "") || "").split(",").filter(Boolean);
fs.mkdirSync(out, { recursive: true });

const types = { ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".x3d": "model/x3d+xml", ".ply": "application/octet-stream", ".html": "text/html", ".png": "image/png" };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const file = u.startsWith("/x_ite/") ? path.join(xite, u.slice(7)) : path.join(root, u);
  fs.readFile(file, (err, buf) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
    res.end(buf);
  });
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

const flags = gpu
  ? ["--use-angle=vulkan", "--enable-features=Vulkan", "--disable-vulkan-surface", "--ignore-gpu-blocklist"]
  : ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"];
const browser = await chromium.launch({ executablePath: process.env.CHROME || "/usr/bin/google-chrome", args: flags });

for (const scene of args) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const html = `<!doctype html><html><head><script src="/x_ite/x_ite.min.js"></script>
<style>html,body{margin:0;background:#000}x3d-canvas{width:${size}px;height:${size}px;display:block}</style></head>
<body><x3d-canvas id="c" contextMenu="false" notifications="false" timings="false" splashScreen="false" antialiased="false"></x3d-canvas></body></html>`;
  await page.route("**/index.html", (r) => r.fulfill({ contentType: "text/html", body: html }));
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  const t0 = Date.now();
  const info = await page.evaluate(async (url) => {
    const canvas = document.getElementById("c");
    const browser = canvas.browser;
    await browser.loadURL(new X3D.MFString(url));
    const gl = browser.getContext();
    const dbg = gl.getExtension("WEBGL_debug_renderer_info");
    return { renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
             version: X3D.getBrowser ? browser.version : null };
  }, `/${scene}`);
  for (const vp of viewpoints.length ? viewpoints : [null]) {
    if (vp) await page.evaluate((name) => {
      document.getElementById("c").browser.currentScene.getNamedNode(name).set_bind = true;
    }, vp);
    await page.waitForTimeout(settle);
    const stem = path.basename(scene).replace(/\.x3d$/, "") + (vp ? `-${vp}` : "");
    const png = path.join(out, `${stem}.png`);
    await page.locator("x3d-canvas").screenshot({ path: png });
    console.log(JSON.stringify({ scene, viewpoint: vp, png, ms: Date.now() - t0, rendererInfo: info, errors }));
  }
  await page.close();
}
await browser.close();
server.close();
