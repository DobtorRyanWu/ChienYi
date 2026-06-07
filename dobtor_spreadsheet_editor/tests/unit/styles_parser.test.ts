// styles_parser.test.ts — 解析 xl/styles.xml（規劃書 §1.5）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import {
    StylesParser,
    numberFormatCode,
    isDateFormatCode,
    isDateNumberFormat,
} from '../../static/src/core/ooxmlspreadsheet/styles_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

const STYLES_XML =
    `<?xml version="1.0"?><styleSheet xmlns="${NS_MAIN}">` +
    `<numFmts count="2">` +
    `<numFmt numFmtId="176" formatCode="[$-404]gge&quot;年&quot;m&quot;月&quot;d&quot;日&quot;;@"/>` +
    `<numFmt numFmtId="179" formatCode="#,##0.00_ "/>` +
    `</numFmts>` +
    `<fonts count="2">` +
    `<font><sz val="12"/><name val="新細明體"/><charset val="134"/></font>` +
    `<font><b/><sz val="14"/><color rgb="FFFF0000"/><name val="標楷體"/><family val="4"/></font>` +
    `</fonts>` +
    `<fills count="3">` +
    `<fill><patternFill patternType="none"/></fill>` +
    `<fill><patternFill patternType="gray125"/></fill>` +
    `<fill><patternFill patternType="solid"><fgColor theme="7" tint="0.799"/><bgColor indexed="64"/></patternFill></fill>` +
    `</fills>` +
    `<borders count="2">` +
    `<border><left/><right/><top/><bottom/><diagonal/></border>` +
    `<border><left style="thin"><color auto="1"/></left><right/><top style="thin"><color auto="1"/></top><bottom/><diagonal/></border>` +
    `</borders>` +
    `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"><alignment vertical="center"/></xf></cellStyleXfs>` +
    `<cellXfs count="2">` +
    `<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"><alignment vertical="center"/></xf>` +
    `<xf numFmtId="176" fontId="1" fillId="2" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>` +
    `</cellXfs>` +
    `<dxfs count="1"><dxf><fill><patternFill><bgColor theme="5" tint="0.799"/></patternFill></fill></dxf></dxfs>` +
    `</styleSheet>`;

describe('StylesParser — 合成 styles', () => {
    const s = StylesParser.parse(STYLES_XML);

    it('自訂 numFmts', () => {
        expect(s.customNumFmts.get(176)).toContain('年');
        expect(s.customNumFmts.get(179)).toBe('#,##0.00_ ');
    });
    it('fonts：粗體 + rgb 色 + family', () => {
        expect(s.fonts).toHaveLength(2);
        expect(s.fonts[0].name).toBe('新細明體');
        expect(s.fonts[0].size).toBe(12);
        expect(s.fonts[1].bold).toBe(true);
        expect(s.fonts[1].color?.rgb).toBe('FFFF0000');
        expect(s.fonts[1].family).toBe(4);
    });
    it('fills：theme+tint / indexed / patternType', () => {
        expect(s.fills).toHaveLength(3);
        expect(s.fills[0].patternType).toBe('none');
        expect(s.fills[2].patternType).toBe('solid');
        expect(s.fills[2].fgColor?.theme).toBe(7);
        expect(s.fills[2].fgColor?.tint).toBeCloseTo(0.799, 3);
        expect(s.fills[2].bgColor?.indexed).toBe(64);
    });
    it('borders：edge style + auto color', () => {
        expect(s.borders).toHaveLength(2);
        expect(s.borders[0].left).toBeUndefined(); // 空 edge
        expect(s.borders[1].left?.style).toBe('thin');
        expect(s.borders[1].left?.color?.auto).toBe(true);
        expect(s.borders[1].right).toBeUndefined();
    });
    it('cellXfs：索引 + apply 旗標 + alignment', () => {
        expect(s.cellXfs).toHaveLength(2);
        const xf = s.cellXfs[1];
        expect(xf.numFmtId).toBe(176);
        expect(xf.fontId).toBe(1);
        expect(xf.fillId).toBe(2);
        expect(xf.borderId).toBe(1);
        expect(xf.applyNumberFormat).toBe(true);
        expect(xf.alignment?.horizontal).toBe('center');
        expect(xf.alignment?.wrapText).toBe(true);
    });
    it('cellStyleXfs', () => {
        expect(s.cellStyleXfs).toHaveLength(1);
        expect(s.cellStyleXfs[0].alignment?.vertical).toBe('center');
    });
    it('dxfs（CF differential format）', () => {
        expect(s.dxfs).toHaveLength(1);
        expect(s.dxfs[0].fill?.bgColor?.theme).toBe(5);
    });
});

describe('numberFormatCode — 自訂 + 內建', () => {
    const s = StylesParser.parse(STYLES_XML);
    it('自訂 id', () => {
        expect(numberFormatCode(s, 179)).toBe('#,##0.00_ ');
    });
    it('內建 id', () => {
        expect(numberFormatCode(s, 0)).toBe('General');
        expect(numberFormatCode(s, 2)).toBe('0.00');
        expect(numberFormatCode(s, 14)).toBe('mm-dd-yy');
        expect(numberFormatCode(s, 9)).toBe('0%');
    });
    it('未知 id', () => {
        expect(numberFormatCode(s, 9999)).toBeUndefined();
    });
});

describe('isDateFormatCode / isDateNumberFormat', () => {
    const s = StylesParser.parse(STYLES_XML);
    it('日期 formatCode（含字面年月日）', () => {
        expect(isDateFormatCode('[$-404]gge"年"m"月"d"日";@')).toBe(true);
        expect(isDateFormatCode('yyyy/mm/dd')).toBe(true);
        expect(isDateFormatCode('h:mm:ss')).toBe(true);
    });
    it('非日期 formatCode', () => {
        expect(isDateFormatCode('#,##0.00_ ')).toBe(false);
        expect(isDateFormatCode('0%')).toBe(false);
        expect(isDateFormatCode('General')).toBe(false);
        expect(isDateFormatCode('"第" # "次估驗附表" ')).toBe(false);
    });
    it('內建日期 id（14-22/45-47）', () => {
        expect(isDateNumberFormat(s, 14)).toBe(true);
        expect(isDateNumberFormat(s, 22)).toBe(true);
        expect(isDateNumberFormat(s, 46)).toBe(true);
    });
    it('內建非日期 id', () => {
        expect(isDateNumberFormat(s, 0)).toBe(false);
        expect(isDateNumberFormat(s, 2)).toBe(false);
    });
    it('自訂日期 id（176 年月日）vs 自訂非日期（179）', () => {
        expect(isDateNumberFormat(s, 176)).toBe(true);
        expect(isDateNumberFormat(s, 179)).toBe(false);
    });
});

describe('StylesParser — 真實估驗差異表', () => {
    const f = join(FIXTURES, '08_chienyii_business', '估驗數量差異說明表再造11309.xlsx');
    const pkg = PackageReader.fromBuffer(readFileSync(f));
    const part = new WorkbookParser(pkg).stylesPart();
    const s = StylesParser.parse(pkg.getPartText(part!));

    it('解析出 4 個自訂 numFmt（176-179）', () => {
        expect(s.customNumFmts.size).toBe(4);
        expect(isDateNumberFormat(s, 176)).toBe(true); // gge年m月d日
        expect(isDateNumberFormat(s, 179)).toBe(false); // #,##0.00
    });
    it('12 fonts / 2 fills / 9 borders / 34 cellXfs', () => {
        expect(s.fonts).toHaveLength(12);
        expect(s.fills).toHaveLength(2);
        expect(s.borders).toHaveLength(9);
        expect(s.cellXfs).toHaveLength(34);
    });
});
