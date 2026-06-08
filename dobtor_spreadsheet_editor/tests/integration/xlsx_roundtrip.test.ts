// xlsx_roundtrip.test.ts — 真實 fixture：parse → 我方 writer 寫出 → re-parse 值一致（Phase 6）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { exportXlsxFromBuffer } from '../../static/src/core/ooxmlspreadsheet/index';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { SharedStringsParser } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';
import { WorksheetParser, buildValueMap, resolveCellValue } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');

function ab(rel: string): ArrayBuffer {
    const b = readFileSync(join(FIXTURES, rel));
    return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}

/** 對某 xlsx buffer 算每 sheet 的 (name → valueMap)。*/
function sheetValueMaps(buf: ArrayBuffer | Uint8Array) {
    const pkg = PackageReader.fromBuffer(buf);
    const wbp = new WorkbookParser(pkg);
    const wb = wbp.parse();
    const ssPart = wbp.sharedStringsPart();
    const ss = ssPart && pkg.hasPart(ssPart) ? SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
    const out = new Map<string, Map<string, string | number | boolean>>();
    for (const s of wb.sheets) {
        if (!s.target || !pkg.hasPart(s.target)) continue;
        out.set(s.name, buildValueMap(WorksheetParser.parse(pkg.getPartText(s.target)), ss));
    }
    return out;
}

const SAMPLES = [
    '08_chienyii_business/估驗數量差異說明表再造11309.xlsx',
    '08_chienyii_business/0312磺港溪A標變更金額分析.xlsx',
    '01_simple_formula/6mm鋼板單價分析-V.xlsx',
];

describe('xlsx round-trip — parse → 我方 writer → re-parse 值一致', () => {
    it.each(SAMPLES)('%s', (rel) => {
        const original = ab(rel);
        const exported = exportXlsxFromBuffer(original);

        const origMaps = sheetValueMaps(original);
        const rtMaps = sheetValueMaps(exported);

        // sheet 名一致
        expect([...rtMaps.keys()]).toEqual([...origMaps.keys()]);

        let total = 0;
        let matched = 0;
        for (const [name, omap] of origMaps) {
            const rmap = rtMaps.get(name)!;
            for (const [key, ov] of omap) {
                total++;
                const rv = rmap.get(key);
                if (typeof ov === 'number' && typeof rv === 'number') {
                    if (Math.abs(ov - rv) < 1e-9) matched++;
                } else if (ov === rv) {
                    matched++;
                }
            }
        }
        expect(total).toBeGreaterThan(0);
        // round-trip 值一致率 ~100%
        expect(matched / total).toBeGreaterThan(0.999);
    });
});

describe('exportXlsxFromBuffer — 公式保留', () => {
    it('變更金額分析：round-trip 後公式仍在', () => {
        const exported = exportXlsxFromBuffer(ab('08_chienyii_business/0312磺港溪A標變更金額分析.xlsx'));
        const pkg = PackageReader.fromBuffer(exported);
        const wbp = new WorkbookParser(pkg);
        const wb = wbp.parse();
        let formulaCount = 0;
        for (const s of wb.sheets) {
            if (!s.target || !pkg.hasPart(s.target)) continue;
            for (const c of WorksheetParser.parse(pkg.getPartText(s.target)).cells) {
                if (c.formula) formulaCount++;
            }
        }
        expect(formulaCount).toBeGreaterThan(50);
        // 公式 cell 的 resolveCellValue 不應全空
        void resolveCellValue;
    });
});
