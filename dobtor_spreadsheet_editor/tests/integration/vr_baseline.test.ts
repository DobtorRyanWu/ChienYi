// vr_baseline.test.ts — VR pipeline 端到端 baseline（puppeteer 光柵化 vs golden PNG）
//
// 預設 `npm test` 跳過（避免 puppeteer 拖慢/不穩）。手動量測：
//   VR_BASELINE=1 npx vitest run tests/integration/vr_baseline.test.ts
//
// 注意：本 render 路徑為 HTML 表格，佈局引擎與 LibreOffice golden 不同，差異率「偏高」屬預期；
// 此 baseline 用於建立 VR 管線與後續自洽回歸基準，非 LibreOffice 像素對等指標。

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { SharedStringsParser } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { renderWorksheetHtml } from '../../static/src/core/ooxmlspreadsheet/vr/html_render';
import { launchBrowser, renderHtmlToPng } from '../../static/src/core/ooxmlspreadsheet/vr/render_png';
import { comparePng } from '../../static/src/core/ooxmlspreadsheet/vr/pixel_compare';

const FIXTURES = join(__dirname, '..', 'fixtures');

const SAMPLES = [
    ['08_chienyii_business', '估驗數量差異說明表再造11309.xlsx'],
    ['08_chienyii_business', '0312磺港溪A標變更金額分析.xlsx'],
    ['04_conditional_format', '磺港溪C-A土單20250221-1.xlsx'],
];

const enabled = process.env.VR_BASELINE === '1';

describe.skipIf(!enabled)('VR pipeline baseline', () => {
    it('render → pixelmatch vs golden', async () => {
        const browser = await launchBrowser();
        try {
            for (const [cat, name] of SAMPLES) {
                const xlsx = join(FIXTURES, cat, name);
                const goldenPng = join(FIXTURES, cat, 'golden', name.replace(/\.xlsx$/i, '.png'));
                if (!existsSync(xlsx) || !existsSync(goldenPng)) continue;

                const pkg = PackageReader.fromBuffer(readFileSync(xlsx));
                const wbp = new WorkbookParser(pkg);
                const wb = wbp.parse();
                const ssPart = wbp.sharedStringsPart();
                const ss = ssPart && pkg.hasPart(ssPart) ? SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
                const stPart = wbp.stylesPart();
                const styles = stPart && pkg.hasPart(stPart) ? StylesParser.parse(pkg.getPartText(stPart)) : undefined;
                const thPart = wbp.themePart();
                const theme = thPart && pkg.hasPart(thPart) ? ThemeParser.parse(pkg.getPartText(thPart)) : ThemeParser.default();
                if (!styles) continue;

                const sheet = wb.sheets.find((s) => s.target && pkg.hasPart(s.target));
                if (!sheet?.target) continue;
                const ws = WorksheetParser.parse(pkg.getPartText(sheet.target));
                const html = renderWorksheetHtml(ws, ss, styles, theme);
                const png = await renderHtmlToPng(browser, html);
                const goldenBuf = readFileSync(goldenPng);
                const raw = comparePng(goldenBuf, png); // 含尺寸假性差異
                const content = comparePng(goldenBuf, png, { scaleToMatch: true }); // 縮放對齊純內容

                // eslint-disable-next-line no-console
                console.log(
                    `[VR] ${name}｜our ${png.length}B｜raw ${(raw.ratio * 100).toFixed(1)}%｜` +
                        `content(scaled) ${(content.ratio * 100).toFixed(1)}%`,
                );
                expect(content.ratio).toBeGreaterThanOrEqual(0);
                expect(content.ratio).toBeLessThanOrEqual(1);
            }
        } finally {
            await browser.close();
        }
    }, 120000);
});
