// xlsx_writer.ts — 寫出最小但合法的 xlsx（規劃書 Phase 6 雙向 round-trip）
//
// 範圍（v1）：cell 值（number/string/boolean）、公式（<f>+cached <v>）、合併儲存格、多工作表、
// sharedStrings 去重。樣式 v1 寫 minimal styles.xml（單一預設 cellXf）——值/結構 round-trip 優先，
// 樣式回寫待後續（需把 ConcreteStyle 反編成 styles.xml 各池）。
//
// 用 fflate zipSync 打包成 OOXML zip。

import { zipSync, strToU8 } from 'fflate';
import { columnIndexToLetter } from './cell_ref';
import { fillBackgroundColor, type ConcreteStyle } from './concrete_style';
import { writeConditionalFormattings, writeDxfs } from './cf_writer';
import type { ConditionalFormatting } from './cf_parser';
import type { Dxf } from './styles_parser';

export interface WriteCell {
    row: number; // 1-based
    col: number; // 1-based
    value?: string | number | boolean;
    /** 公式文字（不含前導 =）；有公式時 value 視為 cached 結果。*/
    formula?: string;
    /** 具體樣式（font/fill/border/numFmt）；寫進 styles.xml 並以 s 索引參照。*/
    style?: ConcreteStyle;
}

const CUSTOM_NUMFMT_BASE = 164;

/** ARGB（FF 前綴）。輸入 6-hex（無 #）或已含 #。*/
function argb(hex: string): string {
    const h = hex.replace('#', '').toUpperCase();
    return h.length === 8 ? h : `FF${h.padStart(6, '0')}`;
}

function colorXml(tag: string, hex: string | undefined): string {
    return hex ? `<${tag} rgb="${argb(hex)}"/>` : '';
}

/**
 * 從 ConcreteStyle 反編 styles.xml 各池（numFmts/fonts/fills/borders/cellXfs），
 * cell 以 cellXf index 參照。fills[0]=none、fills[1]=gray125（Excel 慣例）。
 */
class StyleSheetBuilder {
    private readonly numFmts = new Map<string, number>(); // code → id（custom，164+）
    private readonly fonts = new Map<string, number>();
    private readonly fontXml: string[] = [];
    private readonly fills = new Map<string, number>();
    private readonly fillXml: string[] = [];
    private readonly borders = new Map<string, number>();
    private readonly borderXml: string[] = [];
    private readonly xfs = new Map<string, number>();
    private readonly xfDef: {
        numFmtId: number; fontId: number; fillId: number; borderId: number;
        align: ConcreteStyle['alignment'];
    }[] = [];

    constructor() {
        // 預設池項（index 0 / Excel 慣例）
        this.fontXml.push('<font><sz val="11"/><name val="Calibri"/></font>');
        this.fillXml.push('<fill><patternFill patternType="none"/></fill>');
        this.fillXml.push('<fill><patternFill patternType="gray125"/></fill>');
        this.borderXml.push('<border><left/><right/><top/><bottom/><diagonal/></border>');
    }

    private internNumFmt(code: string, originalId: number): number {
        // 內建（id<164 且非 0）直接用原 id、不入 numFmts；自訂則配 164+
        if (originalId > 0 && originalId < CUSTOM_NUMFMT_BASE) return originalId;
        const existing = this.numFmts.get(code);
        if (existing !== undefined) return existing;
        const id = CUSTOM_NUMFMT_BASE + this.numFmts.size;
        this.numFmts.set(code, id);
        return id;
    }

    private internFont(f: ConcreteStyle['font']): number {
        const parts: string[] = [];
        if (f.bold) parts.push('<b/>');
        if (f.italic) parts.push('<i/>');
        if (f.strike) parts.push('<strike/>');
        if (f.underline && f.underline !== 'none') parts.push('<u/>');
        if (f.size) parts.push(`<sz val="${f.size}"/>`);
        if (f.color) parts.push(colorXml('color', f.color));
        parts.push(`<name val="${f.name ? f.name.replace(/"/g, '') : 'Calibri'}"/>`);
        if (f.family !== undefined) parts.push(`<family val="${f.family}"/>`);
        if (f.charset !== undefined) parts.push(`<charset val="${f.charset}"/>`);
        const xml = `<font>${parts.join('')}</font>`;
        if (xml === '<font><name val="Calibri"/></font>' || xml === this.fontXml[0]) return 0;
        const existing = this.fonts.get(xml);
        if (existing !== undefined) return existing;
        const id = this.fontXml.length;
        this.fonts.set(xml, id);
        this.fontXml.push(xml);
        return id;
    }

    private internFill(fill: ConcreteStyle['fill']): number {
        const bg = fillBackgroundColor(fill);
        if (!bg) return 0; // none
        const xml = `<fill><patternFill patternType="solid"><fgColor rgb="${argb(bg)}"/><bgColor indexed="64"/></patternFill></fill>`;
        const existing = this.fills.get(xml);
        if (existing !== undefined) return existing;
        const id = this.fillXml.length;
        this.fills.set(xml, id);
        this.fillXml.push(xml);
        return id;
    }

    private internBorder(b: ConcreteStyle['border']): number {
        const edge = (side: string, e: { style?: string; color?: string } | undefined): string => {
            if (!e || !e.style) return `<${side}/>`;
            return `<${side} style="${e.style}">${colorXml('color', e.color ?? '000000')}</${side}>`;
        };
        const xml =
            `<border>${edge('left', b.left)}${edge('right', b.right)}${edge('top', b.top)}` +
            `${edge('bottom', b.bottom)}<diagonal/></border>`;
        if (xml === this.borderXml[0]) return 0;
        const existing = this.borders.get(xml);
        if (existing !== undefined) return existing;
        const id = this.borderXml.length;
        this.borders.set(xml, id);
        this.borderXml.push(xml);
        return id;
    }

    /** ConcreteStyle → cellXf index（0 = 預設無樣式）。*/
    intern(cs: ConcreteStyle | undefined): number {
        if (!cs) return 0;
        const numFmtId =
            cs.numFmtCode && cs.numFmtCode !== 'General'
                ? this.internNumFmt(cs.numFmtCode, cs.numFmtId)
                : 0;
        const fontId = this.internFont(cs.font);
        const fillId = this.internFill(cs.fill);
        const borderId = this.internBorder(cs.border);
        const align = cs.alignment;
        const key = JSON.stringify({ numFmtId, fontId, fillId, borderId, align: align ?? null });
        if (numFmtId === 0 && fontId === 0 && fillId === 0 && borderId === 0 && !align) return 0;
        const existing = this.xfs.get(key);
        if (existing !== undefined) return existing;
        const id = this.xfDef.length + 1; // index 0 = 預設 xf
        this.xfs.set(key, id);
        this.xfDef.push({ numFmtId, fontId, fillId, borderId, align });
        return id;
    }

    /** CF 用的 dxfs（exportXlsxFromBuffer 由原始 styles 帶入；保留原索引）。*/
    dxfs: Dxf[] = [];

    toXml(): string {
        const numFmtsXml =
            this.numFmts.size > 0
                ? `<numFmts count="${this.numFmts.size}">` +
                  [...this.numFmts.entries()]
                      .map(([code, id]) => `<numFmt numFmtId="${id}" formatCode="${code.replace(/"/g, '&quot;').replace(/&(?!quot;)/g, '&amp;')}"/>`)
                      .join('') +
                  `</numFmts>`
                : '';

        const xfXml = [`<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>`]
            .concat(
                this.xfDef.map((x) => {
                    const flags =
                        (x.numFmtId ? ' applyNumberFormat="1"' : '') +
                        (x.fontId ? ' applyFont="1"' : '') +
                        (x.fillId ? ' applyFill="1"' : '') +
                        (x.borderId ? ' applyBorder="1"' : '') +
                        (x.align ? ' applyAlignment="1"' : '');
                    let alignXml = '';
                    if (x.align) {
                        const a: string[] = [];
                        if (x.align.horizontal) a.push(`horizontal="${x.align.horizontal}"`);
                        if (x.align.vertical) a.push(`vertical="${x.align.vertical}"`);
                        if (x.align.wrapText) a.push('wrapText="1"');
                        alignXml = `<alignment ${a.join(' ')}/>`;
                    }
                    return `<xf numFmtId="${x.numFmtId}" fontId="${x.fontId}" fillId="${x.fillId}" borderId="${x.borderId}" xfId="0"${flags}>${alignXml}</xf>`;
                }),
            )
            .join('');

        return (
            `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
            `<styleSheet xmlns="${XMLNS_MAIN}">` +
            numFmtsXml +
            `<fonts count="${this.fontXml.length}">${this.fontXml.join('')}</fonts>` +
            `<fills count="${this.fillXml.length}">${this.fillXml.join('')}</fills>` +
            `<borders count="${this.borderXml.length}">${this.borderXml.join('')}</borders>` +
            `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
            `<cellXfs count="${this.xfDef.length + 1}">${xfXml}</cellXfs>` +
            `<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>` +
            writeDxfs(this.dxfs) +
            `</styleSheet>`
        );
    }
}

export interface WriteCol {
    min: number;
    max: number;
    /** 欄寬（字元數）。*/
    width: number;
}

export interface WriteSheet {
    name: string;
    cells: WriteCell[];
    merges: string[];
    /** 自訂欄寬。*/
    cols?: WriteCol[];
    /** 自訂列高（1-based row → point）。*/
    rowHeights?: Map<number, number>;
    /** 條件格式（CF round-trip）。*/
    conditionalFormats?: ConditionalFormatting[];
    /** 此 sheet 連結的 drawing part（相對 worksheet 的 rels target，如 `../drawings/drawing1.xml`）。*/
    drawingTarget?: string;
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

function cellXml(cell: WriteCell, pool: StringPool, styles: StyleSheetBuilder): string {
    const ref = `${columnIndexToLetter(cell.col)}${cell.row}`;
    const v = cell.value;
    const sIdx = styles.intern(cell.style);
    const s = sIdx > 0 ? ` s="${sIdx}"` : '';

    if (cell.formula !== undefined) {
        const f = `<f>${xmlEscape(cell.formula)}</f>`;
        if (typeof v === 'number') return `<c r="${ref}"${s}>${f}<v>${v}</v></c>`;
        if (typeof v === 'boolean') return `<c r="${ref}"${s} t="b">${f}<v>${v ? 1 : 0}</v></c>`;
        if (typeof v === 'string') return `<c r="${ref}"${s} t="str">${f}<v>${xmlEscape(v)}</v></c>`;
        return `<c r="${ref}"${s}>${f}</c>`;
    }
    if (typeof v === 'number') return `<c r="${ref}"${s}><v>${v}</v></c>`;
    if (typeof v === 'boolean') return `<c r="${ref}"${s} t="b"><v>${v ? 1 : 0}</v></c>`;
    if (typeof v === 'string' && v !== '') {
        return `<c r="${ref}"${s} t="s"><v>${pool.intern(v)}</v></c>`;
    }
    return sIdx > 0 ? `<c r="${ref}"${s}/>` : `<c r="${ref}"/>`;
}

function sheetXml(sheet: WriteSheet, pool: StringPool, styles: StyleSheetBuilder): string {
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
    // 列 = 有 cell 的列 ∪ 有自訂列高的列（只有列高的空列也要寫出）
    const rowSet = new Set<number>(byRow.keys());
    if (sheet.rowHeights) for (const r of sheet.rowHeights.keys()) rowSet.add(r);
    const rows = [...rowSet].sort((a, b) => a - b);
    const rowsXml = rows
        .map((r) => {
            const cells = (byRow.get(r) ?? [])
                .sort((a, b) => a.col - b.col)
                .map((c) => cellXml(c, pool, styles))
                .join('');
            const h = sheet.rowHeights?.get(r);
            const rowAttrs = h !== undefined ? ` ht="${h}" customHeight="1"` : '';
            return `<row r="${r}"${rowAttrs}>${cells}</row>`;
        })
        .join('');

    const colsXml =
        sheet.cols && sheet.cols.length > 0
            ? `<cols>${sheet.cols
                  .map((c) => `<col min="${c.min}" max="${c.max}" width="${c.width}" customWidth="1"/>`)
                  .join('')}</cols>`
            : '';

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
        colsXml +
        `<sheetData>${rowsXml}</sheetData>` +
        mergeXml +
        writeConditionalFormattings(sheet.conditionalFormats) +
        (sheet.drawingTarget ? `<drawing r:id="rId1"/>` : '') +
        `</worksheet>`
    );
}

/**
 * 寫出 xlsx bytes。
 * @param opts.dxfs CF 用的 differential formats
 * @param opts.rawParts 直通複製的原始 parts（圖表/drawing/media + 其 _rels）
 * @param opts.extraOverrides Content_Types 的 <Override> 片段（圖表/drawing parts）
 * @param opts.extraDefaults Content_Types 的 <Default> 片段（圖片副檔名）
 */
export function buildXlsx(
    sheets: WriteSheet[],
    opts?: {
        dxfs?: Dxf[];
        rawParts?: Record<string, Uint8Array>;
        extraOverrides?: string;
        extraDefaults?: string;
    },
): Uint8Array {
    const list = sheets.length > 0 ? sheets : [{ name: 'Sheet1', cells: [], merges: [] }];
    const pool = new StringPool();
    const styleBuilder = new StyleSheetBuilder();
    if (opts?.dxfs) styleBuilder.dxfs = opts.dxfs;

    const sheetFiles: Record<string, string> = {};
    const sheetRelsFiles: Record<string, string> = {};
    list.forEach((s, i) => {
        sheetFiles[`xl/worksheets/sheet${i + 1}.xml`] = sheetXml(s, pool, styleBuilder);
        // 有 drawing 的 sheet：重建 worksheet→drawing 關聯（rId1）
        if (s.drawingTarget) {
            sheetRelsFiles[`xl/worksheets/_rels/sheet${i + 1}.xml.rels`] =
                `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
                `<Relationships xmlns="${PKG_REL}">` +
                `<Relationship Id="rId1" Type="${XMLNS_R}/drawing" Target="${s.drawingTarget}"/>` +
                `</Relationships>`;
        }
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

    const styles = styleBuilder.toXml();

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
        (opts?.extraDefaults ?? '') +
        `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
        list
            .map((_s, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`)
            .join('') +
        `<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>` +
        `<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>` +
        (opts?.extraOverrides ?? '') +
        `</Types>`;

    const files: Record<string, Uint8Array> = {
        '[Content_Types].xml': strToU8(contentTypes),
        '_rels/.rels': strToU8(rootRels),
        'xl/workbook.xml': strToU8(workbook),
        'xl/_rels/workbook.xml.rels': strToU8(workbookRels),
        'xl/sharedStrings.xml': strToU8(sharedStrings),
        'xl/styles.xml': strToU8(styles),
        ...Object.fromEntries(Object.entries(sheetFiles).map(([k, v]) => [k, strToU8(v)])),
        ...Object.fromEntries(Object.entries(sheetRelsFiles).map(([k, v]) => [k, strToU8(v)])),
        ...(opts?.rawParts ?? {}),
    };

    return zipSync(files);
}
