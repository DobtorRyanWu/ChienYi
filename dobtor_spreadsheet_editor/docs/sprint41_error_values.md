# Sprint 41 — 公式錯誤值保真（§3.5）

**日期**：2026-06-08｜**Phase**：3

## 緣由
ChienYi 大量錯誤格（土單 2595、管制表 95-109、B標 127）。原本 error 公式格會餵公式讓
o-spreadsheet 重算，可能漂移成不同結果或 #BAD_EXPR，失去原始錯誤值。

## 修法（to_ospreadsheet.ts）
- cell.type === 'e'（錯誤格）→ **不餵公式**，改用 cached 錯誤字串（resolveCellValueStyled 回 raw，如 #N/A/#REF!）
  → 保留 Excel 原始錯誤值原貌。非錯誤格維持原「安全公式→即時運算」邏輯。

## 三層 SOP
- L1 vitest **629 passed**（+2：錯誤公式格→cached #N/A、靜態錯誤格→#REF!）
- L2 既有 Playwright（土單 2595 錯誤格）匯入開啟 errs=none（先前已驗證）
- L3 tsc 乾淨、build、docker -u 升級無誤

## 結果
錯誤格在可編輯試算表顯示與 Excel 一致的錯誤值（#N/A/#REF!/#DIV/0! 等），不因重算漂移。
