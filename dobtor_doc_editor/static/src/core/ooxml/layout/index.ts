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
