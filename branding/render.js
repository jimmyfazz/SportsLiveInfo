// Renders icon.png (128x128) and logo.png (250x100) from the SVG masters.
// Usage: node branding/render.js <outdir> [previewPath]
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
(async () => {
  const dir = __dirname, out = process.argv[2] || path.join(dir, '..', 'sportsliveinfo');
  const mark = fs.readFileSync(path.join(dir, 'mark.svg'), 'utf8'), logo = fs.readFileSync(path.join(dir, 'logo.svg'), 'utf8');
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ deviceScaleFactor: 1 })).newPage();
  for (const [svg, file, w, h] of [[mark, 'icon.png', 128, 128], [logo, 'logo.png', 250, 100]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(out, file), omitBackground: true, clip: { x: 0, y: 0, width: w, height: h } });
  }
  if (process.argv[3]) {
    const p2 = await (await browser.newContext({ deviceScaleFactor: 2, viewport: { width: 760, height: 330 } })).newPage();
    const icon = (s) => `<img src="data:image/svg+xml;base64,${Buffer.from(mark).toString('base64')}" width="${s}" height="${s}">`;
    const lg = `<img src="data:image/svg+xml;base64,${Buffer.from(logo).toString('base64')}" width="250" height="100">`;
    await p2.setContent(`<body style="margin:0;font:12px Inter,sans-serif;display:grid;grid-template-columns:1fr 1fr">
      <div style="background:#fff;padding:20px;color:#333">Light theme<br><br>${icon(128)} ${icon(64)} ${icon(32)}<br><br>${lg}</div>
      <div style="background:#111827;padding:20px;color:#ccc">Dark theme<br><br>${icon(128)} ${icon(64)} ${icon(32)}<br><br>${lg}</div></body>`);
    await p2.screenshot({ path: process.argv[3], fullPage: true });
  }
  await browser.close();
})();
