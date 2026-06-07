// shared_strings_parser.test.ts — 解析 xl/sharedStrings.xml（規劃書 §1.4）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { SharedStringsParser } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

const SYNTHETIC =
    `<?xml version="1.0"?><sst xmlns="${NS_MAIN}" count="6" uniqueCount="6">` +
    `<si><t>純文字</t></si>` +
    `<si><t/></si>` +
    `<si><t xml:space="preserve">  前後空白  </t></si>` +
    `<si><t xml:space="preserve">第一行_x000D_\n第二行</t></si>` +
    `<si><t>字面底線_x005F_x000D_保留</t></si>` +
    `<si><r><t>正常</t></r><r><rPr><b/><sz val="12"/><color rgb="FFFF0000"/><rFont val="標楷體"/><charset val="136"/></rPr><t>紅粗體</t></r></si>` +
    `</sst>`;

describe('SharedStringsParser — 合成 sst', () => {
    const ss = SharedStringsParser.parse(SYNTHETIC);

    it('解析 6 個 si', () => {
        expect(ss).toHaveLength(6);
    });
    it('純文字', () => {
        expect(ss[0].text).toBe('純文字');
        expect(ss[0].runs).toBeUndefined();
    });
    it('空字串 <t/>', () => {
        expect(ss[1].text).toBe('');
    });
    it('xml:space=preserve 保留空白', () => {
        expect(ss[2].text).toBe('  前後空白  ');
    });
    it('_x000D_ 解碼成 CR', () => {
        expect(ss[3].text).toBe('第一行\r\n第二行');
    });
    it('_x005F_ 還原成字面底線（不誤解碼後續）', () => {
        expect(ss[4].text).toBe('字面底線_x000D_保留');
    });
    it('rich text：runs 結構與攤平文字', () => {
        const si = ss[5];
        expect(si.text).toBe('正常紅粗體');
        expect(si.runs).toHaveLength(2);
        expect(si.runs![0].text).toBe('正常');
        expect(si.runs![0].props).toBeUndefined();
        const red = si.runs![1];
        expect(red.text).toBe('紅粗體');
        expect(red.props?.bold).toBe(true);
        expect(red.props?.size).toBe(12);
        expect(red.props?.color).toBe('FFFF0000');
        expect(red.props?.font).toBe('標楷體');
        expect(red.props?.charset).toBe(136);
    });
});

describe('SharedStringsParser — 真實契約詳細表', () => {
    const contract = join(
        FIXTURES,
        '08_chienyii_business',
        '延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx',
    );
    const pkg = PackageReader.fromBuffer(readFileSync(contract));
    const part = new WorkbookParser(pkg).sharedStringsPart();
    const ss = SharedStringsParser.parse(pkg.getPartText(part!));

    it('uniqueCount = 3303 條', () => {
        expect(ss).toHaveLength(3303);
    });
    it('索引 0 為工程處抬頭', () => {
        expect(ss[0].text).toBe('臺北市政府工務局水利工程處');
    });
    it('至少一條 rich text（多 run）', () => {
        expect(ss.some((s) => s.runs !== undefined && s.runs.length > 1)).toBe(true);
    });
    it('含 _x000D_ 解碼後的換行內容', () => {
        // 工項說明欄常見「分析表N_x000D_」→ 解碼後不應殘留字面 _x000D_
        expect(ss.every((s) => !s.text.includes('_x000D_'))).toBe(true);
    });
});
