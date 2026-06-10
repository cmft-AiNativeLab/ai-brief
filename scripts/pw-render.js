#!/usr/bin/env node
/**
 * Playwright Node.js renderer for ai-brief-daily.
 * Usage: node pw-render.js <mode> <input-html> <output-file> [options]
 *   mode: pdf | png | card
 *   For pdf: node pw-render.js pdf input.html output.pdf
 *   For png (dashboard): node pw-render.js png input.html output.png [--width 1920] [--height 1080] [--scale 2]
 *   For card: node pw-render.js card input.html output.png
 *
 * This script injects LD_LIBRARY_PATH so Chromium can find shared libs
 * in /tmp/libs that are missing from the container system.
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const LD_LIB = '/tmp/libs/lib/x86_64-linux-gnu:/tmp/libs/usr/lib/x86_64-linux-gnu';
const NODE_MODULES = '/home/node/.openclaw/workspace/node_modules';

const [,, mode, inputHtml, outputFile, ...rest] = process.argv;

if (!mode || !inputHtml || !outputFile) {
  console.error('Usage: node pw-render.js <pdf|png|card> <input.html> <output>');
  process.exit(1);
}

const inputPath = path.resolve(inputHtml);
const outputPath = path.resolve(outputFile);
fs.mkdirSync(path.dirname(outputPath), { recursive: true });
// Remove stale output before rendering so a failed run cannot look successful.
try { fs.unlinkSync(outputPath); } catch (_) {}

if (!fs.existsSync(inputPath)) {
  console.error(`Input not found: ${inputPath}`);
  process.exit(1);
}

async function render() {
  const env = {
    ...process.env,
    LD_LIBRARY_PATH: LD_LIB + ':' + (process.env.LD_LIBRARY_PATH || ''),
    NODE_PATH: NODE_MODULES
  };

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    env
  });

  try {
    if (mode === 'pdf') {
      const page = await browser.newPage();
      await page.goto(`file://${inputPath}`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(2000);
      await page.pdf({
        path: outputPath,
        format: 'A4',
        printBackground: true,
        margin: { top: '0mm', bottom: '0mm', left: '0mm', right: '0mm' }
      });
      await page.close();
    } else if (mode === 'png') {
      let width = 1920, height = 1080, scale = 2;
      for (let i = 0; i < rest.length; i++) {
        if (rest[i] === '--width' && rest[i+1]) width = parseInt(rest[i+1]);
        if (rest[i] === '--height' && rest[i+1]) height = parseInt(rest[i+1]);
        if (rest[i] === '--scale' && rest[i+1]) scale = parseInt(rest[i+1]);
      }
      if (!Number.isFinite(width) || width <= 0) width = 1920;
      if (!Number.isFinite(height) || height <= 0) height = 1080;
      if (!Number.isFinite(scale) || scale <= 0) scale = 2;
      const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: scale });
      await page.goto(`file://${inputPath}`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(3000);
      await page.screenshot({ path: outputPath, fullPage: false });
      await page.close();
    } else if (mode === 'card') {
      const page = await browser.newPage({ viewport: { width: 580, height: 900 }, deviceScaleFactor: 2 });
      await page.goto(`file://${inputPath}`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: outputPath, fullPage: true });
      await page.close();
    } else {
      console.error(`Unknown mode: ${mode}`);
      process.exit(1);
    }

    const size = fs.existsSync(outputPath) ? fs.statSync(outputPath).size : 0;
    if (size <= 100) {
      throw new Error(`render produced missing/tiny file: ${outputPath} (${size} bytes)`);
    }
    console.log(`[pw-render] ${mode}: ${outputPath} (${size} bytes)`);
  } finally {
    await browser.close();
  }
}

render().catch(e => { console.error(`[pw-render] FAILED: ${e.message}`); process.exit(1); });