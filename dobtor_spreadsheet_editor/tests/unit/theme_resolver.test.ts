// theme_resolver.test.ts — Color → 具體 RGB（規劃書 §2.2）
import { describe, it, expect } from 'vitest';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { ThemeResolver, applyTint } from '../../static/src/core/ooxmlspreadsheet/theme_resolver';

const R = new ThemeResolver(ThemeParser.default());

describe('ThemeResolver — theme 索引映射（含 0/1、2/3 互換）', () => {
    it('theme 0 = lt1（白）、1 = dk1（黑）', () => {
        expect(R.resolveColor({ theme: 0 })).toBe('FFFFFF');
        expect(R.resolveColor({ theme: 1 })).toBe('000000');
    });
    it('theme 2 = lt2、3 = dk2', () => {
        expect(R.resolveColor({ theme: 2 })).toBe('E7E6E6');
        expect(R.resolveColor({ theme: 3 })).toBe('44546A');
    });
    it('theme 4-9 = accent1-6', () => {
        expect(R.resolveColor({ theme: 4 })).toBe('4472C4');
        expect(R.resolveColor({ theme: 7 })).toBe('FFC000'); // accent4
        expect(R.resolveColor({ theme: 9 })).toBe('70AD47');
    });
    it('越界 theme 索引 → undefined', () => {
        expect(R.resolveColor({ theme: 99 })).toBeUndefined();
    });
});

describe('ThemeResolver — tint（HSL luminance）', () => {
    it('accent4 + tint 0.8 = FFF2CC（Excel「Gold, Lighter 80%」）', () => {
        expect(R.resolveColor({ theme: 7, tint: 0.7999816888943144 })).toBe('FFF2CC');
    });
    it('tint > 0 變亮、tint < 0 變暗', () => {
        const base = [0x44, 0x72, 0xc4].reduce((a, b) => a + b, 0);
        const lighter = applyTint('4472C4', 0.5);
        const darker = applyTint('4472C4', -0.5);
        const sum = (h: string) => parseInt(h.slice(0, 2), 16) + parseInt(h.slice(2, 4), 16) + parseInt(h.slice(4, 6), 16);
        expect(sum(lighter)).toBeGreaterThan(base);
        expect(sum(darker)).toBeLessThan(base);
    });
    it('tint 0 不變色', () => {
        expect(applyTint('4472C4', 0)).toBe('4472C4');
    });
    it('純黑 tint 1 → 純白、純白 tint -1 → 純黑', () => {
        expect(applyTint('000000', 1)).toBe('FFFFFF');
        expect(applyTint('FFFFFF', -1)).toBe('000000');
    });
});

describe('ThemeResolver — rgb / indexed / auto', () => {
    it('ARGB 8-hex 去 alpha', () => {
        expect(R.resolveColor({ rgb: 'FFFF0000' })).toBe('FF0000');
    });
    it('RGB 6-hex 原樣（大寫）', () => {
        expect(R.resolveColor({ rgb: 'ff0000' })).toBe('FF0000');
    });
    it('indexed palette', () => {
        expect(R.resolveColor({ indexed: 2 })).toBe('FF0000');
        expect(R.resolveColor({ indexed: 22 })).toBe('C0C0C0');
    });
    it('indexed 64/65（系統色）→ undefined', () => {
        expect(R.resolveColor({ indexed: 64 })).toBeUndefined();
        expect(R.resolveColor({ indexed: 65 })).toBeUndefined();
    });
    it('auto → undefined（系統相關）', () => {
        expect(R.resolveColor({ auto: true })).toBeUndefined();
    });
    it('undefined color → undefined', () => {
        expect(R.resolveColor(undefined)).toBeUndefined();
    });
});
