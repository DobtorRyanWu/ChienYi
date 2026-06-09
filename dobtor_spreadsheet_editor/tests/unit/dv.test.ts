// dv.test.ts — Data Validation 解析 + 編譯（規劃書 §1.8 / §4.2）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseXml } from '../../static/src/core/ooxmlspreadsheet/xml_util';
import { parseDataValidations } from '../../static/src/core/ooxmlspreadsheet/dv_parser';
import { compileDataValidations } from '../../static/src/core/ooxmlspreadsheet/dv_compiler';
import { importXlsxToOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/index';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

const WS = parseXml(
    `<?xml version="1.0"?><worksheet xmlns="${NS}"><dataValidations count="3">` +
        `<dataValidation type="list" allowBlank="1" sqref="A1:A10"><formula1>"是,否,待確認"</formula1></dataValidation>` +
        `<dataValidation type="list" sqref="B1:B5"><formula1>$X$1:$X$9</formula1></dataValidation>` +
        `<dataValidation type="whole" operator="between" sqref="C1"><formula1>1</formula1><formula2>100</formula2></dataValidation>` +
        `</dataValidations></worksheet>`,
)['worksheet'] as Record<string, unknown>;

describe('parseDataValidations', () => {
    const dvs = parseDataValidations(WS);
    it('解析 3 個 DV + 型別/範圍/公式', () => {
        expect(dvs).toHaveLength(3);
        expect(dvs[0]).toMatchObject({ type: 'list', ranges: ['A1:A10'], formula1: '"是,否,待確認"', allowBlank: true });
        expect(dvs[2]).toMatchObject({ type: 'whole', operator: 'between', formula1: '1', formula2: '100' });
    });
});

describe('compileDataValidations', () => {
    const rules = compileDataValidations(parseDataValidations(WS), 'sheet1');
    it('list inline → isValueInList + 選項分割', () => {
        const r = rules.find((x) => x.ranges[0] === 'A1:A10')!;
        expect(r.criterion.type).toBe('isValueInList');
        expect(r.criterion.values).toEqual(['是', '否', '待確認']);
        expect(r.criterion.displayStyle).toBe('arrow');
    });
    it('list 範圍 → isValueInRange', () => {
        const r = rules.find((x) => x.ranges[0] === 'B1:B5')!;
        expect(r.criterion.type).toBe('isValueInRange');
        expect(r.criterion.values).toEqual(['$X$1:$X$9']);
    });
    it('whole between → isBetween 雙值', () => {
        const r = rules.find((x) => x.ranges[0] === 'C1')!;
        expect(r.criterion.type).toBe('isBetween');
        expect(r.criterion.values).toEqual(['1', '100']);
    });
    it('id 帶 sheet 前綴', () => {
        expect(rules[0].id).toMatch(/^sheet1_/);
    });
});

describe('importXlsxToOSpreadsheetData — 真實自檢表 DV', () => {
    it('匯入後含 isValueInList dataValidationRules', () => {
        const b = readFileSync(join(FIXTURES, '06_chart', '自檢表總表單0308.xlsx'));
        const data = importXlsxToOSpreadsheetData(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        const dvs = data.sheets.flatMap((s) => (s as { dataValidationRules: { criterion: { type: string } }[] }).dataValidationRules);
        expect(dvs.length).toBeGreaterThan(0);
        expect(dvs.some((r) => r.criterion.type === 'isValueInList')).toBe(true);
    });
});

describe('exportXlsxFromBuffer — DV round-trip', () => {
    it('匯出檔保留 <dataValidations>，re-parse 仍得 list DV', async () => {
        const { exportXlsxFromBuffer } = await import('../../static/src/core/ooxmlspreadsheet/index');
        const b = readFileSync(join(FIXTURES, '06_chart', '自檢表總表單0308.xlsx'));
        const out = exportXlsxFromBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        const data2 = importXlsxToOSpreadsheetData(out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength));
        const dvs = data2.sheets.flatMap((s) => (s as { dataValidationRules: { criterion: { type: string } }[] }).dataValidationRules);
        expect(dvs.some((r) => r.criterion.type === 'isValueInList')).toBe(true);
    });
});

describe('compileDataValidations — custom / 更多 operator / isBlocking', () => {
    const WS2 = parseXml(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><dataValidations count="4">` +
            `<dataValidation type="custom" sqref="A1"><formula1>ISNUMBER(A1)</formula1></dataValidation>` +
            `<dataValidation type="whole" operator="greaterThanOrEqual" sqref="B1"><formula1>0</formula1></dataValidation>` +
            `<dataValidation type="whole" operator="lessThan" sqref="C1"><formula1>100</formula1></dataValidation>` +
            `<dataValidation type="list" errorStyle="warning" sqref="D1"><formula1>"a,b"</formula1></dataValidation>` +
            `</dataValidations></worksheet>`,
    )['worksheet'] as Record<string, unknown>;
    const rules = compileDataValidations(parseDataValidations(WS2), 's1');
    it('custom → customFormula（補 = 前綴）', () => {
        const r = rules.find((x) => x.ranges[0] === 'A1')!;
        expect(r.criterion.type).toBe('customFormula');
        expect(r.criterion.values).toEqual(['=ISNUMBER(A1)']);
    });
    it('greaterThanOrEqual → isGreaterOrEqualTo、lessThan → isLessThan', () => {
        expect(rules.find((x) => x.ranges[0] === 'B1')!.criterion.type).toBe('isGreaterOrEqualTo');
        expect(rules.find((x) => x.ranges[0] === 'C1')!.criterion.type).toBe('isLessThan');
    });
    it('errorStyle=warning → isBlocking false；預設 stop → true', () => {
        expect(rules.find((x) => x.ranges[0] === 'D1')!.isBlocking).toBe(false);
        expect(rules.find((x) => x.ranges[0] === 'A1')!.isBlocking).toBe(true);
    });
});
