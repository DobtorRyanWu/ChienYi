// dv_compiler.ts — DataValidation → o-spreadsheet dataValidationRules（規劃書 §4.2）
//
// v1：list（inline 清單 → isValueInList、range → isValueInRange）+ 數值/日期 operator
// （between/equal/greaterThan）。custom/textLength 等暫不編譯。

import type { DataValidation } from './dv_parser';

export interface ODataValidationRule {
    id: string;
    criterion: { type: string; values: string[]; displayStyle?: string };
    ranges: string[];
}

// Excel operator → o-spreadsheet criterion type（數值/日期）
const OP_MAP: Readonly<Record<string, string>> = {
    between: 'isBetween',
    equal: 'isEqual',
    greaterThan: 'isGreaterThan',
};

function compileOne(dv: DataValidation, id: string): ODataValidationRule | undefined {
    if (dv.type === 'list') {
        const f1 = (dv.formula1 ?? '').trim();
        if (!f1) return undefined;
        if (f1.startsWith('"') && f1.endsWith('"')) {
            // inline：逗號分隔（Excel list 內選項不含逗號）
            const values = f1
                .slice(1, -1)
                .split(',')
                .map((s) => s.trim())
                .filter((s) => s.length > 0);
            if (values.length === 0) return undefined;
            return { id, criterion: { type: 'isValueInList', values, displayStyle: 'arrow' }, ranges: dv.ranges };
        }
        // 範圍參照（如 $X$1:$X$5 或 Sheet!$A$1:$A$5）
        return { id, criterion: { type: 'isValueInRange', values: [f1], displayStyle: 'arrow' }, ranges: dv.ranges };
    }

    const type = dv.operator ? OP_MAP[dv.operator] : undefined;
    if (type && ['whole', 'decimal', 'date', 'time', 'textLength'].includes(dv.type)) {
        const values =
            type === 'isBetween' ? [dv.formula1 ?? '', dv.formula2 ?? ''] : [dv.formula1 ?? ''];
        if (values.some((v) => v === '')) return undefined;
        return { id, criterion: { type, values }, ranges: dv.ranges };
    }
    return undefined; // custom / textLength 無 operator / 其他 v1 不編譯
}

/** DataValidation[] → o-spreadsheet dataValidationRules（idPrefix 跨 sheet 唯一）。*/
export function compileDataValidations(dvs: DataValidation[], idPrefix = 'dv'): ODataValidationRule[] {
    const out: ODataValidationRule[] = [];
    let n = 1;
    for (const dv of dvs) {
        const rule = compileOne(dv, `${idPrefix}_${n}`);
        if (rule) {
            out.push(rule);
            n++;
        }
    }
    return out;
}
