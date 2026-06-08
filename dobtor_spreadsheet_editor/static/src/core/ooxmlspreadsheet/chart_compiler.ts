// chart_compiler.ts — ChartAst + drawing anchor → o-spreadsheet figure（規劃書 §5.2 ChartMapper）
//
// 解析鏈：worksheet rels → drawingN.xml → drawing rels → chartN.xml → ChartAst → figure。

import type { PackageReader } from './package_reader';
import { parseChart, type ChartAst, type ChartType } from './chart_parser';
import { parseDrawing, type DrawingChartAnchor } from './drawing_parser';

export interface OFigure {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    tag: 'chart';
    data: {
        type: ChartType;
        title: { text: string };
        background: string;
        dataSets: { dataRange: string }[];
        legendPosition: string;
        labelRange?: string;
        dataSetsHaveTitle: boolean;
        verticalAxisPosition?: string;
        stacked?: boolean;
    };
}

// 錨點格座標 → px 估算（o-spreadsheet 預設欄寬/列高近似）
const COL_PX = 64;
const ROW_PX = 20;
const MIN_W = 300;
const MIN_H = 200;

export function chartToFigure(ast: ChartAst, anchor: DrawingChartAnchor, id: string): OFigure | undefined {
    const dataSets = ast.series.filter((s) => s.valuesRef).map((s) => ({ dataRange: s.valuesRef as string }));
    if (dataSets.length === 0) return undefined; // 無數值 ref → 無法成圖
    const labelRange = ast.series.find((s) => s.categoriesRef)?.categoriesRef;

    const x = anchor.fromCol * COL_PX;
    const y = anchor.fromRow * ROW_PX;
    const width = Math.max((anchor.toCol - anchor.fromCol) * COL_PX, MIN_W);
    const height = Math.max((anchor.toRow - anchor.fromRow) * ROW_PX, MIN_H);

    const data: OFigure['data'] = {
        type: ast.type,
        title: { text: ast.title ?? '' },
        background: '#FFFFFF',
        dataSets,
        legendPosition: 'top',
        labelRange,
        dataSetsHaveTitle: false,
    };
    if (ast.type === 'bar' || ast.type === 'line') {
        data.verticalAxisPosition = 'left';
        data.stacked = false;
    }
    return { id, x, y, width, height, tag: 'chart', data };
}

/** 解析某 worksheet part 連結的所有圖表 → o-spreadsheet figures。*/
export function resolveSheetCharts(pkg: PackageReader, sheetPart: string, idPrefix: string): OFigure[] {
    const figures: OFigure[] = [];
    let n = 0;
    const drawingRels = pkg.getRels(sheetPart).filter((r) => r.type.endsWith('/drawing'));
    for (const dr of drawingRels) {
        const drawingPart = dr.resolvedTarget;
        if (!drawingPart || !pkg.hasPart(drawingPart)) continue;
        const anchors = parseDrawing(pkg.getPartText(drawingPart));
        if (anchors.length === 0) continue;
        const relMap = new Map(pkg.getRels(drawingPart).map((r) => [r.id, r.resolvedTarget]));
        for (const anchor of anchors) {
            const chartPart = relMap.get(anchor.chartRId);
            if (!chartPart || !pkg.hasPart(chartPart)) continue;
            const ast = parseChart(pkg.getPartText(chartPart));
            if (!ast) continue;
            const fig = chartToFigure(ast, anchor, `${idPrefix}_fig${n}`);
            if (fig) {
                figures.push(fig);
                n++;
            }
        }
    }
    return figures;
}
