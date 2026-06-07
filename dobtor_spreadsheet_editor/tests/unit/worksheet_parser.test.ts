// worksheet_parser.test.ts — 解析 worksheet + cell value 提取（規劃書 §1.6）
import { describe, it, expect } from 'vitest';
import {
    WorksheetParser,
    resolveCellValue,
    buildValueMap,
    worksheetBounds,
} from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import type { SharedString } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';

const NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const SS: SharedString[] = [{ text: '臺北' }, { text: '估驗' }];

const WS_XML =
    `<?xml version="1.0"?><worksheet xmlns="${NS_MAIN}">` +
    `<dimension ref="A1:E3"/>` +
    `<sheetViews><sheetView showGridLines="0"><pane xSplit="2" ySplit="1" topLeftCell="C2" state="frozen"/></sheetView></sheetViews>` +
    `<cols><col min="1" max="1" width="4.125" customWidth="1"/><col min="2" max="2" width="25.25" customWidth="1" hidden="1"/></cols>` +
    `<sheetData>` +
    `<row r="1"><c r="A1" s="5" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>` +
    `<row r="2">` +
    `<c r="A2"><v>13</v></c>` +
    `<c r="B2" t="b"><v>1</v></c>` +
    `<c r="C2" t="str"><v>hello</v></c>` +
    `<c r="D2" t="e"><v>#DIV/0!</v></c>` +
    `<c r="E2" t="inlineStr"><is><t>行內字</t></is></c>` +
    `</row>` +
    `<row r="3"><c r="A3"><f>SUM(A1:A2)</f><v>13</v></c><c r="B3" s="2"/></row>` +
    `</sheetData>` +
    `<mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>` +
    `</worksheet>`;

describe('WorksheetParser — 結構', () => {
    const ws = WorksheetParser.parse(WS_XML);

    it('dimension / bounds', () => {
        expect(ws.dimensionRef).toBe('A1:E3');
        expect(worksheetBounds(ws)).toEqual({ rows: 3, cols: 5 });
    });
    it('cols（含 hidden）', () => {
        expect(ws.cols).toHaveLength(2);
        expect(ws.cols[1].hidden).toBe(true);
        expect(ws.cols[1].width).toBeCloseTo(25.25, 2);
    });
    it('freeze panes', () => {
        expect(ws.freeze).toEqual({ xSplit: 2, ySplit: 1, topLeftCell: 'C2' });
    });
    it('showGridLines=0', () => {
        expect(ws.showGridLines).toBe(false);
    });
    it('mergeCells', () => {
        expect(ws.merges).toEqual(['A1:B1']);
    });
    it('空樣式格（B3 只有 s）不進 cells', () => {
        expect(ws.cells.find((c) => c.ref === 'B3')).toBeUndefined();
    });
    it('公式 cell 捕捉 <f> 與 cached <v>', () => {
        const a3 = ws.cells.find((c) => c.ref === 'A3');
        expect(a3?.formula).toBe('SUM(A1:A2)');
        expect(a3?.raw).toBe('13');
    });
});

describe('WorksheetParser — cell value 型別解析', () => {
    const ws = WorksheetParser.parse(WS_XML);
    const byRef = (ref: string) => ws.cells.find((c) => c.ref === ref)!;

    it('sharedString（t=s）解參照', () => {
        expect(resolveCellValue(byRef('A1'), SS)).toBe('臺北');
        expect(resolveCellValue(byRef('B1'), SS)).toBe('估驗');
    });
    it('number', () => {
        expect(resolveCellValue(byRef('A2'), SS)).toBe(13);
    });
    it('boolean', () => {
        expect(resolveCellValue(byRef('B2'), SS)).toBe(true);
    });
    it('formula string（t=str）', () => {
        expect(resolveCellValue(byRef('C2'), SS)).toBe('hello');
    });
    it('error（t=e）', () => {
        expect(resolveCellValue(byRef('D2'), SS)).toBe('#DIV/0!');
    });
    it('inlineStr', () => {
        expect(resolveCellValue(byRef('E2'), SS)).toBe('行內字');
    });
    it('formula cell 取 cached number', () => {
        expect(resolveCellValue(byRef('A3'), SS)).toBe(13);
    });
});

describe('WorksheetParser — buildValueMap', () => {
    const ws = WorksheetParser.parse(WS_XML);
    const map = buildValueMap(ws, SS);

    it('鍵為 row:col', () => {
        expect(map.get('1:1')).toBe('臺北'); // A1
        expect(map.get('2:1')).toBe(13); // A2
        expect(map.get('2:5')).toBe('行內字'); // E2
    });
    it('空格不入 map', () => {
        expect(map.has('3:2')).toBe(false); // B3
    });
});
