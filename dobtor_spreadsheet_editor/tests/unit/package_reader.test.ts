// package_reader.test.ts — OPC 容器讀取測試（規劃書 §1.1）
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { zipSync, strToU8 } from 'fflate';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';

const FIXTURES = join(__dirname, '..', 'fixtures');
const WORKBOOK_CT =
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml';

/** 取某分類第一個 xlsx 的絕對路徑。*/
function firstXlsx(category: string): string {
    const dir = join(FIXTURES, category);
    const f = readdirSync(dir).find((n) => n.toLowerCase().endsWith('.xlsx'));
    if (!f) throw new Error(`no xlsx fixture in ${category}`);
    return join(dir, f);
}

/** 合成最小 OPC package，用於精確驗證相對路徑解析。*/
function syntheticXlsx(): Uint8Array {
    const contentTypes =
        `<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
        `<Default Extension="xml" ContentType="application/xml"/>` +
        `<Override PartName="/xl/workbook.xml" ContentType="${WORKBOOK_CT}"/>` +
        `</Types>`;
    const rootRels =
        `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
        `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>` +
        `</Relationships>`;
    const wbRels =
        `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
        `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>` +
        `<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/coreProperties" Target="../docProps/core.xml"/>` +
        `<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com" TargetMode="External"/>` +
        `</Relationships>`;
    return zipSync({
        '[Content_Types].xml': strToU8(contentTypes),
        '_rels/.rels': strToU8(rootRels),
        'xl/workbook.xml': strToU8('<workbook/>'),
        'xl/_rels/workbook.xml.rels': strToU8(wbRels),
        'xl/worksheets/sheet1.xml': strToU8('<worksheet/>'),
    });
}

describe('PackageReader — 合成 package', () => {
    const reader = PackageReader.fromBuffer(syntheticXlsx());

    it('listParts 含核心 part', () => {
        const parts = reader.listParts();
        expect(parts).toContain('[Content_Types].xml');
        expect(parts).toContain('xl/workbook.xml');
    });

    it('getPartText 解碼正確', () => {
        expect(reader.getPartText('xl/workbook.xml')).toBe('<workbook/>');
    });

    it('getPart 不存在回 undefined', () => {
        expect(reader.getPart('xl/nope.xml')).toBeUndefined();
    });

    it('getContentType：Override 優先', () => {
        expect(reader.getContentType('xl/workbook.xml')).toBe(WORKBOOK_CT);
    });

    it('getContentType：Default 依副檔名', () => {
        expect(reader.getContentType('xl/worksheets/sheet1.xml')).toBe('application/xml');
    });

    it('getRootRels：officeDocument 解析成 xl/workbook.xml', () => {
        const rels = reader.getRootRels();
        const office = rels.find((r) => r.type.endsWith('/officeDocument'));
        expect(office?.resolvedTarget).toBe('xl/workbook.xml');
        expect(office?.targetMode).toBe('Internal');
    });

    it('getRels：相對路徑（worksheets/sheet1.xml）解析', () => {
        const rels = reader.getRels('xl/workbook.xml');
        const ws = rels.find((r) => r.id === 'rId1');
        expect(ws?.resolvedTarget).toBe('xl/worksheets/sheet1.xml');
    });

    it('getRels：上層相對路徑（../docProps/core.xml）解析', () => {
        const rels = reader.getRels('xl/workbook.xml');
        const core = rels.find((r) => r.id === 'rId2');
        expect(core?.resolvedTarget).toBe('docProps/core.xml');
    });

    it('getRels：External target 保留原值', () => {
        const rels = reader.getRels('xl/workbook.xml');
        const link = rels.find((r) => r.id === 'rId3');
        expect(link?.targetMode).toBe('External');
        expect(link?.resolvedTarget).toBe('https://example.com');
    });

    it('無 rels 的 part 回空陣列', () => {
        expect(reader.getRels('xl/worksheets/sheet1.xml')).toEqual([]);
    });
});

describe('PackageReader — 非法輸入', () => {
    it('缺 [Content_Types].xml 丟錯', () => {
        const bad = zipSync({ 'foo.xml': strToU8('<x/>') });
        expect(() => PackageReader.fromBuffer(bad)).toThrow(/Content_Types/);
    });
});

describe('PackageReader — 真實 ChienYi fixture', () => {
    const path = firstXlsx('08_chienyii_business');
    const reader = PackageReader.fromBuffer(readFileSync(path));

    it('含 workbook 與 Content_Types', () => {
        expect(reader.hasPart('[Content_Types].xml')).toBe(true);
        expect(reader.hasPart('xl/workbook.xml')).toBe(true);
    });

    it('workbook content type 為 spreadsheetml main', () => {
        expect(reader.getContentType('xl/workbook.xml')).toContain('spreadsheetml');
    });

    it('根關聯指向 xl/workbook.xml', () => {
        const office = reader.getRootRels().find((r) => r.type.endsWith('/officeDocument'));
        expect(office?.resolvedTarget).toBe('xl/workbook.xml');
    });

    it('workbook 關聯含至少一個 worksheet', () => {
        const rels = reader.getRels('xl/workbook.xml');
        const sheets = rels.filter((r) => r.type.endsWith('/worksheet'));
        expect(sheets.length).toBeGreaterThanOrEqual(1);
        expect(sheets[0].resolvedTarget).toMatch(/^xl\/worksheets\//);
    });
});
