// concrete_style.ts — 把 ResolvedStyle 的抽象 Color 全部解成具體 RGB（Phase 4.5 對接層前置）
//
// 串接 §2.1 StyleResolver（xf cascade → ResolvedStyle，色彩仍為抽象 Color）
//      + §2.2 ThemeResolver（Color → 6-hex RGB）
// → ConcreteStyle：font/fill/border 全部具體 hex（或 undefined = 系統/auto 色，由渲染層補黑/白）。
// 這是餵 o-spreadsheet model commands / VR 像素比對前的「完全具體化」樣式。

import type { ParsedStyles, Font, Fill, Border, Alignment, VertAlign } from './styles_parser';
import type { ParsedTheme } from './theme_parser';
import type { Color } from './color';
import { StyleResolver, type ResolvedStyle } from './style_resolver';
import { ThemeResolver } from './theme_resolver';

export interface ConcreteFont {
    name?: string;
    size?: number;
    bold?: boolean;
    italic?: boolean;
    underline?: string;
    strike?: boolean;
    /** 6-hex RGB；undefined = 系統/auto（渲染層預設黑）。*/
    color?: string;
    family?: number;
    charset?: number;
    vertAlign?: VertAlign;
}

export interface ConcreteFill {
    patternType?: string;
    fgColor?: string;
    bgColor?: string;
}

export interface ConcreteBorderEdge {
    style?: string;
    color?: string;
}

export interface ConcreteBorder {
    left?: ConcreteBorderEdge;
    right?: ConcreteBorderEdge;
    top?: ConcreteBorderEdge;
    bottom?: ConcreteBorderEdge;
    diagonal?: ConcreteBorderEdge;
    diagonalUp?: boolean;
    diagonalDown?: boolean;
}

export interface ConcreteStyle {
    numFmtId: number;
    numFmtCode?: string;
    isDate: boolean;
    font: ConcreteFont;
    fill: ConcreteFill;
    border: ConcreteBorder;
    alignment?: Alignment;
}

type ColorFn = (c: Color | undefined) => string | undefined;

function concreteFont(font: Font, toRgb: ColorFn): ConcreteFont {
    const f: ConcreteFont = {};
    if (font.name !== undefined) f.name = font.name;
    if (font.size !== undefined) f.size = font.size;
    if (font.bold !== undefined) f.bold = font.bold;
    if (font.italic !== undefined) f.italic = font.italic;
    if (font.underline !== undefined) f.underline = font.underline;
    if (font.strike !== undefined) f.strike = font.strike;
    if (font.family !== undefined) f.family = font.family;
    if (font.charset !== undefined) f.charset = font.charset;
    if (font.vertAlign !== undefined) f.vertAlign = font.vertAlign;
    const color = toRgb(font.color);
    if (color !== undefined) f.color = color;
    return f;
}

function concreteFill(fill: Fill, toRgb: ColorFn): ConcreteFill {
    const f: ConcreteFill = {};
    if (fill.patternType !== undefined) f.patternType = fill.patternType;
    const fg = toRgb(fill.fgColor);
    if (fg !== undefined) f.fgColor = fg;
    const bg = toRgb(fill.bgColor);
    if (bg !== undefined) f.bgColor = bg;
    return f;
}

function concreteEdge(
    edge: { style?: string; color?: Color } | undefined,
    toRgb: ColorFn,
): ConcreteBorderEdge | undefined {
    if (edge === undefined) return undefined;
    const e: ConcreteBorderEdge = {};
    if (edge.style !== undefined) e.style = edge.style;
    const color = toRgb(edge.color);
    if (color !== undefined) e.color = color;
    return Object.keys(e).length > 0 ? e : undefined;
}

function concreteBorder(border: Border, toRgb: ColorFn): ConcreteBorder {
    const b: ConcreteBorder = {};
    const left = concreteEdge(border.left, toRgb);
    if (left) b.left = left;
    const right = concreteEdge(border.right, toRgb);
    if (right) b.right = right;
    const top = concreteEdge(border.top, toRgb);
    if (top) b.top = top;
    const bottom = concreteEdge(border.bottom, toRgb);
    if (bottom) b.bottom = bottom;
    const diagonal = concreteEdge(border.diagonal, toRgb);
    if (diagonal) b.diagonal = diagonal;
    if (border.diagonalUp) b.diagonalUp = true;
    if (border.diagonalDown) b.diagonalDown = true;
    return b;
}

/**
 * 解 cell 樣式為完全具體（色彩皆 RGB）。組合 StyleResolver + ThemeResolver、結果快取。
 */
export class ConcreteStyleResolver {
    private readonly styleResolver: StyleResolver;
    private readonly themeResolver: ThemeResolver;
    private readonly cache = new Map<number, ConcreteStyle>();

    constructor(styles: ParsedStyles, theme: ParsedTheme) {
        this.styleResolver = new StyleResolver(styles);
        this.themeResolver = new ThemeResolver(theme);
    }

    resolve(styleIndex: number | undefined): ConcreteStyle {
        const key = styleIndex ?? 0;
        const cached = this.cache.get(key);
        if (cached) return cached;
        const concrete = this.concretize(this.styleResolver.resolve(styleIndex));
        this.cache.set(key, concrete);
        return concrete;
    }

    private concretize(rs: ResolvedStyle): ConcreteStyle {
        const toRgb: ColorFn = (c) => this.themeResolver.resolveColor(c);
        const style: ConcreteStyle = {
            numFmtId: rs.numFmtId,
            isDate: rs.isDate,
            font: concreteFont(rs.font, toRgb),
            fill: concreteFill(rs.fill, toRgb),
            border: concreteBorder(rs.border, toRgb),
        };
        if (rs.numFmtCode !== undefined) style.numFmtCode = rs.numFmtCode;
        if (rs.alignment !== undefined) style.alignment = rs.alignment;
        return style;
    }
}

/**
 * 取 fill 的「可見背景色」：solid → fgColor 才是顯示色（OOXML 慣例）；
 * none → undefined；其他 pattern → bgColor（圖樣後方底色）。
 */
export function fillBackgroundColor(fill: ConcreteFill): string | undefined {
    if (fill.patternType === undefined || fill.patternType === 'none') return undefined;
    if (fill.patternType === 'solid') return fill.fgColor;
    return fill.bgColor;
}
