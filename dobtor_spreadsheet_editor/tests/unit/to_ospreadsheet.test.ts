// to_ospreadsheet.test.ts — ParsedWorksheet → o-spreadsheet WorkbookData（Phase 4.5 對接）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { buildOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/to_ospreadsheet';
import { importXlsxToOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/index';
import type { SharedString } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

const STYLES = StylesParser.parse(
    `<?xml version="1.0"?><styleSheet xmlns="${NS}">` +
        `<numFmts count="1"><numFmt numFmtId="178" formatCode="#,##0.00"/></numFmts>` +
        `<fonts count="2"><font><sz val="12"/></font><font><b/><color rgb="FFFF0000"/></font></fonts>` +
        `<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>` +
        `<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills>` +
        `<borders count="1"><border/></borders>` +
        `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
        `<cellXfs count="3">` +
        `<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>` +
        `<xf numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>` +
        `<xf numFmtId="178" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>` +
        `</cellXfs></styleSheet>`,
);
const THEME = ThemeParser.default();
const SS: SharedString[] = [{ text: '標題' }];

const WS = WorksheetParser.parse(
    `<?xml version="1.0"?><worksheet xmlns="${NS}"><dimension ref="A1:C2"/>` +
        `<cols><col min="1" max="1" width="20" customWidth="1"/></cols>` +
        `<sheetData>` +
        `<row r="1"><c r="A1" s="1" t="s"><v>0</v></c><c r="B1" s="1" t="s"><v>0</v></c></row>` +
        `<row r="2"><c r="A2" s="0"><v>13</v></c><c r="C2" s="2"><v>1234.5</v></c></row>` +
        `</sheetData><mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells></worksheet>`,
);

describe('buildOSpreadsheetData', () => {
    const data = buildOSpreadsheetData([{ name: '工作表1', ws: WS }], SS, STYLES, THEME);
    const sheet = data.sheets[0];

    it('WorkbookData 頂層結構', () => {
        expect(data.version).toBeGreaterThanOrEqual(1);
        expect(data.sheets).toHaveLength(1);
        expect(typeof data.styles).toBe('object');
        expect(typeof data.formats).toBe('object');
    });
    it('sheet 維度 / 名稱 / id', () => {
        expect(sheet.name).toBe('工作表1');
        expect(sheet.id).toBe('sheet1');
        expect(sheet.colNumber).toBe(3);
        expect(sheet.rowNumber).toBe(2);
    });
    it('cell content：sharedString / 數字', () => {
        expect(sheet.cells['A1'].content).toBe('標題');
        expect(sheet.cells['A2'].content).toBe('13');
        expect(sheet.cells['C2'].content).toBe('1234.5');
    });
    it('cell style 以 id 參照、池內為 o-spreadsheet 樣式', () => {
        const styleId = sheet.cells['A1'].style;
        expect(styleId).toBeDefined();
        const st = data.styles[styleId!];
        expect(st.bold).toBe(true);
        expect(st.textColor).toBe('#FF0000');
        expect(st.fillColor).toBe('#FFFF00');
        expect(st.align).toBe('center');
        expect(st.verticalAlign).toBe('middle');
        expect(st.wrapping).toBe('wrap');
    });
    it('format 以 id 參照（C2 = #,##0.00）', () => {
        const fmtId = sheet.cells['C2'].format;
        expect(fmtId).toBeDefined();
        expect(data.formats[fmtId!]).toBe('#,##0.00');
    });
    it('merges 保留、cols 0-based 寬度', () => {
        expect(sheet.merges).toEqual(['A1:B1']);
        expect(sheet.cols[0]?.size).toBeGreaterThan(0);
    });
    it('樣式池去重（A1、B1 同樣式 → 同 id）', () => {
        expect(sheet.cells['A1'].style).toBe(sheet.cells['B1'].style);
    });
});

describe('importXlsxToOSpreadsheetData — 真實契約詳細表', () => {
    it('16 sheet → WorkbookData，cells 非空', () => {
        const b = readFileSync(
            join(FIXTURES, '08_chienyii_business', '延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx'),
        );
        const data = importXlsxToOSpreadsheetData(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        expect(data.sheets).toHaveLength(16);
        expect(data.sheets[0].name).toContain('詳細價目表');
        expect(Object.keys(data.sheets[0].cells).length).toBeGreaterThan(0);
        // 所有 cell 的 style/format id 都指向有效池項
        for (const sh of data.sheets) {
            for (const cell of Object.values(sh.cells)) {
                if (cell.style !== undefined) expect(data.styles[cell.style]).toBeDefined();
                if (cell.format !== undefined) expect(data.formats[cell.format]).toBeDefined();
            }
        }
    });
});
