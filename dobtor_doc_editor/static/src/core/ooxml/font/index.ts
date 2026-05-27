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

export {
  ShapingEngine,
  __resetHbForTesting,
  detectScript,
  defaultLanguageForScript,
  defaultDirectionForScript,
  // Sprint 279：browser-compat refactor — caller-injectable hbModuleLoader
  setHbModuleLoader,
  __resetHbModuleLoaderForTesting,
} from './ShapingEngine';
export type { ShapedGlyph, ShapeOptions, RunMetrics, ShapingCacheStats } from './ShapingEngine';
export {
  readFontMetrics,
  lineHeightPt,
  resolveOoxmlLineHeight,
  baselineOffsetPt,
  readOpentypeAdvances,
} from './FontMetrics';
export type { FontMetricsResult, OoxmlLineHeightResult, OpentypeAdvanceResult } from './FontMetrics';
// Sprint 280：browser/Node 通用字型 fetch + fallback chain wire-up
export {
  loadShapingFontWithChain,
  getDefaultCjkFallbackChain,
  FontChainExhaustedError,
} from './ShapingFontChain';
export type {
  ShapingFontChainEntry,
  LoadShapingFontWithChainOptions,
  LoadShapingFontResult,
} from './ShapingFontChain';
// Sprint 302：canvas-editor measureText proxy PROBE
export { TextMeasureProxy } from './TextMeasureProxy';
export type {
  MeasureRunFn,
  TextMeasureProxyOptions,
  TextMeasureCacheEntry,
} from './TextMeasureProxy';
