// table_parser.ts — xl/tables/tableN.xml → ParsedTable（規劃書 §1.11）

import { parseXml, attr, boolAttr } from './xml_util';

export interface ParsedTable {
    /** 範圍 ref（如 "A1:C10"）。*/
    range: string;
    totalsRowShown: boolean;
    /** tableStyleInfo name（與 o-spreadsheet styleId 同格式，如 TableStyleMedium2）。*/
    styleName?: string;
    showFirstColumn: boolean;
    showLastColumn: boolean;
    showRowStripes: boolean;
    showColumnStripes: boolean;
    hasAutoFilter: boolean;
}

/** tableN.xml → ParsedTable。無 ref 回 undefined。*/
export function parseTable(xml: string): ParsedTable | undefined {
    const root = parseXml(xml);
    const table = root['table'] as Record<string, unknown> | undefined;
    if (!table) return undefined;
    const ref = attr(table, 'ref');
    if (!ref) return undefined;
    const styleInfo = table['tableStyleInfo'] as Record<string, unknown> | undefined;
    return {
        range: ref,
        totalsRowShown: boolAttr(table, 'totalsRowShown'),
        styleName: styleInfo ? attr(styleInfo, 'name') : undefined,
        showFirstColumn: styleInfo ? boolAttr(styleInfo, 'showFirstColumn') : false,
        showLastColumn: styleInfo ? boolAttr(styleInfo, 'showLastColumn') : false,
        showRowStripes: styleInfo ? boolAttr(styleInfo, 'showRowStripes') : false,
        showColumnStripes: styleInfo ? boolAttr(styleInfo, 'showColumnStripes') : false,
        hasAutoFilter: table['autoFilter'] !== undefined,
    };
}
