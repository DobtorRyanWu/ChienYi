// theme_parser.ts — 解析 xl/theme/theme1.xml（規劃書 §1.9）
//
// 取 clrScheme 的 12 色 token（dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink）與 fontScheme
// （major/minor 的 latin/ea/cs 字型）。色彩值：srgbClr 取 val、sysClr 取 lastClr（已解析值）。
// 解析結果供 §2.2 ThemeResolver 把 cell 的 theme color → 具體 RGB。

import { parseXmlNoNs, attr, toArray } from './xml_util';

/** clrScheme 12 色（key 為 scheme 元素名，value 為 6-hex RGB，無 alpha）。*/
export interface ThemeColorScheme {
    dk1: string;
    lt1: string;
    dk2: string;
    lt2: string;
    accent1: string;
    accent2: string;
    accent3: string;
    accent4: string;
    accent5: string;
    accent6: string;
    hlink: string;
    folHlink: string;
}

export interface ThemeFont {
    latin?: string;
    ea?: string; // East Asian（CJK）
    cs?: string; // Complex Script
}

export interface ParsedTheme {
    colorScheme: ThemeColorScheme;
    majorFont: ThemeFont;
    minorFont: ThemeFont;
}

const SCHEME_KEYS: (keyof ThemeColorScheme)[] = [
    'dk1', 'lt1', 'dk2', 'lt2',
    'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
    'hlink', 'folHlink',
];

// Office 預設主題（fallback：theme 缺失或某色未定義時用）
const DEFAULT_SCHEME: ThemeColorScheme = {
    dk1: '000000', lt1: 'FFFFFF', dk2: '44546A', lt2: 'E7E6E6',
    accent1: '4472C4', accent2: 'ED7D31', accent3: 'A5A5A5',
    accent4: 'FFC000', accent5: '5B9BD5', accent6: '70AD47',
    hlink: '0563C1', folHlink: '954F72',
};

/** 從 scheme 色元素（如 <dk1><srgbClr val=../sysClr lastClr=..>）取 6-hex。*/
function colorFromElement(el: unknown): string | undefined {
    if (el === null || typeof el !== 'object') return undefined;
    const e = el as Record<string, unknown>;
    const srgb = attr(e['srgbClr'], 'val');
    if (srgb !== undefined) return srgb.toUpperCase();
    const sys = attr(e['sysClr'], 'lastClr');
    if (sys !== undefined) return sys.toUpperCase();
    return undefined;
}

function parseFont(node: unknown): ThemeFont {
    if (node === null || typeof node !== 'object') return {};
    const n = node as Record<string, unknown>;
    const font: ThemeFont = {};
    const latin = attr(n['latin'], 'typeface');
    if (latin) font.latin = latin;
    const ea = attr(n['ea'], 'typeface');
    if (ea) font.ea = ea;
    const cs = attr(n['cs'], 'typeface');
    if (cs) font.cs = cs;
    return font;
}

export class ThemeParser {
    static parse(xmlText: string): ParsedTheme {
        const xml = parseXmlNoNs(xmlText);
        const theme = (xml['theme'] ?? {}) as Record<string, unknown>;
        const elements = (theme['themeElements'] ?? {}) as Record<string, unknown>;

        const clr = (elements['clrScheme'] ?? {}) as Record<string, unknown>;
        const colorScheme = { ...DEFAULT_SCHEME };
        for (const key of SCHEME_KEYS) {
            const c = colorFromElement(clr[key]);
            if (c !== undefined) colorScheme[key] = c;
        }

        const fontScheme = (elements['fontScheme'] ?? {}) as Record<string, unknown>;
        const major = toArray<unknown>(fontScheme['majorFont'])[0];
        const minor = toArray<unknown>(fontScheme['minorFont'])[0];

        return {
            colorScheme,
            majorFont: parseFont(major),
            minorFont: parseFont(minor),
        };
    }

    /** Office 預設主題（無 theme part 時 fallback）。*/
    static default(): ParsedTheme {
        return { colorScheme: { ...DEFAULT_SCHEME }, majorFont: {}, minorFont: {} };
    }
}
