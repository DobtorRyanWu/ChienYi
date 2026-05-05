/**
 * TableParser — 解析 <w:tbl>
 *
 * 職責：
 *   - 走訪 <w:tblGrid> 取得 grid column 寬度
 *   - 走訪 <w:tr> → <w:tc>，取得 cellRaw（含 gridSpan/vMerge 資訊）
 *   - 委派 GridResolver 計算每個 Cell 的 (gridCol, gridSpan, rowSpan, isContinuation)
 *
 * Phase 1 Sprint 3 實作；目前為 stub。
 */

import type { TableNode } from '../ast/types';

export class TableParser {
  // TODO Sprint 3
  parse(_tableElement: unknown): TableNode {
    throw new Error('TableParser.parse() not implemented — Sprint 3');
  }
}
