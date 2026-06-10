import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { resolvePreviewImages, previewImagesHtml } from '../../static/src/core/ooxmlspreadsheet/preview_images';
import { importXlsxToHtmlPreview } from '../../static/src/core/ooxmlspreadsheet/index';
const FX = join(__dirname, '..', 'fixtures');
describe('preview images（§5.3）', () => {
    it('自檢表 → 圖片 data URL（jpeg）', () => {
        const b = readFileSync(join(FX, '06_chart', '自檢表總表單0308.xlsx'));
        const ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
        const pkg = PackageReader.fromBuffer(ab);
        // 找有圖片的 sheet part
        let found = 0;
        for (const p of pkg.listParts()) {
            if (/^xl\/worksheets\/sheet\d+\.xml$/.test(p)) {
                found += resolvePreviewImages(pkg, p).length;
            }
        }
        expect(found).toBeGreaterThan(0);
    });
    it('previewImagesHtml：空清單→空字串；有圖→含 <img data:', () => {
        expect(previewImagesHtml([])).toBe('');
        const html = previewImagesHtml([{ dataUrl: 'data:image/png;base64,AAA', row: 2, col: 3 }]);
        expect(html).toContain('<img src="data:image/png;base64,AAA"');
        expect(html).toContain('R2C3');
    });
});
