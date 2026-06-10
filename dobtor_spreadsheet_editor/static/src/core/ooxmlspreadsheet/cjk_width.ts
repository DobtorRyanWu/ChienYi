// cjk_width.ts — CJK 欄寬估算（規劃書 §2.5 查表法）
//
// 全形（CJK 漢字、假名、全形符號）視為 2 個 ASCII 寬度，半形 1 個。
// 用於無明確 Excel 欄寬的欄：依內容估算顯示寬度，改善 HTML 預覽 CJK 欄擠壓。

/** 單一 code point 的顯示寬度（全形 2、半形 1）。*/
function charWidth(cp: number): number {
    if (
        (cp >= 0x1100 && cp <= 0x115f) || // Hangul Jamo
        (cp >= 0x2e80 && cp <= 0x303e) || // CJK 部首 + 符號
        (cp >= 0x3041 && cp <= 0x33ff) || // 假名 + 注音 + CJK 相容
        (cp >= 0x3400 && cp <= 0x4dbf) || // CJK 擴展 A
        (cp >= 0x4e00 && cp <= 0x9fff) || // CJK 統一表意
        (cp >= 0xa000 && cp <= 0xa4cf) || // 彝文
        (cp >= 0xac00 && cp <= 0xd7a3) || // 諺文音節
        (cp >= 0xf900 && cp <= 0xfaff) || // CJK 相容表意
        (cp >= 0xfe30 && cp <= 0xfe4f) || // CJK 相容形式
        (cp >= 0xff00 && cp <= 0xff60) || // 全形 ASCII
        (cp >= 0xffe0 && cp <= 0xffe6) || // 全形符號
        (cp >= 0x20000 && cp <= 0x3fffd) // CJK 擴展 B+
    ) {
        return 2;
    }
    return 1;
}

/** 文字的顯示寬度（以 ASCII 字元為單位）。*/
export function displayWidth(text: string): number {
    let w = 0;
    for (const ch of text) {
        w += charWidth(ch.codePointAt(0) ?? 0);
    }
    return w;
}
