// concrete_style_corpus.test.ts — 全 48 fixture 端到端：cell → ConcreteStyle（色彩皆具體）
// 串接 StyleResolver + ThemeResolver，驗證 Phase 4.5 對接層在真實資料上健全。
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
const HEX6 = /^[0-9A-F]{6}$/;

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

describe('ConcreteStyle corpus — 端到端具體化', () => {
    it.each(allXlsx())('%s', (path) => {
        const pkg = PackageReader.fromBuffer(readFileSync(path));
        const wbp = new WorkbookParser(pkg);
        const stylesPart = wbp.stylesPart();
        if (!stylesPart || !pkg.hasPart(stylesPart)) return;
        const styles = StylesParser.parse(pkg.getPartText(stylesPart));
        const themePart = wbp.themePart();
        const theme = themePart && pkg.hasPart(themePart)
            ? ThemeParser.parse(pkg.getPartText(themePart))
            : ThemeParser.default();
        const resolver = new ConcreteStyleResolver(styles, theme);

        const okColor = (c: string | undefined) => {
            if (c !== undefined) expect(c).toMatch(HEX6);
        };

        // 取第一個 sheet 的實際 cell styleIndex 走完整路徑
        const firstSheet = wbp.parse().sheets.find((s) => s.target && pkg.hasPart(s.target));
        if (firstSheet?.target) {
            const ws = WorksheetParser.parse(pkg.getPartText(firstSheet.target));
            for (const cell of ws.cells.slice(0, 500)) {
                const s = resolver.resolve(cell.styleIndex);
                okColor(s.font.color);
                okColor(s.fill.fgColor);
                okColor(s.fill.bgColor);
                okColor(s.border.left?.color);
                okColor(s.border.top?.color);
                expect(Number.isInteger(s.numFmtId)).toBe(true);
            }
        }
    });
});
