// style_resolver_corpus.test.ts — StyleResolver 對全 48 fixture 的 cascade 健全性
// 驗證：每個 cellXf 都能攤平成 ResolvedStyle（font/fill/border 為有效物件、numFmt 解析、無丟錯）。
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { StyleResolver } from '../../static/src/core/ooxmlspreadsheet/style_resolver';

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

describe('StyleResolver corpus — cascade 健全性', () => {
    it.each(allXlsx())('%s', (path) => {
        const pkg = PackageReader.fromBuffer(readFileSync(path));
        const stylesPart = new WorkbookParser(pkg).stylesPart();
        if (!stylesPart || !pkg.hasPart(stylesPart)) return;
        const styles = StylesParser.parse(pkg.getPartText(stylesPart));
        const resolver = new StyleResolver(styles);

        // 每個 cellXf 攤平後 font/fill/border 皆為物件、numFmtId 為非負整數
        for (let i = 0; i < styles.cellXfs.length; i++) {
            const rs = resolver.resolve(i);
            expect(typeof rs.font).toBe('object');
            expect(typeof rs.fill).toBe('object');
            expect(typeof rs.border).toBe('object');
            expect(Number.isInteger(rs.numFmtId)).toBe(true);
            expect(rs.numFmtId).toBeGreaterThanOrEqual(0);
            // isDate 與 numFmtCode 一致性：isDate 為 true 時必有 code
            if (rs.isDate) expect(rs.numFmtCode).toBeDefined();
        }
        // 預設樣式（無 s）不丟錯
        expect(() => resolver.resolve(undefined)).not.toThrow();
    });
});
