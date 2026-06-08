# Sprint 33 — 公式 shim（CHOOSE）+ 白名單擴充（Phase 3.2/3.3）

**日期**：2026-06-08｜**Phase**：3

## 發現
word-boundary 掃 o_spreadsheet.js：S18 白名單（45 函數）**過度保守**，多數函數其實已內建
（IFERROR/SUMIFS/VLOOKUP/INDEX/MATCH/OFFSET/INDIRECT/SUMPRODUCT/RANK/EOMONTH/DATEDIF… 都有），
被誤擋成 cached。**真正缺的只有 CHOOSE / MROUND / REPT / SIGN**。

## 修法
- **CHOOSE shim**：`static/src/spreadsheet_functions/choose.js`（`/** @odoo-module **/`，
  `functionRegistry.add("CHOOSE", {...})`，比照 spreadsheet/currency/formulas.js 模式）；掛 web.assets_backend
- **白名單擴充**（to_ospreadsheet.ts SUPPORTED_FUNCTIONS）：45 → ~90 函數（全 word-boundary 確認 + CHOOSE）；
  仍排除 MROUND/REPT/SIGN（確認未內建 → 走 cached）

## 三層 SOP
- L1 vitest **571 passed**（CHOOSE→餵公式即時運算、MROUND→cached fallback）
- L2 Playwright：開 o-spreadsheet 後 **functionRegistry.content.CHOOSE 存在（CHOOSE_REGISTERED=true）**；
  含 CHOOSE 公式 xlsx 匯入開啟 errs=none、無 o_error_dialog
- L3 tsc 乾淨、build、docker -u 含 choose.js 升級無誤

## 結果
| | 前 | 後 |
|---|---|---|
| 支援函數 | 45（過度保守、多誤擋） | ~90（確認內建）+ CHOOSE shim |
| CHOOSE | cached 靜態值 | **即時運算** |

## 待解
- MROUND/REPT/SIGN shim（同 CHOOSE 模式可補）；R1C1/structured ref/array formula（§3.2）
