// to_ospreadsheet.ts — ParsedWorksheet + ConcreteStyle → o-spreadsheet WorkbookData（Phase 4.5 對接）
//
// 產出 o-spreadsheet 的正規化 WorkbookData（styles/formats 池化、cell 以 id 參照），
// 由 OWL 端 `new Model(load(data))` 載入成可編輯試算表。
//
// 範圍（v1）：
//   - content：用萃取值（resolveCellValueStyled）而非原始公式 → 避免 o-spreadsheet 函數覆蓋率落差導致
//     #BAD_EXPR；公式 round-trip 待 Phase 3。
//   - style：bold/italic/strike/underline/fontSize/textColor/fillColor/align/verticalAlign/wrapping
//   - format：numFmtCode（非日期、非 General）
//   - merges、cols 寬度、colNumber/rowNumber
//   - 邊框 v1 不輸出（正規化形狀待瀏覽器驗證後補；無邊框 o-spreadsheet 仍正常渲染）

import { columnWidthToPixels, DEFAULT_MDW } from './units';
import { columnIndexToLetter, parseRange } from './cell_ref';
import { worksheetBounds, type ParsedWorksheet } from './worksheet_parser';
import { resolveCellValueStyled } from './value_resolver';
import { ConcreteStyleResolver, fillBackgroundColor, type ConcreteStyle } from './concrete_style';
import { isDateNumberFormat, type ParsedStyles } from './styles_parser';
import type { ParsedTheme } from './theme_parser';
import type { SharedString } from './shared_strings_parser';

const DEFAULT_COL_WIDTH_CHARS = 8.43;
const MAX_COLS = 200;
const MAX_ROWS = 2000;

export interface OStyle {
    bold?: boolean;
    italic?: boolean;
    strikethrough?: boolean;
    underline?: boolean;
    fontSize?: number;
    textColor?: string;
    fillColor?: string;
    align?: 'left' | 'center' | 'right';
    verticalAlign?: 'top' | 'middle' | 'bottom';
    wrapping?: 'overflow' | 'wrap' | 'clip';
}

export interface OCell {
    content: string;
    style?: number;
    format?: number;
}

export interface OSheet {
    id: string;
    name: string;
    colNumber: number;
    rowNumber: number;
    cells: Record<string, OCell>;
    merges: string[];
    cols: Record<number, { size: number }>;
    rows: Record<number, { size: number }>;
    conditionalFormats: unknown[];
    figures: unknown[];
}

export interface OSpreadsheetData {
    version: number;
    sheets: OSheet[];
    styles: Record<number, OStyle>;
    formats: Record<number, string>;
    borders: Record<number, unknown>;
}

/** 以 JSON key 去重的池（1-based id）。*/
class Pool<T> {
    private readonly map = new Map<string, number>();
    private readonly items: T[] = [];
    intern(value: T): number {
        const key = JSON.stringify(value);
        const existing = this.map.get(key);
        if (existing !== undefined) return existing;
        const id = this.items.length + 1;
        this.map.set(key, id);
        this.items.push(value);
        return id;
    }
    toRecord(): Record<number, T> {
        const out: Record<number, T> = {};
        this.items.forEach((v, i) => {
            out[i + 1] = v;
        });
        return out;
    }
}

function mapAlign(h: string | undefined): OStyle['align'] | undefined {
    if (h === 'left' || h === 'right' || h === 'center') return h;
    if (h === 'centerContinuous') return 'center';
    return undefined;
}

function mapVerticalAlign(v: string | undefined): OStyle['verticalAlign'] | undefined {
    if (v === 'top' || v === 'bottom') return v;
    if (v === 'center' || v === 'middle') return 'middle';
    return undefined;
}

function toOStyle(cs: ConcreteStyle): OStyle | undefined {
    const s: OStyle = {};
    if (cs.font.bold) s.bold = true;
    if (cs.font.italic) s.italic = true;
    if (cs.font.strike) s.strikethrough = true;
    if (cs.font.underline && cs.font.underline !== 'none') s.underline = true;
    if (cs.font.size) s.fontSize = cs.font.size;
    if (cs.font.color) s.textColor = `#${cs.font.color}`;
    const bg = fillBackgroundColor(cs.fill);
    if (bg) s.fillColor = `#${bg}`;
    const align = mapAlign(cs.alignment?.horizontal);
    if (align) s.align = align;
    const valign = mapVerticalAlign(cs.alignment?.vertical);
    if (valign) s.verticalAlign = valign;
    if (cs.alignment?.wrapText) s.wrapping = 'wrap';
    return Object.keys(s).length > 0 ? s : undefined;
}

/** cell value → o-spreadsheet content 字串。*/
function toContent(value: string | number | boolean): string {
    if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
    return String(value);
}

function buildSheet(
    sheetId: string,
    name: string,
    ws: ParsedWorksheet,
    ss: SharedString[],
    styles: ParsedStyles,
    resolver: ConcreteStyleResolver,
    stylePool: Pool<OStyle>,
    formatPool: Pool<string>,
): OSheet {
    const bounds = worksheetBounds(ws);
    const colNumber = Math.min(MAX_COLS, Math.max(bounds.cols, ws.maxCol, 1));
    const rowNumber = Math.min(MAX_ROWS, Math.max(bounds.rows, ws.maxRow, 1));

    const cells: Record<string, OCell> = {};
    for (const cell of ws.cells) {
        if (cell.col > colNumber || cell.row > rowNumber) continue;
        const value = resolveCellValueStyled(cell, ss, styles);
        const concrete = resolver.resolve(cell.styleIndex);
        const oStyle = toOStyle(concrete);

        const oCell: OCell = { content: '' };
        if (value !== '') oCell.content = toContent(value);
        if (oStyle) oCell.style = stylePool.intern(oStyle);
        // 數字（非日期）且有非 General 格式 → 套 format
        if (
            typeof value === 'number' &&
            !isDateNumberFormat(styles, concrete.numFmtId) &&
            concrete.numFmtCode &&
            concrete.numFmtCode !== 'General'
        ) {
            oCell.format = formatPool.intern(concrete.numFmtCode);
        }
        // 只收有內容或樣式的 cell
        if (oCell.content !== '' || oCell.style !== undefined) {
            cells[`${columnIndexToLetter(cell.col)}${cell.row}`] = oCell;
        }
    }

    const cols: Record<number, { size: number }> = {};
    for (const col of ws.cols) {
        if (col.width === undefined) continue;
        const size = columnWidthToPixels(col.width, DEFAULT_MDW);
        for (let c = col.min; c <= col.max && c <= colNumber; c++) {
            cols[c - 1] = { size }; // o-spreadsheet 用 0-based 欄索引
        }
    }

    // merges：超出 colNumber/rowNumber 的丟棄（避免 o-spreadsheet 校驗失敗）
    const merges = ws.merges.filter((ref) => {
        try {
            const { end } = parseRange(ref);
            return end.col <= colNumber && end.row <= rowNumber;
        } catch {
            return false;
        }
    });

    return {
        id: sheetId,
        name,
        colNumber,
        rowNumber,
        cells,
        merges,
        cols,
        rows: {},
        conditionalFormats: [],
        figures: [],
    };
}

export interface SheetInput {
    name: string;
    ws: ParsedWorksheet;
}

/** 多工作表 → o-spreadsheet WorkbookData。*/
export function buildOSpreadsheetData(
    sheets: SheetInput[],
    ss: SharedString[],
    styles: ParsedStyles,
    theme: ParsedTheme,
): OSpreadsheetData {
    const resolver = new ConcreteStyleResolver(styles, theme);
    const stylePool = new Pool<OStyle>();
    const formatPool = new Pool<string>();

    const oSheets = sheets.map((s, i) =>
        buildSheet(`sheet${i + 1}`, s.name, s.ws, ss, styles, resolver, stylePool, formatPool),
    );

    return {
        version: 1,
        sheets: oSheets.length > 0 ? oSheets : [emptySheet()],
        styles: stylePool.toRecord(),
        formats: formatPool.toRecord(),
        borders: {},
    };
}

function emptySheet(): OSheet {
    return {
        id: 'sheet1',
        name: 'Sheet1',
        colNumber: 26,
        rowNumber: 100,
        cells: {},
        merges: [],
        cols: {},
        rows: {},
        conditionalFormats: [],
        figures: [],
    };
}
