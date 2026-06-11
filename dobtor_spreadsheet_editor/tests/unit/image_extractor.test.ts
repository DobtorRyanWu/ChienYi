import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { extractXlsxImages } from '../../static/src/core/ooxmlspreadsheet/index';
describe('extractXlsxImages（§5.3 可編輯）', () => {
    it('自檢表 → 圖片 base64 + 位置 + sheetIndex', () => {
        const b = readFileSync(join(__dirname, '..', 'fixtures', '06_chart', '自檢表總表單0308.xlsx'));
        const imgs = extractXlsxImages(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        expect(imgs.length).toBeGreaterThan(0);
        expect(imgs[0].mimetype).toBe('image/jpeg');
        expect(imgs[0].base64.length).toBeGreaterThan(100);
        expect(imgs[0].base64).not.toContain('data:'); // 純 base64，無前綴
        expect(imgs[0].sheetIndex).toBeGreaterThanOrEqual(0);
        expect(imgs[0].width).toBeGreaterThan(0);
    });
});
