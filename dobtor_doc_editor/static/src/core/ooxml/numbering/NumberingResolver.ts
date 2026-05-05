/**
 * NumberingResolver — word/numbering.xml 多層次清單編號
 *
 * 解析 numId → abstractNumId → levels[ilvl] 鏈，含：
 *   - lvlText 範本展開（"%1.%2." → "1.1." 等）
 *   - lvlRestart 重啟邏輯
 *   - isLgl 強制十進位
 *
 * Phase 1 Sprint 2 實作；目前為 stub。
 */

import type { NumberingMap } from '../ast/types';

export class NumberingResolver {
  // TODO Sprint 2
  resolve(_xml: string): NumberingMap {
    throw new Error('NumberingResolver.resolve() not implemented — Sprint 2');
  }
}
