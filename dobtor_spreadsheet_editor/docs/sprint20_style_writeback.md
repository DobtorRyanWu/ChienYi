# Sprint 20 — 樣式回寫（高保真匯出，Phase 6）

**日期**：2026-06-07
**Phase**：6（Export 對稱性）
**緣由**：Sprint 19 writer v1 只寫值/結構（minimal styles）；本 sprint 補樣式回寫達高保真匯出。

---

## Root cause

下載的 xlsx 無字型/填色/邊框/數字格式。要高保真 round-trip，需把 ConcreteStyle 反編成 styles.xml
各池（fonts/fills/borders/numFmts/cellXfs），cell 以 `s` index 參照。

## 修法

### `xlsx_writer.ts` — `StyleSheetBuilder`
- 池化反編 ConcreteStyle → styles.xml：
  - `numFmts`：自訂格式配 id 164+；內建（id<164）用原 id
  - `fonts`：bold/italic/strike/underline/sz/color(ARGB)/name/family/charset；index 0 = 預設 Calibri
  - `fills`：index 0=none、1=gray125（Excel 慣例）、2+ = solid（fillBackgroundColor → fgColor ARGB）
  - `borders`：index 0=空、四邊 `style`+`color`
  - `cellXfs`：numFmtId/fontId/fillId/borderId + applyX 旗標 + alignment；index 0 = 預設
- `intern(ConcreteStyle)` → cellXf index（全 0 且無 align → 0）
- `buildXlsx` 用 StyleSheetBuilder，cell 寫 `s` index、styles.xml = `builder.toXml()`

### `index.ts`
- `exportXlsxFromBuffer`：每 cell `wc.style = ConcreteStyleResolver.resolve(cell.styleIndex)`
- 日期：值用原始序號 + 日期 numFmt 回寫 → 匯出檔正確顯示日期

### `worksheet_parser.ts`（關鍵保真修正）
- **空白樣式格也收**（原本只收有值/公式/inline）：邊框/填色/粗體常套在空白格（表格框線），
  不收則匯出缺這些。對 cell value 提取無害（buildValueMap 對空值回 '' 不入 map）；
  範圍受 XML 內實際 `<c>` 數限制（不爆量）。

## 三層 SOP 結果

- **L1 vitest**：**549 passed**（unit 211 + integration 338）
  - `xlsx_writer.test.ts` +2：ConcreteStyle（bold/紅字/黃底/thin+medium 框/置中/`#,##0.00`）→ buildXlsx →
    re-parse → **ConcreteStyleResolver 還原 bold/color/fill/border/align**、自訂 numFmt code 還原
  - 既有提取/corpus 全綠（空白樣式格不影響提取）
- **L2 openpyxl + Playwright + LibreOffice**：
  - export 11309 → **粗體 5 cell（B3:F3 空白粗體格）+ 邊框 333 cell**（修正前 29 → 整張表格框線進來）
  - Playwright：DOWNLOAD_OK 17208B、o-spreadsheet GRID_MOUNTED；下載檔 openpyxl（邊框77/numfmt33/6sheet）+ LibreOffice 開啟 ✓
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過、docker -u 升級+重啟無誤

## 高保真匯出達成

```
xlsx → parser（含空白樣式格）→ ConcreteStyle → StyleSheetBuilder → styles.xml 各池
     → 下載 xlsx（字型/填色/邊框/數字格式 round-trip，openpyxl+LibreOffice 驗證）
```

## 側效益（parser 收空白樣式格）

- **VR / o-spreadsheet 對接同步受益**：bordered 空白格現在也渲染 → 表格框線更完整
  （下載 size 15749→17208、邊框 cell 大增）

## 對齊進度

| 項目 | 狀態 |
|---|---|
| 匯出值/公式/合併/結構 | 🟢（S19） |
| 匯出樣式（font/fill/border/numFmt） | 🟢 本 sprint |
| 日期序號 + 日期 numFmt 顯示 | 🟢（值用序號 + numFmt 回寫） |
| 圖表 / 圖片 / 條件格式回寫 | ⚪ 後續 |

## 負面結果 / 待解

1. **theme/indexed 色已轉具體 RGB 回寫**：邊框/字色經 ConcreteStyle（ThemeResolver）→ ARGB，
   但回寫後為固定 RGB（非 theme 參照）——視覺一致、語意上失去 theme 連動（可接受）。
2. **CF / 圖表 / 圖片未回寫**：writer 只處理 cell 層樣式。
3. **欄寬/列高未回寫**：writer 未寫 `<cols>`/row ht（下載檔用預設寬高）。下一步可補。

## 下一步（Sprint 21）

- 欄寬/列高回寫（`<cols>` + row `ht`）補齊版面保真
- 或持久化 + 與 ChienYi 估驗計價模組整合（Phase 8）
