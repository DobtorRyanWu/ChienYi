/**
 * DrawingParser — 解析 <w:drawing> 內嵌與浮動圖片
 *
 * 處理 wp:inline → InlineImageNode、wp:anchor → FloatImageNode。
 * 圖片本身透過 rId 從 PackageReader 取出 blob，由 Renderer 載入。
 *
 * Phase 1 Sprint 3 實作；目前為 stub。
 * Phase 5 SmartArt / Charts 視為 fallback 圖片，仍經此 Parser。
 */

import type { InlineImageNode, FloatImageNode } from '../ast/types';

export class DrawingParser {
  // TODO Sprint 3
  parse(_drawingElement: unknown): InlineImageNode | FloatImageNode {
    throw new Error('DrawingParser.parse() not implemented — Sprint 3');
  }
}
