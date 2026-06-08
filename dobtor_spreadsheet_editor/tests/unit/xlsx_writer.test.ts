// xlsx_writer.test.ts — xlsx 寫出 + round-trip（規劃書 Phase 6）
import { describe, it, expect } from 'vitest';
import { buildXlsx } from '../../static/src/core/ooxmlspreadsheet/xlsx_writer';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { SharedStringsParser } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';
import { WorksheetParser, buildValueMap } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';

function reparse(bytes: Uint8Array) {
    const pkg = PackageReader.fromBuffer(bytes);
    const wbp = new WorkbookParser(pkg);
    const wb = wbp.parse();
    const ssPart = wbp.sharedStringsPart();
    const ss = ssPart && pkg.hasPart(ssPart) ? SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
    return { pkg, wb, ss };
}

describe('buildXlsx — 基本寫出', () => {
    const bytes = buildXlsx([
        {
            name: '工作表A',
            cells: [
                { row: 1, col: 1, value: '標題' },
                { row: 1, col: 2, value: 123.5 },
                { row: 2, col: 1, value: true },
                { row: 2, col: 2, value: 0, formula: 'SUM(B1:B1)' },
            ],
            merges: ['A1:B1'],
        },
        { name: 'Sheet2', cells: [{ row: 1, col: 1, value: 'x' }], merges: [] },
    ]);

    it('產出合法 xlsx（PackageReader 可開）', () => {
        const { pkg, wb } = reparse(bytes);
        expect(pkg.hasPart('xl/workbook.xml')).toBe(true);
        expect(wb.sheets.map((s) => s.name)).toEqual(['工作表A', 'Sheet2']);
    });

    it('cell 值 round-trip（string/number/bool/formula）', () => {
        const { pkg, wb, ss } = reparse(bytes);
        const ws = WorksheetParser.parse(pkg.getPartText(wb.sheets[0].target!));
        const map = buildValueMap(ws, ss);
        expect(map.get('1:1')).toBe('標題');
        expect(map.get('1:2')).toBe(123.5);
        expect(map.get('2:1')).toBe(true);
        expect(map.get('2:2')).toBe(0); // formula cached
        const formulaCell = ws.cells.find((c) => c.ref === 'B2');
        expect(formulaCell?.formula).toBe('SUM(B1:B1)');
    });

    it('合併儲存格 round-trip', () => {
        const { pkg, wb } = reparse(bytes);
        const ws = WorksheetParser.parse(pkg.getPartText(wb.sheets[0].target!));
        expect(ws.merges).toContain('A1:B1');
    });

    it('XML escape（含 < & " 的字串）', () => {
        const b = buildXlsx([{ name: 'S', cells: [{ row: 1, col: 1, value: 'a<b&c"d' }], merges: [] }]);
        const { pkg, wb, ss } = reparse(b);
        const ws = WorksheetParser.parse(pkg.getPartText(wb.sheets[0].target!));
        expect(buildValueMap(ws, ss).get('1:1')).toBe('a<b&c"d');
    });
});
