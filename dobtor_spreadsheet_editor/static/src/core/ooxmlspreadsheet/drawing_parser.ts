// drawing_parser.ts — xl/drawings/drawingN.xml → 圖表錨點（規劃書 §5.3 最小版）
//
// 只取「含圖表（graphicFrame → c:chart r:id）」的 anchor，供 chart 定位。圖片/shape v1 略過。

import { parseXmlNoNs, toArray, attr, textOf } from './xml_util';

export interface DrawingChartAnchor {
    /** twoCellAnchor 的 from/to 格座標（0-based col/row）。oneCellAnchor 時 to = from。*/
    fromCol: number;
    fromRow: number;
    toCol: number;
    toRow: number;
    /** 指向 chart 的 relationship id（由 drawing rels 解析成 chart part）。*/
    chartRId: string;
}

function intText(node: Record<string, unknown> | undefined, key: string): number {
    if (!node) return 0;
    const n = parseInt(textOf(node[key]), 10);
    return Number.isFinite(n) ? n : 0;
}

/** 從 anchor 找 graphicFrame 內的 chart r:id（去前綴後 r:id → id）。*/
function chartRIdOf(anchor: Record<string, unknown>): string | undefined {
    const gf = anchor['graphicFrame'] as Record<string, unknown> | undefined;
    const graphic = gf?.['graphic'] as Record<string, unknown> | undefined;
    const gData = graphic?.['graphicData'] as Record<string, unknown> | undefined;
    const chart = gData?.['chart'] as Record<string, unknown> | undefined;
    if (!chart) return undefined;
    return attr(chart, 'id') ?? attr(chart, 'r:id');
}

/** 圖片錨點（§5.3 預覽用）。*/
export interface DrawingPicAnchor {
    fromCol: number;
    fromRow: number;
    toCol: number;
    toRow: number;
    blipRId: string;
}

function blipRIdOf(anchor: Record<string, unknown>): string | undefined {
    const pic = anchor['pic'] as Record<string, unknown> | undefined;
    const blipFill = pic?.['blipFill'] as Record<string, unknown> | undefined;
    const blip = blipFill?.['blip'] as Record<string, unknown> | undefined;
    if (!blip) return undefined;
    return attr(blip, 'embed') ?? attr(blip, 'r:embed');
}

/** drawingN.xml → 圖片錨點清單（§5.3）。*/
export function parseDrawingPics(xml: string): DrawingPicAnchor[] {
    const root = parseXmlNoNs(xml);
    const wsDr = root['wsDr'] as Record<string, unknown> | undefined;
    if (!wsDr) return [];
    const out: DrawingPicAnchor[] = [];
    for (const anchorKey of ['twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor']) {
        for (const a of toArray<Record<string, unknown>>(
            wsDr[anchorKey] as Record<string, unknown> | Record<string, unknown>[] | undefined,
        )) {
            const blipRId = blipRIdOf(a);
            if (!blipRId) continue;
            const from = a['from'] as Record<string, unknown> | undefined;
            const to = a['to'] as Record<string, unknown> | undefined;
            const fromCol = intText(from, 'col');
            const fromRow = intText(from, 'row');
            out.push({
                fromCol,
                fromRow,
                toCol: to ? intText(to, 'col') : fromCol + 4,
                toRow: to ? intText(to, 'row') : fromRow + 6,
                blipRId,
            });
        }
    }
    return out;
}

/** drawingN.xml → 圖表錨點清單。*/
export function parseDrawing(xml: string): DrawingChartAnchor[] {
    const root = parseXmlNoNs(xml);
    const wsDr = root['wsDr'] as Record<string, unknown> | undefined;
    if (!wsDr) return [];

    const out: DrawingChartAnchor[] = [];
    for (const anchorKey of ['twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor']) {
        for (const a of toArray<Record<string, unknown>>(
            wsDr[anchorKey] as Record<string, unknown> | Record<string, unknown>[] | undefined,
        )) {
            const chartRId = chartRIdOf(a);
            if (!chartRId) continue;
            const from = a['from'] as Record<string, unknown> | undefined;
            const to = a['to'] as Record<string, unknown> | undefined;
            const fromCol = intText(from, 'col');
            const fromRow = intText(from, 'row');
            out.push({
                fromCol,
                fromRow,
                toCol: to ? intText(to, 'col') : fromCol + 8,
                toRow: to ? intText(to, 'row') : fromRow + 15,
                chartRId,
            });
        }
    }
    return out;
}
