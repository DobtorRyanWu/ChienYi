// font_map.test.ts — Excel 字型名 → 渲染字型堆疊（VR 字型保真）
import { describe, it, expect } from 'vitest';
import { fontFamilyStack, CJK_FALLBACK } from '../../static/src/core/ooxmlspreadsheet/vr/font_map';

describe('fontFamilyStack', () => {
    it('Latin metric-compatible 替換', () => {
        expect(fontFamilyStack('Calibri')).toContain("'Carlito'");
        expect(fontFamilyStack('Arial')).toContain("'Liberation Sans'");
        expect(fontFamilyStack('Times New Roman')).toContain("'Liberation Serif'");
    });
    it('CJK / 未知字型保留原名 + CJK 回退', () => {
        const s = fontFamilyStack('標楷體');
        expect(s).toContain("'標楷體'");
        expect(s).toContain('WenQuanYi Zen Hei');
    });
    it('無字型名 → 純 CJK 回退鏈', () => {
        expect(fontFamilyStack(undefined)).toBe(CJK_FALLBACK);
    });
    it('所有堆疊都含 CJK 回退（確保中文字有字型）', () => {
        for (const f of ['Calibri', '新細明體', 'Unknown Font']) {
            expect(fontFamilyStack(f)).toContain('WenQuanYi Zen Hei');
        }
    });
    it('去除字型名中的單引號（避免 CSS 破壞）', () => {
        expect(fontFamilyStack("Bad'Name")).not.toMatch(/'Bad'Name'/);
    });
});
