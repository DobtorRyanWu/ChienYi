// cell_ref.ts — A1 表示法與 (row, col) 數值座標互轉
//
// 全程 1-based（A=1、row 1=1），與 OOXML cell ref 一致。

const CHAR_A = 65; // 'A'
const ALPHABET = 26;

/** 欄字母 → 1-based 欄索引。'A'→1、'Z'→26、'AA'→27。*/
export function columnLetterToIndex(letters: string): number {
    let n = 0;
    for (let i = 0; i < letters.length; i++) {
        n = n * ALPHABET + (letters.charCodeAt(i) - CHAR_A + 1);
    }
    return n;
}

/** 1-based 欄索引 → 欄字母。1→'A'、27→'AA'。*/
export function columnIndexToLetter(index: number): string {
    let n = index;
    let s = '';
    while (n > 0) {
        const rem = (n - 1) % ALPHABET;
        s = String.fromCharCode(CHAR_A + rem) + s;
        n = Math.floor((n - 1) / ALPHABET);
    }
    return s;
}

export interface CellCoord {
    row: number; // 1-based
    col: number; // 1-based
}

const REF_RE = /^([A-Z]+)(\d+)$/;

/** 解析 "C5" → { row: 5, col: 3 }。格式不符丟錯。*/
export function parseCellRef(ref: string): CellCoord {
    const m = REF_RE.exec(ref);
    if (!m) throw new Error(`Invalid cell ref: ${ref}`);
    return { col: columnLetterToIndex(m[1]), row: Number.parseInt(m[2], 10) };
}

/** 解析範圍 "A1:J41" → { start, end }（單格 "A1" 時 start===end）。*/
export interface CellRange {
    start: CellCoord;
    end: CellCoord;
}

export function parseRange(ref: string): CellRange {
    const colon = ref.indexOf(':');
    if (colon === -1) {
        const c = parseCellRef(ref);
        return { start: c, end: c };
    }
    return {
        start: parseCellRef(ref.slice(0, colon)),
        end: parseCellRef(ref.slice(colon + 1)),
    };
}
