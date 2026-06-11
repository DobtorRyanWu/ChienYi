// style_pass_rate.test.ts — 樣式解析完整度量化（規劃書 §6.3）
//
// 跨 corpus 量測：每個有 styleIndex 的 cell 經 ConcreteStyleResolver 解析後，
// 所有色彩欄位（font.color / fill.fg|bg / border 各邊）須為合法 6-hex RGB（或 undefined）。
// 「pass」= 該 cell 全部色彩欄位合法。pass rate = pass / 總 styled cell。

import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { ConcreteStyleResolver } from '../../static/src/core/ooxmlspreadsheet/concrete_style';

const FIXTURES = join(__dirname, '..', 'fixtures');
const HEX6 = /^[0-9A-Fa-f]{6}$/;

function allXlsx(): string[] {
    const out: string[] = [];
    for (const cat of readdirSync(FIXTURES)) {
        const dir = join(FIXTURES, cat);
        if (!existsSync(dir) || cat.startsWith('_')) continue;
        let entries: string[];
        try {
            entries = readdirSync(dir);
        } catch {
            continue;
        }
        for (const f of entries) if (f.toLowerCase().endsWith('.xlsx')) out.push(join(dir, f));
    }
    return out;
}

function colorOk(c: string | undefined): boolean {
    return c === undefined || HEX6.test(c);
}

describe('樣式解析完整度（§6.3 style pass rate）', () => {
    it('所有 styled cell 的色彩欄位均解析為合法 6-hex RGB（pass rate ≥ 99%）', () => {
        let total = 0;
        let pass = 0;
        for (const file of allXlsx()) {
            const b = readFileSync(file);
            const pkg = PackageReader.fromBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
            const wbp = new WorkbookParser(pkg);
            const wb = wbp.parse();
            const stPart = wbp.stylesPart();
            const styles = stPart && pkg.hasPart(stPart)
                ? StylesParser.parse(pkg.getPartText(stPart))
                : StylesParser.parse('<styleSheet/>');
            const thPart = wbp.themePart();
            const theme = thPart && pkg.hasPart(thPart) ? ThemeParser.parse(pkg.getPartText(thPart)) : ThemeParser.default();
            const resolver = new ConcreteStyleResolver(styles, theme);
            for (const s of wb.sheets) {
                if (!s.target || !pkg.hasPart(s.target)) continue;
                const ws = WorksheetParser.parse(pkg.getPartText(s.target));
                for (const cell of ws.cells) {
                    if (cell.styleIndex === undefined) continue;
                    total++;
                    const cs = resolver.resolve(cell.styleIndex);
                    const ok =
                        colorOk(cs.font.color) &&
                        colorOk(cs.fill.fgColor) &&
                        colorOk(cs.fill.bgColor) &&
                        colorOk(cs.border.top?.color) &&
                        colorOk(cs.border.bottom?.color) &&
                        colorOk(cs.border.left?.color) &&
                        colorOk(cs.border.right?.color);
                    if (ok) pass++;
                }
            }
        }
        const rate = total > 0 ? (pass / total) * 100 : 100;
        // eslint-disable-next-line no-console
        console.log(`style pass rate: ${rate.toFixed(3)}% (${pass}/${total} styled cells)`);
        expect(total).toBeGreaterThan(1000);
        expect(rate).toBeGreaterThanOrEqual(99);
    }, 60000);
});
