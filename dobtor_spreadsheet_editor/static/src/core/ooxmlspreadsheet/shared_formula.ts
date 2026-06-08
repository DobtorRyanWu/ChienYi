// shared_formula.ts — OOXML shared formula 展開（規劃書 §1.6 capture → §3.2 expand）
//
// Excel 以 shared formula 壓縮重複公式：master 格 `<f t="shared" ref="C3:C100" si="0">A3*B3</f>`，
// follower 格 `<f t="shared" si="0"/>`（無公式文字）。本模組把 follower 依相對位移還原公式，
// 讓數萬個重複公式在可編輯試算表即時運算（ChienYi 契約詳細表單檔逾 6 萬個）。

import { columnIndexToLetter, columnLetterToIndex } from './cell_ref';

// A1 參照：可選 $（絕對欄）、1-3 欄字母、可選 $（絕對列）、列號
const REF_RE = /(\$?)([A-Za-z]{1,3})(\$?)([0-9]+)/g;

/** 把公式內的相對參照依 (dRow,dCol) 位移（$ 絕對部分不動）。*/
export function adjustRelativeRefs(formula: string, dRow: number, dCol: number): string {
    if (dRow === 0 && dCol === 0) return formula;
    return formula.replace(REF_RE, (match, absCol: string, letters: string, absRow: string, digits: string, offset: number, full: string) => {
        const before = offset > 0 ? full[offset - 1] : '';
        const after = full[offset + match.length] ?? '';
        // 後接 "(" → 函數名；前接英數底線 → 識別字片段（如 sheet 名）→ 不視為 cell 參照
        if (after === '(') return match;
        if (/[A-Za-z0-9_]/.test(before)) return match;

        const colIdx = columnLetterToIndex(letters);
        const rowNum = parseInt(digits, 10);
        const newColIdx = absCol ? colIdx : colIdx + dCol;
        const newRowNum = absRow ? rowNum : rowNum + dRow;
        if (newColIdx < 1 || newRowNum < 1) return match; // 出界 → 保留原樣

        const col = absCol ? letters : columnIndexToLetter(newColIdx);
        const row = absRow ? digits : String(newRowNum);
        return `${absCol}${col}${absRow}${row}`;
    });
}

interface SharedCell {
    row: number;
    col: number;
    formula?: string;
    sharedSi?: number;
}

/**
 * 展開 cells 內的 shared formula：follower（有 si、無公式）依 master 相對位移還原公式。
 * 原地修改 cells（設定 follower 的 formula）。
 */
export function expandSharedFormulas(cells: SharedCell[]): void {
    // master：同時有 si 與公式文字
    const masters = new Map<number, { row: number; col: number; formula: string }>();
    for (const c of cells) {
        if (c.sharedSi !== undefined && c.formula) {
            if (!masters.has(c.sharedSi)) masters.set(c.sharedSi, { row: c.row, col: c.col, formula: c.formula });
        }
    }
    if (masters.size === 0) return;
    for (const c of cells) {
        if (c.sharedSi !== undefined && !c.formula) {
            const m = masters.get(c.sharedSi);
            if (m) c.formula = adjustRelativeRefs(m.formula, c.row - m.row, c.col - m.col);
        }
    }
}
