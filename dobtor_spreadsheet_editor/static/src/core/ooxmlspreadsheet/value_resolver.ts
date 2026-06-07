// value_resolver.ts — 結合 worksheet + styles 的 cell value 解析（規劃書 §2.3）
//
// §1.6 的 resolveCellValue 不認識樣式（純語意層），日期序號維持 number。
// 本層引入 styles：當 cell 為數字且其 numFmt 為日期格式時，序號 → 日期字串，補上提取缺口。
// 放獨立模組以避免 worksheet_parser 反向相依 styles_parser。

import { resolveCellValue, type Cell, type CellValue, type ParsedWorksheet } from './worksheet_parser';
import { isDateNumberFormat, type ParsedStyles } from './styles_parser';
import type { SharedString } from './shared_strings_parser';
import { formatExcelDate } from './number_format';

/**
 * 解析 cell value，並在「數字 + 日期格式」時轉成日期字串。
 * styles 為 undefined 時退化為 §1.6 純語意解析。
 */
export function resolveCellValueStyled(
    cell: Cell,
    sharedStrings: SharedString[],
    styles: ParsedStyles | undefined,
): CellValue {
    const base = resolveCellValue(cell, sharedStrings);
    if (typeof base !== 'number' || styles === undefined || cell.styleIndex === undefined) {
        return base;
    }
    const xf = styles.cellXfs[cell.styleIndex];
    if (xf && isDateNumberFormat(styles, xf.numFmtId)) {
        return formatExcelDate(base);
    }
    return base;
}

/** 建 (row,col) → CellValue 對照表，套用日期格式轉換。*/
export function buildValueMapStyled(
    parsed: ParsedWorksheet,
    sharedStrings: SharedString[],
    styles: ParsedStyles | undefined,
): Map<string, CellValue> {
    const map = new Map<string, CellValue>();
    for (const cell of parsed.cells) {
        const v = resolveCellValueStyled(cell, sharedStrings, styles);
        if (v !== '') map.set(`${cell.row}:${cell.col}`, v);
    }
    return map;
}
