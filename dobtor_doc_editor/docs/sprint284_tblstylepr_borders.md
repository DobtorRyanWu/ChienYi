# Sprint 284 — Phase 1 optional bucket 3/6：`<w:tblStylePr>` row + border 條件樣式 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A、開 borders defer

**日期**：2026-05-26（週二）
**類型**：Strategy A production code 擴張 / 紀律 #18 scope-down
**規畫書對應**：§Phase 1 §1.7 tblStylePr 條件樣式 / borders
**前置**：Sprint 283 tcFitText audit（Phase 1 optional bucket 2/6）

User 指令：「**tblStylePr row+border 條件樣式**」。本 sprint = 3/6。

---

## Gap 揭發 + 修復

Sprint 131 註明（types.ts:943）：「**`w:tcBorders`（需與 BorderConflictResolver
互動、複雜度高）defer to future sprint**」。User 指定要開 borders → 本 sprint。

### 修改前狀態（Sprint 131 後）

| 條件樣式 cell-level prop | 已實作 | 缺 |
|---|---|---|
| `w:shd` (shading) | ✓ | — |
| `w:vAlign` | ✓ | — |
| **`w:tcBorders`** | ✗ | **defer 註明** |
| `w:tcMar` (margins) | ✗ | defer |
| `w:noWrap` / `w:textDirection` | ✗ | defer |

### 修改後（Sprint 284）

`w:tcBorders` 全 6 side（top/bottom/left/right/insideH/insideV）開通。

---

## 修法（~75 行跨 3 檔）

### 1. AST `types.ts:947` 擴 TableConditionalCellProps

```typescript
export interface TableConditionalCellProps {
  shading?: { fill?: HexColor; color?: HexColor; pattern?: string };
  vAlign?: 'top' | 'center' | 'bottom';
  /** Sprint 284：`<w:tcBorders>` 條件邊框（OOXML §17.4.66） */
  borders?: CellBorders;
}
```

### 2. `StyleResolver.parseConditionalTcPr` + inline 新 helper

```typescript
const bordersEl = directChild(tcPr, 'w:tcBorders');
if (bordersEl) {
  const borders = parseConditionalCellBorders(bordersEl);
  if (borders) out.borders = borders;
}
// ...
if (!out.shading && !out.vAlign && !out.borders) return undefined;

function parseConditionalCellBorders(el: Element): CellBorders | undefined {
  // 走 6 個 side，含 w:start ↔ w:left / w:end ↔ w:right alias
  // 全空 → return undefined（紀律 #21）
}
```

為何 inline 不 import TableParser 的 parseCellBorders：避免 styles ↔ table
模組循環、與 borderShading.parseParagraphBorders 同模式。

### 3. `TableStyleApplicator` per-side merge + apply

```typescript
// mergeCellConditionalProps：per-side 合併（base + overlay）
if (overlay.borders) {
  out.borders = { ...(base.borders ?? {}), ...overlay.borders };
}

// applyConditionalCellProps：explicit cell border 優先、per-side 補入
if (effC.borders) {
  if (cell.props.borders === undefined) cell.props.borders = {};
  const target = cell.props.borders;
  for (const side of ['top', 'bottom', 'left', 'right', 'insideH', 'insideV'] as const) {
    if (effC.borders[side] && target[side] === undefined) {
      target[side] = { ...effC.borders[side] };
    }
  }
  if (Object.keys(target).length === 0) delete cell.props.borders;
}

// 條件 effC 包含 borders 時也觸發 apply
if (effC.shading || effC.vAlign || effC.borders) {
  applyConditionalCellProps(cell, effC);
}
```

---

## 10 unit test 場景

### StyleResolver 端（5 案）

| Test | 驗證 |
|---|---|
| firstRow + top + bottom | borders 兩 side 正確讀、widthPt 對齊 sz/8 換算 |
| lastRow + left + right + insideH 三 side | 全讀、未指定 side undefined |
| `w:start` / `w:end` alias → left / right | OOXML alias 支援 |
| 全空 `<w:tcBorders/>` | cProps.borders undefined、tblStylePr 整體不掛 conditional（紀律 #21） |
| shading + borders 並存 | 兩 key 同 cProps、互不影響 |

### TableStyleApplicator 端（5 案）

| Test | 驗證 |
|---|---|
| firstRow + borders.top → 第一列 cell.props.borders.top 寫入 | 非首列不套 |
| lastRow + borders.bottom → 末列寫入 | row 0/1 不影響 |
| band1Horz + borders.insideH → odd band 套用、even / firstRow 不套 | banding 邏輯正確 |
| Explicit cell border 優先：條件 top + explicit top → 保留 explicit | 紀律 #21 explicit-first |
| Per-side 補入：explicit top + 條件 top+bottom → top 保留、bottom 補入 | atomic-per-side、不 all-or-none |

**10/10 passed / 17ms**。

---

## 與 BorderConflictResolver 互動

紀律 #21：BorderConflictResolver 之後續 pass 不變、條件 borders 視為 cell
explicit borders 進入解析。Sprint 219 BorderConflictResolver 對相鄰 cell 邊框
衝突的處理（top-of-cell vs bottom-of-cell-above）會在 cell.props.borders 已
填好後跑、條件 borders 在這之前完成寫入、行為一致。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：production code 擴張 ~75 行 跨 3 檔 | ✅ |
| #14.b clean scope：commit 含 3 production code 檔 + 1 unit test + 1 doc | ✅ |
| #18 scope-down：不擴張 tcMar / noWrap / textDirection（continue defer） | ✅ |
| #21 explicit-first per-side：cell.props.borders 已存在的 side 不被條件覆蓋 | ✅ |
| #22 verify：10/10 unit test、含 explicit-first 驗證為硬數據 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 284

**Phase 1 optional bucket 3/6 完成（tblStylePr row+border 條件樣式）**。

vitest 2127 → 2137 hypothesis（+10 unit test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增。

剩餘 Phase 1 optional bucket 3/6：
- Sprint 285：lvlOverride（清單覆寫）
- Sprint 286：effectExtent（DrawingML 效果範圍）
- Sprint 287：wp:anchor 完整

**STOP for user review**（user 指令「跑完停下叫我 review」）。等 user 確認後
再啟動 Sprint 285。
