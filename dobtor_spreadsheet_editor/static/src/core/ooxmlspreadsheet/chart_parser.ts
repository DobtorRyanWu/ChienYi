// chart_parser.ts — xl/charts/chartN.xml（DrawingML chartSpace）→ ChartAst（規劃書 §5.2）
//
// 解析圖表類型、series（categories/values cell ref）、title。用 parseXmlNoNs 去前綴（c:/a:）。

import { parseXmlNoNs, toArray, textOf, attr } from './xml_util';

export type ChartType = 'bar' | 'line' | 'pie' | 'scatter';

export interface ChartSeries {
    /** series 名稱（字面值；ref 名 v1 不解析）。*/
    name?: string;
    /** 類別軸 cell ref（如 `統計圖!$B$3:$B$31`）。*/
    categoriesRef?: string;
    /** 數值 cell ref。*/
    valuesRef?: string;
    /** series 顏色（§5.2）：`#RRGGBB`（srgbClr）或 `scheme:accent1`（schemeClr，由 compiler 經 theme 解析）。*/
    color?: string;
}

export interface ChartAst {
    type: ChartType;
    title?: string;
    series: ChartSeries[];
}

// Excel chartSpace 內的 chart 元素 → o-spreadsheet 類型（去前綴後的 key）
const TYPE_MAP: Readonly<Record<string, ChartType>> = {
    barChart: 'bar',
    bar3DChart: 'bar',
    lineChart: 'line',
    line3DChart: 'line',
    stockChart: 'line',
    areaChart: 'line',
    area3DChart: 'line',
    pieChart: 'pie',
    pie3DChart: 'pie',
    doughnutChart: 'pie',
    ofPieChart: 'pie',
    scatterChart: 'scatter',
    bubbleChart: 'scatter',
};

/** 取 c:cat / c:val / c:tx 內的 cell ref（numRef/strRef/multiLvlStrRef 的 <c:f>），排除 #REF!。*/
function refOf(node: unknown): string | undefined {
    const n = node as Record<string, unknown> | undefined;
    if (!n) return undefined;
    const r = (n['numRef'] ?? n['strRef'] ?? n['multiLvlStrRef']) as Record<string, unknown> | undefined;
    if (!r) return undefined;
    const f = textOf(r['f']).trim();
    return f && !f.includes('#REF!') ? f : undefined;
}

/** 取 series spPr 的填色（§5.2）：srgbClr→#RRGGBB、schemeClr→scheme:name。*/
function colorOf(ser: Record<string, unknown>): string | undefined {
    const spPr = ser['spPr'] as Record<string, unknown> | undefined;
    const fill = spPr?.['solidFill'] as Record<string, unknown> | undefined;
    if (!fill) return undefined;
    const srgb = fill['srgbClr'] as Record<string, unknown> | undefined;
    const srgbVal = srgb && attr(srgb, 'val');
    if (srgbVal) return `#${srgbVal}`;
    const scheme = fill['schemeClr'] as Record<string, unknown> | undefined;
    const schemeVal = scheme && attr(scheme, 'val');
    if (schemeVal) return `scheme:${schemeVal}`;
    return undefined;
}

function parseSeries(ser: Record<string, unknown>): ChartSeries {
    const tx = ser['tx'] as Record<string, unknown> | undefined;
    const literalName = tx ? textOf(tx['v']).trim() : '';
    return {
        name: literalName || undefined,
        categoriesRef: refOf(ser['cat']),
        valuesRef: refOf(ser['val']),
        color: colorOf(ser),
    };
}

/** 從 c:title 抽出標題文字（title>tx>rich>p>r>t，去前綴後遞迴收集 t）。*/
function extractTitle(title: unknown): string | undefined {
    if (!title || typeof title !== 'object') return undefined;
    const texts: string[] = [];
    const walk = (node: unknown): void => {
        if (Array.isArray(node)) {
            node.forEach(walk);
            return;
        }
        if (node && typeof node === 'object') {
            const o = node as Record<string, unknown>;
            for (const [k, v] of Object.entries(o)) {
                if (k === 't') texts.push(textOf(v));
                else if (typeof v === 'object') walk(v);
            }
        }
    };
    walk(title);
    const s = texts.join('').trim();
    return s || undefined;
}

/** chartN.xml → ChartAst。無法辨識類型/無 series 時回 undefined。*/
export function parseChart(xml: string): ChartAst | undefined {
    const root = parseXmlNoNs(xml);
    const chartSpace = root['chartSpace'] as Record<string, unknown> | undefined;
    const chart = chartSpace?.['chart'] as Record<string, unknown> | undefined;
    const plotArea = chart?.['plotArea'] as Record<string, unknown> | undefined;
    if (!plotArea) return undefined;

    let type: ChartType | undefined;
    let typeNode: Record<string, unknown> | undefined;
    for (const [key, mapped] of Object.entries(TYPE_MAP)) {
        if (plotArea[key]) {
            type = mapped;
            typeNode = plotArea[key] as Record<string, unknown>;
            break;
        }
    }
    if (!type || !typeNode) return undefined;

    const series = toArray<Record<string, unknown>>(
        typeNode['ser'] as Record<string, unknown> | Record<string, unknown>[] | undefined,
    )
        .map(parseSeries)
        .filter((s) => s.valuesRef || s.categoriesRef);
    if (series.length === 0) return undefined;

    return { type, title: extractTitle(chart?.['title']), series };
}
