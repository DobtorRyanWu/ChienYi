// color.ts — OOXML 色彩參照（規劃書 §1.5 / §2.2）
//
// Excel 色彩有四種來源，互斥出現在 <color>/<fgColor>/<bgColor>：
//   rgb="FFFFFF00"            ARGB 直接色
//   theme="7" tint="0.799"    主題色 token + 明暗調整（tint -1..1）
//   indexed="64"             舊版 56 色 palette 索引
//   auto="1"                 系統自動色（通常黑字白底）
// 本層只「保真擷取」，實際解析成 RGB（theme/tint/indexed → 具體色）是 §2.2 ThemeResolver 的工作。

import { attr } from './xml_util';

export interface Color {
    /** ARGB hex（如 "FFFFFF00"）。*/
    rgb?: string;
    /** 主題色索引（對應 theme1.xml clrScheme）。*/
    theme?: number;
    /** 明暗調整 -1（變暗）..1（變亮）。*/
    tint?: number;
    /** 舊版 indexed palette 索引。*/
    indexed?: number;
    /** 系統自動色。*/
    auto?: boolean;
}

/** 從 color 類元素（fgColor/bgColor/color）擷取 Color；無任何色彩屬性回 undefined。*/
export function parseColor(node: unknown): Color | undefined {
    if (node === null || node === undefined) return undefined;
    const color: Color = {};
    const rgb = attr(node, 'rgb');
    if (rgb !== undefined) color.rgb = rgb;
    const theme = attr(node, 'theme');
    if (theme !== undefined) color.theme = Number.parseInt(theme, 10);
    const tint = attr(node, 'tint');
    if (tint !== undefined) color.tint = Number(tint);
    const indexed = attr(node, 'indexed');
    if (indexed !== undefined) color.indexed = Number.parseInt(indexed, 10);
    if (attr(node, 'auto') === '1') color.auto = true;
    return Object.keys(color).length > 0 ? color : undefined;
}
