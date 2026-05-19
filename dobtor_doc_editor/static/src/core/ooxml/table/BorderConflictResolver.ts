/**
 * BorderConflictResolver — ECMA-376 §17.4.65 表格邊框衝突解決
 *
 * 目的：
 *   Word 表格邊框可從 4 處來源：
 *     1. cell 自己的 <w:tcBorders>
 *     2. row 的 <w:trPr>（罕見）
 *     3. table 的 <w:tblBorders>（含 insideH/insideV 控制 cell 內邊）
 *     4. style 的 <w:tblBorders>（從 tblStyle 繼承，已被 StyleResolver 展開到 entry）
 *   多個來源在同一邊衝突時，需依優先級表決勝。
 *
 * 提供：
 *   - mergeCellBorders(cell, row, table, isInside) → CellBorders（單格 4 邊）
 *   - resolveCellEdge(edgeA, edgeB) → BorderDef（相鄰 cell 兩側競合）
 *   - resolveTableBorders(table) → 對全表 mutate 每 cell 的 borders 為 resolved 結果
 *
 * 優先級規則（§17.4.65 簡化版）：
 *   - nil/none 永遠輸（除非雙方皆 nil）
 *   - size 較大者勝
 *   - size 平手 → style weight 排序
 *   - style 平手 → color 字典序（穩定排序，少見）
 *
 * 為何在 Parser 階段做：
 *   - 渲染端（canvas-editor）只接受 cell 級 4 邊，不知道 insideH/insideV 概念
 *   - 跨 cell 邊框衝突在 layout 前要解決，否則重疊邊框會被畫兩次或缺失
 *   - 此處輸出的 CellBorders 已是 resolved 結果，render 直接用
 */

import type {
  BorderDef,
  BorderStyle,
  CellBorders,
  CellNode,
  RowNode,
  TableNode,
} from '../ast/types';

/**
 * Border style weight 排序（依 ECMA-376 §17.4.65 與 §17.18.2 決定）。
 *
 * 數字越大 = 越「強」優先級。
 * style 同尺寸時，weight 大者勝。
 */
const STYLE_WEIGHT: Record<string, number> = {
  nil: 0,
  none: 0,
  // 細線
  hair: 1,
  dotted: 2,
  dashed: 3,
  dashDot: 4,
  dashDotDot: 5,
  dashSmallGap: 4,
  dashDotStroked: 5,
  // 標準
  single: 10,
  // 粗線
  thick: 20,
  // 多線
  double: 30,
  triple: 32,
  // 內厚外薄 / 外厚內薄
  thinThickSmallGap: 40,
  thickThinSmallGap: 41,
  thinThickThinSmallGap: 42,
  thickThinThinSmallGap: 43,
  thinThickMediumGap: 44,
  thickThinMediumGap: 45,
  thinThickThinMediumGap: 46,
  thickThinThinMediumGap: 47,
  thinThickLargeGap: 48,
  thickThinLargeGap: 49,
  thinThickThinLargeGap: 50,
  thickThinThinLargeGap: 51,
  // 浪線/裝飾
  wave: 60,
  doubleWave: 61,
  dashLongHeavy: 62,
  dashDotHeavy: 63,
  dashDotDotHeavy: 64,
};

function styleWeight(style: BorderStyle | undefined): number {
  if (!style) return 0;
  return STYLE_WEIGHT[style] ?? 5;  // 未列入表的給中等權重
}

/**
 * 比較兩個 BorderDef，回傳「贏家」（即優先採用的那一側）。
 *
 * 規則：
 *   1. 任一為 nil/none：另一方勝（皆 nil → undefined，雙方都不畫）
 *   2. width（pt）較大者勝
 *   3. width 平手 → styleWeight 較大者勝
 *   4. style 平手 → color 字典序穩定排序
 *   5. 全平手 → 回 a（穩定）
 */
export function resolveCellEdge(
  a: BorderDef | undefined,
  b: BorderDef | undefined,
): BorderDef | undefined {
  if (!a && !b) return undefined;
  if (!a) return isNil(b) ? undefined : b;
  if (!b) return isNil(a) ? undefined : a;
  if (isNil(a) && isNil(b)) return undefined;
  if (isNil(a)) return b;
  if (isNil(b)) return a;

  if (a.width !== b.width) return a.width > b.width ? a : b;

  const wa = styleWeight(a.style);
  const wb = styleWeight(b.style);
  if (wa !== wb) return wa > wb ? a : b;

  if (a.color !== b.color) return a.color < b.color ? a : b;
  return a;
}

function isNil(b: BorderDef | undefined): boolean {
  if (!b) return true;
  return b.style === 'nil' || b.style === 'none';
}

/**
 * 對單一 cell 計算其四邊 effective borders。
 *
 * 套用順序（後者可能蓋前者，依 resolveCellEdge 競爭）：
 *   1. table.borders.top/bottom/left/right → cell 對應外邊
 *   2. table.borders.insideH/insideV → cell 內邊（非外緣 cell 的）
 *   3. cell.props.borders.* → cell 自己的設定
 *
 * @param cell           CellNode（將回傳新的 CellBorders，不 mutate cell）
 * @param row            cell 所在 RowNode（目前 row 沒 borders 欄位，留待未來擴展）
 * @param table          TableNode
 * @param totalRows      表格列總數
 * @param rowIndex       此 cell 所在 row index（0-based）
 */
export function mergeCellBorders(
  cell: CellNode,
  _row: RowNode,
  table: TableNode,
  rowIndex: number,
  totalRows: number,
): CellBorders {
  const out: CellBorders = {};
  const tblBorders = table.props.borders;
  const cellBorders = cell.props.borders;

  const isFirstRow = rowIndex === 0;
  const isLastRow = rowIndex === totalRows - 1;
  const isFirstCol = cell.gridCol === 0;
  const isLastCol = cell.gridCol + cell.gridSpan === table.grid.length;

  // top
  let top: BorderDef | undefined;
  if (isFirstRow) top = tblBorders?.top;
  else top = tblBorders?.insideH;
  top = resolveCellEdge(top, cellBorders?.top);
  if (top) out.top = top;

  // bottom
  let bottom: BorderDef | undefined;
  if (isLastRow) bottom = tblBorders?.bottom;
  else bottom = tblBorders?.insideH;
  bottom = resolveCellEdge(bottom, cellBorders?.bottom);
  if (bottom) out.bottom = bottom;

  // left
  let left: BorderDef | undefined;
  if (isFirstCol) left = tblBorders?.left;
  else left = tblBorders?.insideV;
  left = resolveCellEdge(left, cellBorders?.left);
  if (left) out.left = left;

  // right
  let right: BorderDef | undefined;
  if (isLastCol) right = tblBorders?.right;
  else right = tblBorders?.insideV;
  right = resolveCellEdge(right, cellBorders?.right);
  if (right) out.right = right;

  return out;
}

/**
 * 對全表 mutate 每 cell.props.borders 為 resolved 結果。
 *
 * 步驟：
 *   1. 對每 cell 跑 mergeCellBorders 取「table inside/outside + cell own」競爭結果
 *   2. 對相鄰 cell 兩側做 resolveCellEdge：
 *        - 同列左右相鄰：cell[i].right vs cell[i+1].left
 *        - 跨列上下相鄰：cell(r, c).bottom vs cell(r+1, c).top
 *      取勝者寫回兩側（讓兩邊看到的 border 一致）
 *   3. vMerge continuation cell 的水平邊（在 anchor span 中段）省略：
 *        - anchor cell 的 bottom = anchor 範圍內最末 row 的 bottom（不被 inside 影響）
 *        - 簡化：本實作只處理「不可見 continuation」，不對 cross-page render 做 special handling
 *
 * 副作用：mutate table.rows[*].cells[*].props.borders
 */
export function resolveTableBorders(table: TableNode): void {
  const totalRows = table.rows.length;
  const totalCols = table.grid.length;

  // Pass 1：每 cell 算自己的 4 邊（與 tblBorders 競爭）
  for (let r = 0; r < totalRows; r++) {
    const row = table.rows[r];
    for (const cell of row.cells) {
      cell.props.borders = mergeCellBorders(cell, row, table, r, totalRows);
    }
  }

  // Pass 2：相鄰 cell 邊界協調
  // 建 grid-position map：(row, gridCol) → cell
  const cellAt: (CellNode | undefined)[][] = [];
  for (let r = 0; r < totalRows; r++) {
    cellAt[r] = new Array(totalCols).fill(undefined);
    for (const cell of table.rows[r].cells) {
      for (let c = cell.gridCol; c < cell.gridCol + cell.gridSpan && c < totalCols; c++) {
        cellAt[r][c] = cell;
      }
    }
  }

  // 同列左右相鄰
  for (let r = 0; r < totalRows; r++) {
    for (let c = 0; c < totalCols - 1; c++) {
      const left = cellAt[r][c];
      const right = cellAt[r][c + 1];
      if (!left || !right) continue;
      if (left === right) continue; // 同 cell（gridSpan）跳過
      const winner = resolveCellEdge(left.props.borders?.right, right.props.borders?.left);
      if (winner) {
        if (!left.props.borders) left.props.borders = {};
        if (!right.props.borders) right.props.borders = {};
        left.props.borders.right = winner;
        right.props.borders.left = winner;
      }
    }
  }

  // 跨列上下相鄰
  for (let r = 0; r < totalRows - 1; r++) {
    for (let c = 0; c < totalCols; c++) {
      const top = cellAt[r][c];
      const bottom = cellAt[r + 1][c];
      if (!top || !bottom) continue;
      if (top === bottom) continue; // vMerge anchor 跨多 row 視為同 cell
      // 若 top 是 vMerge anchor 且 bottom 是 continuation：bottom 不渲染，跳過協調
      if (bottom.isContinuation && bottom === cellAt[r][c]) continue;
      const winner = resolveCellEdge(top.props.borders?.bottom, bottom.props.borders?.top);
      if (winner) {
        if (!top.props.borders) top.props.borders = {};
        if (!bottom.props.borders) bottom.props.borders = {};
        top.props.borders.bottom = winner;
        bottom.props.borders.top = winner;
      }
    }
  }
}
