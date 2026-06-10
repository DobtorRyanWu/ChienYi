import { describe, it, expect } from 'vitest';
import { parseChart } from '../../static/src/core/ooxmlspreadsheet/chart_parser';
import { chartToFigure } from '../../static/src/core/ooxmlspreadsheet/chart_compiler';
const anchor = { fromCol: 0, fromRow: 0, toCol: 8, toRow: 15, chartRId: 'rId1' };
const CHART = (color: string) =>
    `<?xml version="1.0"?><c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">` +
    `<c:chart><c:plotArea><c:barChart><c:ser>${color}` +
    `<c:val><c:numRef><c:f>Sheet1!$B$1:$B$3</c:f></c:numRef></c:val></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>`;
describe('chart series 顏色（§5.2）', () => {
    it('srgbClr → backgroundColor #hex', () => {
        const ast = parseChart(CHART('<c:spPr><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></c:spPr>'))!;
        const fig = chartToFigure(ast, anchor, 'f1')!;
        expect(fig.data.dataSets[0].backgroundColor).toBe('#FF0000');
    });
    it('schemeClr accent1 → 經 themeColors 解析', () => {
        const ast = parseChart(CHART('<c:spPr><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></c:spPr>'))!;
        const fig = chartToFigure(ast, anchor, 'f1', { accent1: '#4472C4' })!;
        expect(fig.data.dataSets[0].backgroundColor).toBe('#4472C4');
    });
    it('無顏色 → dataSet 無 backgroundColor', () => {
        const ast = parseChart(CHART(''))!;
        const fig = chartToFigure(ast, anchor, 'f1')!;
        expect(fig.data.dataSets[0].backgroundColor).toBeUndefined();
    });
});
