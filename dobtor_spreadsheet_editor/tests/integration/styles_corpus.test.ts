// styles_corpus.test.ts — StylesParser 對全 48 fixture 的結構完整性
// 驗證：每個 cell.styleIndex 指向有效 cellXf；每個 cellXf 的 font/fill/border 索引在界內。
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

describe('StylesParser corpus — 結構完整性', () => {
    it.each(allXlsx())('%s', (path) => {
        const pkg = PackageReader.fromBuffer(readFileSync(path));
        const wbp = new WorkbookParser(pkg);
        const stylesPart = wbp.stylesPart();
        // styles.xml 幾乎必存在；若無則跳過（極罕見）
        if (!stylesPart || !pkg.hasPart(stylesPart)) return;
        const styles = StylesParser.parse(pkg.getPartText(stylesPart));

        // 每個 cellXf 的 font/fill/border 索引在界內
        for (const xf of styles.cellXfs) {
            expect(xf.fontId).toBeLessThan(styles.fonts.length);
            expect(xf.fillId).toBeLessThan(styles.fills.length);
            expect(xf.borderId).toBeLessThan(styles.borders.length);
            if (xf.xfId !== undefined) {
                expect(xf.xfId).toBeLessThan(styles.cellStyleXfs.length);
            }
        }

        // 每個 cell.styleIndex 指向有效 cellXf
        for (const sheet of wbp.parse().sheets) {
            if (!sheet.target || !pkg.hasPart(sheet.target)) continue;
            const ws = WorksheetParser.parse(pkg.getPartText(sheet.target));
            for (const cell of ws.cells) {
                if (cell.styleIndex !== undefined) {
                    expect(cell.styleIndex).toBeLessThan(styles.cellXfs.length);
                }
            }
        }
    });
});
