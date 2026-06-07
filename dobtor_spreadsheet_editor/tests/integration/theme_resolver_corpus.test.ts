// theme_resolver_corpus.test.ts — ThemeResolver 對全 48 fixture 的色彩解析健全性
// 驗證：styles 內所有 theme/indexed/rgb 色 → 具體 6-hex（或 undefined 系統色），格式有效、不丟錯。
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { ThemeResolver } from '../../static/src/core/ooxmlspreadsheet/theme_resolver';
import type { Color } from '../../static/src/core/ooxmlspreadsheet/color';

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

describe('ThemeResolver corpus — 色彩解析健全性', () => {
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
        const resolver = new ThemeResolver(theme);

        const check = (c: Color | undefined) => {
            const hex = resolver.resolveColor(c);
            if (hex !== undefined) expect(hex).toMatch(HEX6);
        };

        for (const fill of styles.fills) {
            check(fill.fgColor);
            check(fill.bgColor);
        }
        for (const font of styles.fonts) check(font.color);
        for (const border of styles.borders) {
            check(border.left?.color);
            check(border.right?.color);
            check(border.top?.color);
            check(border.bottom?.color);
        }
        // 註：純黑白營造文件可能全用 auto/系統色（解析後皆 undefined 屬正常）；
        // 此 corpus 只保證「有定義的色彩皆解析成合法 6-hex、且不丟錯」。
    });
});
