/**
 * Layout module — Phase 6 Layout Engine 自寫 入口
 *
 * Sprint 277 MVP：greedy LineBreaker（消費 Phase 2 ShapingEngine API）。
 * Phase 6 完整 Layout 才會擴充至 mixed run / Knuth-Plass / hyphenation /
 * CJK justification / bidi。
 */

export { breakParagraph } from './LineBreaker';
export type {
  BrokenLine,
  LineBreakResult,
  LineBreakOptions,
} from './LineBreaker';

// Sprint 288：Phase 2.1-2.3 整合 façade（ShapingEngine + FontMetrics + LineBreaker
// + ShapingFontChain 接成單一 production-grade 入口、給 Phase 6 自寫 Layout 消費）
export {
  layoutParagraph,
  layoutParagraphWithFontChain,
} from './LayoutPipeline';
export type {
  LayoutParagraphOptions,
  LayoutParagraphWithFontChainOptions,
  ParagraphLayoutResult,
  ParagraphLayoutWithChainResult,
} from './LayoutPipeline';

// Sprint 296：wrapTight polygon layout 數學工具（pure-fn、layout engine 整合留 future）
export {
  transformWrapPolygon,
  polygonBoundingBox,
  pointInPolygon,
  rectIntersectsPolygon,
} from './wrap_polygon_math';
export type { ImageRect, PolygonBoundingBox } from './wrap_polygon_math';
