// cf_corpus.test.ts — CFParser 對全 48 fixture：CF 解析無誤、dxfId 連結有效
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');

function allXlsx(): string[] {
    const out: string[] = [];
    for (const cat of readdirSync(FIXTURES)) {
        const dir = join(FIXTURES, cat);
        if (!existsSync(dir)) continue;
        let e: string[];
        try {
            e = readdirSync(dir);
        } catch {
            continue;
        }
        for (const f of e) if (f.toLowerCase().endsWith('.xlsx')) out.push(join(dir, f));
    }
    return out;
}

describe('CFParser corpus — CF 解析 + dxfId 連結', () => {
    it.each(allXlsx())('%s', (path) => {
        const pkg = PackageReader.fromBuffer(readFileSync(path));
        const wbp = new WorkbookParser(pkg);
        const stylesPart = wbp.stylesPart();
        const dxfCount =
            stylesPart && pkg.hasPart(stylesPart)
                ? StylesParser.parse(pkg.getPartText(stylesPart)).dxfs.length
                : 0;

        for (const sheet of wbp.parse().sheets) {
            if (!sheet.target || !pkg.hasPart(sheet.target)) continue;
            const ws = WorksheetParser.parse(pkg.getPartText(sheet.target));
            for (const cf of ws.conditionalFormatting) {
                expect(cf.ranges.length).toBeGreaterThan(0); // sqref 至少一段
                for (const rule of cf.rules) {
                    expect(rule.priority).toBeGreaterThanOrEqual(0);
                    // dxfId（若有）必指向有效 dxfs
                    if (rule.dxfId !== undefined) {
                        expect(rule.dxfId).toBeLessThan(dxfCount);
                    }
                }
            }
        }
    });
});
