// Inline the processed dataset into the viewer and write the two published pages in dist/.
// Usage: deno run -A tools/build.mjs [src/index.html data/campus.json dist/uoft-twin.html]   (or: node tools/build.mjs …)
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const [src, data, out] = [
  process.argv[2] || join(ROOT, 'src', 'index.html'),
  process.argv[3] || join(ROOT, 'data', 'campus.json'),
  process.argv[4] || join(ROOT, 'dist', 'uoft-twin.html'),
];
const read = (f) => readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
const html = read(src);
// "</" inside the JSON would end the inline <script> element early
const payload = read(data).replaceAll('</', '<\\/');
if (!html.includes('__TWIN_DATA__')) throw new Error(`${src} has no __TWIN_DATA__ placeholder`);
const page = html.split('__TWIN_DATA__').join(payload);
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, page);
console.log(out, Math.round(html.length / 1024), 'KB template +', Math.round(payload.length / 1024), 'KB data');

// a standalone copy with its own document skeleton, for opening locally
const standalone = out.replace('uoft-twin.html', 'index.html');
if (standalone !== out) {
  const skel = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    + '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
    + 'body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n';
  writeFileSync(standalone, skel + page + '\n</body>\n</html>\n');
  console.log(standalone);
}
