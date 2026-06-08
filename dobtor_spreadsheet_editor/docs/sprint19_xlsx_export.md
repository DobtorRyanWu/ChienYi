# Sprint 19 — 匯出回 xlsx（Phase 6）

**日期**：2026-06-07
**Phase**：6（Export 對稱性）
**對齊**：規劃書 Phase 6「雙向 xlsx round-trip」

---

## Root cause

匯入 → 可編輯（Sprint 16-18）已成；但缺「寫回 xlsx」。o-spreadsheet 雖內建 `exportXLSX`，
規劃書 Phase 6 要的是**我方 writer**（高保真、不依賴 o-spreadsheet、可 round-trip 驗證）。

## 修法

### `xlsx_writer.ts`
- `buildXlsx(WriteSheet[])` → `Uint8Array`（fflate `zipSync` 打 OOXML）
  - 產 `[Content_Types].xml` / `_rels/.rels` / `xl/workbook.xml`(+rels) / `xl/sharedStrings.xml` /
    `xl/styles.xml`(minimal + cellStyles Normal) / `xl/worksheets/sheetN.xml`
  - cell 編碼：number `<v>`、string sharedString `t="s"`、boolean `t="b"`、
    **公式 `<f>`+cached `<v>`**（string 結果 `t="str"`）；XML escape
  - 合併儲存格、多工作表、依列分組、dimension 計算

### `index.ts`
- `exportXlsxFromBuffer(buffer)`：parse xlsx → 每 sheet WriteCell（值用**原始 resolveCellValue**
  保型別、含 formula）→ buildXlsx

### OWL（`xlsx_import.js/xml`）
- 「**下載 xlsx（重新匯出）**」按鈕 → `exportXlsxFromBuffer` → Blob → `<a download>` 觸發下載

## 三層 SOP 結果

- **L1 vitest**：**547 passed**（unit 209 + integration 338）
  - `xlsx_writer.test.ts`（4）：合法 xlsx（PackageReader 可開）、值 round-trip（string/number/bool/formula）、
    合併、XML escape
  - `xlsx_roundtrip.test.ts`（4）：3 真實 fixture **parse→writer→re-parse 值一致率 >99.9%**、
    多 sheet 名一致、公式保留（變更金額分析 >50 公式）
- **L2 Playwright E2E**：上傳 → 點「下載 xlsx」→ `DOWNLOAD_OK ..._roundtrip.xlsx size=13438`
  - 下載檔三方驗證：**我方 parser ✓ / openpyxl ✓（sheets+值正確）/ LibreOffice ✓（轉 CSV 成功）**
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過、docker -u 升級+重啟無誤

## 雙向 round-trip 達成

```
xlsx → [parser + 樣式 + 公式] → 可編輯 o-spreadsheet（Sprint 16-18）
xlsx → [exportXlsxFromBuffer] → xlsx（openpyxl/LibreOffice/我方 parser 皆可開）← Sprint 19
```

## 對齊進度

| 項目 | 狀態 |
|---|---|
| 匯入（值/樣式/公式/合併/邊框） | 🟢 |
| 匯出 xlsx（值/公式/合併/多sheet/sharedStrings） | 🟢 本 sprint |
| 匯出**樣式回寫**（font/fill/border/numFmt → styles.xml 池） | ⚪ 待續 |
| 從**編輯後**的 o-spreadsheet 匯出 | 🟢（o-spreadsheet 原生 exportXLSX、OCA 編輯器內） |

## 負面結果 / 待解（紀律 #4）

1. **樣式未回寫**：writer v1 只寫值/公式/合併/結構，styles.xml 為 minimal（單一預設 xf）→ 下載檔無
   字型/填色/邊框/數字格式。高保真匯出需把 ConcreteStyle 反編成 styles.xml 各池（fonts/fills/borders/
   cellXfs/numFmts），為下一 sprint。
2. **日期序號**：值用原始 resolveCellValue（數字/序號），未寫 numFmt → 下載檔日期顯示為序號。樣式回寫時一併補。
3. **「下載 xlsx」是重新匯出原始解析**：非匯出編輯後內容；編輯後匯出走 o-spreadsheet 原生 exportXLSX。

## 下一步（Sprint 20）

- **樣式回寫**：ConcreteStyle/ParsedStyles → styles.xml 各池（含 numFmt 日期）→ 高保真匯出 round-trip
- 或持久化 + ChienYi 估驗計價模組整合（Phase 8）
