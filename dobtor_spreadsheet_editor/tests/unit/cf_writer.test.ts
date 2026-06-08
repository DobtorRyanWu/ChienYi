// cf_writer.test.ts — CF + dxfs 匯出回 xlsx round-trip（Phase 6 §6.2）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { CFParser } from '../../static/src/core/ooxmlspreadsheet/cf_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { writeConditionalFormattings, writeDxfs } from '../../static/src/core/ooxmlspreadsheet/cf_writer';
import { exportXlsxFromBuffer } from '../../static/src/core/ooxmlspreadsheet/index';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

describe('cf_writer — 合成 CF/dxfs round-trip', () => {
    const dxfsXml =
        `<?xml version="1.0"?><styleSheet xmlns="${NS}"><dxfs count="2">` +
        `<dxf><font><b/><color rgb="FFFF0000"/></font><fill><patternFill><bgColor rgb="FFFFFF00"/></patternFill></fill></dxf>` +
        `<dxf><fill><patternFill patternType="solid"><fgColor rgb="FF00FF00"/></patternFill></fill></dxf>` +
        `</dxfs></styleSheet>`;
    const dxfs = StylesParser.parse(dxfsXml).dxfs;
    const cf = CFParser.parse(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetData/>` +
            `<conditionalFormatting sqref="D1:D10 F1:F5">` +
            `<cfRule type="cellIs" dxfId="0" priority="1" operator="equal"><formula>"B5"</formula></cfRule>` +
            `<cfRule type="containsText" dxfId="1" priority="2" operator="containsText" text="作廢"><formula>X</formula></cfRule>` +
            `</conditionalFormatting></worksheet>`,
    );

    it('CF 序列化 → 重解析一致', () => {
        const xml = `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetData/>${writeConditionalFormattings(cf)}</worksheet>`;
        const back = CFParser.parse(xml);
        expect(back).toHaveLength(1);
        expect(back[0].ranges).toEqual(['D1:D10', 'F1:F5']);
        expect(back[0].rules[0].type).toBe('cellIs');
        expect(back[0].rules[0].operator).toBe('equal');
        expect(back[0].rules[0].dxfId).toBe(0);
        expect(back[0].rules[0].formulas).toEqual(['"B5"']);
        expect(back[0].rules[1].text).toBe('作廢');
    });

    it('dxfs 序列化 → 重解析保留 font/fill', () => {
        const xml = `<?xml version="1.0"?><styleSheet xmlns="${NS}">${writeDxfs(dxfs)}</styleSheet>`;
        const back = StylesParser.parse(xml).dxfs;
        expect(back).toHaveLength(2);
        expect(back[0].font?.bold).toBe(true);
        expect(back[0].font?.color?.rgb).toBe('FFFF0000');
        expect(back[0].fill?.bgColor?.rgb).toBe('FFFFFF00');
        expect(back[1].fill?.fgColor?.rgb).toBe('FF00FF00');
    });
});

describe('exportXlsxFromBuffer — 真實土單 CF round-trip', () => {
    it('匯出檔含 conditionalFormatting + dxfs，cellIs 規則保留', () => {
        const b = readFileSync(join(FIXTURES, '04_conditional_format', '磺港溪C-A土單20250221-1.xlsx'));
        const out = exportXlsxFromBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));

        const pkg = PackageReader.fromBuffer(out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength));
        const wb = new WorkbookParser(pkg).parse();
        // 至少一個 sheet 有 CF
        let cfCount = 0;
        for (const s of wb.sheets) {
            if (!s.target || !pkg.hasPart(s.target)) continue;
            const ws = WorksheetParser.parse(pkg.getPartText(s.target));
            cfCount += ws.conditionalFormatting.reduce((n, b2) => n + b2.rules.length, 0);
        }
        expect(cfCount).toBeGreaterThan(0);
        // styles.xml 有 dxfs
        const styles = StylesParser.parse(pkg.getPartText('xl/styles.xml'));
        expect(styles.dxfs.length).toBeGreaterThan(0);
    });
});
