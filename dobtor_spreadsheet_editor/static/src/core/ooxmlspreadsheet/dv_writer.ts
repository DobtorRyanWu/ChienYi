// dv_writer.ts — DataValidation[] → OOXML <dataValidations>（Phase 6 §6.2 DV 匯出回 xlsx）

import type { DataValidation } from './dv_parser';

function escAttr(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escText(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function dvXml(dv: DataValidation): string {
    const a: string[] = [`type="${escAttr(dv.type)}"`];
    if (dv.operator) a.push(`operator="${escAttr(dv.operator)}"`);
    if (dv.allowBlank) a.push('allowBlank="1"');
    a.push(`sqref="${escAttr(dv.ranges.join(' '))}"`);
    let inner = '';
    if (dv.formula1 !== undefined && dv.formula1 !== '') inner += `<formula1>${escText(dv.formula1)}</formula1>`;
    if (dv.formula2 !== undefined && dv.formula2 !== '') inner += `<formula2>${escText(dv.formula2)}</formula2>`;
    return inner ? `<dataValidation ${a.join(' ')}>${inner}</dataValidation>` : `<dataValidation ${a.join(' ')}/>`;
}

/** DataValidation[] → `<dataValidations>`（放在 conditionalFormatting 之後）。*/
export function writeDataValidations(dvs: DataValidation[] | undefined): string {
    if (!dvs || dvs.length === 0) return '';
    const valid = dvs.filter((d) => d.ranges.length > 0);
    if (valid.length === 0) return '';
    return `<dataValidations count="${valid.length}">${valid.map(dvXml).join('')}</dataValidations>`;
}
