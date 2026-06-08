// dv_parser.ts — worksheet <dataValidations> → DataValidation[]（規劃書 §1.8）

import { toArray, attr, boolAttr, textOf } from './xml_util';

export interface DataValidation {
    /** list / whole / decimal / date / time / textLength / custom。*/
    type: string;
    /** between / notBetween / equal / greaterThan / lessThan ...（list/custom 無）。*/
    operator?: string;
    /** 套用範圍（sqref 以空白分隔）。*/
    ranges: string[];
    formula1?: string;
    formula2?: string;
    allowBlank: boolean;
}

function parseOne(dv: Record<string, unknown>): DataValidation | undefined {
    const sqref = attr(dv, 'sqref');
    if (!sqref) return undefined;
    const f1 = dv['formula1'];
    const f2 = dv['formula2'];
    return {
        type: attr(dv, 'type') ?? 'none',
        operator: attr(dv, 'operator'),
        ranges: sqref.split(/\s+/).filter((s) => s.length > 0),
        formula1: f1 !== undefined ? textOf(f1) : undefined,
        formula2: f2 !== undefined ? textOf(f2) : undefined,
        allowBlank: boolAttr(dv, 'allowBlank'),
    };
}

/** 解析 worksheet 的 <dataValidations>。*/
export function parseDataValidations(ws: Record<string, unknown>): DataValidation[] {
    const container = ws['dataValidations'] as Record<string, unknown> | undefined;
    if (!container) return [];
    return toArray<Record<string, unknown>>(container['dataValidation'] as never)
        .map(parseOne)
        .filter((d): d is DataValidation => d !== undefined && d.ranges.length > 0);
}
