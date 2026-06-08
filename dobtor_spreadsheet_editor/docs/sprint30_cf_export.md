# Sprint 30 — CF 匯出回 xlsx（Phase 6 §6.2）

**日期**：2026-06-08｜**Phase**：6

## Root cause
Sprint 29 把 CF 編譯進可編輯 o-spreadsheet（單向）。但 exportXlsxFromBuffer 匯出時不寫 CF
——CF 無法 round-trip 回 xlsx。本 sprint 補匯出。

## 修法
- 新 `cf_writer.ts`：
  - `writeConditionalFormattings(blocks)`：ConditionalFormatting[] → `<conditionalFormatting sqref><cfRule .../>`
    （type/operator/dxfId/priority/text/percent/rank/stopIfTrue + formulas + colorScale/dataBar/iconSet 子元素）
  - `writeDxfs(dxfs)`：Dxf[] → `<dxfs>`（font/fill/border + color 序列化；保留原索引，cfRule.dxfId 仍有效）
- `xlsx_writer.ts`：WriteSheet 加 conditionalFormats；sheetXml 在 mergeCells 後寫 CF；
  StyleSheetBuilder.toXml 在 cellStyles 後寫 `<dxfs>`；buildXlsx 收 opts.dxfs
- `index.ts`：exportXlsxFromBuffer 每 sheet 帶 ws.conditionalFormatting + buildXlsx 帶 styles.dxfs

## 三層 SOP
- L1 vitest **561 passed**（+3：CF 序列化重解析、dxfs font/fill 重解析、真實土單匯出含 CF+dxfs）
- L2 openpyxl：匯出土單 → **讀到 2 個 CF 範圍**；LibreOffice 開啟無損毀
- L3 tsc 乾淨、build 通過

## 結果
| | 前 | 後 |
|---|---|---|
| CF 匯出 | 不寫 | **conditionalFormatting + dxfs 回寫，openpyxl/LibreOffice 可讀** |

CF 雙向完成：xlsx → 解析 → 編譯到 o-spreadsheet（S29）→ 匯出回 xlsx（S30）。

## 待解
- colorScale/dataBar/iconSet 雖會序列化回 xlsx（解析保留），但 o-spreadsheet 編譯端尚未支援（S29 待解）
- theme1.xml 未重生成（dxf theme 色彩以原 theme 索引寫回）
