// worksheet_parser.ts — 解析 xl/worksheets/sheetN.xml（規劃書 §1.6，核心）
//
// 提取 cell value（含型別解析 + sharedString 解參照）、公式、合併儲存格、欄資訊、凍結窗格。
// cell value 是 Phase 1 Exit「提取率 > 95%」的量測對象，對照 calamine golden 比對。

import { parseXml, toArray, attr, intAttr, boolAttr, textOf, decodeOoxmlEscapes } from './xml_util';
import { parseCellRef, parseRange } from './cell_ref';
import { parseStringItem, type SharedString } from './shared_strings_parser';
import { parseConditionalFormattings, type ConditionalFormatting } from './cf_parser';
import { parseDataValidations, type DataValidation } from './dv_parser';

/** OOXML cell type（t 屬性）。預設（無 t）視為 number。*/
export type CellType = 'n' | 's' | 'str' | 'b' | 'e' | 'inlineStr' | 'd';

/** 解析後的 cell value（'' 表空格，與 calamine 對齊）。*/
export type CellValue = string | number | boolean;

export interface Cell {
    ref: string;
    row: number; // 1-based
    col: number; // 1-based
    type: CellType;
    styleIndex: number | undefined; // s 屬性
    /** 原始 <v> 文字（未轉型）；空格或 inlineStr 為 undefined。*/
    raw: string | undefined;
    /** 公式文字（<f>）；無公式 undefined。*/
    formula: string | undefined;
    /** inline 字串（t="inlineStr"）。*/
    inline: SharedString | undefined;
}

export interface ColumnInfo {
    min: number;
    max: number;
    width: number | undefined;
    customWidth: boolean;
    hidden: boolean;
    bestFit: boolean;
}

export interface FreezePanes {
    xSplit: number;
    ySplit: number;
    topLeftCell: string | undefined;
}

export interface ParsedWorksheet {
    dimensionRef: string | undefined;
    cols: ColumnInfo[];
    cells: Cell[];
    /** 合併範圍 ref 清單（如 "A1:I1"）。*/
    merges: string[];
    /** 自訂列高（1-based row → 高度 point）；無 customHeight 的列不入。*/
    rowHeights: Map<number, number>;
    /** 條件格式（§1.7）。*/
    conditionalFormatting: ConditionalFormatting[];
    /** 資料驗證（§1.8）。*/
    dataValidations: DataValidation[];
    freeze: FreezePanes | undefined;
    showGridLines: boolean;
    /** 最大行/列（1-based）；無資料為 0。*/
    maxRow: number;
    maxCol: number;
}

function parseCols(wsData: Record<string, unknown>): ColumnInfo[] {
    const colsContainer = wsData['cols'];
    if (colsContainer === undefined) return [];
    return toArray<unknown>((colsContainer as Record<string, unknown>)['col']).map((c) => {
        const w = attr(c, 'width');
        return {
            min: intAttr(c, 'min') ?? 0,
            max: intAttr(c, 'max') ?? 0,
            width: w !== undefined ? Number(w) : undefined,
            customWidth: boolAttr(c, 'customWidth'),
            hidden: boolAttr(c, 'hidden'),
            bestFit: boolAttr(c, 'bestFit'),
        };
    });
}

function parseFreeze(wsData: Record<string, unknown>): FreezePanes | undefined {
    const views = wsData['sheetViews'];
    if (views === undefined) return undefined;
    const view = toArray<unknown>((views as Record<string, unknown>)['sheetView'])[0];
    if (view === undefined || typeof view !== 'object') return undefined;
    const pane = (view as Record<string, unknown>)['pane'];
    if (pane === undefined) return undefined;
    const xSplit = intAttr(pane, 'xSplit') ?? 0;
    const ySplit = intAttr(pane, 'ySplit') ?? 0;
    if (xSplit === 0 && ySplit === 0) return undefined;
    return { xSplit, ySplit, topLeftCell: attr(pane, 'topLeftCell') };
}

function parseCell(cRaw: unknown): Cell {
    const c = (cRaw ?? {}) as Record<string, unknown>;
    const ref = attr(c, 'r') ?? '';
    const coord = ref ? parseCellRef(ref) : { row: 0, col: 0 };
    const type = (attr(c, 't') ?? 'n') as CellType;

    let raw: string | undefined;
    let inline: SharedString | undefined;
    if (type === 'inlineStr') {
        const is = c['is'];
        if (is !== undefined) inline = parseStringItem(is as Record<string, unknown>);
    } else if ('v' in c) {
        raw = textOf(c['v']);
    }

    let formula: string | undefined;
    if ('f' in c) {
        const f = textOf(c['f']);
        formula = f === '' ? undefined : f;
    }

    return {
        ref,
        row: coord.row,
        col: coord.col,
        type,
        styleIndex: intAttr(c, 's'),
        raw,
        formula,
        inline,
    };
}

export class WorksheetParser {
    static parse(xmlText: string): ParsedWorksheet {
        const xml = parseXml(xmlText);
        const ws = (xml['worksheet'] ?? {}) as Record<string, unknown>;

        const dimensionRef = attr(ws['dimension'], 'ref');
        const cols = parseCols(ws);
        const freeze = parseFreeze(ws);
        const showGridLines =
            attr(toArray<unknown>((ws['sheetViews'] as Record<string, unknown>)?.['sheetView'])[0], 'showGridLines') !==
            '0';

        // ── sheetData → cells ──
        const sheetData = (ws['sheetData'] ?? {}) as Record<string, unknown>;
        const cells: Cell[] = [];
        const rowHeights = new Map<number, number>();
        let maxRow = 0;
        let maxCol = 0;
        for (const rowRaw of toArray<unknown>(sheetData['row'])) {
            const row = (rowRaw ?? {}) as Record<string, unknown>;
            // 自訂列高（customHeight=1 才視為使用者設定）
            const rIdx = intAttr(row, 'r');
            const ht = attr(row, 'ht');
            if (rIdx !== undefined && ht !== undefined && boolAttr(row, 'customHeight')) {
                rowHeights.set(rIdx, Number(ht));
            }
            for (const cRaw of toArray<unknown>(row['c'])) {
                const cell = parseCell(cRaw);
                // 收有值/公式/inline 的 cell；另收「有樣式的空白格」（邊框/填色/粗體等，匯出與渲染保真需要）。
                // 對 cell value 提取無害：buildValueMap/buildValueMapStyled 對空值回 '' 不入 map。
                const hasContent =
                    cell.raw !== undefined || cell.formula !== undefined || cell.inline !== undefined;
                if (hasContent || cell.styleIndex !== undefined) {
                    cells.push(cell);
                    if (cell.row > maxRow) maxRow = cell.row;
                    if (cell.col > maxCol) maxCol = cell.col;
                }
            }
        }

        // ── mergeCells ──
        const mergeContainer = ws['mergeCells'];
        const merges = mergeContainer
            ? toArray<unknown>((mergeContainer as Record<string, unknown>)['mergeCell'])
                  .map((m) => attr(m, 'ref'))
                  .filter((r): r is string => r !== undefined)
            : [];

        return {
            dimensionRef,
            cols,
            cells,
            merges,
            rowHeights,
            conditionalFormatting: parseConditionalFormattings(ws),
            dataValidations: parseDataValidations(ws),
            freeze,
            showGridLines,
            maxRow,
            maxCol,
        };
    }
}

/**
 * 解析單一 cell 的型別化 value（依 t 屬性 + sharedStrings 解參照）。
 * 空格回 ''（與 calamine to_python 對齊）。
 * 注意：日期序號（type='n' 但格式為日期）此層不轉日期字串，待 §2.3 NumberFormatCompiler。
 */
export function resolveCellValue(cell: Cell, sharedStrings: SharedString[]): CellValue {
    switch (cell.type) {
        case 'inlineStr':
            return cell.inline?.text ?? '';
        case 's': {
            if (cell.raw === undefined) return '';
            const idx = Number.parseInt(cell.raw, 10);
            return sharedStrings[idx]?.text ?? '';
        }
        case 'str':
            return cell.raw !== undefined ? decodeOoxmlEscapes(cell.raw) : '';
        case 'b':
            return cell.raw === '1';
        case 'e':
            return cell.raw ?? '';
        case 'd':
            return cell.raw ?? '';
        case 'n':
        default: {
            if (cell.raw === undefined || cell.raw === '') return '';
            const n = Number(cell.raw);
            return Number.isNaN(n) ? cell.raw : n;
        }
    }
}

/**
 * 建 (row,col) → CellValue 的對照表（1-based），供 golden grid 逐格比對。
 */
export function buildValueMap(
    parsed: ParsedWorksheet,
    sharedStrings: SharedString[],
): Map<string, CellValue> {
    const map = new Map<string, CellValue>();
    for (const cell of parsed.cells) {
        const v = resolveCellValue(cell, sharedStrings);
        if (v !== '') map.set(`${cell.row}:${cell.col}`, v);
    }
    return map;
}

/** 解析 dimension ref（"A1:J41"）的列數/欄數；無則回 maxRow/maxCol。*/
export function worksheetBounds(parsed: ParsedWorksheet): { rows: number; cols: number } {
    if (parsed.dimensionRef) {
        const { end } = parseRange(parsed.dimensionRef);
        return { rows: end.row, cols: end.col };
    }
    return { rows: parsed.maxRow, cols: parsed.maxCol };
}
