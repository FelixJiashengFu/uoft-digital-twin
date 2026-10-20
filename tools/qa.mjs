// Automated browser checks for the built page in headless Chrome: language default, zoom smoothness,
// pan / rotate / pinch / fly-to, and console errors. Writes qa/report.json and qa/*.png.
// Usage: deno run -A --unsafe-proto tools/qa.mjs [url]   (without a url it serves dist/ itself)
import { chromium } from 'playwright-core';
import { createServer } from 'node:http';
import { mkdirSync, writeFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'qa');
mkdirSync(OUT, { recursive: true });

let server = null;
let URL_ = process.argv[2];
if (!URL_) {
  const DIST = join(ROOT, 'dist');
  server = createServer(async (req, res) => {
    const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^([/\\])+/, '');
    const file = join(DIST, path === '' ? 'index.html' : path);
    if (!file.startsWith(DIST)) { res.writeHead(403).end(); return; }
    try {
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': extname(file) === '.html' ? 'text/html; charset=utf-8' : 'application/octet-stream' }).end(body);
    } catch {
      res.writeHead(404).end('not found');
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  URL_ = `http://127.0.0.1:${server.address().port}/`;
}
const report = { url: URL_, when: new Date().toISOString(), checks: [], errors: [], failed: [] };
const check = (name, ok, detail) => { report.checks.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail !== undefined ? '  ' + JSON.stringify(detail) : ''}`); };

// Installed Chrome renders headless on the real GPU; set CHROME to use another browser binary.
const browser = await chromium.launch({
  executablePath: process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
  args: ['--ignore-gpu-blocklist'],
});

async function open(url, ctxOpts) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  // the browser's own /favicon.ico probe is not the page's error (the page declares no icon)
  page.on('console', (m) => { if (m.type() === 'error' && !/\/favicon\.ico$/.test(m.location().url || '')) report.errors.push(`${m.text()} ${m.location().url || ''}`.trim()); });
  page.on('pageerror', (e) => report.errors.push(String(e)));
  page.on('response', (r) => { if (r.status() >= 400) report.failed.push(`${r.status()} ${r.url()}`); });
  await page.goto(url, { waitUntil: 'load' });
  await waitReady(page);
  return { ctx, page };
}
const waitReady = (page) => page.waitForFunction(() => window.twin && window.twin.frames > 5, null, { timeout: 60000 });
const settle = (page, ms) => page.waitForTimeout(ms);
// the camera follows pointer input on the next frame
const nextFrame = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const langState = (page) => page.evaluate(() => ({
  html: document.documentElement.lang, title: document.title, brand: document.querySelector('.brand h1').textContent,
  btn: document.querySelector('#langBtn').textContent, stored: Object.keys(localStorage),
}));
const view = (page, v, s = 0.3) => page.evaluate(([v, s]) => window.twin.controls.flyTo(v, s), [v, s]);
const camState = (page) => page.evaluate(() => {
  const { controls: c, camera } = window.twin;
  return { dist: c.dist, yaw: c.yaw, pitch: c.pitch, target: c.target.toArray(), cam: camera.position.toArray() };
});
// the scene point under a screen position, and where a scene point is on screen
const surfaceUnder = (page, x, y) => page.evaluate(([x, y]) => {
  const { camera, castRay } = window.twin;
  const rect = document.querySelector('#scene').getBoundingClientRect();
  const V = camera.position.constructor;
  const dir = new V(((x - rect.left) / rect.width) * 2 - 1, -((y - rect.top) / rect.height) * 2 + 1, 0.5).unproject(camera).sub(camera.position).normalize();
  const hit = castRay(camera.position.clone(), dir);
  return hit ? hit.point.toArray() : null;
}, [x, y]);
const screenOf = (page, p) => page.evaluate((p) => {
  const { camera } = window.twin;
  const rect = document.querySelector('#scene').getBoundingClientRect();
  const q = new camera.position.constructor(...p).project(camera);
  return [((q.x + 1) / 2) * rect.width + rect.left, ((1 - q.y) / 2) * rect.height + rect.top];
}, p);

// remember where each fly-to should leave the camera, then compare with where it ended up
const recordFlights = (page) => page.evaluate(() => {
  const c = window.twin.controls, fly = c.flyTo.bind(c);
  c.flyTo = (v, s) => {
    const f = new c.target.constructor(Math.sin(v.yaw) * Math.cos(v.pitch), -Math.sin(v.pitch), -Math.cos(v.yaw) * Math.cos(v.pitch));
    window.__flyCam = v.target.clone().addScaledVector(f, -v.dist).toArray();
    return fly(v, s);
  };
});
const flightEnd = (page) => page.evaluate(() => {
  const { controls, camera } = window.twin;
  const [x, y, z] = window.__flyCam;
  return { panel: document.querySelector('#panelBody').textContent.includes('Robarts Library'), moving: !!controls.anim, offM: +Math.hypot(camera.position.x - x, camera.position.y - y, camera.position.z - z).toFixed(3) };
});

// one wheel notch at (x, y), sampled every frame for a second
const notch = (page, x, y, deltaY) => page.evaluate(([x, y, deltaY]) => new Promise((res) => {
  const { controls, camera, castRay } = window.twin;
  const canvas = document.querySelector('#scene');
  const rect = canvas.getBoundingClientRect();
  const V = camera.position.constructor;
  const dir = new V(((x - rect.left) / rect.width) * 2 - 1, -((y - rect.top) / rect.height) * 2 + 1, 0.5).unproject(camera).sub(camera.position).normalize();
  const anchor = castRay(camera.position.clone(), dir).point.clone();
  const t0 = performance.now(), d0 = controls.dist, samples = [];
  canvas.dispatchEvent(new WheelEvent('wheel', { deltaY, deltaMode: 0, clientX: x, clientY: y, bubbles: true, cancelable: true }));
  const tick = (now) => {
    const p = anchor.clone().project(camera);
    samples.push({ t: now - t0, dist: controls.dist, px: ((p.x + 1) / 2) * rect.width + rect.left, py: ((1 - p.y) / 2) * rect.height + rect.top });
    if (samples.length < 60) requestAnimationFrame(tick); else res({ d0, samples });
  };
  requestAnimationFrame(tick);
}), [x, y, deltaY]);
function zoomStats(z, x, y) {
  const ds = [z.d0, ...z.samples.map((s) => s.dist)];
  const steps = ds.slice(1).map((d, i) => Math.abs(Math.log(d / ds[i]))); // includes the first frame after the event
  const total = Math.abs(Math.log(ds[ds.length - 1] / ds[0]));
  let acc = 0, ms95 = null;
  steps.forEach((s, i) => { acc += s; if (ms95 === null && acc >= 0.95 * total) ms95 = Math.round(z.samples[i].t); });
  const dir = Math.sign(ds[ds.length - 1] - ds[0]);
  return {
    from: Math.round(ds[0]), to: Math.round(ds[ds.length - 1]), factor: +(ds[0] / ds[ds.length - 1]).toFixed(3),
    framesMoving: steps.filter((s) => s > 1e-4).length, biggestFrameShare: +(Math.max(...steps) / total).toFixed(3), ms95,
    driftPx: +Math.max(...z.samples.map((s) => Math.hypot(s.px - x, s.py - y))).toFixed(2),
    monotonic: ds.slice(1).every((d, i) => (d - ds[i]) * dir >= -1e-6),
    frameShares: steps.slice(0, 24).map((s) => +(s / total).toFixed(3)),
  };
}

// ---------------------------------------------------------------- desktop, Chinese browser
{
  const { ctx, page } = await open(URL_, { viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const en = await langState(page);
  report.renderer = await page.evaluate(() => {
    const g = document.querySelector('#scene').getContext('webgl2') || document.querySelector('#scene').getContext('webgl');
    const ext = g && g.getExtension('WEBGL_debug_renderer_info');
    return ext ? g.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown';
  });
  check('opens in English for a zh-CN browser', en.html === 'en' && en.title === 'U of T Digital Twin' && en.brand === 'U of T Digital Twin' && en.btn === '中文', en);
  await settle(page, 3500); // intro flight
  await page.screenshot({ path: join(OUT, 'desktop-en.png') });

  // --- zoom smoothness: one wheel notch, sampled every frame
  const [cx, cy] = [620, 470];
  await view(page, { dist: 900, pitch: 0.75 });
  await settle(page, 900);
  const z = zoomStats(await notch(page, cx, cy, -100), cx, cy);
  report.zoom = z;
  check('one wheel notch zooms in about 1.3x', z.factor > 1.25 && z.factor < 1.35, { from: z.from, to: z.to, factor: z.factor });
  check('the notch is spread over many frames, none above 15% of it', z.framesMoving >= 12 && z.biggestFrameShare < 0.15, { framesMoving: z.framesMoving, biggestFrameShare: z.biggestFrameShare, ms95: z.ms95 });
  check('95% of the notch is done within about 0.3 s', z.ms95 > 200 && z.ms95 < 450, { ms95: z.ms95 });
  check('the point under the cursor stays put while zooming', z.driftPx < 3, { driftPx: z.driftPx });
  check('zoom eases monotonically', z.monotonic);

  // --- a fast spin of the wheel: six notches on six consecutive frames
  await view(page, { dist: 900, pitch: 0.75 });
  await settle(page, 900);
  const burst = await page.evaluate(([x, y]) => new Promise((res) => {
    const { controls } = window.twin;
    const canvas = document.querySelector('#scene');
    const out = [controls.dist];
    let n = 0;
    const tick = () => {
      if (n < 6) canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, clientX: x, clientY: y, bubbles: true, cancelable: true }));
      out.push(controls.dist);
      if (++n < 80) requestAnimationFrame(tick); else res(out);
    };
    requestAnimationFrame(tick);
  }), [cx, cy]);
  const bsteps = burst.slice(1).map((d, i) => Math.abs(Math.log(d / burst[i])));
  const btotal = Math.abs(Math.log(burst[burst.length - 1] / burst[0]));
  report.burst = { from: Math.round(burst[0]), to: Math.round(burst[burst.length - 1]), biggestFrameShare: +(Math.max(...bsteps) / btotal).toFixed(3) };
  check('burst of six notches: no frame above 15% of the zoom', report.burst.biggestFrameShare < 0.15, report.burst);

  // --- left drag pans and keeps the grabbed point under the pointer
  await view(page, { dist: 900, pitch: 0.75 });
  await settle(page, 900);
  const grabbed = await surfaceUnder(page, 520, 420);
  await page.mouse.move(520, 420);
  await page.mouse.down();
  await page.mouse.move(700, 560, { steps: 12 });
  await nextFrame(page);
  const grabAt = await screenOf(page, grabbed);
  await page.mouse.up();
  const panErr = Math.hypot(grabAt[0] - 700, grabAt[1] - 560);
  check('left drag pans with the grabbed point under the pointer', panErr < 3, { errorPx: +panErr.toFixed(2) });
  await settle(page, 1200);

  // --- right drag rotates, middle drag zooms
  const r0 = await camState(page);
  await page.mouse.move(620, 470);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(740, 470, { steps: 12 });
  const r1 = await camState(page);
  await page.mouse.up({ button: 'right' });
  const dyaw = Math.atan2(Math.sin(r1.yaw - r0.yaw), Math.cos(r1.yaw - r0.yaw));
  check('right drag rotates the view', Math.abs(dyaw - 120 * 0.0055) < 0.05, { dyaw: +dyaw.toFixed(3) });
  await settle(page, 1200);
  const m0 = await camState(page);
  await page.mouse.move(620, 420);
  await page.mouse.down({ button: 'middle' });
  await page.mouse.move(620, 520, { steps: 10 });
  const m1 = await camState(page);
  await page.mouse.up({ button: 'middle' });
  check('middle drag down zooms out', m1.dist / m0.dist > 1.5 && m1.dist / m0.dist < 1.8, { ratio: +(m1.dist / m0.dist).toFixed(3) });
  await settle(page, 800);

  // --- search and fly to a building, then turn north up with the compass
  await recordFlights(page);
  await page.fill('#q', 'Robarts');
  await page.keyboard.press('Enter');
  await settle(page, 2200);
  const fly = await flightEnd(page);
  check('search result flies to Robarts Library', fly.panel && !fly.moving && fly.offM < 0.5, fly);
  await page.screenshot({ path: join(OUT, 'desktop-robarts.png') });
  await page.click('#compass');
  await settle(page, 1300);
  const north = await camState(page);
  check('compass turns the view north up', Math.abs(north.yaw) < 0.01, { yaw: +north.yaw.toFixed(4) });

  // --- language switch is not remembered
  await page.click('#langBtn');
  await settle(page, 400);
  const zh = await langState(page);
  check('switches to Chinese', zh.html === 'zh-CN' && zh.title === '多伦多大学数字孪生' && zh.brand === '多伦多大学数字孪生' && zh.btn === 'EN', zh);
  await page.screenshot({ path: join(OUT, 'desktop-zh.png') });
  check('the language choice is not stored', zh.stored.length === 0, zh.stored);
  await page.reload({ waitUntil: 'load' });
  await waitReady(page);
  const again = await langState(page);
  check('opens in English again after a reload', again.html === 'en' && again.brand === 'U of T Digital Twin', again);
  await ctx.close();
}

// ---------------------------------------------------------------- ?lang=zh
{
  const { ctx, page } = await open(new URL('?lang=zh', URL_).href, { viewport: { width: 1280, height: 800 }, locale: 'en-US' });
  const s = await langState(page);
  check('?lang=zh opens in Chinese', s.html === 'zh-CN' && s.brand === '多伦多大学数字孪生' && s.btn === 'EN', s);
  await ctx.close();
}

// ---------------------------------------------------------------- phone: layout and a two-finger pinch
{
  const { ctx, page } = await open(URL_, { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'zh-CN' });
  await settle(page, 3500);
  await page.screenshot({ path: join(OUT, 'phone.png') });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth);
  check('phone layout has no horizontal overflow', !overflow);
  await view(page, { dist: 900, pitch: 0.75 });
  await settle(page, 900);
  const [mx, my] = [195, 330];
  const mid = await surfaceUnder(page, mx, my);
  const p0 = await camState(page);
  const cdp = await ctx.newCDPSession(page);
  const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
  await touch('touchStart', [[mx - 50, my], [mx + 50, my]]);
  for (let i = 1; i <= 10; i++) { await touch('touchMove', [[mx - 50 - 5 * i, my], [mx + 50 + 5 * i, my]]); await settle(page, 16); }
  await nextFrame(page);
  const p1 = await camState(page);
  const midAt = await screenOf(page, mid);
  await touch('touchEnd', []);
  const pinchErr = Math.hypot(midAt[0] - mx, midAt[1] - my);
  check('two-finger pinch zooms about the point between the fingers', Math.abs(p1.dist / p0.dist - 0.5) < 0.03 && pinchErr < 3, { ratio: +(p1.dist / p0.dist).toFixed(3), errorPx: +pinchErr.toFixed(2) });
  await ctx.close();
}

await browser.close();
if (server) server.close();
check('no console errors', report.errors.length === 0, report.errors.slice(0, 5));
writeFileSync(join(OUT, 'report.json'), JSON.stringify(report, null, 2));
const failed = report.checks.filter((c) => !c.ok).length;
console.log(`\n${report.checks.length - failed}/${report.checks.length} checks passed · renderer: ${report.renderer}`);
process.exit(failed ? 1 : 0);
