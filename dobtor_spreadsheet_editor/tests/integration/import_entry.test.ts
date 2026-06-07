// import_entry.test.ts — Phase 4.5 對外入口 importXlsxToHtmlPreview
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { importXlsxToHtmlPreview } from '../../static/src/core/ooxmlspreadsheet/index';

const FIXTURES = join(__dirname, '..', 'fixtures');

function buf(rel: string): ArrayBuffer {
    const b = readFileSync(join(FIXTURES, rel));
    return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}

describe('importXlsxToHtmlPreview', () => {
    it('契約詳細表（16 sheet）→ sheet 清單 + 首 sheet HTML 預覽', () => {
        const p = importXlsxToHtmlPreview(
            buf('08_chienyii_business/延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx'),
        );
        expect(p.sheets).toHaveLength(16);
        expect(p.activeSheet).toBe(0);
        expect(p.html).toContain('<table>');
        expect(p.sheets[0]).toContain('詳細價目表');
    });

    it('可指定 sheetIndex 渲染不同工作表', () => {
        const file = buf('08_chienyii_business/延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx');
        const p1 = importXlsxToHtmlPreview(file, 10); // 單價分析表
        expect(p1.activeSheet).toBe(10);
        expect(p1.html).toContain('<table>');
    });

    it('越界 sheetIndex 夾到合法範圍', () => {
        const p = importXlsxToHtmlPreview(buf('08_chienyii_business/估驗數量差異說明表再造11309.xlsx'), 999);
        expect(p.activeSheet).toBe(0); // 單 sheet → 夾到 0
        expect(p.html).toContain('臺北市政府工務局水利工程處');
    });
});
