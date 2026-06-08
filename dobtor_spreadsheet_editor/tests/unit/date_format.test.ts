// date_format.test.ts — 日期格式碼渲染含民國年（§2.3）
import { describe, it, expect } from 'vitest';
import { formatExcelDateByCode } from '../../static/src/core/ooxmlspreadsheet/number_format';

// 2025-12-15 的 Excel serial = 46006（1899-12-30 基準）
const S = 46006;
describe('formatExcelDateByCode', () => {
    it('民國年 e"年"m"月"d"日"', () => {
        expect(formatExcelDateByCode(S, '[$-404]e"年"m"月"d"日";@')).toBe('114年12月15日');
    });
    it('民國 e/m/d', () => {
        expect(formatExcelDateByCode(S, '[$-404]e/m/d;@')).toBe('114/12/15');
    });
    it('民國 ee.mm.dd（補零）', () => {
        expect(formatExcelDateByCode(S, '[$-404]ee.mm.dd;@')).toBe('114.12.15');
    });
    it('gge 年（民國前綴）', () => {
        expect(formatExcelDateByCode(S, '[$-404]gge"年"m"月"d"日";@')).toBe('民國114年12月15日');
    });
    it('西元 yyyy/m/d', () => {
        expect(formatExcelDateByCode(S, 'yyyy/m/d;@')).toBe('2025/12/15');
    });
    it('m"月"d"日"', () => {
        expect(formatExcelDateByCode(S, 'm"月"d"日"')).toBe('12月15日');
    });
    it('非日期格式 → undefined', () => {
        expect(formatExcelDateByCode(S, '#,##0.00')).toBeUndefined();
    });
});
