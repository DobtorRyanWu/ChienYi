/**
 * Revision module — Sprint 300。
 *
 * AST 追蹤修訂 accept/reject pure-fn helpers。詳見 accept_reject.ts 檔頭。
 */
export {
  acceptRevisions,
  rejectRevisions,
  acceptParagraphRevisions,
  rejectParagraphRevisions,
  listRevisions,
} from './accept_reject';
export type {
  AcceptRejectOptions,
  RevisionPredicate,
  RevisionListEntry,
} from './accept_reject';

// Sprint 305：逐筆審 revision 狀態機（UI-agnostic）
export { RevisionReviewSession } from './RevisionReviewSession';
export type { ReviewChoice, ReviewSessionStats } from './RevisionReviewSession';

// Sprint 310：人類可讀 revision diff summary（by author / by type / markdown）
export {
  summarizeByAuthor,
  summarizeByType,
  formatSummaryMarkdown,
} from './RevisionDiffSummary';
export type { AuthorSummary, TypeSummary } from './RevisionDiffSummary';
