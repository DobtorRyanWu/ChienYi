// cf_compiler.ts — CFParser AST → o-spreadsheet conditionalFormats（規劃書 §4.1）
//
// 把解析出的條件格式編譯成 o-spreadsheet 的 CF 物件，讓匯入的 xlsx CF 在可編輯試算表顯示。
// v1 範圍：CellIsRule（cellIs operator + dxf 樣式）+ containsText 系列（o-spreadsheet 確定支援）。
// colorScale/dataBar/iconSet/duplicateValues/expression 暫不編譯（o-spreadsheet 無直接對應或色彩格式待確認）。

import { parseRange, columnIndexToLetter } from './cell_ref';
import type { ConditionalFormatting, CfRule, CfValueObject } from './cf_parser';
import type { Dxf, Fill } from './styles_parser';
import type { Color } from './color';
import type { ThemeResolver } from './theme_resolver';

/** o-spreadsheet CellIsRule 的樣式（CF 命中時套用）。*/
interface OCfStyle {
    bold?: boolean;
    italic?: boolean;
    strikethrough?: boolean;
    underline?: boolean;
    textColor?: string;
    fillColor?: string;
}

interface OCellIsRule {
    type: 'CellIsRule';
    operator: string;
    values: string[];
    style: OCfStyle;
}

/** o-spreadsheet colorScale threshold（color 為 RGB 整數）。*/
interface OThreshold {
    type: string;
    color: number;
    value?: string;
}

interface OColorScaleRule {
    type: 'ColorScaleRule';
    minimum: OThreshold;
    midpoint: OThreshold | null;
    maximum: OThreshold;
}

interface ODataBarRule {
    type: 'DataBarRule';
    color: number;
}

interface OInflectionPoint {
    type: string;
    value: string;
    operator: string;
}

interface OIconSetRule {
    type: 'IconSetRule';
    icons: { upper: string; middle: string; lower: string };
    lowerInflectionPoint: OInflectionPoint;
    upperInflectionPoint: OInflectionPoint;
}

export interface OConditionalFormat {
    id: string;
    ranges: string[];
    rule: OCellIsRule | OColorScaleRule | ODataBarRule | OIconSetRule;
}

// Excel cellIs operator → o-spreadsheet operator
const OPERATOR_MAP: Readonly<Record<string, string>> = {
    equal: 'Equal',
    notEqual: 'NotEqual',
    greaterThan: 'GreaterThan',
    greaterThanOrEqual: 'GreaterThanOrEqual',
    lessThan: 'LessThan',
    lessThanOrEqual: 'LessThanOrEqual',
    between: 'Between',
    notBetween: 'NotBetween',
};

// containsText 系列 type → o-spreadsheet operator
const TEXT_TYPE_MAP: Readonly<Record<string, string>> = {
    containsText: 'ContainsText',
    notContainsText: 'NotContains',
    beginsWith: 'BeginsWith',
    endsWith: 'EndsWith',
};

/** dxf 的填色（CF dxf 慣例色彩在 bgColor，退而求 fgColor）→ 具體 RGB。*/
function dxfFillColor(fill: Fill | undefined, theme: ThemeResolver): string | undefined {
    if (!fill) return undefined;
    return theme.resolveColor(fill.bgColor) ?? theme.resolveColor(fill.fgColor);
}

function dxfToStyle(dxf: Dxf, theme: ThemeResolver): OCfStyle {
    const style: OCfStyle = {};
    if (dxf.font) {
        if (dxf.font.bold) style.bold = true;
        if (dxf.font.italic) style.italic = true;
        if (dxf.font.strike) style.strikethrough = true;
        if (dxf.font.underline && dxf.font.underline !== 'none') style.underline = true;
        const tc = theme.resolveColor(dxf.font.color);
        if (tc) style.textColor = `#${tc}`;
    }
    const fc = dxfFillColor(dxf.fill, theme);
    if (fc) style.fillColor = `#${fc}`;
    return style;
}

/** 將 range 的結尾列/欄夾到 sheet 範圍內（避免 D1:D1048576 這類超大範圍）。*/
function clampRange(ref: string, maxRow: number, maxCol: number): string | undefined {
    try {
        const { start, end } = parseRange(ref);
        const er = Math.min(end.row, Math.max(maxRow, start.row));
        const ec = Math.min(end.col, Math.max(maxCol, start.col));
        const s = `${columnIndexToLetter(start.col)}${start.row}`;
        const e = `${columnIndexToLetter(ec)}${er}`;
        return s === e ? s : `${s}:${e}`;
    } catch {
        return undefined;
    }
}

// Excel cfvo type → o-spreadsheet threshold type
const CFVO_TYPE_MAP: Readonly<Record<string, string>> = {
    min: 'value',
    max: 'value',
    num: 'number',
    percent: 'percentage',
    percentile: 'percentile',
    formula: 'formula',
};

/** Excel Color → o-spreadsheet RGB 整數（colorScale/dataBar 用）。*/
function colorToNumber(c: Color | undefined, theme: ThemeResolver): number {
    const hex = theme.resolveColor(c);
    if (!hex) return 0xffffff;
    const rgb = hex.length === 8 ? hex.slice(2) : hex; // 去 alpha
    const n = parseInt(rgb, 16);
    return Number.isFinite(n) ? n : 0xffffff;
}

function toThreshold(cfvo: CfValueObject, color: Color | undefined, theme: ThemeResolver): OThreshold {
    const type = CFVO_TYPE_MAP[cfvo.type] ?? 'value';
    const t: OThreshold = { type, color: colorToNumber(color, theme) };
    // 'value'（min/max 自動）不帶 value；其餘帶閾值
    if (type !== 'value' && cfvo.val !== undefined) t.value = cfvo.val;
    return t;
}

function compileColorScale(rule: CfRule, theme: ThemeResolver): OColorScaleRule | undefined {
    const cs = rule.colorScale;
    if (!cs || cs.cfvo.length < 2 || cs.colors.length < 2) return undefined;
    const last = cs.cfvo.length - 1;
    const minimum = toThreshold(cs.cfvo[0], cs.colors[0], theme);
    const maximum = toThreshold(cs.cfvo[last], cs.colors[last], theme);
    const midpoint =
        cs.cfvo.length >= 3 ? toThreshold(cs.cfvo[1], cs.colors[1], theme) : null;
    return { type: 'ColorScaleRule', minimum, midpoint, maximum };
}

// Excel iconSet 名稱 → o-spreadsheet icon family（只有 arrow/dot/smiley 三家族）
function iconFamily(iconSet: string): 'arrow' | 'dot' | 'smiley' {
    if (/Arrow/i.test(iconSet)) return 'arrow';
    if (/Symbol|Flag|Rating|Star|Quarter|Box/i.test(iconSet)) return 'smiley';
    return 'dot'; // TrafficLights / Signs / 其他
}

// Excel cfvo 的 gte 預設為 true（>=）→ o-spreadsheet operator 'ge'
function compileIconSet(rule: CfRule): OIconSetRule | undefined {
    const is = rule.iconSet;
    if (!is || is.cfvo.length < 3) return undefined;
    const fam = iconFamily(is.iconSet);
    const icons = { upper: `${fam}Good`, middle: `${fam}Neutral`, lower: `${fam}Bad` };
    // 3-icon：cfvo[0]=最低（忽略）、cfvo[1]=下閾值、cfvo[2]=上閾值
    const infl = (cfvo: CfValueObject): OInflectionPoint => ({
        type: CFVO_TYPE_MAP[cfvo.type] ?? 'percentage',
        value: cfvo.val ?? '0',
        operator: 'ge',
    });
    return {
        type: 'IconSetRule',
        icons,
        lowerInflectionPoint: infl(is.cfvo[1]),
        upperInflectionPoint: infl(is.cfvo[is.cfvo.length - 1]),
    };
}

function compileRule(rule: CfRule, dxfs: Dxf[], theme: ThemeResolver): OConditionalFormat['rule'] | undefined {
    const style = rule.dxfId !== undefined && dxfs[rule.dxfId] ? dxfToStyle(dxfs[rule.dxfId], theme) : {};
    if (rule.type === 'cellIs') {
        const operator = rule.operator ? OPERATOR_MAP[rule.operator] : undefined;
        if (!operator) return undefined;
        return { type: 'CellIsRule', operator, values: rule.formulas.slice(), style };
    }
    if (rule.type in TEXT_TYPE_MAP) {
        const operator = TEXT_TYPE_MAP[rule.type];
        const value = rule.text ?? '';
        return { type: 'CellIsRule', operator, values: [value], style };
    }
    if (rule.type === 'colorScale') {
        return compileColorScale(rule, theme);
    }
    if (rule.type === 'dataBar' && rule.dataBar) {
        // o-spreadsheet DataBarRule：{type, color(RGB 整數)}；bar 長度由 CF range 值自動推算
        return { type: 'DataBarRule', color: colorToNumber(rule.dataBar.color, theme) };
    }
    if (rule.type === 'iconSet') {
        return compileIconSet(rule);
    }
    return undefined; // duplicateValues/expression v1 不編譯
}

/**
 * 編譯 worksheet 的 CF → o-spreadsheet conditionalFormats。
 * @param idPrefix CF id 前綴（跨 sheet 唯一，如 sheet id）。
 */
export function compileConditionalFormats(
    cfBlocks: ConditionalFormatting[],
    dxfs: Dxf[],
    theme: ThemeResolver,
    maxRow: number,
    maxCol: number,
    idPrefix = 'cf',
): OConditionalFormat[] {
    const out: OConditionalFormat[] = [];
    let n = 1;
    for (const block of cfBlocks) {
        const ranges = block.ranges
            .map((r) => clampRange(r, maxRow, maxCol))
            .filter((r): r is string => r !== undefined);
        if (ranges.length === 0) continue;
        for (const rule of block.rules) {
            const compiled = compileRule(rule, dxfs, theme);
            if (compiled) {
                out.push({ id: `${idPrefix}_${n++}`, ranges, rule: compiled });
            }
        }
    }
    return out;
}
