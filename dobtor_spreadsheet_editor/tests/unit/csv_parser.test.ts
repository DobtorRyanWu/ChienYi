// csv_parser.test.ts — CSV 解析 + 轉 o-spreadsheet
import { describe, it, expect } from 'vitest';
import { parseCsv, csvToOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/csv_parser';

describe('parseCsv', () => {
    it('基本逗號分隔', () => {
        expect(parseCsv('a,b,c\n1,2,3')).toEqual([['a', 'b', 'c'], ['1', '2', '3']]);
    });
    it('引號內逗號/換行/跳脫引號', () => {
        expect(parseCsv('"a,b","c\nd","e""f"')).toEqual([['a,b', 'c\nd', 'e"f']]);
    });
    it('CRLF 換行 + BOM', () => {
        expect(parseCsv('﻿x,y\r\n1,2\r\n')).toEqual([['x', 'y'], ['1', '2']]);
    });
    it('無結尾換行的最後一行不漏', () => {
        expect(parseCsv('a,b\nc,d')).toEqual([['a', 'b'], ['c', 'd']]);
    });
    it('空欄保留', () => {
        expect(parseCsv('a,,c')).toEqual([['a', '', 'c']]);
    });
});

describe('csvToOSpreadsheetData', () => {
    const data = csvToOSpreadsheetData('項次,名稱,金額\n1,測試,1000\n2,項目,2000');
    const sheet = data.sheets[0];
    it('單一工作表 + 維度', () => {
        expect(data.sheets).toHaveLength(1);
        expect(sheet.colNumber).toBe(3);
        expect(sheet.rowNumber).toBe(3);
    });
    it('cell 內容（A1 表頭、B2 值）', () => {
        expect(sheet.cells['A1'].content).toBe('項次');
        expect(sheet.cells['B2'].content).toBe('測試');
        expect(sheet.cells['C3'].content).toBe('2000');
    });
    it('空值不建 cell', () => {
        const d2 = csvToOSpreadsheetData('a,,c').sheets[0];
        expect(d2.cells['B1']).toBeUndefined();
    });
});
