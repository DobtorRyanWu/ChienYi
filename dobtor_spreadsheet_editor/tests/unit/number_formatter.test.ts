// number_formatter.test.ts — Excel number format → 顯示字串（規劃書 §2.3）
import { describe, it, expect } from 'vitest';
import { formatNumber } from '../../static/src/core/ooxmlspreadsheet/number_formatter';

describe('formatNumber — 基本數字', () => {
    it('千分位 + 兩位小數', () => {
        expect(formatNumber(1234.5, '#,##0.00')).toBe('1,234.50');
        expect(formatNumber(1234567.891, '#,##0.00')).toBe('1,234,567.89');
    });
    it('千分位整數（四捨五入）', () => {
        expect(formatNumber(1234.5, '#,##0')).toBe('1,235');
        expect(formatNumber(1234.4, '#,##0')).toBe('1,234');
    });
    it('最小整數位數補零', () => {
        expect(formatNumber(5, '000')).toBe('005');
        expect(formatNumber(0, '#,##0')).toBe('0');
    });
    it('小數固定位數', () => {
        expect(formatNumber(3, '0.00')).toBe('3.00');
        expect(formatNumber(3.14159, '0.0')).toBe('3.1');
    });
    it('ChienYi 估驗用 #,##0.00_ （含尾隨寬度空白）', () => {
        expect(formatNumber(1234.5, '#,##0.00_ ')).toBe('1,234.50 ');
    });
});

describe('formatNumber — 百分比', () => {
    it('0% / 0.0%', () => {
        expect(formatNumber(0.05, '0%')).toBe('5%');
        expect(formatNumber(0.1234, '0.0%')).toBe('12.3%');
        expect(formatNumber(1, '0%')).toBe('100%');
    });
});

describe('formatNumber — 貨幣 / 字面', () => {
    it('引號字面前綴', () => {
        expect(formatNumber(1234.5, '"NT$"#,##0')).toBe('NT$1,235');
    });
    it('[$貨幣] 取符號', () => {
        expect(formatNumber(1234.5, '[$NT$-404]#,##0.00')).toBe('NT$1,234.50');
        expect(formatNumber(1234.5, '[$-404]#,##0')).toBe('1,235'); // 純 locale → 無符號
    });
    it('ChienYi numFmt178「第 # 次估驗附表」', () => {
        expect(formatNumber(5, '"第"\\ #\\ "次估驗附表"\\ ')).toBe('第 5 次估驗附表 ');
    });
});

describe('formatNumber — 負數 / 零 多段', () => {
    it('單段負數補負號', () => {
        expect(formatNumber(-1234.5, '#,##0.00')).toBe('-1,234.50');
    });
    it('負數段用括號（會計）', () => {
        expect(formatNumber(-5, '#,##0;(#,##0)')).toBe('(5)');
        expect(formatNumber(5, '#,##0;(#,##0)')).toBe('5');
    });
    it('零段', () => {
        expect(formatNumber(0, '#,##0;(#,##0);"-"')).toBe('-');
    });
});

describe('formatNumber — General', () => {
    it('General / 空 → 原樣', () => {
        expect(formatNumber(13, 'General')).toBe('13');
        expect(formatNumber(13.5, 'General')).toBe('13.5');
        expect(formatNumber(13, '')).toBe('13');
    });
});
