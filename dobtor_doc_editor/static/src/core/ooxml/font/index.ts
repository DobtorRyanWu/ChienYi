/**
 * Font Pipeline — Phase D.2 / Phase 6 Layout Engine 預備
 *
 * 包含：
 *   - ShapingEngine：HarfBuzz WASM 文字成形
 *   - FontMetrics：opentype.js 讀字型核心度量（行高計算用）
 *
 * Phase D 範圍：提供類別與單測；不接到 OoxmlParser 主流程
 * Phase 6 範圍：自寫 Layout Engine 時取代 canvas-editor 的 measureText
 */

export { ShapingEngine, __resetHbForTesting } from './ShapingEngine';
export type { ShapedGlyph } from './ShapingEngine';
export { readFontMetrics, lineHeightPt } from './FontMetrics';
export type { FontMetricsResult } from './FontMetrics';
