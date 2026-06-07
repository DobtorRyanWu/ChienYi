// package_reader_corpus.test.ts — PackageReader 對全 48 份 ChienYi fixture 的 smoke
// 對齊規劃書 Phase 1 Exit Criteria：「Parser 對 fixture 全部無 error」
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';

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
            continue; // 非目錄（如 README.md）
        }
        for (const f of entries) {
            if (f.toLowerCase().endsWith('.xlsx')) out.push(join(dir, f));
        }
    }
    return out;
}

const files = allXlsx();

describe('PackageReader corpus — 全 fixture 無 error', () => {
    it('至少收集到 40 份 fixture', () => {
        expect(files.length).toBeGreaterThanOrEqual(40);
    });

    it.each(files)('%s 可解析且 workbook 關聯可解出 worksheet', (path) => {
        const reader = PackageReader.fromBuffer(readFileSync(path));
        // Content_Types 必存在（fromBuffer 已驗證）
        expect(reader.hasPart('xl/workbook.xml')).toBe(true);
        // 根 → officeDocument 必指向某 workbook part
        const office = reader.getRootRels().find((r) => r.type.endsWith('/officeDocument'));
        expect(office).toBeDefined();
        const wbPart = office!.resolvedTarget;
        expect(reader.hasPart(wbPart)).toBe(true);
        // workbook 關聯至少一個 worksheet，且 target part 實際存在
        const sheets = reader.getRels(wbPart).filter((r) => r.type.endsWith('/worksheet'));
        expect(sheets.length).toBeGreaterThanOrEqual(1);
        expect(reader.hasPart(sheets[0].resolvedTarget)).toBe(true);
    });
});
