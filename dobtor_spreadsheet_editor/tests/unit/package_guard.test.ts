// package_guard.test.ts — §4.5.4 上傳/zip bomb 防護
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';

describe('PackageReader 防護', () => {
    it('壓縮輸入過大（>30MB）→ 丟錯', () => {
        const big = new Uint8Array(31 * 1024 * 1024);
        expect(() => PackageReader.fromBuffer(big.buffer)).toThrow(/過大/);
    });
    it('非 zip → 丟錯（不誤判為通過）', () => {
        const garbage = new TextEncoder().encode('not a zip');
        expect(() => PackageReader.fromBuffer(garbage.buffer)).toThrow();
    });
    it('正常 xlsx（含最大旗艦檔）→ 正常解析', () => {
        const b = readFileSync(join(__dirname, '..', 'fixtures', '08_chienyii_business', '延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx'));
        const pkg = PackageReader.fromBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        expect(pkg.hasPart('xl/workbook.xml')).toBe(true);
    });
});
