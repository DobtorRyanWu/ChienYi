/**
 * GridResolver — vMerge 兩-pass 演算法
 *
 * 演算法（Sprint 3）：
 *   Pass 1：掃所有 row × cell，累計 gridCol（依 gridSpan 跨欄推進），
 *           標記每個 vMerge="restart" 為主格、vMerge="continue" 為延續格。
 *   Pass 2：自下而上回掃，對每個 vMerge 鏈計算主格的 rowSpan。
 *
 * 邊界情況（不可省略）：
 *   - 同一 column 跨多列 vMerge → 第一頁底邊框 omit、第二頁頂邊框 omit
 *   - 不可用陣列索引推 column，必須累加 gridSpan
 *   - 列高混合 atLeast/exact/auto 時，rowSpan 計算不變、僅 Renderer 負責拉伸
 *
 * 目前為 stub，Sprint 3 實作。
 */

export class GridResolver {
  // TODO Sprint 3
  resolve(_rows: unknown[]): never {
    throw new Error('GridResolver.resolve() not implemented — Sprint 3');
  }
}
