# Sprint 9 — CFParser（條件格式，§1.7）

**日期**：2026-06-07
**Phase**：1 §1.7（Conditional Formatting）
**對齊**：規劃書 §1.7 Conditional Formatting

---

## Root cause（開工前假設）

§1.5 已解析 dxfs（CF 用的 differential format），§2.2 已能解 dxf 內的色，但 CF **規則本體**（哪個範圍、
什麼條件、套哪個 dxf）尚未解析——規則在 worksheet XML 的 `<conditionalFormatting>`。沒有它，CF 無法重建。
假設：解析 cfRule 各型別 + sqref 範圍 + dxfId 連結即可。

## 修法（實際做的事）

### `cf_parser.ts`（§1.7）
- `parseConditionalFormattings(ws)`：從已解析 worksheet 節點取 `<conditionalFormatting>` → `ConditionalFormatting[]`
  （sqref 拆多段 ranges + cfRule 清單），**整合進 WorksheetParser 單次解析**（ParsedWorksheet.conditionalFormatting）
- `CFParser.parse(xmlText)`：獨立解析（測試用）
- 規則涵蓋：
  - **cellIs**（operator + 1-2 個 formula）、**expression**（1 formula）、**duplicateValues/uniqueValues**（無 formula）
  - **containsText 系列**（text 屬性）、**top10**（percent/rank/bottom）、timePeriod、stopIfTrue
  - **colorScale**（cfvo[] + colors[]）、**dataBar**（cfvo + color + min/maxLength + showValue）、
    **iconSet**（iconSet 名 + cfvo[] + reverse + showValue）
  - 每規則保留 dxfId（→ styles.dxfs）+ priority

## 三層 SOP 結果

- **L1 vitest**：**436 passed**（unit 153 + integration 283）
  - `cf_parser.test.ts`（14）：合成涵蓋全 9 種規則型別（cellIs equal/between、expression、duplicateValues、
    containsText、top10、colorScale 2 色、dataBar、iconSet 3 cfvo+reverse）+ sqref 多段拆分
    + **真實土單**（cellIs 狀態色、dxfId 有定義、WorksheetParser 已整合 CF 欄位）
  - `cf_corpus.test.ts`（48）：**全 48 fixture** CF 解析無誤、sqref 非空、**每規則 dxfId 指向有效 dxfs 索引**
- **L2 visual regression**：N/A
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（13.3s）

## 實檔分布（紀律 #4）

全 corpus cfRule 型別實測：**cellIs ×9、duplicateValues ×9、expression ×4**；
**colorScale / dataBar / iconSet ×0**（ChienYi 營造文件不用，與 fixture 收集時的發現一致）。
→ 富類型（colorScale/dataBar/iconSet）僅由合成測試覆蓋；真實連結驗證走 cellIs/expression/duplicateValues。

## 設計取捨

1. **CF 整合進 WorksheetParser**：避免為 CF 二次解析大 worksheet（65k cell），單次 parse 同時產出
   cells + merges + CF。`parseConditionalFormattings` 拆成獨立函式維持可測性。
2. **type 用 string 而非嚴格 union**：CF 規則型別多且各版本 Excel 可能新增，用 string 保前向相容、
   不因未知型別崩潰。
3. **不解 cfvo 的 formula 語意**：cfvo.val 存原始字串（min/max 無 val、num/percentile 有），
   公式求值待 Phase 3。

## 對齊 Phase 進度

| 項目 | 狀態 |
|---|---|
| §1.5 dxfs 解析 | 🟢（Sprint 5） |
| §1.7 CFParser（規則本體） | 🟢 本 sprint |
| CF 渲染（dxf 套用 + colorScale/dataBar/iconSet 繪製） | ⚪ Phase 4 |

## 負面結果 / 待解

1. **CF 公式未求值**：cellIs/expression 的 formula 存原始字串，實際命中與否需公式引擎（Phase 3）。
2. **colorScale/dataBar/iconSet 無真實樣本**：僅合成驗證解析；真實渲染正確性待日後補通用 fixture（Sprint 2 待辦）。

## 下一步（Sprint 10）

可選：§1.8 DataValidations（資料驗證 list/whole/custom）、§1.11 Tables（Excel Table 物件）、
或整合 StyleResolver+ThemeResolver → ConcreteStyle 對接層（Phase 4.5 餵 o-spreadsheet 前置）。
