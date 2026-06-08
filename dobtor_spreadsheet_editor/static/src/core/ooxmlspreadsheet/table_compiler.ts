// table_compiler.ts — ParsedTable → o-spreadsheet sheet.tables（規劃書 §1.11 / §5）
//
// 解析鏈：worksheet rels → tableN.xml → ParsedTable → o-spreadsheet table。

import type { PackageReader } from './package_reader';
import { parseTable } from './table_parser';

export interface OTable {
    range: string;
    type: 'static';
    config: {
        hasFilters: boolean;
        totalRow: boolean;
        firstColumn: boolean;
        lastColumn: boolean;
        numberOfHeaders: number;
        bandedRows: boolean;
        bandedColumns: boolean;
        styleId: string;
    };
}

const DEFAULT_STYLE = 'TableStyleMedium2';

/** 解析某 worksheet part 連結的所有 Excel Table → o-spreadsheet tables。*/
export function resolveSheetTables(pkg: PackageReader, sheetPart: string): OTable[] {
    const out: OTable[] = [];
    const tableRels = pkg.getRels(sheetPart).filter((r) => r.type.endsWith('/table'));
    for (const rel of tableRels) {
        const part = rel.resolvedTarget;
        if (!part || !pkg.hasPart(part)) continue;
        const t = parseTable(pkg.getPartText(part));
        if (!t) continue;
        out.push({
            range: t.range,
            type: 'static',
            config: {
                hasFilters: t.hasAutoFilter,
                totalRow: t.totalsRowShown,
                firstColumn: t.showFirstColumn,
                lastColumn: t.showLastColumn,
                numberOfHeaders: 1, // Excel Table 預設 1 列表頭
                bandedRows: t.showRowStripes,
                bandedColumns: t.showColumnStripes,
                styleId: t.styleName ?? DEFAULT_STYLE,
            },
        });
    }
    return out;
}
