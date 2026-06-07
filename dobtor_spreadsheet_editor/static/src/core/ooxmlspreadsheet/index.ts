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

export const SPRINT = 10;
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

/**
 * importXlsx — 主入口（Phase 1 後實作）
 * @param buffer xlsx 檔案 ArrayBuffer
 * @returns Workbook AST（Phase 1）+ o-spreadsheet model commands（Phase 4.5）
 */
export async function importXlsx(_buffer: ArrayBuffer): Promise<void> {
    throw new Error('importXlsx not yet implemented — Phase 1 task');
}
