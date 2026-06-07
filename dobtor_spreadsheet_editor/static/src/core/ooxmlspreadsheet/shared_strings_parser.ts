// shared_strings_parser.ts — 解析 xl/sharedStrings.xml（規劃書 §1.4）
//
// sst 是字串池，worksheet cell（t="s"）以索引引用。每個 <si> 可能是：
//   純文字：  <si><t>text</t></si>
//   空字串：  <si><t/></si>
//   保留空白：<si><t xml:space="preserve"> a </t></si>
//   rich text：<si><r><t>..</t></r><r><rPr>..</rPr><t>..</t></r></si>（多 run、各有字型樣式）
//
// 本層攤平出純文字（text，供 cell value 提取），並保留 rich run 結構（runs，Phase 2 套樣式用）。
// 同時解碼 OOXML 的 _xHHHH_ 控制字元跳脫。

import { parseXml, toArray, attr, textOf, decodeOoxmlEscapes } from './xml_util';

export type VertAlign = 'baseline' | 'superscript' | 'subscript';

/** rich text run 的字型樣式（§1.4 結構保留，完整套用於 Phase 2）。*/
export interface RunProperties {
    bold?: boolean;
    italic?: boolean;
    underline?: boolean;
    strike?: boolean;
    /** 字級（point）。*/
    size?: number;
    /** ARGB hex（如 "FFFF0000"）；theme/indexed 色 Phase 2 再解析。*/
    color?: string;
    /** 字型名稱（rFont）。*/
    font?: string;
    family?: number;
    charset?: number;
    vertAlign?: VertAlign;
}

export interface RichTextRun {
    text: string;
    props?: RunProperties;
}

export interface SharedString {
    /** 攤平純文字（已串接 runs、已解碼 _xHHHH_）。*/
    text: string;
    /** rich text 結構；純文字 si 為 undefined。*/
    runs?: RichTextRun[];
}

/** 判斷 rPr 旗標型子元素（如 <b/>、<b val="0"/>）。存在且 val≠"0" 即 true。*/
function flag(rPr: Record<string, unknown>, tag: string): boolean | undefined {
    if (!(tag in rPr)) return undefined;
    return attr(rPr[tag], 'val') !== '0';
}

function parseRunProperties(rPrRaw: unknown): RunProperties | undefined {
    if (rPrRaw === null || typeof rPrRaw !== 'object') return undefined;
    const rPr = rPrRaw as Record<string, unknown>;
    const props: RunProperties = {};

    const b = flag(rPr, 'b');
    if (b !== undefined) props.bold = b;
    const i = flag(rPr, 'i');
    if (i !== undefined) props.italic = i;
    if ('strike' in rPr) props.strike = flag(rPr, 'strike') ?? true;
    if ('u' in rPr) props.underline = attr(rPr['u'], 'val') !== 'none';

    const sz = attr(rPr['sz'], 'val');
    if (sz !== undefined) {
        const n = Number(sz);
        if (!Number.isNaN(n)) props.size = n;
    }
    const rgb = attr(rPr['color'], 'rgb');
    if (rgb !== undefined) props.color = rgb;

    const font = attr(rPr['rFont'], 'val');
    if (font !== undefined) props.font = font;
    const family = attr(rPr['family'], 'val');
    if (family !== undefined) props.family = Number.parseInt(family, 10);
    const charset = attr(rPr['charset'], 'val');
    if (charset !== undefined) props.charset = Number.parseInt(charset, 10);

    const va = attr(rPr['vertAlign'], 'val');
    if (va === 'superscript' || va === 'subscript' || va === 'baseline') props.vertAlign = va;

    return Object.keys(props).length > 0 ? props : undefined;
}

/**
 * 解析單一 string item（`<si>` 或 worksheet 的 inline `<is>`，兩者結構相同）。
 * 攤平出純文字並保留 rich run。
 */
export function parseStringItem(si: Record<string, unknown>): SharedString {
    // rich text：含 <r> run
    if ('r' in si) {
        const runs: RichTextRun[] = toArray<unknown>(si['r']).map((r) => {
            const run = (r ?? {}) as Record<string, unknown>;
            const text = decodeOoxmlEscapes(textOf(run['t']));
            const props = parseRunProperties(run['rPr']);
            return props ? { text, props } : { text };
        });
        return { text: runs.map((r) => r.text).join(''), runs };
    }
    // 純文字 <t>（可能含 xml:space="preserve"、可能為空）
    return { text: decodeOoxmlEscapes(textOf(si['t'])) };
}

export class SharedStringsParser {
    /** 解析 sharedStrings.xml 字串 → SharedString[]（索引 = sst 索引）。*/
    static parse(xmlText: string): SharedString[] {
        const xml = parseXml(xmlText);
        const sst = (xml['sst'] ?? {}) as Record<string, unknown>;
        return toArray<unknown>(sst['si']).map((si) =>
            parseStringItem((si ?? {}) as Record<string, unknown>),
        );
    }
}
