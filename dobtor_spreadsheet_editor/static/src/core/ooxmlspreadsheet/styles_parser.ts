// styles_parser.ts — 解析 xl/styles.xml（規劃書 §1.5，★ Phase 1 內容最大）
//
// styles.xml 是樣式索引池：cell 的 s 屬性 → cellXfs[s] → 指向 fontId/fillId/borderId/numFmtId。
// 本層完整解析各池與 cellXfs/cellStyleXfs/dxfs，並提供 numFmt 解析（自訂 + 內建表）與日期格式判定。
// 注意：把 xf 串接攤平成單一 ResolvedStyle 是 §2.1 StyleResolver 的工作，本層只「解析」不「解析串接」。

import { parseXml, toArray, attr, intAttr, boolAttr } from './xml_util';
import { parseColor, type Color } from './color';

const CUSTOM_NUMFMT_MIN_ID = 164; // ≥164 為自訂格式

/** 內建數字格式 ID → formatCode（ECMA-376 §18.8.30）。*/
const BUILTIN_NUMFMTS: Readonly<Record<number, string>> = {
    0: 'General',
    1: '0',
    2: '0.00',
    3: '#,##0',
    4: '#,##0.00',
    9: '0%',
    10: '0.00%',
    11: '0.00E+00',
    12: '# ?/?',
    13: '# ??/??',
    14: 'mm-dd-yy',
    15: 'd-mmm-yy',
    16: 'd-mmm',
    17: 'mmm-yy',
    18: 'h:mm AM/PM',
    19: 'h:mm:ss AM/PM',
    20: 'h:mm',
    21: 'h:mm:ss',
    22: 'm/d/yy h:mm',
    37: '#,##0 ;(#,##0)',
    38: '#,##0 ;[Red](#,##0)',
    39: '#,##0.00;(#,##0.00)',
    40: '#,##0.00;[Red](#,##0.00)',
    45: 'mm:ss',
    46: '[h]:mm:ss',
    47: 'mmss.0',
    48: '##0.0E+0',
    49: '@',
};

/** 內建日期/時間格式 ID（ECMA-376）。*/
const BUILTIN_DATE_IDS = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47]);

export type VertAlign = 'baseline' | 'superscript' | 'subscript';

export interface Font {
    name?: string;
    size?: number;
    bold?: boolean;
    italic?: boolean;
    /** underline 樣式（none/single/double/...）；<u/> 無 val 視為 'single'。*/
    underline?: string;
    strike?: boolean;
    color?: Color;
    family?: number;
    charset?: number;
    vertAlign?: VertAlign;
}

export interface Fill {
    patternType?: string;
    fgColor?: Color;
    bgColor?: Color;
}

export interface BorderEdge {
    style?: string;
    color?: Color;
}

export interface Border {
    left?: BorderEdge;
    right?: BorderEdge;
    top?: BorderEdge;
    bottom?: BorderEdge;
    diagonal?: BorderEdge;
    diagonalUp?: boolean;
    diagonalDown?: boolean;
}

export interface Alignment {
    horizontal?: string;
    vertical?: string;
    wrapText?: boolean;
    textRotation?: number;
    indent?: number;
    shrinkToFit?: boolean;
}

export interface CellXf {
    numFmtId: number;
    fontId: number;
    fillId: number;
    borderId: number;
    /** 指向 cellStyleXfs 的 index（named style 繼承來源）。*/
    xfId: number | undefined;
    applyNumberFormat: boolean;
    applyFont: boolean;
    applyFill: boolean;
    applyBorder: boolean;
    applyAlignment: boolean;
    alignment: Alignment | undefined;
}

/** differential format（條件格式 dxfs 使用，欄位皆 optional）。*/
export interface Dxf {
    font?: Font;
    fill?: Fill;
    border?: Border;
    numFmtId?: number;
    numFmtCode?: string;
}

export interface ParsedStyles {
    /** 自訂 numFmt（id → code，id≥164）。*/
    customNumFmts: Map<number, string>;
    fonts: Font[];
    fills: Fill[];
    borders: Border[];
    cellXfs: CellXf[];
    cellStyleXfs: CellXf[];
    dxfs: Dxf[];
}

function parseFont(node: unknown): Font {
    const f = (node ?? {}) as Record<string, unknown>;
    const font: Font = {};
    if ('b' in f) font.bold = attr(f['b'], 'val') !== '0';
    if ('i' in f) font.italic = attr(f['i'], 'val') !== '0';
    if ('strike' in f) font.strike = attr(f['strike'], 'val') !== '0';
    if ('u' in f) font.underline = attr(f['u'], 'val') ?? 'single';
    const sz = attr(f['sz'], 'val');
    if (sz !== undefined) font.size = Number(sz);
    const name = attr(f['name'], 'val');
    if (name !== undefined) font.name = name;
    const family = attr(f['family'], 'val');
    if (family !== undefined) font.family = Number.parseInt(family, 10);
    const charset = attr(f['charset'], 'val');
    if (charset !== undefined) font.charset = Number.parseInt(charset, 10);
    const va = attr(f['vertAlign'], 'val');
    if (va === 'superscript' || va === 'subscript' || va === 'baseline') font.vertAlign = va;
    const color = parseColor(f['color']);
    if (color !== undefined) font.color = color;
    return font;
}

function parseFill(node: unknown): Fill {
    const fillObj = (node ?? {}) as Record<string, unknown>;
    const pf = (fillObj['patternFill'] ?? {}) as Record<string, unknown>;
    const fill: Fill = {};
    const pt = attr(pf, 'patternType');
    if (pt !== undefined) fill.patternType = pt;
    const fg = parseColor(pf['fgColor']);
    if (fg !== undefined) fill.fgColor = fg;
    const bg = parseColor(pf['bgColor']);
    if (bg !== undefined) fill.bgColor = bg;
    return fill;
}

function parseEdge(node: unknown): BorderEdge | undefined {
    if (node === null || node === undefined) return undefined;
    const edge: BorderEdge = {};
    const style = attr(node, 'style');
    if (style !== undefined) edge.style = style;
    const color = parseColor((node as Record<string, unknown>)['color']);
    if (color !== undefined) edge.color = color;
    return Object.keys(edge).length > 0 ? edge : undefined;
}

function parseBorder(node: unknown): Border {
    const b = (node ?? {}) as Record<string, unknown>;
    const border: Border = {};
    const left = parseEdge(b['left']);
    if (left) border.left = left;
    const right = parseEdge(b['right']);
    if (right) border.right = right;
    const top = parseEdge(b['top']);
    if (top) border.top = top;
    const bottom = parseEdge(b['bottom']);
    if (bottom) border.bottom = bottom;
    const diagonal = parseEdge(b['diagonal']);
    if (diagonal) border.diagonal = diagonal;
    if (boolAttr(b, 'diagonalUp')) border.diagonalUp = true;
    if (boolAttr(b, 'diagonalDown')) border.diagonalDown = true;
    return border;
}

function parseAlignment(node: unknown): Alignment | undefined {
    if (node === null || node === undefined) return undefined;
    const a: Alignment = {};
    const h = attr(node, 'horizontal');
    if (h !== undefined) a.horizontal = h;
    const v = attr(node, 'vertical');
    if (v !== undefined) a.vertical = v;
    if (boolAttr(node, 'wrapText')) a.wrapText = true;
    const rot = intAttr(node, 'textRotation');
    if (rot !== undefined) a.textRotation = rot;
    const indent = intAttr(node, 'indent');
    if (indent !== undefined) a.indent = indent;
    if (boolAttr(node, 'shrinkToFit')) a.shrinkToFit = true;
    return Object.keys(a).length > 0 ? a : undefined;
}

function parseXf(node: unknown): CellXf {
    const x = (node ?? {}) as Record<string, unknown>;
    return {
        numFmtId: intAttr(x, 'numFmtId') ?? 0,
        fontId: intAttr(x, 'fontId') ?? 0,
        fillId: intAttr(x, 'fillId') ?? 0,
        borderId: intAttr(x, 'borderId') ?? 0,
        xfId: intAttr(x, 'xfId'),
        applyNumberFormat: boolAttr(x, 'applyNumberFormat'),
        applyFont: boolAttr(x, 'applyFont'),
        applyFill: boolAttr(x, 'applyFill'),
        applyBorder: boolAttr(x, 'applyBorder'),
        applyAlignment: boolAttr(x, 'applyAlignment'),
        alignment: parseAlignment(x['alignment']),
    };
}

function childArray(parent: Record<string, unknown>, container: string, child: string): unknown[] {
    const c = parent[container];
    if (c === undefined) return [];
    return toArray<unknown>((c as Record<string, unknown>)[child]);
}

export class StylesParser {
    static parse(xmlText: string): ParsedStyles {
        const xml = parseXml(xmlText);
        const ss = (xml['styleSheet'] ?? {}) as Record<string, unknown>;

        const customNumFmts = new Map<number, string>();
        for (const nf of childArray(ss, 'numFmts', 'numFmt')) {
            const id = intAttr(nf, 'numFmtId');
            const code = attr(nf, 'formatCode');
            if (id !== undefined && code !== undefined) customNumFmts.set(id, code);
        }

        const fonts = childArray(ss, 'fonts', 'font').map(parseFont);
        const fills = childArray(ss, 'fills', 'fill').map(parseFill);
        const borders = childArray(ss, 'borders', 'border').map(parseBorder);
        const cellStyleXfs = childArray(ss, 'cellStyleXfs', 'xf').map(parseXf);
        const cellXfs = childArray(ss, 'cellXfs', 'xf').map(parseXf);

        const dxfs: Dxf[] = childArray(ss, 'dxfs', 'dxf').map((d) => {
            const dd = (d ?? {}) as Record<string, unknown>;
            const dxf: Dxf = {};
            if ('font' in dd) dxf.font = parseFont(dd['font']);
            if ('fill' in dd) dxf.fill = parseFill(dd['fill']);
            if ('border' in dd) dxf.border = parseBorder(dd['border']);
            const id = intAttr(dd['numFmt'], 'numFmtId');
            const code = attr(dd['numFmt'], 'formatCode');
            if (id !== undefined) dxf.numFmtId = id;
            if (code !== undefined) dxf.numFmtCode = code;
            return dxf;
        });

        return { customNumFmts, fonts, fills, borders, cellXfs, cellStyleXfs, dxfs };
    }
}

/** 取 numFmtId 的 formatCode：自訂優先、否則內建表；查無回 undefined。*/
export function numberFormatCode(
    styles: ParsedStyles,
    numFmtId: number,
): string | undefined {
    return styles.customNumFmts.get(numFmtId) ?? BUILTIN_NUMFMTS[numFmtId];
}

/** 判定某 formatCode 是否為日期/時間格式（移除引號/方括號/跳脫後檢 y/m/d/h/s token）。*/
export function isDateFormatCode(code: string): boolean {
    const stripped = code
        .replace(/\[[^\]]*\]/g, '') // [$-404]、[Red]、[h]
        .replace(/"[^"]*"/g, '') // "年" 等字面
        .replace(/\\./g, '') // \年 跳脫字面
        .toLowerCase();
    return /[ymdhs]/.test(stripped);
}

/** 判定某 numFmtId 是否為日期/時間格式（供 §2.3 序號轉日期使用）。*/
export function isDateNumberFormat(styles: ParsedStyles, numFmtId: number): boolean {
    if (BUILTIN_DATE_IDS.has(numFmtId)) return true;
    if (numFmtId < CUSTOM_NUMFMT_MIN_ID) return false;
    const code = styles.customNumFmts.get(numFmtId);
    return code !== undefined && isDateFormatCode(code);
}
