/**
 * ParagraphParser — 解析 <w:p> 與內部 <w:r>（Run）
 *
 * 處理範圍（Sprint 1）：
 *   - w:pPr 段落屬性（對齊、縮排、行距、numbering）
 *   - w:rPr Run 屬性（字型、字級、粗斜體、下劃線、顏色、highlight）
 *   - w:t 文字、w:br 換行、w:tab、w:fldSimple/w:fldChar 欄位
 *   - w:drawing 內嵌圖片（轉發 DrawingParser）
 *
 * Phase 1 Sprint 1 實作；目前為 stub。
 */

import type { ParagraphNode } from '../ast/types';

export class ParagraphParser {
  // TODO Sprint 1
  parse(_paragraphElement: unknown): ParagraphNode {
    throw new Error('ParagraphParser.parse() not implemented — Sprint 1');
  }
}
