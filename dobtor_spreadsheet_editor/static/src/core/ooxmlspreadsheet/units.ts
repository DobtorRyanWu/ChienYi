// units.ts — OOXML SpreadsheetML 單位系統（規劃書 §1.2）
//
// xlsx 內混用多種長度單位，渲染前需統一轉成 pixel：
//   - EMU（English Metric Unit）：DrawingML 圖形/圖片座標，1 inch = 914400 EMU
//   - point（pt）：字級、列高，1 inch = 72 pt
//   - pixel（px）：螢幕渲染基準，預設 96 DPI
//   - column-width units：Excel 特殊單位 =「以最大數字字元寬度為基準的字元數」
//
// 參考：ECMA-376 Part 1 §18.3.1.13（col width）、§22.1.2（EMU）

// ── 不可變常數（紀律：禁止 magic number）──────────────────────────────
export const EMU_PER_INCH = 914400;
export const POINTS_PER_INCH = 72;
export const EMU_PER_POINT = EMU_PER_INCH / POINTS_PER_INCH; // 12700
export const DEFAULT_DPI = 96;

/**
 * Calibri 11pt @ 96 DPI 的「最大數字字元寬度」(Maximum Digit Width, MDW)。
 * Excel 預設字型下 MDW = 7px，column width 的字元單位以此為基準。
 * 不同預設字型 MDW 不同（Arial 10 = 7、Calibri 11 = 7），故開放為參數。
 */
export const DEFAULT_MDW = 7;

/** Excel column width 字元數 → pixel 的固定 padding（左右邊距），單位 px。*/
const COL_WIDTH_PADDING_PX = 5;

// ── point ↔ pixel ────────────────────────────────────────────────────
export function pointsToPixels(pt: number, dpi: number = DEFAULT_DPI): number {
    return (pt * dpi) / POINTS_PER_INCH;
}

export function pixelsToPoints(px: number, dpi: number = DEFAULT_DPI): number {
    return (px * POINTS_PER_INCH) / dpi;
}

// ── EMU ↔ pixel ──────────────────────────────────────────────────────
export function emuToPixels(emu: number, dpi: number = DEFAULT_DPI): number {
    return (emu * dpi) / EMU_PER_INCH;
}

export function pixelsToEmu(px: number, dpi: number = DEFAULT_DPI): number {
    return Math.round((px * EMU_PER_INCH) / dpi);
}

// ── EMU ↔ point ──────────────────────────────────────────────────────
export function emuToPoints(emu: number): number {
    return emu / EMU_PER_POINT;
}

export function pointsToEmu(pt: number): number {
    return Math.round(pt * EMU_PER_POINT);
}

// ── 列高（row ht 屬性 = point）↔ pixel ────────────────────────────────
// 注意：規劃書 §1.2 寫「half-points」，但 ECMA-376 §18.3.1.73 明定 row@ht 單位為
// point（半點是 WordprocessingML 的慣例）。此處依規格以 point 處理。
export function rowHeightToPixels(ht: number, dpi: number = DEFAULT_DPI): number {
    return pointsToPixels(ht, dpi);
}

// ── 欄寬（col width 屬性 = 字元數）↔ pixel ────────────────────────────
/**
 * 儲存的 column width（字元數）→ pixel。
 * ECMA-376 §18.3.1.13 note 反算式：
 *   pixels = Truncate( ( (256 * width + Truncate(128 / MDW)) / 256 ) * MDW )
 */
export function columnWidthToPixels(width: number, mdw: number = DEFAULT_MDW): number {
    return Math.trunc(((256 * width + Math.trunc(128 / mdw)) / 256) * mdw);
}

/**
 * pixel → 儲存的 column width（字元數），為 columnWidthToPixels 的近似反函式。
 * 用於 Phase 6 匯出對稱性。
 */
export function pixelsToColumnWidth(px: number, mdw: number = DEFAULT_MDW): number {
    return Math.trunc(((px - COL_WIDTH_PADDING_PX) / mdw) * 100 + 0.5) / 100;
}
