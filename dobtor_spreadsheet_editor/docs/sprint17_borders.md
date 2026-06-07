# Sprint 17 — 邊框對接 o-spreadsheet（Phase 4.5）

**日期**：2026-06-07
**Phase**：4.5（產品化）
**緣由**：Sprint 16 邊框 v1 暫不輸出（怕形狀猜錯 throw）；有 Playwright dogfood 後可安全驗證、補上。

---

## Root cause

營造表格（估驗表/契約表）都是重邊框網格。Sprint 16 的 o-spreadsheet 對接略過邊框，
可編輯網格少了表格框線。本 sprint 補邊框——關鍵是確認 o-spreadsheet 邊框正規化形狀，
並用 Playwright 實證渲染。

## 調查（o-spreadsheet 邊框形狀）

從 o_spreadsheet.js 確認：
- `borderStyles = ["thin", "medium", "thick", "dashed", "dotted"]`
- 邊框描述子為**物件** `{ style, color }`（`.style`/`.color` 屬性存取，非 tuple；`["thin",` 僅是 enum）
- 正規化 `borders` 池：id → `{ top?, bottom?, left?, right? }`，cell 以 `border` id 參照

## 修法（`to_ospreadsheet.ts`）

- `OBorderDescr { style, color }` / `OBorder { top?,bottom?,left?,right? }`、`OCell.border?: number`
- `BORDER_STYLE_MAP`：Excel style → o-spreadsheet 5 style
  （hair→thin、mediumDashed/DashDot→medium、**double→medium**、dashDot/slantDashDot→dashed…）
- `toOBorder(ConcreteBorder)`：每邊 `{style, color:'#'+hex(預設 #000000)}`、空邊框回 undefined
- border 池化（與 styles/formats 同 Pool 去重）、`data.borders = borderPool.toRecord()`
- cell 收錄條件加 border（有邊框但無值/樣式的格也收）

## 三層 SOP 結果

- **L1 vitest**：**535 passed**（unit 201 + integration 334）
  - `to_ospreadsheet.test.ts` +1：cell.border id 參照、池內 `{style,color}` 物件、
    thin/medium/thin/**double→medium** 映射
- **L2 Playwright E2E**：`admin-dobtor-spreadsheet-xlsx.spec.ts` 重跑 → `OPEN_RESULT=GRID_MOUNTED`
  - 截圖 `sse-02-editable.png`：**標題框 + 表格區邊框框線渲染**（對比 Sprint 16 無邊框）、無 #ERROR、無 throw
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過、docker -u 升級+重啟無誤

## 驗證對比

| | Sprint 16 | Sprint 17 |
|---|---|---|
| o-spreadsheet grid | ✅ 掛起 | ✅ 掛起 |
| 值 / 樣式 / 合併 | ✅ | ✅ |
| **邊框** | ❌ 無 | ✅ **渲染**（標題框 + 表格框線） |
| #ERROR | 0（S16 修自訂格式後） | 0 |

## 對齊進度

| 項目 | 狀態 |
|---|---|
| xlsx → o-spreadsheet（值/樣式/格式/合併/欄寬） | 🟢（S16） |
| 邊框 | 🟢 本 sprint |
| 公式 round-trip | ⚪ Phase 3 |
| 匯出回 xlsx（openpyxl） | ⚪ Phase 6 |
| 持久化 / ChienYi 業務模組整合 | ⚪ Phase 8 |

## 負面結果 / 待解

1. **double 邊框降級 medium**：o-spreadsheet 無 double style。影響估驗表少數雙線框（視覺近似）。
2. **diagonal 邊框未輸出**：o-spreadsheet 基本 border 僅四邊。
3. **邊框色未驗證精確度**：多為 auto（→#000000），theme/indexed 邊框色已走 ThemeResolver，未逐一像素比對。

## 下一步（Sprint 18）

- 公式 round-trip（feed 公式而非 cached 值，需先盤 o-spreadsheet 函數覆蓋率、缺的做 shim）
- 或匯出回 xlsx（Phase 6, openpyxl）/ 持久化整合
