// chart_parser.test.ts — chartN.xml/drawingN.xml 解析 + chart→figure（規劃書 §5.2/5.3）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseChart } from '../../static/src/core/ooxmlspreadsheet/chart_parser';
import { parseDrawing } from '../../static/src/core/ooxmlspreadsheet/drawing_parser';
import { chartToFigure } from '../../static/src/core/ooxmlspreadsheet/chart_compiler';
import { importXlsxToOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/index';

const FIXTURES = join(__dirname, '..', 'fixtures');
const C = 'http://schemas.openxmlformats.org/drawingml/2006/chart';
const A = 'http://schemas.openxmlformats.org/drawingml/2006/main';
const XDR = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing';
const R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

describe('parseChart', () => {
    const xml =
        `<?xml version="1.0"?><c:chartSpace xmlns:c="${C}" xmlns:a="${A}">` +
        `<c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>進度統計</a:t></a:r></a:p></c:rich></c:tx></c:title>` +
        `<c:plotArea><c:barChart><c:barDir val="col"/>` +
        `<c:ser><c:tx><c:strRef><c:f>統計圖!$C$2</c:f></c:strRef></c:tx>` +
        `<c:cat><c:strRef><c:f>統計圖!$B$3:$B$31</c:f></c:strRef></c:cat>` +
        `<c:val><c:numRef><c:f>統計圖!$C$3:$C$31</c:f></c:numRef></c:val></c:ser>` +
        `<c:ser><c:cat><c:strRef><c:f>統計圖!#REF!</c:f></c:strRef></c:cat>` +
        `<c:val><c:numRef><c:f>統計圖!$D$3:$D$31</c:f></c:numRef></c:val></c:ser>` +
        `</c:barChart></c:plotArea></c:chart></c:chartSpace>`;
    const ast = parseChart(xml)!;

    it('類型 bar（barChart）', () => expect(ast.type).toBe('bar'));
    it('title 抽出', () => expect(ast.title).toBe('進度統計'));
    it('series 數 + cat/val ref', () => {
        expect(ast.series).toHaveLength(2);
        expect(ast.series[0].categoriesRef).toBe('統計圖!$B$3:$B$31');
        expect(ast.series[0].valuesRef).toBe('統計圖!$C$3:$C$31');
    });
    it('#REF! 的 cat 被濾掉、val 仍保留', () => {
        expect(ast.series[1].categoriesRef).toBeUndefined();
        expect(ast.series[1].valuesRef).toBe('統計圖!$D$3:$D$31');
    });
    it('pie/line 類型映射', () => {
        expect(parseChart(xml.replace(/barChart/g, 'pieChart'))!.type).toBe('pie');
        expect(parseChart(xml.replace(/barChart/g, 'line3DChart'))!.type).toBe('line');
    });
});

describe('parseDrawing', () => {
    const xml =
        `<?xml version="1.0"?><xdr:wsDr xmlns:xdr="${XDR}" xmlns:r="${R}">` +
        `<xdr:twoCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:row>33</xdr:row></xdr:from>` +
        `<xdr:to><xdr:col>5</xdr:col><xdr:row>45</xdr:row></xdr:to>` +
        `<xdr:graphicFrame><a:graphic xmlns:a="${A}"><a:graphicData>` +
        `<c:chart xmlns:c="${C}" r:id="rId1"/></a:graphicData></a:graphic></xdr:graphicFrame>` +
        `</xdr:twoCellAnchor></xdr:wsDr>`;
    const anchors = parseDrawing(xml);

    it('twoCellAnchor + chart rId', () => {
        expect(anchors).toHaveLength(1);
        expect(anchors[0]).toMatchObject({ fromCol: 0, fromRow: 33, toCol: 5, toRow: 45, chartRId: 'rId1' });
    });
});

describe('chartToFigure', () => {
    const ast = parseChart(
        `<?xml version="1.0"?><c:chartSpace xmlns:c="${C}"><c:chart><c:plotArea><c:barChart>` +
            `<c:ser><c:cat><c:strRef><c:f>S!$A$1:$A$3</c:f></c:strRef></c:cat>` +
            `<c:val><c:numRef><c:f>S!$B$1:$B$3</c:f></c:numRef></c:val></c:ser>` +
            `</c:barChart></c:plotArea></c:chart></c:chartSpace>`,
    )!;
    const fig = chartToFigure(ast, { fromCol: 0, fromRow: 33, toCol: 5, toRow: 45, chartRId: 'rId1' }, 'sheet1_fig0')!;

    it('figure 結構（tag chart + dataSets + labelRange）', () => {
        expect(fig.tag).toBe('chart');
        expect(fig.data.type).toBe('bar');
        expect(fig.data.dataSets).toEqual([{ dataRange: 'S!$B$1:$B$3' }]);
        expect(fig.data.labelRange).toBe('S!$A$1:$A$3');
        expect(fig.width).toBeGreaterThan(0);
        expect(fig.height).toBeGreaterThan(0);
    });
});

describe('importXlsxToOSpreadsheetData — 真實 chart fixture', () => {
    it('自檢表總表單匯入後 figures 含 chart', () => {
        const b = readFileSync(join(FIXTURES, '06_chart', '自檢表總表單0308.xlsx'));
        const data = importXlsxToOSpreadsheetData(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        const figs = data.sheets.flatMap((s) => s.figures as { tag: string; data: { dataSets: unknown[] } }[]);
        expect(figs.length).toBeGreaterThan(0);
        expect(figs[0].tag).toBe('chart');
        expect(figs[0].data.dataSets.length).toBeGreaterThan(0);
    });
});
