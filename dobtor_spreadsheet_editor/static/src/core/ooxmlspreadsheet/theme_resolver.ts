// theme_resolver.ts — Color（theme/indexed/rgb/auto）→ 具體 RGB（規劃書 §2.2）
//
// tint/shade 用 HSL luminance 演算法（沿用 dobtor_doc_editor Sprint 130 邏輯，OOXML §20.1.2.3.20）：
//   SpreadsheetML 的 tint 屬性範圍 -1..1：
//     tint > 0（變亮）：L' = L + (1 - L) * tint
//     tint < 0（變暗）：L' = L * (1 + tint)
//   只調亮度 L、保留 hue/saturation，避免 vivid 色被洗成灰。

import type { Color } from './color';
import type { ParsedTheme, ThemeColorScheme } from './theme_parser';

// <color theme="N"> 的索引順序：注意 0/1 與 2/3 相對 clrScheme XML 順序「互換」
// （Excel：theme 0 = Background1 = lt1、theme 1 = Text1 = dk1）。
const THEME_INDEX: (keyof ThemeColorScheme)[] = [
    'lt1', 'dk1', 'lt2', 'dk2',
    'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
    'hlink', 'folHlink',
];

// 舊版 indexed 56 色 palette（ECMA-376 §18.8.27）。64/65 為系統前/背景色（context 相關）。
const INDEXED_PALETTE: Readonly<Record<number, string>> = {
    0: '000000', 1: 'FFFFFF', 2: 'FF0000', 3: '00FF00', 4: '0000FF', 5: 'FFFF00', 6: 'FF00FF', 7: '00FFFF',
    8: '000000', 9: 'FFFFFF', 10: 'FF0000', 11: '00FF00', 12: '0000FF', 13: 'FFFF00', 14: 'FF00FF', 15: '00FFFF',
    16: '800000', 17: '008000', 18: '000080', 19: '808000', 20: '800080', 21: '008080', 22: 'C0C0C0', 23: '808080',
    24: '9999FF', 25: '993366', 26: 'FFFFCC', 27: 'CCFFFF', 28: '660066', 29: 'FF8080', 30: '0066CC', 31: 'CCCCFF',
    32: '000080', 33: 'FF00FF', 34: 'FFFF00', 35: '00FFFF', 36: '800080', 37: '800000', 38: '008080', 39: '0000FF',
    40: '00CCFF', 41: 'CCFFFF', 42: 'CCFFCC', 43: 'FFFF99', 44: '99CCFF', 45: 'FF99CC', 46: 'CC99FF', 47: 'FFCC99',
    48: '3366FF', 49: '33CCCC', 50: '99CC00', 51: 'FFCC00', 52: 'FF9900', 53: 'FF6600', 54: '666699', 55: '969696',
    56: '003366', 57: '339966', 58: '003300', 59: '333300', 60: '993300', 61: '993366', 62: '333399', 63: '333333',
};

// ── HSL 色彩數學（port 自 dobtor_doc_editor ThemeResolver Sprint 130）──────
function clamp01(x: number): number {
    return Math.max(0, Math.min(1, x));
}

function hexToRgb(hex: string): [number, number, number] {
    const h = hex.replace('#', '').padStart(6, '0');
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function rgbToHex(rgb: [number, number, number]): string {
    return rgb
        .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0').toUpperCase())
        .join('');
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
    const rn = r / 255, gn = g / 255, bn = b / 255;
    const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h: number;
    switch (max) {
        case rn: h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6; break;
        case gn: h = ((bn - rn) / d + 2) / 6; break;
        default: h = ((rn - gn) / d + 4) / 6; break;
    }
    return [h, s, l];
}

function hueToRgb(p: number, q: number, t: number): number {
    let tt = t;
    if (tt < 0) tt += 1;
    if (tt > 1) tt -= 1;
    if (tt < 1 / 6) return p + (q - p) * 6 * tt;
    if (tt < 1 / 2) return q;
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
    return p;
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
    const lc = clamp01(l), sc = clamp01(s);
    if (sc === 0) {
        const v = lc * 255;
        return [v, v, v];
    }
    const q = lc < 0.5 ? lc * (1 + sc) : lc + sc - lc * sc;
    const p = 2 * lc - q;
    const hMod = ((h % 1) + 1) % 1;
    return [hueToRgb(p, q, hMod + 1 / 3) * 255, hueToRgb(p, q, hMod) * 255, hueToRgb(p, q, hMod - 1 / 3) * 255];
}

/** 對 6-hex 套 SpreadsheetML tint（-1..1）。*/
export function applyTint(hex: string, tint: number): string {
    if (tint === 0) return hex.toUpperCase();
    const [r, g, b] = hexToRgb(hex);
    const [h, s, l] = rgbToHsl(r, g, b);
    const lNew = tint > 0 ? l + (1 - l) * clamp01(tint) : l * (1 + Math.max(-1, tint));
    return rgbToHex(hslToRgb(h, s, lNew));
}

/** ARGB（8-hex）或 RGB（6-hex）→ 6-hex（去 alpha、大寫）。*/
function normalizeRgb(rgb: string): string {
    const h = rgb.replace('#', '').toUpperCase();
    return h.length === 8 ? h.slice(2) : h.padStart(6, '0');
}

export class ThemeResolver {
    constructor(private readonly theme: ParsedTheme) {}

    /**
     * Color → 6-hex RGB。
     * auto / indexed 64-65（系統色）/ 無效 theme 索引 → undefined（系統相關、由 caller 決定）。
     */
    resolveColor(color: Color | undefined): string | undefined {
        if (color === undefined) return undefined;
        if (color.auto) return undefined;

        if (color.rgb !== undefined) {
            const hex = normalizeRgb(color.rgb);
            return color.tint !== undefined ? applyTint(hex, color.tint) : hex;
        }
        if (color.theme !== undefined) {
            const key = THEME_INDEX[color.theme];
            if (key === undefined) return undefined;
            const base = this.theme.colorScheme[key];
            return color.tint !== undefined ? applyTint(base, color.tint) : base;
        }
        if (color.indexed !== undefined) {
            const hex = INDEXED_PALETTE[color.indexed];
            if (hex === undefined) return undefined; // 64/65 系統色或越界
            return color.tint !== undefined ? applyTint(hex, color.tint) : hex;
        }
        return undefined;
    }
}
