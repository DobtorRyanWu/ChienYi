// html_render.test.ts — ParsedWorksheet → HTML 表格（VR render 路徑）
import { describe, it, expect } from 'vitest';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { renderWorksheetHtml } from '../../static/src/core/ooxmlspreadsheet/vr/html_render';
import type { SharedString } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';

const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

const STYLES = StylesParser.parse(
    `<?xml version="1.0"?><styleSheet xmlns="${NS}">` +
        `<fonts count="2"><font><sz val="12"/></font><font><b/><color rgb="FFFF0000"/></font></fonts>` +
        `<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>` +
        `<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills>` +
        `<borders count="1"><border><left/><right/><top/><bottom/></border></borders>` +
        `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
        `<cellXfs count="2">` +
        `<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>` +
        `<xf numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>` +
        `</cellXfs></styleSheet>`,
);
const THEME = ThemeParser.default();
const SS: SharedString[] = [{ text: '標題' }, { text: '內容' }];

// A1:B1 合併、A1 紅粗體黃底置中標題；A2 數字、B2 sharedString
const WS = WorksheetParser.parse(
    `<?xml version="1.0"?><worksheet xmlns="${NS}"><dimension ref="A1:B2"/><sheetData>` +
        `<row r="1"><c r="A1" s="1" t="s"><v>0</v></c><c r="B1" s="1"/></row>` +
        `<row r="2"><c r="A2" s="0"><v>123.5</v></c><c r="B2" s="0" t="s"><v>1</v></c></row>` +
        `</sheetData><mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells></worksheet>`,
);

describe('renderWorksheetHtml', () => {
    const html = renderWorksheetHtml(WS, SS, STYLES, THEME);

    it('輸出完整 HTML 文件含 table', () => {
        expect(html).toContain('<!DOCTYPE html>');
        expect(html).toContain('<table>');
        expect(html).toContain('</table>');
    });
    it('cell 值出現', () => {
        expect(html).toContain('標題');
        expect(html).toContain('123.5');
        expect(html).toContain('內容');
    });
    it('合併格 → colspan/rowspan，covered 格跳過', () => {
        expect(html).toMatch(/colspan="2" rowspan="1"/);
        // A1:B1 合併 → 第一列只有 1 個 td
        const firstRow = html.match(/<tr>(.*?)<\/tr>/)![1];
        expect((firstRow.match(/<td/g) ?? []).length).toBe(1);
    });
    it('樣式 CSS：黃底 + 紅字 + 粗體 + 置中', () => {
        expect(html).toContain('background:#FFFF00');
        expect(html).toContain('color:#FF0000');
        expect(html).toContain('font-weight:bold');
        expect(html).toContain('text-align:center');
    });
    it('欄寬 px 出現在 style', () => {
        expect(html).toMatch(/width:\d+px/);
    });
});

describe('renderWorksheetHtml — HTML escaping', () => {
    const wsEsc = WorksheetParser.parse(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><dimension ref="A1:A1"/><sheetData>` +
            `<row r="1"><c r="A1" t="inlineStr"><is><t>a&lt;b&amp;c"d</t></is></c></row>` +
            `</sheetData></worksheet>`,
    );
    it('特殊字元 escape', () => {
        const html = renderWorksheetHtml(wsEsc, [], STYLES, THEME);
        expect(html).toContain('a&lt;b&amp;c&quot;d');
    });
});
