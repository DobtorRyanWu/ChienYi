// style_resolver.ts — xf cascade 攤平成 ResolvedStyle（規劃書 §2.1）
//
// cell 的 s 屬性 → cellXfs[s]（直接格式）→ 可繼承 cellStyleXfs[xfId]（named style 基底）。
// 各屬性群（numFmt/font/fill/border/alignment）依 cellXf 的 applyX 旗標決定：
//   applyX=1 → 用 cellXf 自身的 id；否則繼承 named style 的 id。
// 無 named style（xfId 未定義）時一律用 cellXf 自身 id。
// 輸出攤平後的單一 ResolvedStyle（具體 font/fill/border 物件 + numFmt 解析 + isDate）。
//
// 注意：theme/indexed color → 具體 RGB 是 §2.2 ThemeResolver；本層只攤平索引、不解色。

import type { ParsedStyles, CellXf, Font, Fill, Border, Alignment } from './styles_parser';
import { numberFormatCode, isDateNumberFormat } from './styles_parser';

export interface ResolvedStyle {
    numFmtId: number;
    numFmtCode: string | undefined;
    isDate: boolean;
    font: Font;
    fill: Fill;
    border: Border;
    alignment: Alignment | undefined;
}

const EMPTY_FONT: Readonly<Font> = {};
const EMPTY_FILL: Readonly<Fill> = {};
const EMPTY_BORDER: Readonly<Border> = {};

export class StyleResolver {
    private readonly cache = new Map<number, ResolvedStyle>();

    constructor(private readonly styles: ParsedStyles) {}

    /**
     * 解析 cell 的 styleIndex（s 屬性）→ ResolvedStyle。
     * styleIndex 未定義（cell 無 s）→ 用預設 cellXf（index 0）或全空樣式。
     */
    resolve(styleIndex: number | undefined): ResolvedStyle {
        const idx = styleIndex ?? 0;
        const cached = this.cache.get(idx);
        if (cached) return cached;
        const xf = this.styles.cellXfs[idx];
        const resolved = xf ? this.resolveXf(xf) : this.defaultStyle();
        this.cache.set(idx, resolved);
        return resolved;
    }

    /** 對單一 cellXf 做 cascade 攤平。*/
    resolveXf(xf: CellXf): ResolvedStyle {
        const parent =
            xf.xfId !== undefined ? this.styles.cellStyleXfs[xf.xfId] : undefined;
        const hasParent = parent !== undefined;

        // 各屬性依 applyX 旗標取 cellXf 或 named style 的 id（無 parent 時恆用 cellXf）。
        // numFmt 例外：cellXf 自身有非 0 numFmtId 時直接採用（與 Excel/calamine 一致——
        // 部分工具如 openpyxl 省略 applyNumberFormat，但 numFmtId≠0 即表示套該格式）。
        const numFmtId =
            hasParent && !xf.applyNumberFormat && xf.numFmtId === 0 ? parent.numFmtId : xf.numFmtId;
        const fontId = hasParent && !xf.applyFont ? parent.fontId : xf.fontId;
        const fillId = hasParent && !xf.applyFill ? parent.fillId : xf.fillId;
        const borderId = hasParent && !xf.applyBorder ? parent.borderId : xf.borderId;
        const alignment = hasParent && !xf.applyAlignment ? parent.alignment : xf.alignment;

        return {
            numFmtId,
            numFmtCode: numberFormatCode(this.styles, numFmtId),
            isDate: isDateNumberFormat(this.styles, numFmtId),
            font: this.styles.fonts[fontId] ?? EMPTY_FONT,
            fill: this.styles.fills[fillId] ?? EMPTY_FILL,
            border: this.styles.borders[borderId] ?? EMPTY_BORDER,
            alignment,
        };
    }

    private defaultStyle(): ResolvedStyle {
        return {
            numFmtId: 0,
            numFmtCode: numberFormatCode(this.styles, 0),
            isDate: false,
            font: this.styles.fonts[0] ?? EMPTY_FONT,
            fill: this.styles.fills[0] ?? EMPTY_FILL,
            border: this.styles.borders[0] ?? EMPTY_BORDER,
            alignment: undefined,
        };
    }
}
