/**
 * SectionParser — 解析 <w:sectPr>
 *
 * 職責：
 *   - 取得頁面尺寸 / margins / orientation
 *   - 取得欄位設定（cols count / space / equalWidth）
 *   - 取得 header/footer 引用 rId（default / first / even）
 *   - 取得 titlePg / evenAndOddHeaders 旗標
 *
 * Phase 1 Sprint 2 實作；目前為 stub。
 */

import type { SectionNode } from '../ast/types';

export class SectionParser {
  // TODO Sprint 2
  parse(_sectPrElement: unknown): SectionNode {
    throw new Error('SectionParser.parse() not implemented — Sprint 2');
  }
}
