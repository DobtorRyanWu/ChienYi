// package_reader.ts — OPC（Open Packaging Conventions）容器讀取（規劃書 §1.1）
//
// xlsx = 一個 zip（OPC package），內含多個 part：
//   [Content_Types].xml      每個 part 的 MIME type（Default by extension + Override by name）
//   _rels/.rels              package 層級關聯（根 → xl/workbook.xml）
//   xl/workbook.xml          活頁簿主檔
//   xl/_rels/workbook.xml.rels   workbook → 各 worksheet / sharedStrings / styles 的關聯
//   xl/worksheets/sheetN.xml ...
//
// 本層只負責：解 zip、取 part bytes/text、解析 Content_Types、解析 .rels（含相對路徑解析）。
// 不解析任何試算表語意（那是 §1.3+ 各 parser 的工作）。

import { unzipSync, strFromU8 } from 'fflate';
import { parseXml, toArray, attr } from './xml_util';

const CONTENT_TYPES_PART = '[Content_Types].xml';

/** 單一 OPC 關聯。*/
export interface Relationship {
    id: string;
    type: string;
    /** 原始 Target 屬性值（可能是相對或外部 URL）。*/
    target: string;
    /** Internal（預設，套件內部 part）或 External（外部 URL）。*/
    targetMode: 'Internal' | 'External';
    /** Internal 時：已解析成 package 絕對路徑（無前導斜線）；External 時等同 target。*/
    resolvedTarget: string;
}

interface ContentTypesIndex {
    defaults: Map<string, string>; // extension(小寫) → contentType
    overrides: Map<string, string>; // partName(前導斜線) → contentType
}

/** 正規化 part 名稱：去前導斜線，作為 zip entry key。*/
function normalizePart(name: string): string {
    return name.replace(/^\/+/, '');
}

/**
 * 解析相對 target：以 sourcePart 所在目錄為基準，支援 `../`。
 * 例：source = 'xl/workbook.xml'、target = 'worksheets/sheet1.xml'
 *     → 'xl/worksheets/sheet1.xml'
 * 例：source = 'xl/worksheets/sheet1.xml'、target = '../sharedStrings.xml'
 *     → 'xl/sharedStrings.xml'
 */
function resolveRelativeTarget(sourcePart: string, target: string): string {
    if (target.startsWith('/')) return normalizePart(target); // package 絕對路徑
    const baseDir = sourcePart.includes('/') ? sourcePart.replace(/\/[^/]*$/, '') : '';
    const stack = baseDir ? baseDir.split('/') : [];
    for (const seg of target.split('/')) {
        if (seg === '' || seg === '.') continue;
        if (seg === '..') stack.pop();
        else stack.push(seg);
    }
    return stack.join('/');
}

export class PackageReader {
    private readonly parts: Record<string, Uint8Array>;
    private contentTypesCache: ContentTypesIndex | null = null;
    private readonly relsCache = new Map<string, Relationship[]>();

    private constructor(parts: Record<string, Uint8Array>) {
        this.parts = parts;
    }

    /** 從 xlsx 二進位（ArrayBuffer 或 Uint8Array）建立 reader。*/
    static fromBuffer(buffer: ArrayBuffer | Uint8Array): PackageReader {
        const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        const parts = unzipSync(bytes);
        if (!(CONTENT_TYPES_PART in parts)) {
            throw new Error(`Invalid xlsx: missing ${CONTENT_TYPES_PART}`);
        }
        return new PackageReader(parts);
    }

    /** 列出所有 part 名稱（zip entry，無前導斜線）。*/
    listParts(): string[] {
        return Object.keys(this.parts);
    }

    hasPart(name: string): boolean {
        return normalizePart(name) in this.parts;
    }

    /** 取 part 原始 bytes；不存在回 undefined。*/
    getPart(name: string): Uint8Array | undefined {
        return this.parts[normalizePart(name)];
    }

    /** 取 part 並 UTF-8 解碼成字串；不存在則丟錯。*/
    getPartText(name: string): string {
        const bytes = this.getPart(name);
        if (bytes === undefined) throw new Error(`Part not found: ${name}`);
        return strFromU8(bytes);
    }

    private buildContentTypesIndex(): ContentTypesIndex {
        const xml = parseXml(this.getPartText(CONTENT_TYPES_PART));
        const types = (xml['Types'] ?? {}) as Record<string, unknown>;
        const defaults = new Map<string, string>();
        const overrides = new Map<string, string>();
        for (const d of toArray<unknown>(types['Default'])) {
            const ext = attr(d, 'Extension');
            const ct = attr(d, 'ContentType');
            if (ext && ct) defaults.set(ext.toLowerCase(), ct);
        }
        for (const o of toArray<unknown>(types['Override'])) {
            const part = attr(o, 'PartName');
            const ct = attr(o, 'ContentType');
            if (part && ct) overrides.set(part, ct);
        }
        return { defaults, overrides };
    }

    /**
     * 取得 part 的 content type：Override（依完整 part 名）優先，否則 Default（依副檔名）。
     * 查無回 undefined。
     */
    getContentType(name: string): string | undefined {
        if (this.contentTypesCache === null) {
            this.contentTypesCache = this.buildContentTypesIndex();
        }
        const withSlash = '/' + normalizePart(name);
        const override = this.contentTypesCache.overrides.get(withSlash);
        if (override) return override;
        const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : '';
        return this.contentTypesCache.defaults.get(ext);
    }

    /**
     * 取得某 part 的關聯清單。對 part `dir/name.xml` 讀 `dir/_rels/name.xml.rels`。
     * 傳入空字串或 '/' 取 package 根關聯（`_rels/.rels`）。查無回空陣列。
     */
    getRels(partName: string): Relationship[] {
        const part = normalizePart(partName);
        const cached = this.relsCache.get(part);
        if (cached) return cached;

        const slash = part.lastIndexOf('/');
        const dir = slash >= 0 ? part.slice(0, slash) : '';
        const file = slash >= 0 ? part.slice(slash + 1) : part;
        const relsPath = (dir ? dir + '/' : '') + '_rels/' + file + '.rels';

        const rels: Relationship[] = [];
        if (this.hasPart(relsPath)) {
            const xml = parseXml(this.getPartText(relsPath));
            const container = (xml['Relationships'] ?? {}) as Record<string, unknown>;
            for (const r of toArray<unknown>(container['Relationship'])) {
                const target = attr(r, 'Target') ?? '';
                const mode = attr(r, 'TargetMode') === 'External' ? 'External' : 'Internal';
                rels.push({
                    id: attr(r, 'Id') ?? '',
                    type: attr(r, 'Type') ?? '',
                    target,
                    targetMode: mode,
                    resolvedTarget:
                        mode === 'External' ? target : resolveRelativeTarget(part, target),
                });
            }
        }
        this.relsCache.set(part, rels);
        return rels;
    }

    /** 取得 package 根關聯（`_rels/.rels`）的捷徑。*/
    getRootRels(): Relationship[] {
        return this.getRels('');
    }
}
