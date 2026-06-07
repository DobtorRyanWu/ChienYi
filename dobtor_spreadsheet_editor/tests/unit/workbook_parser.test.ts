// workbook_parser.test.ts — 解析 xl/workbook.xml（規劃書 §1.3）
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { zipSync, strToU8 } from 'fflate';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

function firstXlsx(category: string): string {
    const dir = join(FIXTURES, category);
    const f = readdirSync(dir).find((n) => n.toLowerCase().endsWith('.xlsx'));
    if (!f) throw new Error(`no xlsx in ${category}`);
    return join(dir, f);
}

/** 合成含 2 sheet（一隱藏）、定義名稱、view、calcPr 的最小 workbook package。*/
function syntheticWorkbook(): Uint8Array {
    const ct =
        `<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
        `<Default Extension="xml" ContentType="application/xml"/></Types>`;
    const rootRels =
        `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
        `<Relationship Id="rId1" Type="${NS_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
    const wbRels =
        `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
        `<Relationship Id="rId1" Type="${NS_REL}/worksheet" Target="worksheets/sheet1.xml"/>` +
        `<Relationship Id="rId2" Type="${NS_REL}/worksheet" Target="worksheets/sheet2.xml"/>` +
        `<Relationship Id="rId3" Type="${NS_REL}/sharedStrings" Target="sharedStrings.xml"/>` +
        `<Relationship Id="rId4" Type="${NS_REL}/styles" Target="styles.xml"/>` +
        `<Relationship Id="rId5" Type="${NS_REL}/theme" Target="theme/theme1.xml"/>` +
        `</Relationships>`;
    const wb =
        `<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ` +
        `xmlns:r="${NS_REL}">` +
        `<bookViews><workbookView activeTab="1" firstSheet="0"/></bookViews>` +
        `<sheets>` +
        `<sheet name="工作表1" sheetId="1" r:id="rId1"/>` +
        `<sheet name="隱藏表" sheetId="2" state="hidden" r:id="rId2"/>` +
        `</sheets>` +
        `<definedNames>` +
        `<definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'工作表1'!$A$1:$C$9</definedName>` +
        `<definedName name="稅率">'工作表1'!$Z$1</definedName>` +
        `</definedNames>` +
        `<calcPr calcId="191029" refMode="R1C1"/>` +
        `</workbook>`;
    return zipSync({
        '[Content_Types].xml': strToU8(ct),
        '_rels/.rels': strToU8(rootRels),
        'xl/workbook.xml': strToU8(wb),
        'xl/_rels/workbook.xml.rels': strToU8(wbRels),
        'xl/worksheets/sheet1.xml': strToU8('<worksheet/>'),
        'xl/worksheets/sheet2.xml': strToU8('<worksheet/>'),
    });
}

describe('WorkbookParser — 合成 workbook', () => {
    const parser = new WorkbookParser(PackageReader.fromBuffer(syntheticWorkbook()));
    const result = parser.parse();

    it('解析 2 個 sheet 與名稱', () => {
        expect(result.sheets.map((s) => s.name)).toEqual(['工作表1', '隱藏表']);
    });
    it('sheetId 轉整數', () => {
        expect(result.sheets[0].sheetId).toBe(1);
    });
    it('state：預設 visible、明確 hidden', () => {
        expect(result.sheets[0].state).toBe('visible');
        expect(result.sheets[1].state).toBe('hidden');
    });
    it('r:id 解析成 worksheet part 路徑', () => {
        expect(result.sheets[0].target).toBe('xl/worksheets/sheet1.xml');
        expect(result.sheets[1].target).toBe('xl/worksheets/sheet2.xml');
    });
    it('definedNames：保留名與全域名稱', () => {
        expect(result.definedNames).toHaveLength(2);
        const filter = result.definedNames[0];
        expect(filter.name).toBe('_xlnm._FilterDatabase');
        expect(filter.reserved).toBe(true);
        expect(filter.localSheetId).toBe(0);
        expect(filter.hidden).toBe(true);
        expect(filter.formula).toBe("'工作表1'!$A$1:$C$9");
        const rate = result.definedNames[1];
        expect(rate.reserved).toBe(false);
        expect(rate.localSheetId).toBeUndefined();
    });
    it('workbookView：activeTab / firstSheet', () => {
        expect(result.view.activeTab).toBe(1);
        expect(result.view.firstSheet).toBe(0);
    });
    it('calcPr：refMode R1C1', () => {
        expect(result.calc.refMode).toBe('R1C1');
        expect(result.calc.iterate).toBe(false);
    });
    it('相關 part 解析', () => {
        expect(parser.sharedStringsPart()).toBe('xl/sharedStrings.xml');
        expect(parser.stylesPart()).toBe('xl/styles.xml');
        expect(parser.themePart()).toBe('xl/theme/theme1.xml');
        expect(parser.worksheetParts()).toEqual([
            'xl/worksheets/sheet1.xml',
            'xl/worksheets/sheet2.xml',
        ]);
    });
});

describe('WorkbookParser — 真實契約詳細表（16 sheet）', () => {
    const path = firstXlsx('08_chienyii_business'); // 估驗差異表為首；改用契約詳細表更具代表
    const contract = join(
        FIXTURES,
        '08_chienyii_business',
        '延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx',
    );
    const parser = new WorkbookParser(PackageReader.fromBuffer(readFileSync(contract)));
    const result = parser.parse();

    it('16 個 sheet', () => {
        expect(result.sheets).toHaveLength(16);
    });
    it('sheet 名稱含詳細價目表', () => {
        expect(result.sheets[0].name).toContain('詳細價目表');
    });
    it('每個 sheet 都解出 worksheet target 且實存', () => {
        const pkg = PackageReader.fromBuffer(readFileSync(contract));
        for (const s of result.sheets) {
            expect(s.target).toBeDefined();
            expect(pkg.hasPart(s.target!)).toBe(true);
        }
    });
    it('含 _xlnm 保留定義名稱', () => {
        expect(result.definedNames.some((d) => d.reserved)).toBe(true);
    });
    it('sharedStrings / styles part 可解析', () => {
        expect(parser.sharedStringsPart()).toBe('xl/sharedStrings.xml');
        expect(parser.stylesPart()).toBe('xl/styles.xml');
    });
    // path 變數保留以確保 firstXlsx 對該分類可用
    it('分類至少一個 xlsx', () => {
        expect(path).toMatch(/\.xlsx$/);
    });
});
