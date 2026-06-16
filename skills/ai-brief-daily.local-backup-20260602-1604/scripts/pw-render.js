/**
 * Node.js renderer using Playwright for PDF & PNG export.
 * Called by render.py instead of direct Chrome invocation.
 *
 * Usage:
 *   node pw-render.js pdf <htmlPath> <pdfPath>
 *   node pw-render.js png <htmlPath> <pngPath> [width] [height] [scale]
 *   node pw-render.js card <htmlPath> <pngPath> [width] [height] [scale]
 */

const { chromium } = require('playwright');
const path = require('path');

const mode = process.argv[2];
const htmlPath = process.argv[3];
const outPath = process.argv[4];

const LD_PATHS = [
  '/home/node/.local/lib',
  '/home/node/.local/lib-stubs',
  '/home/node/.openclaw/workspace/node_modules/canvas/build/Release',
];

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    if (mode === 'pdf') {
      const page = await browser.newPage();
      await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
      await page.pdf({
        path: outPath,
        format: 'A4',
        printBackground: true,
        margin: { top: '0', bottom: '0', left: '0', right: '0' },
        displayHeaderFooter: false,
      });
      console.log('PDF_OK:' + outPath);
    } else if (mode === 'png') {
      const w = parseInt(process.argv[5] || '1920', 10);
      const h = parseInt(process.argv[6] || '1080', 10);
      const scale = parseInt(process.argv[7] || '2', 10);
      const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: scale });
      await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
      await page.screenshot({ path: outPath, clip: { x: 0, y: 0, width: w, height: h } });
      console.log('PNG_OK:' + outPath);
    } else if (mode === 'card') {
      const w = parseInt(process.argv[5] || '520', 10);
      const h = parseInt(process.argv[6] || '520', 10);
      const scale = parseInt(process.argv[7] || '2', 10);
      const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: scale });
      await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
      await page.screenshot({ path: outPath, clip: { x: 0, y: 0, width: w, height: h } });
      console.log('CARD_OK:' + outPath);
    } else {
      console.error('Unknown mode: ' + mode);
      process.exit(1);
    }
  } catch (e) {
    console.error('Error: ' + e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
