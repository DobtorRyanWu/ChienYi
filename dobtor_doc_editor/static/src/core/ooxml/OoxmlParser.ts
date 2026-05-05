/**
 * OoxmlParser — 對外總入口
 *
 * 把 ArrayBuffer (.docx) 一路解析成 DocumentNode。
 *
 * 內部組裝順序（Phase 1）：
 *   1. PackageReader 解 ZIP → parts + relationships + media
 *   2. StyleResolver 展開 styles.xml → StyleMap
 *   3. NumberingResolver 展開 numbering.xml → NumberingMap
 *   4. DocumentParser 走訪 document.xml body
 *      ├─ ParagraphParser
 *      ├─ TableParser → GridResolver
 *      ├─ SectionParser
 *      └─ DrawingParser
 *   5. HeaderFooterParser 處理 headerN/footerN.xml
 *   6. 組裝 DocumentNode
 *
 * Phase 1 Sprint 1 起逐步實作；目前為 stub。
 */

import type { DocumentNode } from './ast/types';
import { PackageReader } from './package';

export interface ParseOptions {
  /** 是否在 Run 上預先填入近似 LineMetrics（Phase 1 預設 false，Phase 2 開啟） */
  fillMetrics?: boolean;
}

export class OoxmlParser {
  private packageReader = new PackageReader();

  parse(_buffer: ArrayBuffer, _options: ParseOptions = {}): DocumentNode {
    throw new Error('OoxmlParser.parse() not implemented — Sprint 1');
  }
}

// 旁路：方便外部探測 stub 是否已連通
export const __DOBTOR_OOXML_STUB__ = 'phase-0' as const;
