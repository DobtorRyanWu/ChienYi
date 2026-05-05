/**
 * HeaderFooterParser — 解析 word/headerN.xml 與 word/footerN.xml
 *
 * 結構與 document.xml 的 body 相同（BlockNode[]），可重用 DocumentParser 的 body 走訪邏輯。
 *
 * Phase 1 Sprint 2 實作；目前為 stub。
 */

import type { HeaderFooterContent } from '../ast/types';

export class HeaderFooterParser {
  // TODO Sprint 2
  parse(_xml: string, _rId: string): HeaderFooterContent {
    throw new Error('HeaderFooterParser.parse() not implemented — Sprint 2');
  }
}
