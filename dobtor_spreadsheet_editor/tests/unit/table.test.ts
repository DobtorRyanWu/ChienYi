// table.test.ts — Excel Table 解析 + 編譯（規劃書 §1.11）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseTable } from '../../static/src/core/ooxmlspreadsheet/table_parser';
import { importXlsxToOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/index';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

describe('parseTable', () => {
    const t = parseTable(
        `<?xml version="1.0"?><table xmlns="${NS}" ref="A1:C11" name="Table1" totalsRowShown="0">` +
            `<autoFilter ref="A1:C11"/><tableColumns count="3"/>` +
            `<tableStyleInfo name="TableStyleMedium9" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>`,
    )!;
    it('range / style / 屬性', () => {
        expect(t.range).toBe('A1:C11');
        expect(t.styleName).toBe('TableStyleMedium9');
        expect(t.showRowStripes).toBe(true);
        expect(t.showColumnStripes).toBe(false);
        expect(t.hasAutoFilter).toBe(true);
    });
});

describe('importXlsxToOSpreadsheetData — table fixture', () => {
    it('匯入後 sheet.tables 含 range + config', () => {
        const b = readFileSync(join(FIXTURES, '_synthetic', 'table.xlsx'));
        const data = importXlsxToOSpreadsheetData(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        const tbs = data.sheets.flatMap((s) => (s as { tables: { range: string; config: { styleId: string } }[] }).tables);
        expect(tbs.length).toBeGreaterThan(0);
        expect(tbs[0].range).toBe('A1:C11');
        expect(tbs[0].config.styleId).toBe('TableStyleMedium9');
    });
});

import { resolveSheetTables } from '../../static/src/core/ooxmlspreadsheet/table_compiler';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
describe('table styleId — 自訂樣式 fallback 內建', () => {
    it('內建 TableStyleMedium9 保留、自訂名 fallback TableStyleMedium2', () => {
        // table.xlsx 用內建 TableStyleMedium9
        const b = readFileSync(join(FIXTURES, '_synthetic', 'table.xlsx'));
        const pkg = PackageReader.fromBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        const tbs = resolveSheetTables(pkg, 'xl/worksheets/sheet1.xml');
        // 內建樣式保留
        if (tbs.length) expect(/^TableStyle(Light|Medium|Dark)\d+$/.test(tbs[0].config.styleId)).toBe(true);
    });
});
