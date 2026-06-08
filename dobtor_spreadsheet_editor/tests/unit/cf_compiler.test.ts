// cf_compiler.test.ts — CF AST → o-spreadsheet conditionalFormats（規劃書 §4.1）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { CFParser } from '../../static/src/core/ooxmlspreadsheet/cf_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { ThemeResolver } from '../../static/src/core/ooxmlspreadsheet/theme_resolver';
import { compileConditionalFormats } from '../../static/src/core/ooxmlspreadsheet/cf_compiler';
import { importXlsxToOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/index';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const THEME = new ThemeResolver(ThemeParser.default());

// dxfs：0 = 紅字黃底
const STYLES = StylesParser.parse(
    `<?xml version="1.0"?><styleSheet xmlns="${NS}">` +
        `<dxfs count="2">` +
        `<dxf><font><b/><color rgb="FFFF0000"/></font><fill><patternFill><bgColor rgb="FFFFFF00"/></patternFill></fill></dxf>` +
        `<dxf><fill><patternFill><bgColor rgb="FF00FF00"/></patternFill></fill></dxf>` +
        `</dxfs></styleSheet>`,
);

const CF = CFParser.parse(
    `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetData/>` +
        `<conditionalFormatting sqref="D1:D1048576">` +
        `<cfRule type="cellIs" dxfId="0" priority="1" operator="equal"><formula>"B5"</formula></cfRule>` +
        `<cfRule type="cellIs" dxfId="1" priority="2" operator="between"><formula>1</formula><formula>10</formula></cfRule>` +
        `<cfRule type="containsText" dxfId="0" priority="3" operator="containsText" text="作廢"><formula>X</formula></cfRule>` +
        `<cfRule type="duplicateValues" dxfId="1" priority="4"/>` +
        `</conditionalFormatting></worksheet>`,
);

describe('compileConditionalFormats', () => {
    const cfs = compileConditionalFormats(CF, STYLES.dxfs, THEME, 100, 10, 'sheet1');

    it('cellIs equal → CellIsRule Equal + dxf 樣式', () => {
        const r = cfs.find((c) => c.rule.operator === 'Equal');
        expect(r).toBeDefined();
        expect(r!.rule.type).toBe('CellIsRule');
        expect(r!.rule.values).toEqual(['"B5"']);
        expect(r!.rule.style.bold).toBe(true);
        expect(r!.rule.style.textColor).toBe('#FF0000');
        expect(r!.rule.style.fillColor).toBe('#FFFF00');
    });
    it('cellIs between → 雙值', () => {
        const r = cfs.find((c) => c.rule.operator === 'Between');
        expect(r!.rule.values).toEqual(['1', '10']);
        expect(r!.rule.style.fillColor).toBe('#00FF00');
    });
    it('containsText → ContainsText + text 值', () => {
        const r = cfs.find((c) => c.rule.operator === 'ContainsText');
        expect(r!.rule.values).toEqual(['作廢']);
    });
    it('duplicateValues 不編譯（v1 未支援）', () => {
        // 4 規則中只有 3 個可編譯（cellIs×2 + containsText），duplicateValues 略過
        expect(cfs).toHaveLength(3);
    });
    it('超大範圍 D1:D1048576 夾到 maxRow', () => {
        expect(cfs[0].ranges[0]).toBe('D1:D100');
    });
    it('id 帶 sheet 前綴', () => {
        expect(cfs[0].id).toMatch(/^sheet1_/);
    });
});

describe('compileConditionalFormats — colorScale', () => {
    const cs = CFParser.parse(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetData/>` +
            // 3-color: min 紅 → percentile50 黃 → max 綠
            `<conditionalFormatting sqref="E1:E20">` +
            `<cfRule type="colorScale" priority="1"><colorScale>` +
            `<cfvo type="min"/><cfvo type="percentile" val="50"/><cfvo type="max"/>` +
            `<color rgb="FFFF0000"/><color rgb="FFFFFF00"/><color rgb="FF00FF00"/>` +
            `</colorScale></cfRule></conditionalFormatting>` +
            // 2-color: num 0 白 → num 100 藍
            `<conditionalFormatting sqref="F1:F20">` +
            `<cfRule type="colorScale" priority="2"><colorScale>` +
            `<cfvo type="num" val="0"/><cfvo type="num" val="100"/>` +
            `<color rgb="FFFFFFFF"/><color rgb="FF0000FF"/>` +
            `</colorScale></cfRule></conditionalFormatting></worksheet>`,
    );
    const cfs = compileConditionalFormats(cs, [], THEME, 100, 10, 'sheet1');

    it('3-color → ColorScaleRule min/mid/max + RGB 整數色', () => {
        const r = cfs.find((c) => c.ranges[0] === 'E1:E20')!.rule;
        expect(r.type).toBe('ColorScaleRule');
        if (r.type !== 'ColorScaleRule') return;
        expect(r.minimum).toEqual({ type: 'value', color: 0xff0000 });
        expect(r.midpoint).toEqual({ type: 'percentile', color: 0xffff00, value: '50' });
        expect(r.maximum).toEqual({ type: 'value', color: 0x00ff00 });
    });
    it('2-color → midpoint null、num 帶 value', () => {
        const r = cfs.find((c) => c.ranges[0] === 'F1:F20')!.rule;
        if (r.type !== 'ColorScaleRule') throw new Error('not colorScale');
        expect(r.midpoint).toBeNull();
        expect(r.minimum).toEqual({ type: 'number', color: 0xffffff, value: '0' });
        expect(r.maximum).toEqual({ type: 'number', color: 0x0000ff, value: '100' });
    });
});

describe('compileConditionalFormats — dataBar', () => {
    const db = CFParser.parse(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetData/>` +
            `<conditionalFormatting sqref="G1:G20"><cfRule type="dataBar" priority="1"><dataBar>` +
            `<cfvo type="min"/><cfvo type="max"/><color rgb="FF638EC6"/>` +
            `</dataBar></cfRule></conditionalFormatting></worksheet>`,
    );
    it('dataBar → DataBarRule + RGB 整數色', () => {
        const cfs = compileConditionalFormats(db, [], THEME, 100, 10, 'sheet1');
        expect(cfs).toHaveLength(1);
        expect(cfs[0].rule).toEqual({ type: 'DataBarRule', color: 0x638ec6 });
    });
});

describe('importXlsxToOSpreadsheetData — 真實土單 CF 編譯', () => {
    it('土單匯入後含 CellIsRule conditionalFormats', () => {
        const b = readFileSync(join(FIXTURES, '04_conditional_format', '磺港溪C-A土單20250221-1.xlsx'));
        const data = importXlsxToOSpreadsheetData(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        const allCf = data.sheets.flatMap((s) => s.conditionalFormats as { rule: { type: string } }[]);
        expect(allCf.length).toBeGreaterThan(0);
        expect(allCf.every((c) => c.rule.type === 'CellIsRule')).toBe(true);
    });
});
