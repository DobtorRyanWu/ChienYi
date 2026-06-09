// robustness.test.ts — 部署前穩健性掃描（規劃書 §4.5.4 異常處理）
//   ①所有 fixture 經兩條 import 路徑不丟錯、id 全有效 ②損壞輸入乾淨丟錯（供 UI catch）
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import {
    importXlsxToOSpreadsheetData,
    importXlsxToHtmlPreview,
} from '../../static/src/core/ooxmlspreadsheet/index';

const FX = join(__dirname, '..', 'fixtures');

describe('穩健性掃描', () => {
    it('所有 fixture import（o-spreadsheet + 預覽）不丟錯、style/border id 全有效', () => {
        const dirs = readdirSync(FX).filter((d) => !d.startsWith('_') && !d.includes('.'));
        const fails: string[] = [];
        let count = 0;
        for (const dir of dirs) {
            for (const f of readdirSync(join(FX, dir))) {
                if (!f.endsWith('.xlsx')) continue;
                count++;
                try {
                    const b = readFileSync(join(FX, dir, f));
                    const ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
                    const data = importXlsxToOSpreadsheetData(ab);
                    if (data.sheets.length === 0) fails.push(`${f}: 無 sheet`);
                    for (const sh of data.sheets) {
                        for (const [ref, c] of Object.entries(sh.cells)) {
                            const cc = c as { style?: number; border?: number };
                            if (cc.style !== undefined && data.styles[cc.style] === undefined) fails.push(`${f}:${ref} style`);
                            if (cc.border !== undefined && data.borders[cc.border] === undefined) fails.push(`${f}:${ref} border`);
                        }
                    }
                    importXlsxToHtmlPreview(ab, 0);
                } catch (e) {
                    fails.push(`${f}: THROW ${String(e).slice(0, 80)}`);
                }
            }
        }
        expect(count).toBeGreaterThan(40);
        expect(fails).toEqual([]);
    }, 60000);

    it('損壞輸入（非 zip）→ 乾淨丟 Error（供 OWL try/catch 顯示友善訊息）', () => {
        const garbage = new TextEncoder().encode('not a valid xlsx, just garbage');
        expect(() => importXlsxToOSpreadsheetData(garbage.buffer)).toThrow();
        expect(() => importXlsxToHtmlPreview(garbage.buffer)).toThrow();
    });
});
