# Sprint 26 — 產生的估驗試算表用即時公式（Phase 8）

**日期**：2026-06-08｜**Phase**：8

## Root cause
Sprint 25 產生的試算表是靜態值，改數量不會重算。估驗工作需要會算的表。

## 修法（bridge _build_estimate_workbook_data）
- **H 本次估驗金額 = `=F{r}*G{r}`**（單價 × 本次估驗數量）
- **J 累計估驗金額 = `=F{r}*I{r}`**（單價 × 累計估驗數量）
- 底部**小計列**（粗體）：`H 小計 =SUM(H3:H{last})`、`J 小計 =SUM(J3:J{last})`

## 三層 SOP
- L1：N/A（純 Python）
- L2 Playwright（估驗 33、181 工項）：GENERATE_GRID_MOUNTED、無 #ERROR；
  截圖驗證 H=F×G 即時計算（193.12×408.7=78928.144）、J 同理、小計列
- L3 docker -u 升級無誤

## 結果
| | Sprint 25 | Sprint 26 |
|---|---|---|
| 金額欄 | 靜態值 | **即時公式 F×G / F×I** |
| 小計 | 無 | SUM 公式列 |
| 改數量/單價重算 | ❌ | ✅ |

→ 產生的估驗試算表成為會重算的計算表。
