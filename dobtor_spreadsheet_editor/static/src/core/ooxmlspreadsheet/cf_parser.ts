// cf_parser.ts — 解析 worksheet 的 <conditionalFormatting>（規劃書 §1.7）
//
// CF 規則本體在 worksheet XML，格式（dxfId）指向 styles.xml 的 dxfs。
// 本層解析規則結構；套用渲染/解 dxf 由上層（Phase 4）處理。
//
// 實檔分布（ChienYi）：cellIs / expression / duplicateValues。
// 完整規格另含 colorScale / dataBar / iconSet / containsText 系列 / top10，一併解析。

import { parseXml, toArray, attr, intAttr, boolAttr, textOf } from './xml_util';
import { parseColor, type Color } from './color';

/** cfvo（conditional format value object）：min/max/num/percent/percentile/formula。*/
export interface CfValueObject {
    type: string;
    val: string | undefined;
}

export interface ColorScale {
    cfvo: CfValueObject[];
    colors: Color[];
}

export interface DataBar {
    cfvo: CfValueObject[];
    color: Color | undefined;
    minLength: number | undefined;
    maxLength: number | undefined;
    showValue: boolean;
}

export interface IconSet {
    iconSet: string;
    cfvo: CfValueObject[];
    reverse: boolean;
    showValue: boolean;
}

export interface CfRule {
    /** cellIs / expression / colorScale / dataBar / iconSet / containsText / duplicateValues / top10 ... */
    type: string;
    priority: number;
    dxfId: number | undefined;
    /** cellIs / containsText 等：equal / greaterThan / between ... */
    operator: string | undefined;
    /** containsText 系列的比對文字。*/
    text: string | undefined;
    /** <formula> 子元素（cellIs 可有 1-2 個、expression 1 個）。*/
    formulas: string[];
    stopIfTrue: boolean;
    /** top10：百分比模式 / 名次 / 由下往上。*/
    percent: boolean;
    rank: number | undefined;
    bottom: boolean;
    colorScale: ColorScale | undefined;
    dataBar: DataBar | undefined;
    iconSet: IconSet | undefined;
    timePeriod: string | undefined;
}

export interface ConditionalFormatting {
    /** 原始 sqref（可含多段、空白分隔）。*/
    sqref: string;
    /** 拆分後的範圍清單。*/
    ranges: string[];
    rules: CfRule[];
}

function parseCfvo(node: unknown): CfValueObject {
    return { type: attr(node, 'type') ?? '', val: attr(node, 'val') };
}

function parseCfvoList(container: unknown): CfValueObject[] {
    if (container === null || typeof container !== 'object') return [];
    return toArray<unknown>((container as Record<string, unknown>)['cfvo']).map(parseCfvo);
}

function parseRule(node: unknown): CfRule {
    const r = (node ?? {}) as Record<string, unknown>;
    const rule: CfRule = {
        type: attr(r, 'type') ?? '',
        priority: intAttr(r, 'priority') ?? 0,
        dxfId: intAttr(r, 'dxfId'),
        operator: attr(r, 'operator'),
        text: attr(r, 'text'),
        formulas: toArray<unknown>(r['formula']).map((f) => textOf(f)),
        stopIfTrue: boolAttr(r, 'stopIfTrue'),
        percent: boolAttr(r, 'percent'),
        rank: intAttr(r, 'rank'),
        bottom: boolAttr(r, 'bottom'),
        colorScale: undefined,
        dataBar: undefined,
        iconSet: undefined,
        timePeriod: attr(r, 'timePeriod'),
    };

    if ('colorScale' in r) {
        const cs = r['colorScale'] as Record<string, unknown>;
        rule.colorScale = {
            cfvo: parseCfvoList(cs),
            colors: toArray<unknown>(cs['color'])
                .map((c) => parseColor(c))
                .filter((c): c is Color => c !== undefined),
        };
    }
    if ('dataBar' in r) {
        const db = r['dataBar'] as Record<string, unknown>;
        rule.dataBar = {
            cfvo: parseCfvoList(db),
            color: parseColor(db['color']),
            minLength: intAttr(db, 'minLength'),
            maxLength: intAttr(db, 'maxLength'),
            showValue: attr(db, 'showValue') !== '0',
        };
    }
    if ('iconSet' in r) {
        const is = r['iconSet'] as Record<string, unknown>;
        rule.iconSet = {
            iconSet: attr(is, 'iconSet') ?? '3TrafficLights1',
            cfvo: parseCfvoList(is),
            reverse: boolAttr(is, 'reverse'),
            showValue: attr(is, 'showValue') !== '0',
        };
    }
    return rule;
}

/** 從已解析的 worksheet 節點取出全部 conditionalFormatting。*/
export function parseConditionalFormattings(ws: Record<string, unknown>): ConditionalFormatting[] {
    return toArray<unknown>(ws['conditionalFormatting']).map((cfNode) => {
        const cf = (cfNode ?? {}) as Record<string, unknown>;
        const sqref = attr(cf, 'sqref') ?? '';
        return {
            sqref,
            ranges: sqref.split(/\s+/).filter((s) => s.length > 0),
            rules: toArray<unknown>(cf['cfRule']).map(parseRule),
        };
    });
}

export class CFParser {
    /** 從 worksheet XML 字串獨立解析 CF（測試/獨立使用）。*/
    static parse(xmlText: string): ConditionalFormatting[] {
        const xml = parseXml(xmlText);
        const ws = (xml['worksheet'] ?? {}) as Record<string, unknown>;
        return parseConditionalFormattings(ws);
    }
}
