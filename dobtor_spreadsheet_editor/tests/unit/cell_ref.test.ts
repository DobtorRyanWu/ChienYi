// cell_ref.test.ts — A1 ↔ (row,col) 互轉（規劃書 §1.6 支援）
import { describe, it, expect } from 'vitest';
import {
    columnLetterToIndex,
    columnIndexToLetter,
    parseCellRef,
    parseRange,
} from '../../static/src/core/ooxmlspreadsheet/cell_ref';

describe('cell_ref — 欄字母 ↔ 索引', () => {
    it('字母轉索引', () => {
        expect(columnLetterToIndex('A')).toBe(1);
        expect(columnLetterToIndex('Z')).toBe(26);
        expect(columnLetterToIndex('AA')).toBe(27);
        expect(columnLetterToIndex('AB')).toBe(28);
        expect(columnLetterToIndex('AZ')).toBe(52);
        expect(columnLetterToIndex('BA')).toBe(53);
    });
    it('索引轉字母（互逆）', () => {
        for (const n of [1, 26, 27, 52, 53, 702, 703]) {
            expect(columnLetterToIndex(columnIndexToLetter(n))).toBe(n);
        }
        expect(columnIndexToLetter(1)).toBe('A');
        expect(columnIndexToLetter(27)).toBe('AA');
    });
});

describe('cell_ref — 解析 ref / range', () => {
    it('parseCellRef', () => {
        expect(parseCellRef('C5')).toEqual({ col: 3, row: 5 });
        expect(parseCellRef('AA10')).toEqual({ col: 27, row: 10 });
    });
    it('非法 ref 丟錯', () => {
        expect(() => parseCellRef('5C')).toThrow(/Invalid/);
    });
    it('parseRange', () => {
        expect(parseRange('A1:J41')).toEqual({
            start: { col: 1, row: 1 },
            end: { col: 10, row: 41 },
        });
    });
    it('parseRange 單格', () => {
        const r = parseRange('B2');
        expect(r.start).toEqual(r.end);
        expect(r.end).toEqual({ col: 2, row: 2 });
    });
});
