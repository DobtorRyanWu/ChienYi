/**
 * FontMetrics — 用 opentype.js 讀字型 ascender / descender / lineGap
 *
 * 用途：
 *   行高計算 = (ascent + descent + lineGap) * sizePt / unitsPerEm
 *
 *   canvas-editor 內部用 Browser measureText，不接受外部 metrics；
 *   但 Phase 6 自寫 Layout Engine 需要這個函式正確計算行高。
 *
 * 為何分開於 ShapingEngine：
 *   - opentype.js 是純 JS（無 WASM），體積小很多（~80KB）
 *   - 即使 HarfBuzz WASM 整合失敗，metrics-only 路徑仍可用
 *   - opentype.js 用 require()（CJS）載入，避開 ESM/CJS 互通問題
 *
 * Sprint 14：visual_regression IIFE bundle（瀏覽器）會把 'node:module' alias 成 stub
 *   （見 rollup.visual_regression.config.js）。caller 不呼叫 readFontMetrics 即無感；
 *   呼叫到才會 throw，符合「browser 沒有 opentype.js」的事實。
 */

// Sprint 62：改用直接 ESM import 取代 createRequire；
// 讓 visual_regression IIFE bundle 也能把 opentype.js 包進來、Sprint 62 FontMetricsAdapter
// 真實字型 metric 能在瀏覽器內 work（之前 createRequire('opentype.js') 在 rollup stub 下 throw、
// 全部 registerFont silent-fail → adapter 空 → VR 0.074899 = baseline 不變、揭示假性結果）。
//
// opentype.js v1.3.5 在 package.json 有 module: opentype.mjs（ESM）；rollup resolve + commonjs
// 兩 plugin 處理 default export 互通即可。增加 IIFE bundle size ~80KB。
import * as opentypeNs from 'opentype.js';
const opentype = (opentypeNs as { default?: unknown }).default ?? opentypeNs;

/** 字型核心 metrics（pt 為單位需乘以 sizePt / unitsPerEm） */
export interface FontMetricsResult {
  /** 每 em 的設計單位數（OOXML 規格內字型大小用） */
  unitsPerEm: number;
  /** 基線以上高度 */
  ascender: number;
  /** 基線以下深度（正值） */
  descender: number;
  /** 字型建議的額外行距 */
  lineGap: number;
  /** x-height（小寫 x 高度，OOXML 文字渲染未必用得到，但常被排版引擎查） */
  xHeight?: number;
  /** cap-height（大寫高度） */
  capHeight?: number;
}

interface OpentypeFont {
  unitsPerEm: number;
  ascender: number;
  descender: number;
  tables?: {
    os2?: { sxHeight?: number; sCapHeight?: number; sTypoLineGap?: number };
    hhea?: { lineGap?: number };
  };
}

interface OpentypeModule {
  parse: (buffer: ArrayBuffer | Uint8Array) => OpentypeFont;
}

function getOpentype(): OpentypeModule {
  // Sprint 62：opentype.js 已透過 ESM static import 取得；module 可能 default-exported 或 namespace
  return opentype as OpentypeModule;
}

/**
 * 解析字型 byte buffer，回傳核心 metrics。
 *
 * lineGap 取值優先順序：
 *   OS/2 table sTypoLineGap > hhea table lineGap > 0
 *
 * @param fontBytes TTF / OTF 位元組（Uint8Array 或 ArrayBuffer）
 * @returns FontMetricsResult；解析失敗時 throw
 */
export function readFontMetrics(fontBytes: Uint8Array | ArrayBuffer): FontMetricsResult {
  const ot = getOpentype();
  // opentype.js 接受 ArrayBuffer；Uint8Array → 取其 underlying buffer 切片
  // 注意：buffer.slice 在 SharedArrayBuffer 時回 SharedArrayBuffer，需強制視為 ArrayBuffer
  const buffer: ArrayBuffer =
    fontBytes instanceof Uint8Array
      ? (fontBytes.buffer.slice(
          fontBytes.byteOffset,
          fontBytes.byteOffset + fontBytes.byteLength,
        ) as ArrayBuffer)
      : fontBytes;
  const font = ot.parse(buffer);

  const out: FontMetricsResult = {
    unitsPerEm: font.unitsPerEm,
    ascender: font.ascender,
    descender: Math.abs(font.descender), // descender 通常為負，取絕對值
    lineGap:
      font.tables?.os2?.sTypoLineGap ??
      font.tables?.hhea?.lineGap ??
      0,
  };
  if (font.tables?.os2?.sxHeight) out.xHeight = font.tables.os2.sxHeight;
  if (font.tables?.os2?.sCapHeight) out.capHeight = font.tables.os2.sCapHeight;
  return out;
}

/**
 * 計算單行的高度（pt）。
 *
 * Phase 6 Layout Engine 排版時用：每行的高度 = ascent + descent + lineGap
 * （皆已換算為 pt）。
 *
 * @param metrics 由 readFontMetrics 取得
 * @param sizePt 字級（點 pt）
 */
export function lineHeightPt(metrics: FontMetricsResult, sizePt: number): number {
  const { unitsPerEm, ascender, descender, lineGap } = metrics;
  return ((ascender + descender + lineGap) * sizePt) / unitsPerEm;
}
