# Sprint 32 — Chart 匯出回 xlsx（直通，Phase 6 §6.2）

**日期**：2026-06-08｜**Phase**：6

## 做法：原始 DrawingML parts 直通複製（最高保真）
exportXlsxFromBuffer 重建 xlsx 時，把原始圖表保留：
- `xlsx_writer.buildXlsx` opts 加 `rawParts`（xl/drawings、xl/charts、xl/media + _rels 逐位元組複製）、
  `extraOverrides`/`extraDefaults`（Content_Types 片段）；WriteSheet.drawingTarget → 重建 worksheet→drawing rel + `<drawing r:id="rId1"/>`
- `index.exportXlsxFromBuffer`：收集 xl/(drawings|charts|media)/* parts、從原 Content_Types regex 抽 chart/drawing Override + 圖片 Default、每 sheet 設 drawingTarget（rel.resolvedTarget）

## 三層 SOP
- L1 vitest **570 passed**（+1：匯出檔自家 re-parse 仍得 chart figure）
- L2 openpyxl：匯出自檢表 → **chart 物件數 1**（chart1/style1/colors1 + drawings + worksheet rels 齊全）；LibreOffice 開啟 ✓
- L3 tsc 乾淨、build 通過

## 結果
chart 雙向：xlsx → 解析 figure（S31）→ 匯出保留原始 chart parts（S32）。
**附帶**：圖片（drawing2/media）也一併直通保留。

## 待解
- 編輯後的 chart（o-spreadsheet 改資料範圍）尚不回寫（目前直通原始，不反映編輯）；
  Pivot；theme1.xml 重生成
