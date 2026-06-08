// xlsx_writer.ts — 寫出最小但合法的 xlsx（規劃書 Phase 6 雙向 round-trip）
//
// 範圍（v1）：cell 值（number/string/boolean）、公式（<f>+cached <v>）、合併儲存格、多工作表、
// sharedStrings 去重。樣式 v1 寫 minimal styles.xml（單一預設 cellXf）——值/結構 round-trip 優先，
// 樣式回寫待後續（需把 ConcreteStyle 反編成 styles.xml 各池）。
//
// 用 fflate zipSync 打包成 OOXML zip。

import { zipSync, strToU8 } from 'fflate';
import { columnIndexToLetter } from './cell_ref';

export interface WriteCell {
    row: number; // 1-based
    col: number; // 1-based
    value?: string | number | boolean;
    /** 公式文字（不含前導 =）；有公式時 value 視為 cached 結果。*/
    formula?: string;
}

export interface WriteSheet {
    name: string;
    cells: WriteCell[];
    merges: string[];
}

const XMLNS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const XMLNS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const CT = 'http://schemas.openxmlformats.org/package/2006/content-types';
const PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships';

function xmlEscape(s: string): string {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** sharedStrings 去重池。*/
class StringPool {
    private readonly map = new Map<string, number>();
    readonly items: string[] = [];
    intern(s: string): number {
        const existing = this.map.get(s);
        if (existing !== undefined) return existing;
        const id = this.items.length;
        this.map.set(s, id);
        this.items.push(s);
        return id;
    }
}

function cellXml(cell: WriteCell, pool: StringPool): string {
    const ref = `${columnIndexToLetter(cell.col)}${cell.row}`;
    const v = cell.value;

    if (cell.formula !== undefined) {
        const f = `<f>${xmlEscape(cell.formula)}</f>`;
        if (typeof v === 'number') return `<c r="${ref}">${f}<v>${v}</v></c>`;
        if (typeof v === 'boolean') return `<c r="${ref}" t="b">${f}<v>${v ? 1 : 0}</v></c>`;
        if (typeof v === 'string') return `<c r="${ref}" t="str">${f}<v>${xmlEscape(v)}</v></c>`;
        return `<c r="${ref}">${f}</c>`;
    }
    if (typeof v === 'number') return `<c r="${ref}"><v>${v}</v></c>`;
    if (typeof v === 'boolean') return `<c r="${ref}" t="b"><v>${v ? 1 : 0}</v></c>`;
    if (typeof v === 'string' && v !== '') {
        return `<c r="${ref}" t="s"><v>${pool.intern(v)}</v></c>`;
    }
    return `<c r="${ref}"/>`;
}

function sheetXml(sheet: WriteSheet, pool: StringPool): string {
    // 依列分組
    const byRow = new Map<number, WriteCell[]>();
    let maxRow = 1;
    let maxCol = 1;
    for (const c of sheet.cells) {
        if (!byRow.has(c.row)) byRow.set(c.row, []);
        byRow.get(c.row)!.push(c);
        if (c.row > maxRow) maxRow = c.row;
        if (c.col > maxCol) maxCol = c.col;
    }
    const rows = [...byRow.keys()].sort((a, b) => a - b);
    const rowsXml = rows
        .map((r) => {
            const cells = byRow
                .get(r)!
                .sort((a, b) => a.col - b.col)
                .map((c) => cellXml(c, pool))
                .join('');
            return `<row r="${r}">${cells}</row>`;
        })
        .join('');

    const dim = `A1:${columnIndexToLetter(maxCol)}${maxRow}`;
    const mergeXml =
        sheet.merges.length > 0
            ? `<mergeCells count="${sheet.merges.length}">${sheet.merges
                  .map((m) => `<mergeCell ref="${m}"/>`)
                  .join('')}</mergeCells>`
            : '';

    return (
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<worksheet xmlns="${XMLNS_MAIN}" xmlns:r="${XMLNS_R}">` +
        `<dimension ref="${dim}"/>` +
        `<sheetData>${rowsXml}</sheetData>` +
        mergeXml +
        `</worksheet>`
    );
}

/** 寫出 xlsx bytes。*/
export function buildXlsx(sheets: WriteSheet[]): Uint8Array {
    const list = sheets.length > 0 ? sheets : [{ name: 'Sheet1', cells: [], merges: [] }];
    const pool = new StringPool();

    const sheetFiles: Record<string, string> = {};
    list.forEach((s, i) => {
        sheetFiles[`xl/worksheets/sheet${i + 1}.xml`] = sheetXml(s, pool);
    });

    const sharedStrings =
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<sst xmlns="${XMLNS_MAIN}" count="${pool.items.length}" uniqueCount="${pool.items.length}">` +
        pool.items.map((t) => `<si><t xml:space="preserve">${xmlEscape(t)}</t></si>`).join('') +
        `</sst>`;

    const workbook =
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<workbook xmlns="${XMLNS_MAIN}" xmlns:r="${XMLNS_R}"><sheets>` +
        list
            .map((s, i) => `<sheet name="${xmlEscape(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`)
            .join('') +
        `</sheets></workbook>`;

    const wbRelItems = list
        .map((_s, i) => `<Relationship Id="rId${i + 1}" Type="${XMLNS_R}/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`)
        .join('');
    const ssId = list.length + 1;
    const stylesId = list.length + 2;
    const workbookRels =
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<Relationships xmlns="${PKG_REL}">` +
        wbRelItems +
        `<Relationship Id="rId${ssId}" Type="${XMLNS_R}/sharedStrings" Target="sharedStrings.xml"/>` +
        `<Relationship Id="rId${stylesId}" Type="${XMLNS_R}/styles" Target="styles.xml"/>` +
        `</Relationships>`;

    const styles =
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<styleSheet xmlns="${XMLNS_MAIN}">` +
        `<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>` +
        `<fills count="1"><fill><patternFill patternType="none"/></fill></fills>` +
        `<borders count="1"><border/></borders>` +
        `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
        `<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>` +
        `<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>` +
        `</styleSheet>`;

    const rootRels =
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<Relationships xmlns="${PKG_REL}">` +
        `<Relationship Id="rId1" Type="${XMLNS_R}/officeDocument" Target="xl/workbook.xml"/>` +
        `</Relationships>`;

    const contentTypes =
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<Types xmlns="${CT}">` +
        `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
        `<Default Extension="xml" ContentType="application/xml"/>` +
        `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
        list
            .map((_s, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`)
            .join('') +
        `<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>` +
        `<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>` +
        `</Types>`;

    const files: Record<string, Uint8Array> = {
        '[Content_Types].xml': strToU8(contentTypes),
        '_rels/.rels': strToU8(rootRels),
        'xl/workbook.xml': strToU8(workbook),
        'xl/_rels/workbook.xml.rels': strToU8(workbookRels),
        'xl/sharedStrings.xml': strToU8(sharedStrings),
        'xl/styles.xml': strToU8(styles),
        ...Object.fromEntries(Object.entries(sheetFiles).map(([k, v]) => [k, strToU8(v)])),
    };

    return zipSync(files);
}
