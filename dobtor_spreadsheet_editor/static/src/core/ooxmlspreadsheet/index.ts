// dobtor_spreadsheet_editor — OOXML SpreadsheetML Parser entry
//
// Sprint 0：空殼 export
// Sprint 2（Phase 1 §1.1-1.2）：PackageReader（OPC 容器）+ units（單位系統）
// Sprint 3（Phase 1 §1.3-1.4）：WorkbookParser + SharedStringsParser
// Sprint 4（Phase 1 §1.6）：WorksheetParser（cell value 提取）+ cell_ref
// Sprint 5（Phase 1 §1.5）：StylesParser（numFmts/fonts/fills/borders/cellXfs/dxfs）+ color
// Sprint 6（§2.3 最小版）：日期序號 → 日期字串（number_format + value_resolver）
// Sprint 7（§2.1）：StyleResolver（xf cascade 攤平成 ResolvedStyle）
// Sprint 8（§1.9 + §2.2）：ThemeParser + ThemeResolver（theme/indexed/tint → 具體 RGB）
// Sprint 9（§1.7）：CFParser（條件格式 rules）
// Sprint 10：ConcreteStyleResolver（StyleResolver + ThemeResolver → 全具體 RGB 樣式，Phase 4.5 對接前置）
//
// 對接層：parser → ast → style/formula/cf/... compiler → XlsxModelBridge → o-spreadsheet model commands

export const SPRINT = 19;
export const BUILD_DATE = '2026-06-07';
export const TARGET_FIDELITY = 'Google Sheets / Excel A- (95%)';

// Phase 1 §1.1 — OPC 容器讀取
export { PackageReader } from './package_reader';
export type { Relationship } from './package_reader';
// Phase 1 §1.2 — 單位系統
export * from './units';
// Phase 1 §1.3 — 活頁簿
export { WorkbookParser } from './workbook_parser';
export type {
    ParsedWorkbook,
    WorkbookSheet,
    SheetState,
    DefinedName,
    WorkbookView,
    RefMode,
    CalcProperties,
} from './workbook_parser';
// Phase 1 §1.4 — 共享字串
export { SharedStringsParser, parseStringItem } from './shared_strings_parser';
export type {
    SharedString,
    RichTextRun,
    RunProperties,
    VertAlign,
} from './shared_strings_parser';
// Phase 1 §1.6 — 工作表 + cell value 提取
export {
    WorksheetParser,
    resolveCellValue,
    buildValueMap,
    worksheetBounds,
} from './worksheet_parser';
export type {
    ParsedWorksheet,
    Cell,
    CellType,
    CellValue,
    ColumnInfo,
    FreezePanes,
} from './worksheet_parser';
// cell ref 工具
export {
    columnLetterToIndex,
    columnIndexToLetter,
    parseCellRef,
    parseRange,
} from './cell_ref';
export type { CellCoord, CellRange } from './cell_ref';
// Phase 1 §1.5 — 樣式
export {
    StylesParser,
    numberFormatCode,
    isDateFormatCode,
    isDateNumberFormat,
} from './styles_parser';
export type {
    ParsedStyles,
    Font,
    Fill,
    Border,
    BorderEdge,
    Alignment,
    CellXf,
    Dxf,
} from './styles_parser';
export { parseColor } from './color';
export type { Color } from './color';
// §2.3 最小版 — 日期序號轉換 + styled value 解析
export { civilFromDays, excelSerialToYmd, formatExcelDate } from './number_format';
export type { Ymd } from './number_format';
// §2.3 — number format 渲染（千分位/貨幣/百分比，僅顯示用）
export { formatNumber } from './number_formatter';
export { resolveCellValueStyled, buildValueMapStyled } from './value_resolver';
// Phase 2 §2.1 — 樣式 cascade 攤平
export { StyleResolver } from './style_resolver';
export type { ResolvedStyle } from './style_resolver';
// §1.9 — 主題解析
export { ThemeParser } from './theme_parser';
export type { ParsedTheme, ThemeColorScheme, ThemeFont } from './theme_parser';
// §2.2 — 主題/indexed/tint 色彩解析
export { ThemeResolver, applyTint } from './theme_resolver';
// Phase 1 §1.7 — 條件格式
export { CFParser, parseConditionalFormattings } from './cf_parser';
export type {
    ConditionalFormatting,
    CfRule,
    CfValueObject,
    ColorScale,
    DataBar,
    IconSet,
} from './cf_parser';
// Phase 4.5 對接層前置 — 全具體 RGB 樣式
export { ConcreteStyleResolver, fillBackgroundColor } from './concrete_style';
export type {
    ConcreteStyle,
    ConcreteFont,
    ConcreteFill,
    ConcreteBorder,
    ConcreteBorderEdge,
} from './concrete_style';

// ── Phase 4.5 對接入口（Odoo UI 用）────────────────────────────────────
import { PackageReader as _PackageReader } from './package_reader';
import { WorkbookParser as _WorkbookParser } from './workbook_parser';
import { SharedStringsParser as _SharedStringsParser, type SharedString as _SharedString } from './shared_strings_parser';
import { StylesParser as _StylesParser } from './styles_parser';
import { ThemeParser as _ThemeParser } from './theme_parser';
import { WorksheetParser as _WorksheetParser } from './worksheet_parser';
import { renderWorksheetHtml as _renderWorksheetHtml } from './vr/html_render';
import { buildOSpreadsheetData as _buildOSpreadsheetData, type OSpreadsheetData, type SheetInput as _SheetInput } from './to_ospreadsheet';
import { resolveCellValue as _resolveCellValue } from './worksheet_parser';
import { buildXlsx as _buildXlsx, type WriteSheet as _WriteSheet, type WriteCell as _WriteCell } from './xlsx_writer';

export { buildOSpreadsheetData } from './to_ospreadsheet';
export type { OSpreadsheetData, OSheet, OCell, OStyle, SheetInput } from './to_ospreadsheet';
export { buildXlsx } from './xlsx_writer';
export type { WriteSheet, WriteCell } from './xlsx_writer';

export interface XlsxPreview {
    /** 全部工作表名稱（依順序）。*/
    sheets: string[];
    /** 目前渲染的工作表索引。*/
    activeSheet: number;
    /** 該工作表的 HTML 預覽（<table>）。*/
    html: string;
}

/**
 * 解析 xlsx 並把指定工作表渲染成 HTML 預覽（Odoo 前端用）。
 * @param buffer     xlsx ArrayBuffer
 * @param sheetIndex 要渲染的工作表索引（預設 0）
 */
export function importXlsxToHtmlPreview(buffer: ArrayBuffer, sheetIndex = 0): XlsxPreview {
    const pkg = _PackageReader.fromBuffer(buffer);
    const wbp = new _WorkbookParser(pkg);
    const wb = wbp.parse();

    const ssPart = wbp.sharedStringsPart();
    const ss: _SharedString[] =
        ssPart && pkg.hasPart(ssPart) ? _SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
    const stPart = wbp.stylesPart();
    const styles = stPart && pkg.hasPart(stPart)
        ? _StylesParser.parse(pkg.getPartText(stPart))
        : _StylesParser.parse('<styleSheet/>');
    const thPart = wbp.themePart();
    const theme = thPart && pkg.hasPart(thPart)
        ? _ThemeParser.parse(pkg.getPartText(thPart))
        : _ThemeParser.default();

    const idx = Math.max(0, Math.min(sheetIndex, wb.sheets.length - 1));
    const target = wb.sheets[idx]?.target;
    let html = '';
    if (target && pkg.hasPart(target)) {
        const ws = _WorksheetParser.parse(pkg.getPartText(target));
        html = _renderWorksheetHtml(ws, ss, styles, theme);
    }
    return { sheets: wb.sheets.map((s) => s.name), activeSheet: idx, html };
}

/**
 * 解析 xlsx → o-spreadsheet WorkbookData（可編輯試算表用，OWL 端 new Model(load(data))）。
 */
export function importXlsxToOSpreadsheetData(buffer: ArrayBuffer): OSpreadsheetData {
    const pkg = _PackageReader.fromBuffer(buffer);
    const wbp = new _WorkbookParser(pkg);
    const wb = wbp.parse();

    const ssPart = wbp.sharedStringsPart();
    const ss: _SharedString[] =
        ssPart && pkg.hasPart(ssPart) ? _SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];
    const stPart = wbp.stylesPart();
    const styles = stPart && pkg.hasPart(stPart)
        ? _StylesParser.parse(pkg.getPartText(stPart))
        : _StylesParser.parse('<styleSheet/>');
    const thPart = wbp.themePart();
    const theme = thPart && pkg.hasPart(thPart)
        ? _ThemeParser.parse(pkg.getPartText(thPart))
        : _ThemeParser.default();

    const sheets: _SheetInput[] = wb.sheets
        .filter((s) => s.target && pkg.hasPart(s.target))
        .map((s) => ({ name: s.name, ws: _WorksheetParser.parse(pkg.getPartText(s.target!)) }));

    return _buildOSpreadsheetData(sheets, ss, styles, theme);
}

/**
 * 解析 xlsx → 用我方 writer 重新寫出 xlsx（Phase 6 round-trip）。
 * 值用原始萃取（數字保持數字、日期保持序號）以利 round-trip 一致。
 */
export function exportXlsxFromBuffer(buffer: ArrayBuffer): Uint8Array {
    const pkg = _PackageReader.fromBuffer(buffer);
    const wbp = new _WorkbookParser(pkg);
    const wb = wbp.parse();
    const ssPart = wbp.sharedStringsPart();
    const ss: _SharedString[] =
        ssPart && pkg.hasPart(ssPart) ? _SharedStringsParser.parse(pkg.getPartText(ssPart)) : [];

    const sheets: _WriteSheet[] = wb.sheets
        .filter((s) => s.target && pkg.hasPart(s.target))
        .map((s) => {
            const ws = _WorksheetParser.parse(pkg.getPartText(s.target!));
            const cells: _WriteCell[] = ws.cells.map((cell) => {
                const value = _resolveCellValue(cell, ss);
                const wc: _WriteCell = { row: cell.row, col: cell.col };
                if (value !== '') wc.value = value;
                if (cell.formula !== undefined) wc.formula = cell.formula;
                return wc;
            });
            return { name: s.name, cells, merges: ws.merges };
        });

    return _buildXlsx(sheets);
}
