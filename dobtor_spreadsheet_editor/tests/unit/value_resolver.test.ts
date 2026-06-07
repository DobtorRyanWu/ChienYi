// value_resolver.test.ts — worksheet + styles 結合解析（規劃書 §2.3）
import { describe, it, expect } from 'vitest';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import {
    resolveCellValueStyled,
    buildValueMapStyled,
} from '../../static/src/core/ooxmlspreadsheet/value_resolver';
import type { SharedString } from '../../static/src/core/ooxmlspreadsheet/shared_strings_parser';

const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

// cellXfs：index0 = 日期(numFmtId 14)、index1 = 一般(0)、index2 = 自訂日期(176)
const STYLES = StylesParser.parse(
    `<?xml version="1.0"?><styleSheet xmlns="${NS}">` +
        `<numFmts count="1"><numFmt numFmtId="176" formatCode="[$-404]e&quot;年&quot;m&quot;月&quot;d&quot;日&quot;;@"/></numFmts>` +
        `<cellXfs count="3">` +
        `<xf numFmtId="14" fontId="0" fillId="0" borderId="0"/>` +
        `<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>` +
        `<xf numFmtId="176" fontId="0" fillId="0" borderId="0"/>` +
        `</cellXfs></styleSheet>`,
);

// A1：日期序號(s=0)、B1：一般數字(s=1)、C1：自訂日期(s=2)、D1：日期格式但字串值
const WS = WorksheetParser.parse(
    `<?xml version="1.0"?><worksheet xmlns="${NS}"><dimension ref="A1:D1"/><sheetData>` +
        `<row r="1">` +
        `<c r="A1" s="0"><v>45875</v></c>` +
        `<c r="B1" s="1"><v>1234.5</v></c>` +
        `<c r="C1" s="2"><v>45292</v></c>` +
        `<c r="D1" s="0" t="s"><v>0</v></c>` +
        `</row></sheetData></worksheet>`,
);
const SS: SharedString[] = [{ text: '不是日期' }];
const byRef = (r: string) => WS.cells.find((c) => c.ref === r)!;

describe('resolveCellValueStyled', () => {
    it('日期格式（內建 14）數字 → 日期字串', () => {
        expect(resolveCellValueStyled(byRef('A1'), SS, STYLES)).toBe('2025-08-06');
    });
    it('一般數字格式 → 維持 number', () => {
        expect(resolveCellValueStyled(byRef('B1'), SS, STYLES)).toBe(1234.5);
    });
    it('自訂日期格式（176）數字 → 日期字串', () => {
        expect(resolveCellValueStyled(byRef('C1'), SS, STYLES)).toBe('2024-01-01');
    });
    it('日期格式但值為字串 → 不誤轉（仍為字串）', () => {
        expect(resolveCellValueStyled(byRef('D1'), SS, STYLES)).toBe('不是日期');
    });
    it('styles=undefined → 退化為純數字（§1.6 行為）', () => {
        expect(resolveCellValueStyled(byRef('A1'), SS, undefined)).toBe(45875);
    });
});

describe('buildValueMapStyled', () => {
    const map = buildValueMapStyled(WS, SS, STYLES);
    it('日期格列轉字串、數字維持', () => {
        expect(map.get('1:1')).toBe('2025-08-06');
        expect(map.get('1:2')).toBe(1234.5);
        expect(map.get('1:3')).toBe('2024-01-01');
    });
});
