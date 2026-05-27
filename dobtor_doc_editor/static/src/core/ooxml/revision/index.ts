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
