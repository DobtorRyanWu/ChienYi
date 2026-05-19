/**
 * ShapingEngine — HarfBuzz WASM 文字成形引擎封裝
 *
 * 職責：
 *   - 載入 harfbuzzjs WASM（lazy，第一次 shape 才實際載入）
 *   - 把字型 byte buffer 包裝為 hb.face + hb.font
 *   - 對 (text, font) 呼叫 hb.shape，回傳精確 glyph[]（含 advance / offset）
 *
 * 為什麼不在 OoxmlParser 主流程使用：
 *   - WASM 體積 ~200KB，會大幅增加 bundle 大小
 *   - canvas-editor 內部用自己的 measureText，不接受外部 metrics
 *   - Phase 6 自寫 Layout Engine 時才會真正使用此引擎
 *
 * Phase D.2 範圍：
 *   - 提供 ShapingEngine 類別 + 單測
 *   - 不接到 OoxmlParser.parse() / ParagraphParser
 *   - 保留 fillMetrics ParseOption 旗標供未來啟用
 *
 * Phase 6+ 使用方式（規劃）：
 *   const engine = new ShapingEngine();
 *   await engine.loadFont('Times New Roman', fontBytes);
 *   const glyphs = engine.shape('Hello world', 'Times New Roman', 12);
 *   // → [{ glyphId, xAdvance, yAdvance, xOffset, yOffset, cluster }, ...]
 */

import { createRequire } from 'node:module';

/** 單一 glyph 的成形結果（HarfBuzz 標準 + cluster 字元位置）。 */
export interface ShapedGlyph {
  /** 字型內 glyph index（0 = .notdef，字型不支援該字元） */
  glyphId: number;
  /** Horizontal advance（字型 unitsPerEm 為單位） */
  xAdvance: number;
  /** Vertical advance（橫排為 0） */
  yAdvance: number;
  /** Horizontal placement offset */
  xOffset: number;
  /** Vertical placement offset */
  yOffset: number;
  /** 該 glyph 對應原文字 cluster index */
  cluster: number;
}

/** harfbuzzjs 的最小型別宣告（避開直接 import 它的型別檔） */
interface HBInstance {
  createBlob: (data: Uint8Array) => unknown;
  createFace: (blob: unknown) => unknown;
  createFont: (face: unknown) => unknown;
  createBuffer: () => HBBuffer;
  shape: (font: unknown, buffer: unknown) => void;
}

interface HBBuffer {
  addText: (text: string) => void;
  guessSegmentProperties: () => void;
  setDirection?: (dir: 'ltr' | 'rtl' | 'ttb' | 'btt') => void;
  setScript?: (script: string) => void;
  setLanguage?: (lang: string) => void;
  json: () => Array<{
    ax: number;
    ay: number;
    dx: number;
    dy: number;
    g: number;
    cl: number;
  }>;
}

/**
 * 載入 harfbuzzjs（CJS Promise pattern）。
 *
 * harfbuzzjs index.js 是 `module.exports = new Promise(...)`：
 *   - 在純 Node CJS：直接 await require('harfbuzzjs')
 *   - 在 ESM / vitest：用 createRequire 取 CJS module.exports，再 await
 *
 * 此函式封裝了載入細節並 cache 結果。
 */
let hbInstancePromise: Promise<HBInstance> | undefined;

async function loadHb(): Promise<HBInstance> {
  if (!hbInstancePromise) {
    // createRequire(import.meta.url) 在純瀏覽器環境會失敗（但 ShapingEngine
    // 預期只在 Node CLI / Layout Engine 階段使用，瀏覽器內走 canvas-editor measureText）
    const localRequire = createRequire(import.meta.url);
    const mod = localRequire('harfbuzzjs');
    hbInstancePromise = (mod as Promise<HBInstance>);
  }
  return hbInstancePromise;
}

interface FontEntry {
  bytes: Uint8Array;
  hbFont?: unknown;  // 第一次 shape 時 lazy 建立
}

export class ShapingEngine {
  /** 已載入的字型（key = font family name）。 */
  private fonts = new Map<string, FontEntry>();

  /**
   * 註冊字型 byte buffer（從檔案 / 網路 / Odoo Asset 取得後傳入）。
   *
   * @param family 字型 family name（與 RunProps.fontFamily 對應）
   * @param bytes 字型檔位元組（TTF / OTF）
   */
  loadFont(family: string, bytes: Uint8Array): void {
    this.fonts.set(family, { bytes });
  }

  /** 列出已載入的字型 family。 */
  listFonts(): string[] {
    return Array.from(this.fonts.keys());
  }

  /**
   * 對指定字型 + 文字做 shaping。
   *
   * @param text 原文字（可含 CJK / 西文混排 / 連字 / 變音符號）
   * @param family 字型 family name（必須先呼叫 loadFont 註冊）
   * @param sizePt 字級（點 pt）— Phase 6 Layout Engine 換算 advance 為 pt 用
   * @returns ShapedGlyph[]，依文字順序排列
   * @throws Error 若字型未註冊或 hb 載入失敗
   */
  async shape(text: string, family: string, _sizePt: number): Promise<ShapedGlyph[]> {
    const entry = this.fonts.get(family);
    if (!entry) {
      throw new Error(`ShapingEngine: font "${family}" not loaded — call loadFont() first`);
    }
    const hb = await loadHb();

    // Lazy 建立 hb.face / hb.font（每個 family 只建一次）
    if (!entry.hbFont) {
      const blob = hb.createBlob(entry.bytes);
      const face = hb.createFace(blob);
      entry.hbFont = hb.createFont(face);
    }

    const buffer = hb.createBuffer();
    buffer.addText(text);
    buffer.guessSegmentProperties();
    hb.shape(entry.hbFont!, buffer);

    return buffer.json().map((g) => ({
      glyphId: g.g,
      xAdvance: g.ax,
      yAdvance: g.ay,
      xOffset: g.dx,
      yOffset: g.dy,
      cluster: g.cl,
    }));
  }

  /** 清除字型快取（測試 / 字型熱更新用）。 */
  clear(): void {
    this.fonts.clear();
  }
}

/** 重置全域 hb instance（測試用） */
export function __resetHbForTesting(): void {
  hbInstancePromise = undefined;
}
