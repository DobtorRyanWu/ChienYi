# Sprint 40 — Shared formula 展開（§1.6 capture → §3.2 expand）

**日期**：2026-06-08｜**Phase**：1 / 3

## 緣由（高真實價值）
ChienYi 大量用 OOXML shared formula 壓縮重複公式：契約詳細表單檔 **62,286 個** follower
（`<f t="shared" si="0"/>` 無公式文字）。原本只 capture 不展開 → 數萬公式在可編輯表只有 cached 值。

## 修法
- `shared_formula.ts`：
  - `adjustRelativeRefs(formula, dRow, dCol)`：A1 參照依位移調整（$ 絕對部分不動；後接 "(" 的函數名、
    前接英數的識別字片段不誤判；出界保留）
  - `expandSharedFormulas(cells)`：建 si→master(有公式)；follower(有 si 無公式)依 (row-,col-) 位移還原
- `worksheet_parser.ts`：parseCell 捕捉 `t="shared"` 的 si（Cell.sharedSi）；parse 末呼叫 expandSharedFormulas

## 連帶修：entity 展開上限
展開後匯出檔變大、re-parse 時 escaped & 跨檔逾 1000 → fast-xml-parser「Entity expansion limit exceeded」。
可信 xlsx 無 DoS 疑慮 → xml_util 兩 parser config 設 `processEntities:{maxTotalExpansions:Infinity}`。

## 三層 SOP
- L1 vitest **627 passed**（+9：adjustRelativeRefs 列/欄/絕對/函數名/出界、expandSharedFormulas master/follower）；提取率 99.998% 不回歸
- L2 整合：契約詳細表展開後公式 cell **65,548**；災後動員統計表 772 shared cells **全數展開**；
  Playwright SHAREDF_GRID_MOUNTED errs=none（o-spreadsheet 即時運算無 #BAD_EXPR）
- L3 tsc 乾淨、build、docker -u 升級無誤

## 影響
ChienYi 契約/數量計算表的數萬重複公式從「靜態 cached」變成「即時運算」——改數量自動重算整張表。
