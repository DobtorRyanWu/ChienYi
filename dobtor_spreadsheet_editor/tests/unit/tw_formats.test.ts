// tw_formats.test.ts — 台灣常見自訂格式 + 條件運算（§2.3）
import { describe, it, expect } from 'vitest';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { buildOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/to_ospreadsheet';
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const THEME = ThemeParser.default();

function fmtOf(code: string, val = 5000): string | undefined {
    const styles = StylesParser.parse(
        `<?xml version="1.0"?><styleSheet xmlns="${NS}"><numFmts count="1"><numFmt numFmtId="190" formatCode="${code.replace(/"/g, '&quot;')}"/></numFmts>` +
            `<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="190" applyNumberFormat="1"/></cellXfs></styleSheet>`,
    );
    const ws = WorksheetParser.parse(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><dimension ref="A1:A1"/><sheetData><row r="1"><c r="A1" s="1"><v>${val}</v></c></row></sheetData></worksheet>`,
    );
    return buildOSpreadsheetData([{ name: 'X', ws }], [], styles, THEME).sheets[0].cells['A1']?.format;
}

describe('台灣常見格式 → o-spreadsheet 安全數字格式', () => {
    it('千分位 #,##0 / #,##0.00 / #,##0.000', () => {
        expect(fmtOf('#,##0')).toBe('#,##0');
        expect(fmtOf('#,##0.00')).toBe('#,##0.00');
        expect(fmtOf('#,##0.000')).toBe('#,##0.000');
    });
    it('百分比 0.00% / 0.0%', () => {
        expect(fmtOf('0.00%')).toBe('0.00%');
        expect(fmtOf('0.0%')).toBe('0.0%');
    });
    it('條件運算 [>1000]#,##0 → 剝除條件、套 #,##0', () => {
        expect(fmtOf('[>1000]#,##0;0')).toBe('#,##0');
    });
    it('貨幣 [$NT$-404]#,##0.00 → 取數字 #,##0.00（去貨幣 token）', () => {
        expect(fmtOf('[$NT$-404]#,##0.00')).toBe('#,##0.00');
    });
    it('"字面"格式（0.00"元"）→ 不套（含非數字字面）', () => {
        expect(fmtOf('0.00"元"')).toBeUndefined();
    });
});
