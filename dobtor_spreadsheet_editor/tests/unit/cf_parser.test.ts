// cf_parser.test.ts — 條件格式解析（規劃書 §1.7）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { CFParser } from '../../static/src/core/ooxmlspreadsheet/cf_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

const WS_XML =
    `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetData/>` +
    `<conditionalFormatting sqref="D1:D100 F1:F5">` +
    `<cfRule type="cellIs" dxfId="3" priority="1" operator="equal"><formula>"B5"</formula></cfRule>` +
    `<cfRule type="cellIs" dxfId="2" priority="2" operator="between"><formula>1</formula><formula>10</formula></cfRule>` +
    `<cfRule type="expression" dxfId="1" priority="3"><formula>$A1&gt;0</formula></cfRule>` +
    `<cfRule type="duplicateValues" dxfId="0" priority="4"/>` +
    `<cfRule type="containsText" dxfId="5" priority="5" operator="containsText" text="x"><formula>NOT(ISERROR(SEARCH("x",D1)))</formula></cfRule>` +
    `<cfRule type="top10" dxfId="6" priority="6" percent="1" rank="10" bottom="1"/>` +
    `</conditionalFormatting>` +
    `<conditionalFormatting sqref="E1:E10">` +
    `<cfRule type="colorScale" priority="7"><colorScale><cfvo type="min"/><cfvo type="max"/><color rgb="FFF8696B"/><color rgb="FF63BE7B"/></colorScale></cfRule>` +
    `<cfRule type="dataBar" priority="8"><dataBar minLength="0" maxLength="100"><cfvo type="min"/><cfvo type="max"/><color rgb="FF638EC6"/></dataBar></cfRule>` +
    `<cfRule type="iconSet" priority="9"><iconSet iconSet="3TrafficLights1" reverse="1"><cfvo type="percent" val="0"/><cfvo type="percent" val="33"/><cfvo type="percent" val="67"/></iconSet></cfRule>` +
    `</conditionalFormatting>` +
    `</worksheet>`;

describe('CFParser — 合成 CF', () => {
    const cfs = CFParser.parse(WS_XML);

    it('2 個 CF 區塊', () => {
        expect(cfs).toHaveLength(2);
    });
    it('sqref 拆多段範圍', () => {
        expect(cfs[0].ranges).toEqual(['D1:D100', 'F1:F5']);
    });
    it('cellIs equal（單 formula）', () => {
        const r = cfs[0].rules[0];
        expect(r.type).toBe('cellIs');
        expect(r.operator).toBe('equal');
        expect(r.dxfId).toBe(3);
        expect(r.priority).toBe(1);
        expect(r.formulas).toEqual(['"B5"']);
    });
    it('cellIs between（雙 formula）', () => {
        expect(cfs[0].rules[1].formulas).toEqual(['1', '10']);
    });
    it('expression', () => {
        const r = cfs[0].rules[2];
        expect(r.type).toBe('expression');
        expect(r.formulas).toEqual(['$A1>0']);
    });
    it('duplicateValues（無 formula）', () => {
        const r = cfs[0].rules[3];
        expect(r.type).toBe('duplicateValues');
        expect(r.dxfId).toBe(0);
        expect(r.formulas).toEqual([]);
    });
    it('containsText（text 屬性）', () => {
        const r = cfs[0].rules[4];
        expect(r.type).toBe('containsText');
        expect(r.text).toBe('x');
    });
    it('top10（percent/rank/bottom）', () => {
        const r = cfs[0].rules[5];
        expect(r.percent).toBe(true);
        expect(r.rank).toBe(10);
        expect(r.bottom).toBe(true);
    });
    it('colorScale（2 cfvo + 2 色）', () => {
        const r = cfs[1].rules[0];
        expect(r.colorScale?.cfvo.map((c) => c.type)).toEqual(['min', 'max']);
        expect(r.colorScale?.colors[0].rgb).toBe('FFF8696B');
        expect(r.colorScale?.colors).toHaveLength(2);
    });
    it('dataBar（color + min/maxLength）', () => {
        const r = cfs[1].rules[1];
        expect(r.dataBar?.color?.rgb).toBe('FF638EC6');
        expect(r.dataBar?.minLength).toBe(0);
        expect(r.dataBar?.maxLength).toBe(100);
        expect(r.dataBar?.cfvo).toHaveLength(2);
    });
    it('iconSet（3 cfvo + reverse）', () => {
        const r = cfs[1].rules[2];
        expect(r.iconSet?.iconSet).toBe('3TrafficLights1');
        expect(r.iconSet?.reverse).toBe(true);
        expect(r.iconSet?.cfvo).toHaveLength(3);
        expect(r.iconSet?.cfvo[1].val).toBe('33');
    });
});

describe('CFParser — 真實土單（cellIs 狀態色）', () => {
    const f = join(FIXTURES, '04_conditional_format', '磺港溪C-A土單20250221-1.xlsx');
    const pkg = PackageReader.fromBuffer(readFileSync(f));
    const wb = new WorkbookParser(pkg).parse();

    // 蒐集所有 sheet 的 CF（經 WorksheetParser，驗證已整合）
    const allCf = wb.sheets
        .filter((s) => s.target && pkg.hasPart(s.target))
        .flatMap((s) => WorksheetParser.parse(pkg.getPartText(s.target!)).conditionalFormatting);

    it('解析到 CF 區塊', () => {
        expect(allCf.length).toBeGreaterThan(0);
    });
    it('含 cellIs 規則且 dxfId 有定義', () => {
        const cellIsRules = allCf.flatMap((cf) => cf.rules).filter((r) => r.type === 'cellIs');
        expect(cellIsRules.length).toBeGreaterThan(0);
        expect(cellIsRules.every((r) => r.dxfId !== undefined)).toBe(true);
    });
    it('WorksheetParser 已整合 conditionalFormatting 欄位', () => {
        const withCf = wb.sheets
            .filter((s) => s.target && pkg.hasPart(s.target))
            .map((s) => WorksheetParser.parse(pkg.getPartText(s.target!)))
            .find((ws) => ws.conditionalFormatting.length > 0);
        expect(withCf).toBeDefined();
    });
});
