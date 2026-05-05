/**
 * StyleResolver — word/styles.xml 樣式繼承鏈展開
 *
 * 解析三層繼承鏈：docDefaults → pStyle (basedOn 鏈) → 直接屬性
 * Resolver 完成後輸出已展開的 StyleMap，供 ParagraphParser 直接合併。
 *
 * Phase 1 Sprint 2 實作；目前為 stub。
 */

import type { StyleMap } from '../ast/types';

export class StyleResolver {
  // TODO Sprint 2
  resolve(_xml: string): StyleMap {
    throw new Error('StyleResolver.resolve() not implemented — Sprint 2');
  }
}
