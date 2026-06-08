// html_render.ts — ParsedWorksheet + ConcreteStyle → HTML 表格（VR pipeline 的 render 路徑）
//
// 這是「model → DOM」的第一條 render 路徑：把解析出的 cell 值 + 具體樣式 render 成 HTML <table>，
// 供 puppeteer 光柵化成 PNG。注意：HTML 佈局引擎與 LibreOffice 不同，與 golden 的像素差異會偏高，
// 本路徑用於建立 VR 管線與自洽回歸基準，而非一步到位的 LibreOffice 像素對等。

import { columnWidthToPixels, rowHeightToPixels, DEFAULT_MDW } from '../units';
import { parseRange } from '../cell_ref';
import { worksheetBounds, type ParsedWorksheet, type CellValue } from '../worksheet_parser';
import { buildValueMapStyled } from '../value_resolver';
import type { ParsedStyles } from '../styles_parser';
import type { ParsedTheme } from '../theme_parser';
import { ConcreteStyleResolver, fillBackgroundColor, type ConcreteStyle } from '../concrete_style';
import { formatNumber } from '../number_formatter';
import { formatYmdByCode } from '../number_format';
import { fontFamilyStack, CJK_FALLBACK } from './font_map';
import type { SharedString } from '../shared_strings_parser';

// 已轉 ISO 的日期字串（buildValueMapStyled 對日期格輸出 YYYY-MM-DD）
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export interface RenderOptions {
    maxRows?: number;
    maxCols?: number;
    /** 預設欄寬（字元數），無 col 定義時用。*/
    defaultColWidthChars?: number;
    /** 預設列高（point）。*/
    defaultRowHeightPt?: number;
}

// 安全上限放寬以涵蓋完整 sheet（golden 為完整首 sheet），避免截斷造成尺寸不匹配假性差異。
const DEFAULT_MAX_ROWS = 500;
const DEFAULT_MAX_COLS = 80;
const DEFAULT_COL_WIDTH_CHARS = 8.43;
const DEFAULT_ROW_HEIGHT_PT = 15;

const BORDER_WIDTH: Readonly<Record<string, number>> = {
    hair: 1, thin: 1, dotted: 1, dashed: 1,
    medium: 2, mediumDashed: 2,
    thick: 3, double: 3,
};

function esc(s: string): string {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function valueToText(v: CellValue | undefined): string {
    if (v === undefined) return '';
    if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
    return String(v);
}

function edgeCss(side: string, edge: { style?: string; color?: string } | undefined): string {
    if (!edge || !edge.style || edge.style === 'none') return '';
    const w = BORDER_WIDTH[edge.style] ?? 1;
    const kind = edge.style === 'double' ? 'double' : edge.style.includes('dash') ? 'dashed' : edge.style === 'dotted' ? 'dotted' : 'solid';
    const color = edge.color ? `#${edge.color}` : '#000';
    return `border-${side}:${w}px ${kind} ${color};`;
}

function cellCss(style: ConcreteStyle, colW: number, rowH: number): string {
    let css = `width:${colW}px;height:${rowH}px;`;
    const bg = fillBackgroundColor(style.fill);
    if (bg) css += `background:#${bg};`;
    const f = style.font;
    if (f.color) css += `color:#${f.color};`;
    if (f.bold) css += 'font-weight:bold;';
    if (f.italic) css += 'font-style:italic;';
    if (f.size) css += `font-size:${(f.size * 96) / 72}px;`;
    if (f.name) css += `font-family:${fontFamilyStack(f.name)};`;
    const deco: string[] = [];
    if (f.underline && f.underline !== 'none') deco.push('underline');
    if (f.strike) deco.push('line-through');
    if (deco.length) css += `text-decoration:${deco.join(' ')};`;
    const a = style.alignment;
    if (a?.horizontal) css += `text-align:${a.horizontal};`;
    css += `vertical-align:${a?.vertical ?? 'bottom'};`;
    css += a?.wrapText ? 'white-space:normal;' : 'white-space:nowrap;overflow:hidden;';
    css += edgeCss('left', style.border.left);
    css += edgeCss('right', style.border.right);
    css += edgeCss('top', style.border.top);
    css += edgeCss('bottom', style.border.bottom);
    return css;
}

/** 建合併資訊：anchor "r:c" → {rowspan,colspan}；covered "r:c" → true（跳過）。*/
function buildMergeMaps(merges: string[]): {
    anchors: Map<string, { rowspan: number; colspan: number }>;
    covered: Set<string>;
} {
    const anchors = new Map<string, { rowspan: number; colspan: number }>();
    const covered = new Set<string>();
    for (const ref of merges) {
        const { start, end } = parseRange(ref);
        anchors.set(`${start.row}:${start.col}`, {
            rowspan: end.row - start.row + 1,
            colspan: end.col - start.col + 1,
        });
        for (let r = start.row; r <= end.row; r++) {
            for (let c = start.col; c <= end.col; c++) {
                if (r === start.row && c === start.col) continue;
                covered.add(`${r}:${c}`);
            }
        }
    }
    return { anchors, covered };
}

/** 建欄索引（1-based）→ 寬度 px 的對照（依 ws.cols，否則預設）。*/
function buildColWidths(ws: ParsedWorksheet, maxCol: number, defaultChars: number): number[] {
    const widths = new Array<number>(maxCol + 1).fill(columnWidthToPixels(defaultChars, DEFAULT_MDW));
    for (const col of ws.cols) {
        if (col.width === undefined) continue;
        const px = columnWidthToPixels(col.width, DEFAULT_MDW);
        for (let c = col.min; c <= col.max && c <= maxCol; c++) widths[c] = px;
    }
    return widths;
}

/** ParsedWorksheet → 完整 HTML 文件字串。*/
export function renderWorksheetHtml(
    ws: ParsedWorksheet,
    sharedStrings: SharedString[],
    styles: ParsedStyles,
    theme: ParsedTheme,
    opts: RenderOptions = {},
): string {
    const maxRows = opts.maxRows ?? DEFAULT_MAX_ROWS;
    const maxCols = opts.maxCols ?? DEFAULT_MAX_COLS;
    const defaultChars = opts.defaultColWidthChars ?? DEFAULT_COL_WIDTH_CHARS;
    const rowHpx = rowHeightToPixels(opts.defaultRowHeightPt ?? DEFAULT_ROW_HEIGHT_PT);

    // 用 dimension 的完整 used range（涵蓋 golden 的全 sheet 範圍），而非僅有值的 cell 範圍
    const bounds = worksheetBounds(ws);
    const nRows = Math.min(maxRows, Math.max(bounds.rows, ws.maxRow, 1));
    const nCols = Math.min(maxCols, Math.max(bounds.cols, ws.maxCol, 1));

    const resolver = new ConcreteStyleResolver(styles, theme);
    const valueMap = buildValueMapStyled(ws, sharedStrings, styles);
    const styleIndexMap = new Map<string, number | undefined>();
    for (const cell of ws.cells) styleIndexMap.set(`${cell.row}:${cell.col}`, cell.styleIndex);
    const colW = buildColWidths(ws, nCols, defaultChars);
    const { anchors, covered } = buildMergeMaps(ws.merges);

    const rowsHtml: string[] = [];
    for (let r = 1; r <= nRows; r++) {
        const cells: string[] = [];
        for (let c = 1; c <= nCols; c++) {
            const key = `${r}:${c}`;
            if (covered.has(key)) continue;
            const merge = anchors.get(key);
            const span = merge ? ` colspan="${merge.colspan}" rowspan="${merge.rowspan}"` : '';
            const style = resolver.resolve(styleIndexMap.get(key));
            const raw = valueMap.get(key);
            // 數字 + 非 General numFmt → number format（千分位/貨幣/百分比）；
            // 已轉 ISO 的日期字串 + 日期格式碼 → 日期格式（含民國年）；其餘原樣。
            let display: string;
            if (typeof raw === 'number' && style.numFmtCode && style.numFmtCode !== 'General') {
                display = formatNumber(raw, style.numFmtCode);
            } else if (typeof raw === 'string' && style.numFmtCode && ISO_DATE_RE.test(raw)) {
                const [yy, mm, dd] = raw.split('-').map((n) => parseInt(n, 10));
                display = formatYmdByCode({ y: yy, m: mm, d: dd }, style.numFmtCode) ?? valueToText(raw);
            } else {
                display = valueToText(raw);
            }
            cells.push(`<td${span} style="${cellCss(style, colW[c], rowHpx)}">${esc(display)}</td>`);
        }
        rowsHtml.push(`<tr>${cells.join('')}</tr>`);
    }

    return (
        `<!DOCTYPE html><html><head><meta charset="utf-8"><style>` +
        `*{box-sizing:border-box;margin:0;padding:0}` +
        `body{background:#fff}` +
        `table{border-collapse:collapse;table-layout:fixed;font-family:${CJK_FALLBACK};font-size:14.667px}` +
        `td{padding:0 2px;border:1px solid #d4d4d4}` +
        `</style></head><body><table>${rowsHtml.join('')}</table></body></html>`
    );
}
