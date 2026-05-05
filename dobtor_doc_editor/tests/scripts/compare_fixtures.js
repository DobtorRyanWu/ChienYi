/**
 * compare_fixtures.js — 比對 canvas-editor 渲染結果與 golden PNG
 *
 * 執行環境：本機 Windows（非 Docker，Puppeteer 需要本機 Chrome）
 * 執行方式：
 *   node tests/scripts/compare_fixtures.js
 *   node tests/scripts/compare_fixtures.js --fixture 03_complex_table
 *
 * 依賴安裝：
 *   npm install --save-dev puppeteer pixelmatch pngjs glob
 *
 * ── 前置條件 ──────────────────────────────────────────────────────────────────
 *
 * 1. Golden PNG 已由 generate_golden.sh 產生：
 *      tests/fixtures/<category>/golden/<name>-<page>.png
 *
 * 2. Odoo dev server 已啟動（http://localhost:10003）
 *
 * 3. Odoo Controller 必須提供「Clean Layout 測試路由」：
 *      GET /dobtor_doc_editor/test?fixture=<relPath>
 *    此路由只能滿版顯示 canvas-editor 的 Canvas，不可有 Header / Sidebar /
 *    Odoo 工具列等額外 UI 元素。若頁面含任何非 Canvas 元素，截圖尺寸會與
 *    golden PNG 不符，導致 100% diff 失敗。
 *
 * 4. canvas-editor 在渲染完成後必須設置旗標：
 *      window.__canvasEditorReady = true;
 *    （在 doc_editor.js 的 editor.on('rendered', ...) 中加入）
 *    若不設此旗標，Puppeteer 可能在 CJK 字型尚未載入時截圖，
 *    導致字型退回 Arial，diff 爆表。
 *
 * ── 截圖策略 ──────────────────────────────────────────────────────────────────
 *
 * 不使用 page.screenshot({ fullPage: true })，因為那會截下整個可捲動頁面，
 * 包含工具列，尺寸必然與 golden PNG（A4 單頁，約 1240×1754px）不符。
 *
 * 改為：對 canvas-editor 第一頁的 Canvas 元素使用 elementHandle.screenshot()，
 * 只截取白紙部分的像素。
 *
 * ── DPI 對齊策略 ──────────────────────────────────────────────────────────────
 *
 * Golden PNG 由 pdftoppm -r 150 產生，A4 寬度 ≈ 1240px（150 DPI）。
 * 瀏覽器預設渲染解析度為 96 DPI（CSS px）。
 * 設定 deviceScaleFactor = 150 / 96 ≈ 1.5625，讓截圖物理像素接近 golden 尺寸。
 * ⚠️ 此為概算值，實際 canvas-editor 的紙張寬度可能需要微調 Scale Factor。
 */

'use strict';

const puppeteer = require('puppeteer');
const pixelmatch = require('pixelmatch');
const { PNG } = require('pngjs');
const fs = require('fs');
const path = require('path');
const glob = require('glob');

// ── 設定 ─────────────────────────────────────────────────────────────────────

const PASS_THRESHOLD  = 0.05;      // 5%：Pass/Fail 邊界（Phase 3 目標）
const ODOO_BASE_URL   = 'http://localhost:10003';
const FONT_READY_TIMEOUT = 15000;  // 等待字型 + 渲染完成的 timeout（ms）

// DPI 對齊：golden PNG 為 150 DPI，瀏覽器預設 96 DPI
// 150 / 96 ≈ 1.5625（概算，未來可能需要微調以精確對齊 golden 尺寸）
const DEVICE_SCALE_FACTOR = 1.5625;

const FIXTURES_ROOT = path.resolve(__dirname, '../fixtures');

// canvas-editor 第一頁的 Canvas 元素選擇器
// Phase 1 實作時依實際 DOM 結構調整
const CANVAS_PAGE_SELECTOR = 'canvas';

// ── 引數解析 ──────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const filterIdx = args.indexOf('--fixture');
const fixtureFilter = filterIdx >= 0 ? args[filterIdx + 1] : null;

// ── 工具函數 ──────────────────────────────────────────────────────────────────

/** 取得某個 fixture 的所有 golden PNG 路徑，依頁碼升冪排序 */
function getGoldenPages(docxPath) {
  const dir = path.dirname(docxPath);
  const name = path.basename(docxPath, '.docx');
  const goldenDir = path.join(dir, 'golden');
  if (!fs.existsSync(goldenDir)) return [];

  return fs
    .readdirSync(goldenDir)
    .filter(f => f.startsWith(name + '-') && f.endsWith('.png') && !f.includes('_diff'))
    .sort((a, b) => {
      const pageOf = f => parseInt(f.match(/-(\d+)\.png$/)?.[1] ?? '0', 10);
      return pageOf(a) - pageOf(b);
    })
    .map(f => path.join(goldenDir, f));
}

/**
 * 使用 Puppeteer 開啟 canvas-editor，渲染指定 DOCX，截取第一頁 Canvas
 *
 * 截圖策略：使用 elementHandle.screenshot() 只截取白紙 Canvas 元素，
 * 排除 Odoo 工具列等非 Canvas UI，確保尺寸與 golden PNG 可比對。
 */
async function renderFixture(page, docxPath) {
  const relPath = path.relative(FIXTURES_ROOT, docxPath).replace(/\\/g, '/');
  const url = `${ODOO_BASE_URL}/dobtor_doc_editor/test?fixture=${encodeURIComponent(relPath)}`;

  await page.goto(url, { waitUntil: 'networkidle2' });

  // 等待 CSS @font-face 字型
  await page.evaluate(() => document.fonts.ready);

  // 等待 canvas-editor 渲染完成旗標（在 doc_editor.js 的 rendered 事件中設置）
  await page.waitForFunction(
    () => window.__canvasEditorReady === true,
    { timeout: FONT_READY_TIMEOUT }
  );

  // 只截取 Canvas 元素（白紙部分），排除工具列
  const canvasHandle = await page.$(CANVAS_PAGE_SELECTOR);
  if (!canvasHandle) {
    throw new Error(`Canvas element not found (selector: "${CANVAS_PAGE_SELECTOR}")`);
  }
  return canvasHandle.screenshot({ encoding: 'binary' });
}

/**
 * 比對兩張 PNG，回傳 diff ratio（0~1）
 * 若有差異，在 diffOutputPath 輸出 diff image（人工檢視用）
 */
function comparePngs(goldenBuffer, renderedBuffer, diffOutputPath) {
  const golden = PNG.sync.read(goldenBuffer);
  const rendered = PNG.sync.read(renderedBuffer);

  if (golden.width !== rendered.width || golden.height !== rendered.height) {
    console.warn(
      `    ⚠️  Size mismatch: golden ${golden.width}×${golden.height}` +
      ` vs rendered ${rendered.width}×${rendered.height}` +
      ` (check DEVICE_SCALE_FACTOR or Clean Layout route)`
    );
    return 1.0;
  }

  const diff = new PNG({ width: golden.width, height: golden.height });
  const numDiff = pixelmatch(
    golden.data, rendered.data, diff.data,
    golden.width, golden.height,
    { threshold: 0.1 }
  );
  const ratio = numDiff / (golden.width * golden.height);

  if (ratio >= PASS_THRESHOLD) {
    fs.writeFileSync(diffOutputPath, PNG.sync.write(diff));
  }

  return ratio;
}

// ── 主程式 ────────────────────────────────────────────────────────────────────

async function main() {
  let docxFiles = glob.sync('**/*.docx', { cwd: FIXTURES_ROOT, absolute: true });
  if (fixtureFilter) {
    docxFiles = docxFiles.filter(f => f.includes(fixtureFilter));
  }
  if (docxFiles.length === 0) {
    console.error('No fixture DOCX files found.');
    process.exit(1);
  }

  console.log(`\n=== compare_fixtures.js ===`);
  console.log(`Fixtures     : ${FIXTURES_ROOT}`);
  console.log(`Filter       : ${fixtureFilter ?? '(all)'}`);
  console.log(`Pass target  : diff < ${PASS_THRESHOLD * 100}%`);
  console.log(`Scale factor : ${DEVICE_SCALE_FACTOR} (150/96 DPI ≈, may need tuning)\n`);

  const browser = await puppeteer.launch({ headless: 'new' });
  const results = [];

  for (const docxPath of docxFiles) {
    const relFixture = path.relative(FIXTURES_ROOT, docxPath);
    const goldenPages = getGoldenPages(docxPath);

    if (goldenPages.length === 0) {
      console.log(`  ⚠️  SKIP  ${relFixture}  (no golden, run generate_golden.sh first)`);
      continue;
    }

    console.log(`  Testing  ${relFixture}  (${goldenPages.length} page(s))`);

    const page = await browser.newPage();
    await page.setViewport({
      width: 1400,
      height: 2000,
      deviceScaleFactor: DEVICE_SCALE_FACTOR,
    });

    let renderedBuffer;
    try {
      renderedBuffer = await renderFixture(page, docxPath);
    } catch (err) {
      console.error(`    ❌ Render failed: ${err.message}`);
      await page.close();
      results.push({ fixture: relFixture, error: err.message });
      continue;
    }
    await page.close();

    // 與第一頁 golden 比對（Phase 1 完成後擴充為逐頁比對）
    const goldenBuffer = fs.readFileSync(goldenPages[0]);
    const diffPath = goldenPages[0].replace('.png', '_diff.png');
    const ratio = comparePngs(goldenBuffer, Buffer.from(renderedBuffer), diffPath);

    const pass = ratio < PASS_THRESHOLD;
    console.log(
      `    ${pass ? '✅' : '❌'} page 1: ${(ratio * 100).toFixed(1)}%` +
      (!pass ? `  → ${diffPath}` : '')
    );

    results.push({ fixture: relFixture, ratio, pass });
  }

  await browser.close();

  // ── 總結報告 ────────────────────────────────────────────────────────────────
  console.log('\n=== 還原度報告 ===\n');
  results.forEach(r => {
    if (r.error) {
      console.log(`  💥 ${r.fixture.padEnd(55)} ERROR: ${r.error}`);
    } else {
      console.log(
        `  ${r.pass ? '✅' : '❌'} ${r.fixture.padEnd(55)} ${(r.ratio * 100).toFixed(1)}%`
      );
    }
  });

  const total  = results.filter(r => !r.error).length;
  const passed = results.filter(r => r.pass).length;
  console.log(`\n${passed}/${total} 通過（目標：全部 < ${PASS_THRESHOLD * 100}%）\n`);

  if (passed < total) process.exit(1);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
