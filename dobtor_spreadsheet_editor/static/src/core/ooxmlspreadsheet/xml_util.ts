// xml_util.ts — OOXML XML 解析共用工具
//
// 全 parser 共用一份 fast-xml-parser 設定與 helper，避免各檔重複。

import { XMLParser } from 'fast-xml-parser';

export const ATTR_PREFIX = '@_';
export const TEXT_NODE = '#text';

const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: ATTR_PREFIX,
    textNodeName: TEXT_NODE,
    parseAttributeValue: false, // 屬性一律當字串，由各 parser 自行轉型
    parseTagValue: false, // 文字節點保留原字串（避免 "1.1.1" 被當數字）
    trimValues: false, // 保留空白（sharedStrings xml:space="preserve" 需要）
});

/** 解析 XML 字串成物件樹（保留命名空間前綴，如 r:id）。*/
export function parseXml(text: string): Record<string, unknown> {
    return parser.parse(text) as Record<string, unknown>;
}

// theme1.xml 全程 a: 前綴；去前綴後存取較乾淨（dk1/srgbClr 而非 a:dk1）。
const parserNoNs = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: ATTR_PREFIX,
    textNodeName: TEXT_NODE,
    parseAttributeValue: false,
    parseTagValue: false,
    trimValues: false,
    removeNSPrefix: true,
});

/** 解析 XML 字串並移除命名空間前綴（給 DrawingML theme 用，勿用於 r:id 相關）。*/
export function parseXmlNoNs(text: string): Record<string, unknown> {
    return parserNoNs.parse(text) as Record<string, unknown>;
}

/** fast-xml-parser 對單一/多個同名節點回傳 object/array 不一致，統一轉陣列。*/
export function toArray<T>(node: T | T[] | undefined | null): T[] {
    if (node === undefined || node === null) return [];
    return Array.isArray(node) ? node : [node];
}

/** 讀屬性字串（自動補 ATTR_PREFIX）；無回 undefined。*/
export function attr(obj: unknown, name: string): string | undefined {
    if (obj === null || typeof obj !== 'object') return undefined;
    const v = (obj as Record<string, unknown>)[ATTR_PREFIX + name];
    return v === undefined || v === null ? undefined : String(v);
}

/** 讀屬性並轉整數；無或非數字回 undefined。*/
export function intAttr(obj: unknown, name: string): number | undefined {
    const s = attr(obj, name);
    if (s === undefined) return undefined;
    const n = Number.parseInt(s, 10);
    return Number.isNaN(n) ? undefined : n;
}

/** 讀屬性並轉布林（"1"/"true" → true）。預設 false。*/
export function boolAttr(obj: unknown, name: string): boolean {
    const s = attr(obj, name);
    return s === '1' || s === 'true';
}

/** 取文字節點內容。*/
/**
 * 解碼 XML numeric character reference（`&#NNNN;` / `&#xHHHH;`）。
 * fast-xml-parser 預設不解這類 reference（部分工具如 openpyxl 用此編碼 CJK，
 * 真實 Excel 多直接寫 UTF-8 故少見）。命名實體（&amp; 等）已由 parser 處理。
 */
function decodeNumericEntities(s: string): string {
    if (s.indexOf('&#') === -1) return s;
    return s
        .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
        .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)));
}

export function textOf(obj: unknown): string {
    if (obj === null || obj === undefined) return '';
    if (typeof obj === 'string') return decodeNumericEntities(obj);
    if (typeof obj === 'object') {
        const v = (obj as Record<string, unknown>)[TEXT_NODE];
        return v === undefined || v === null ? '' : decodeNumericEntities(String(v));
    }
    return String(obj);
}

/**
 * 解碼 OOXML 的 `_xHHHH_` 控制字元跳脫（ECMA-376 §22.4.2.4）。
 * 例：`_x000D_` → CR。單次左到右掃描即可正確處理 `_x005F_`（跳脫的底線）：
 *   `_x005F_x000D_`（字面 "_x000D_"）→ 先還原 `_x005F_`→`_`，剩 `x000D_` 不再被吃，得字面 `_x000D_`。
 */
export function decodeOoxmlEscapes(s: string): string {
    if (s.indexOf('_x') === -1) return s;
    return s.replace(/_x([0-9A-Fa-f]{4})_/g, (_m, hex: string) =>
        String.fromCharCode(Number.parseInt(hex, 16)),
    );
}
