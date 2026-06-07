// workbook_corpus.test.ts — WorkbookParser + SharedStringsParser 對全 48 fixture 的 smoke
// 對齊規劃書 Phase 1 Exit：「Parser 對 fixture 全部無 error」（跨 Excel/WPS/LibreOffice 方言）
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { SharedStringsParser } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');

function allXlsx(): string[] {
    const out: string[] = [];
    for (const cat of readdirSync(FIXTURES)) {
        const dir = join(FIXTURES, cat);
        if (!existsSync(dir)) continue;
        let entries: string[];
        try {
            entries = readdirSync(dir);
        } catch {
            continue;
        }
        for (const f of entries) {
            if (f.toLowerCase().endsWith('.xlsx')) out.push(join(dir, f));
        }
    }
    return out;
}

const files = allXlsx();

describe('Workbook + SharedStrings corpus — 全 fixture 無 error', () => {
    it.each(files)('%s', (path) => {
        const pkg = PackageReader.fromBuffer(readFileSync(path));
        const wbp = new WorkbookParser(pkg);
        const wb = wbp.parse();

        // 至少一個 sheet，且每個 sheet 都解出實存 worksheet part
        expect(wb.sheets.length).toBeGreaterThanOrEqual(1);
        for (const s of wb.sheets) {
            expect(s.target).toBeDefined();
            expect(pkg.hasPart(s.target!)).toBe(true);
        }
        // activeTab 不超出 sheet 範圍（容錯：有些檔 activeTab 指向已刪 sheet，僅檢 >=0）
        expect(wb.view.activeTab).toBeGreaterThanOrEqual(0);

        // sharedStrings（若存在）可解析，且無殘留未解碼的 _xHHHH_
        const ssPart = wbp.sharedStringsPart();
        if (ssPart && pkg.hasPart(ssPart)) {
            const ss = SharedStringsParser.parse(pkg.getPartText(ssPart));
            expect(Array.isArray(ss)).toBe(true);
            for (const s of ss) {
                expect(s.text).not.toMatch(/_x[0-9A-Fa-f]{4}_/);
            }
        }
    });
});
