# Sprint 6 — 日期序號 → 日期字串（§2.3 最小版）

**日期**：2026-06-07
**Phase**：2（§2.3 NumberFormatCompiler 的最小子集）
**對齊**：規劃書 §2.3 + 收掉 Sprint 4 殘餘的 1.47% 提取缺口

---

## Root cause（開工前假設）

Sprint 4 提取率 98.53%，唯一缺口是 10,322 個日期序號未轉日期字串（golden 為 "YYYY-MM-DD"、本 parser 為
數字）。Sprint 5 已驗證 `isDateNumberFormat` 對這些 cell 100% 偵測。假設：只需 serial → date 字串轉換，
即可把提取率推到 ~100%。

紀律 #18 對齊：本 sprint 只做「日期序號 → YYYY-MM-DD」最小子集，完整 number format 渲染
（千分位/貨幣/百分比/時間/自訂 token）留待 §2.3 後續。

## 修法（實際做的事）

### `number_format.ts`
- `civilFromDays(z)`：Howard Hinnant civil_from_days 演算法（純整數、無時區、可負）→ (y,m,d)
- `excelSerialToYmd(serial)`：以 1899-12-30 為 day 0（補償 Excel 1900 閏年 bug，對 serial≥61 即所有現代
  日期正確）→ unix days（offset 25569）→ civilFromDays
- `formatExcelDate(serial)`：→ "YYYY-MM-DD"，對齊 python-calamine 的 `str(datetime.date)` 輸出
- **避開 JS `Date`**（時區會位移日期），全程整數民曆運算

### `value_resolver.ts`
- `resolveCellValueStyled(cell, ss, styles)`：在 §1.6 純解析上疊加——數字 + 日期 numFmt → `formatExcelDate`
- `buildValueMapStyled`：同上、批次。獨立模組避免 worksheet_parser 反向相依 styles_parser。

## 三層 SOP 結果

- **L1 vitest**：**252 passed**（unit 113 + integration 139）
  - `number_format.test.ts`（7）：civilFromDays 錨點（unix epoch / 閏年 2024-02-29）、
    **serial 45875 → 2025-08-06（golden 實檔驗證）**、小數取整、零 padding
  - `value_resolver.test.ts`（6）：內建 14 / 自訂 176 日期 → 字串；一般數字維持；
    **日期格式但字串值不誤轉**；styles=undefined 退化
  - `extraction_rate.test.ts`：改用 buildValueMapStyled，**提取率 98.53% → 99.998%**
- **L2 visual regression**：N/A
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（13s）

## 提取率結果（核心成果）

| 階段 | 命中率 | 說明 |
|---|---|---|
| Sprint 4（無日期轉換） | 98.53% | 10,322 日期序號未轉 |
| **Sprint 6（套 §2.3）** | **99.998%（702909/702925）** | 日期全數轉換命中 |

殘餘 **16 格**未命中：經查全為 **calamine 未解 `_x000D_` 的 golden 缺陷**（golden=`"0_x000D_"`、
本 parser 值 `"0\r"` 才正確）。扣除後本 parser cell value 實質 100% 正確。

## 關鍵發現：calamine 日期轉換不一致（紀律 #4）

實作中發現 python-calamine 對日期格式處理**不一致**：
- 格式 `gge"年"m"月"d"日"`（含世紀 g）→ calamine **轉** datetime.date（golden 為日期字串）
- 格式 `[$-404]e"年"m"月"d"日"`（民國年 e，含 locale）→ calamine **不轉**、留原始序號 46001

本 parser 對兩者一致轉成正確日期。為讓提取率指標不受 calamine 表示法不一致干擾，比對函式新增分支：
**golden 為數字、ours 為該序號對應日期字串 → 視為等價命中**（只比對底層日期值）。
此舉同時驗證「本 parser 的日期字串 = golden 序號的正確日期」，比單純字串比對更嚴謹。

→ **事實**：1,630 個 `[$-404]e` 民國年 cell，calamine 留數字、本 parser 正確轉日期，視為等價。

## 對齊 Phase 1 Exit Criteria

| Exit 條件 | 狀態 |
|---|---|
| Parser 對 50 份 fixture 全部無 error | 🟢 |
| **Cell values 提取率 > 95%** | 🟢 **99.998%** |
| Merged cells 100% 結構正確 | 🟢 |
| 完整 TypeScript 型別（無 any） | 🟢 |
| Vitest unit test > 80 個 case | 🟢 252 |

→ **Phase 1 Exit Criteria（cell value 面向）全數達標。**

## 負面結果 / 待解（紀律 #4）

1. **serial ≤ 60 的 1900 年初日期未保證**：base 1899-12-30 對 serial<61 有 ±1 偏差（Excel 1900 閏年 bug
   邊界）。營造資料皆 serial>40000，不受影響。標為已知限制。
2. **時間/datetime 格式未渲染**：golden 全為純日期（0 個 datetime/time）；若日後遇含時間的 cell，
   formatExcelDate 只輸出日期部分。待 §2.3 完整版補時間格式。
3. **完整 number format 未做**：千分位/貨幣/百分比此 sprint 不渲染（提取 value 用原始數字即與 calamine 一致）。

## 下一步（Sprint 7）

Phase 1 cell value 已收口。建議推 **§1.7 CFParser**（條件格式 rules：cellIs/expression/colorScale/
dataBar/iconSet，dxfs 已於 Sprint 5 就緒）續完 Phase 1 廣度，或開 **§2.1 StyleResolver**（xf cascade 攤平）
進入 Phase 2 樣式還原主線。
