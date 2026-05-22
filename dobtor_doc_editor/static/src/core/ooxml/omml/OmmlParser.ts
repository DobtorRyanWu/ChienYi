/**
 * OmmlParser — 解析 OMML 數學公式（`m:` 命名空間、ECMA-376 §22.1、Phase 5.1）
 *
 * Sprint 179（capture-only）：
 *   Word 數學公式（「插入 → 方程式」）以 OMML（Office Math Markup Language）儲存，
 *   內嵌於 document.xml 的段落中：
 *     - 段落直屬 `<m:oMath>`                    → 行內公式（inline math）
 *     - 段落直屬 `<m:oMathPara><m:oMath>...`     → 獨立置中公式（display math）
 *
 *   OMML 結構元素（部分）：
 *     <m:f>   分數（<m:num> 分子 / <m:den> 分母）
 *     <m:rad> 根號（<m:deg> 次數 / <m:e> 被開方數）
 *     <m:nary> n 元運算子（求和 / 積分；<m:sub> 下限 / <m:sup> 上限 / <m:e> 主體）
 *     <m:sSub> / <m:sSup> / <m:sSubSup>  下標 / 上標 / 上下標
 *     <m:d>   括號分隔符（delimiter）
 *     <m:m>   矩陣（<m:mr> 列 / <m:e> 格）
 *     <m:r>   math run（含 <m:t> 文字）
 *
 * capture-only：以遞迴通用樹（OmmlNode）保留完整結構，不解語意、不轉 MathML / KaTeX。
 * 渲染（OMML → KaTeX）+ 行內位置 wire-up 留 Sprint 180。
 *
 * Scope-down（紀律 #18）：只走訪元素節點與 `<m:t>` 文字；
 * `<m:rPr>` / `<m:ctrlPr>` 等屬性容器一併以通用樹保留（不另解語意）。
 *
 * 防禦：undefined / 無子元素 → 回空陣列（不 throw）。
 */

import type { OmmlNode } from '../ast/types';
import { directChildren } from '../utils/dom';

/** OMML 命名空間前綴。 */
const MATH_NS_PREFIX = 'm:';
/** OMML 文字葉節點標籤（去前綴後）。 */
const MATH_TEXT_TAG = 't';

/**
 * 把 OOXML 標籤名去掉 `m:` 命名空間前綴，回傳 localName。
 * 無前綴（理論上不會發生於 OMML 子樹）則原樣回傳。
 */
function stripMathPrefix(tagName: string): string {
  return tagName.startsWith(MATH_NS_PREFIX)
    ? tagName.slice(MATH_NS_PREFIX.length)
    : tagName;
}

/**
 * 遞迴解析 OMML 元素的子節點為 OmmlNode 樹。
 *
 * @param el `<m:oMath>` 或任一 OMML 結構元素
 * @returns 子節點的 OmmlNode 陣列；無元素子節點 → 空陣列
 */
export function parseOmmlChildren(el: Element | undefined | null): OmmlNode[] {
  if (!el) return [];
  const out: OmmlNode[] = [];
  for (const child of directChildren(el)) {
    const tag = stripMathPrefix(child.tagName);
    const node: OmmlNode = { tag };
    if (tag === MATH_TEXT_TAG) {
      // `<m:t>` 為文字葉節點（OOXML §22.1.2.116）
      node.text = child.textContent ?? '';
    } else {
      const kids = parseOmmlChildren(child);
      // 紀律 #21：無子節點不掛 key、避免 AST diff noise
      if (kids.length > 0) node.children = kids;
    }
    out.push(node);
  }
  return out;
}
