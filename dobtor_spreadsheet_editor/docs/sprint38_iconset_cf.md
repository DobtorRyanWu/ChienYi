# Sprint 38 — iconSet CF 編譯（Phase 4.1，CF 五型完成）

**日期**：2026-06-08｜**Phase**：4

## 取得結構的方法
o-spreadsheet IconSetRule 結構在 minified bundle 無法 grep；page.evaluate 在未開檔時模組未載入。
改用 o-spreadsheet 18 已知結構**直接實作 + 空驗證迭代**（同 CF 其他型）：一次命中、o-spreadsheet 接受。

## 修法（cf_compiler.ts）
- compileIconSet → o-spreadsheet **IconSetRule**：
  - `icons: {upper:`${fam}Good`, middle:`${fam}Neutral`, lower:`${fam}Bad`}`
  - iconSet 名稱 → family：Arrow→arrow、Symbol/Flag/Rating→smiley、其餘（TrafficLights/Signs）→dot
  - `lower/upperInflectionPoint: {type(cfvo→percentage/number/percentile/formula), value(cfvo.val), operator:'ge'}`
    （3-icon：cfvo[1]=下閾值、cfvo[last]=上閾值；cfvo[0] 最低忽略）
- OConditionalFormat.rule union 加 OIconSetRule

## 三層 SOP
- L1 vitest 通過（openpyxl iconSet 匯入編譯：3TrafficLights→dot、33/67 閾值）
- L2 Playwright（openpyxl iconset.xlsx、D1:D20=5..100、3TrafficLights1）：
  **ICONSET_GRID_MOUNTED errs=none**；**截圖確認紅(<33%)/橙(33-67%)/綠(>67%) 圓點**
- L3 tsc 乾淨、build、docker -u 升級無誤

## CF 五型全部完成 🎉
cellIs（S29）+ containsText（S29）+ colorScale（S34）+ dataBar（S37）+ **iconSet（S38）**。
duplicateValues/expression 無 o-spreadsheet 直接對應（解析保留、匯出 round-trip、但不編譯顯示）。
