// font_map.ts — Excel 字型名 → 渲染字型堆疊（VR 字型保真）
//
// golden 由 LibreOffice 渲染、走 fontconfig 字型替換。我方 puppeteer Chrome 也走 fontconfig，
// 但若 CSS 加通用 fallback（sans-serif）會讓 Chrome 自選回退、與 LibreOffice 不一致。
// 本模組把 Excel 字型釘死到 LibreOffice 慣用的 metric-compatible 替換 + 一致的 CJK 回退鏈。

// Latin metric-compatible 替換（與原字型字寬一致，LibreOffice/系統內建）：
//   Calibri→Carlito、Arial→Liberation Sans、Times New Roman→Liberation Serif ...
const METRIC_COMPATIBLE: Readonly<Record<string, string>> = {
    Calibri: 'Carlito',
    'Calibri Light': 'Carlito',
    Cambria: 'Caladea',
    Arial: 'Liberation Sans',
    'Arial Narrow': 'Liberation Sans Narrow',
    Helvetica: 'Liberation Sans',
    'Times New Roman': 'Liberation Serif',
    Georgia: 'Liberation Serif',
    'Courier New': 'Liberation Mono',
};

// 系統實際存在的 CJK 字型（fc-list 確認）；CJK 字元的最終回退，確保與 LibreOffice 同源。
const CJK_FALLBACK = "'WenQuanYi Zen Hei','Droid Sans Fallback',sans-serif";

/**
 * Excel 字型名 → CSS font-family 堆疊。
 * - Latin 有 metric-compatible 替換 → 用替換 + CJK 回退
 * - CJK / 未知字型 → 原名（讓 fontconfig 比照 LibreOffice 替換）+ CJK 回退
 */
export function fontFamilyStack(name?: string): string {
    if (!name) return CJK_FALLBACK;
    const mc = METRIC_COMPATIBLE[name];
    const primary = mc ?? name;
    return `'${primary.replace(/'/g, '')}',${CJK_FALLBACK}`;
}

export { CJK_FALLBACK };
