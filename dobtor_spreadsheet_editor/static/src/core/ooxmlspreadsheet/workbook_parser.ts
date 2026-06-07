// workbook_parser.ts — 解析 xl/workbook.xml（規劃書 §1.3）
//
// 產出活頁簿層級結構：sheet 清單（含隱藏狀態與對應 worksheet part）、
// definedNames（含 _xlnm 保留名）、workbookView（啟用 tab）、calcPr（refMode）。
// sheet 的 r:id 透過 workbook 的 .rels 解析成實際 worksheet part 路徑。

import type { PackageReader } from './package_reader';
import { parseXml, toArray, attr, intAttr, boolAttr, textOf } from './xml_util';

const REL_WORKSHEET = '/worksheet';
const REL_SHARED_STRINGS = '/sharedStrings';
const REL_STYLES = '/styles';
const REL_THEME = '/theme';
const REL_OFFICE_DOCUMENT = '/officeDocument';
const RESERVED_NAME_PREFIX = '_xlnm.';

export type SheetState = 'visible' | 'hidden' | 'veryHidden';

export interface WorkbookSheet {
    name: string;
    sheetId: number;
    rId: string;
    state: SheetState;
    /** 解析後的 worksheet part 路徑（無前導斜線）；rId 解不到時為 undefined。*/
    target: string | undefined;
}

export interface DefinedName {
    name: string;
    /** 0-based sheet index（localSheetId）；全域名稱為 undefined。*/
    localSheetId: number | undefined;
    hidden: boolean;
    /** 公式/範圍文字，如 "'Sheet1'!$A$1:$B$2"。*/
    formula: string;
    /** 是否為 Excel 保留名（_xlnm.*，如 _FilterDatabase / Print_Area）。*/
    reserved: boolean;
}

export interface WorkbookView {
    activeTab: number;
    firstSheet: number;
}

export type RefMode = 'A1' | 'R1C1';

export interface CalcProperties {
    refMode: RefMode;
    iterate: boolean;
}

export interface ParsedWorkbook {
    sheets: WorkbookSheet[];
    definedNames: DefinedName[];
    view: WorkbookView;
    calc: CalcProperties;
}

function toSheetState(raw: string | undefined): SheetState {
    return raw === 'hidden' || raw === 'veryHidden' ? raw : 'visible';
}

export class WorkbookParser {
    constructor(private readonly pkg: PackageReader) {}

    /** 取 workbook part 路徑（root officeDocument 關聯）。查無丟錯。*/
    workbookPart(): string {
        const office = this.pkg
            .getRootRels()
            .find((r) => r.type.endsWith(REL_OFFICE_DOCUMENT));
        if (!office) throw new Error('workbook.xml not found: missing officeDocument relationship');
        return office.resolvedTarget;
    }

    /** rId → resolvedTarget 對照（workbook 層級關聯）。*/
    private relMap(): Map<string, string> {
        const map = new Map<string, string>();
        for (const r of this.pkg.getRels(this.workbookPart())) {
            map.set(r.id, r.resolvedTarget);
        }
        return map;
    }

    parse(): ParsedWorkbook {
        const xml = parseXml(this.pkg.getPartText(this.workbookPart()));
        const wb = (xml['workbook'] ?? {}) as Record<string, unknown>;
        const relMap = this.relMap();

        // ── sheets ──
        const sheetsContainer = (wb['sheets'] ?? {}) as Record<string, unknown>;
        const sheets: WorkbookSheet[] = toArray<unknown>(sheetsContainer['sheet']).map((s) => {
            const rId = attr(s, 'r:id') ?? '';
            return {
                name: attr(s, 'name') ?? '',
                sheetId: intAttr(s, 'sheetId') ?? 0,
                rId,
                state: toSheetState(attr(s, 'state')),
                target: relMap.get(rId),
            };
        });

        // ── definedNames ──
        const dnContainer = (wb['definedNames'] ?? {}) as Record<string, unknown>;
        const definedNames: DefinedName[] = toArray<unknown>(dnContainer['definedName']).map(
            (d) => {
                const name = attr(d, 'name') ?? '';
                return {
                    name,
                    localSheetId: intAttr(d, 'localSheetId'),
                    hidden: boolAttr(d, 'hidden'),
                    formula: textOf(d),
                    reserved: name.startsWith(RESERVED_NAME_PREFIX),
                };
            },
        );

        // ── workbookView（取第一個 bookView）──
        const bookViews = (wb['bookViews'] ?? {}) as Record<string, unknown>;
        const firstView = toArray<unknown>(bookViews['workbookView'])[0];
        const view: WorkbookView = {
            activeTab: intAttr(firstView, 'activeTab') ?? 0,
            firstSheet: intAttr(firstView, 'firstSheet') ?? 0,
        };

        // ── calcPr ──
        const calcPr = wb['calcPr'];
        const calc: CalcProperties = {
            refMode: attr(calcPr, 'refMode') === 'R1C1' ? 'R1C1' : 'A1',
            iterate: boolAttr(calcPr, 'iterate'),
        };

        return { sheets, definedNames, view, calc };
    }

    // ── 相關 part 解析（供後續 sprint 使用）─────────────────────────────
    private partByRelType(suffix: string): string | undefined {
        return this.pkg
            .getRels(this.workbookPart())
            .find((r) => r.type.endsWith(suffix))?.resolvedTarget;
    }

    /** worksheet part 路徑清單（依 workbook sheets 順序）。*/
    worksheetParts(): string[] {
        return this.parse()
            .sheets.map((s) => s.target)
            .filter((t): t is string => t !== undefined);
    }

    sharedStringsPart(): string | undefined {
        return this.partByRelType(REL_SHARED_STRINGS);
    }

    stylesPart(): string | undefined {
        return this.partByRelType(REL_STYLES);
    }

    themePart(): string | undefined {
        return this.partByRelType(REL_THEME);
    }
}
