// shared_formula.test.ts — shared formula 展開（規劃書 §1.6/§3.2）
import { describe, it, expect } from 'vitest';
import { adjustRelativeRefs, expandSharedFormulas } from '../../static/src/core/ooxmlspreadsheet/shared_formula';

describe('adjustRelativeRefs', () => {
    it('相對參照依列位移', () => {
        expect(adjustRelativeRefs('A3*B3', 1, 0)).toBe('A4*B4');
        expect(adjustRelativeRefs('A3*B3', 5, 0)).toBe('A8*B8');
    });
    it('相對參照依欄位移', () => {
        expect(adjustRelativeRefs('A3*B3', 0, 1)).toBe('B3*C3');
        expect(adjustRelativeRefs('A3+A4', 0, 2)).toBe('C3+C4');
    });
    it('$ 絕對部分不動', () => {
        expect(adjustRelativeRefs('$A$3*B3', 1, 1)).toBe('$A$3*C4');
        expect(adjustRelativeRefs('A$3*$B3', 2, 0)).toBe('A$3*$B5');
    });
    it('函數名不被當參照（後接括號）', () => {
        expect(adjustRelativeRefs('SUM(A1:A3)', 1, 0)).toBe('SUM(A2:A4)');
        expect(adjustRelativeRefs('LOG10(A1)', 1, 0)).toBe('LOG10(A2)');
    });
    it('出界保留原樣', () => {
        expect(adjustRelativeRefs('A1', -5, 0)).toBe('A1');
    });
    it('位移為 0 不變', () => {
        expect(adjustRelativeRefs('A3*B3', 0, 0)).toBe('A3*B3');
    });
});

describe('expandSharedFormulas', () => {
    it('follower 依 master 相對位移還原公式', () => {
        const cells = [
            { row: 3, col: 3, formula: 'A3*B3', sharedSi: 0 }, // master C3
            { row: 4, col: 3, formula: undefined, sharedSi: 0 }, // C4 follower
            { row: 5, col: 3, formula: undefined, sharedSi: 0 }, // C5 follower
        ];
        expandSharedFormulas(cells);
        expect(cells[1].formula).toBe('A4*B4');
        expect(cells[2].formula).toBe('A5*B5');
    });
    it('無 master 的 follower 保持 undefined', () => {
        const cells = [{ row: 4, col: 3, formula: undefined, sharedSi: 9 }];
        expandSharedFormulas(cells);
        expect(cells[0].formula).toBeUndefined();
    });
    it('非 shared 公式不受影響', () => {
        const cells = [{ row: 1, col: 1, formula: 'SUM(A1:A2)', sharedSi: undefined }];
        expandSharedFormulas(cells);
        expect(cells[0].formula).toBe('SUM(A1:A2)');
    });
});
