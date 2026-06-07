// number_format.test.ts — Excel 日期序號 → 日期字串（規劃書 §2.3 最小版）
import { describe, it, expect } from 'vitest';
import {
    civilFromDays,
    excelSerialToYmd,
    formatExcelDate,
} from '../../static/src/core/ooxmlspreadsheet/number_format';

describe('civilFromDays — Hinnant 民曆演算法', () => {
    it('unix epoch', () => {
        expect(civilFromDays(0)).toEqual({ y: 1970, m: 1, d: 1 });
    });
    it('前一天 / 後一月', () => {
        expect(civilFromDays(-1)).toEqual({ y: 1969, m: 12, d: 31 });
        expect(civilFromDays(31)).toEqual({ y: 1970, m: 2, d: 1 });
    });
    it('閏年 2 月底', () => {
        // 2024-02-29 距 1970-01-01 = 19782 天
        expect(civilFromDays(19782)).toEqual({ y: 2024, m: 2, d: 29 });
    });
});

describe('excelSerialToYmd / formatExcelDate', () => {
    it('serial 25569 = 1970-01-01（Excel epoch 對齊）', () => {
        expect(excelSerialToYmd(25569)).toEqual({ y: 1970, m: 1, d: 1 });
    });
    it('serial 45875 = 2025-08-06（golden 實檔驗證）', () => {
        expect(formatExcelDate(45875)).toBe('2025-08-06');
    });
    it('小數序號取整數部分（日期不含時間）', () => {
        expect(formatExcelDate(45875.625)).toBe('2025-08-06');
    });
    it('零padding 補齊', () => {
        // serial 367 = 1901-01-01（base 1899-12-30 + 367）
        expect(formatExcelDate(367)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
});
