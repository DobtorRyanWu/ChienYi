/**
 * DocumentParser — word/document.xml 主解析器
 *
 * 職責：
 *   - 走訪 <w:body> 子節點，分派到 ParagraphParser / TableParser / SectionParser
 *   - 串接 StyleResolver / NumberingResolver 把樣式繼承鏈展開到每個 Run/Paragraph
 *   - 輸出 DocumentNode（見 ast/types.ts）
 *
 * Phase 1 Sprint 1-2 實作；目前為 stub。
 */

import type { DocumentNode } from '../ast/types';

export class DocumentParser {
  // TODO Sprint 1-2
  parse(_xml: string): DocumentNode {
    throw new Error('DocumentParser.parse() not implemented — Sprint 1-2');
  }
}
