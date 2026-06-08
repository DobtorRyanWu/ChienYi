# Sprint 42 — MROUND / REPT / SIGN functionRegistry shim（§3.3）

**日期**：2026-06-08｜**Phase**：3

## 修法
- `static/src/spreadsheet_functions/extra_functions.js`（@odoo-module）：
  - **MROUND**(value, factor)：四捨五入到最接近倍數（異號→#NUM!）
  - **REPT**(text, n)：文字重複 n 次（負→#VALUE!）
  - **SIGN**(value)：正負號（Math.sign）
  - addIfMissing 守衛（未來版本內建後不衝突）
- `__manifest__.py`：assets_backend 加入 extra_functions.js
- `to_ospreadsheet.ts`：白名單加 MROUND/REPT/SIGN（→ 餵公式即時運算）

## 三層 SOP
- L1 vitest **629 passed**（CHOOSE/MROUND 餵公式、GEOMEAN→仍 cached）
- L2 Playwright（shim.xlsx）：**SHIM_REGISTERED={MROUND,REPT,SIGN: true} errs=none**；
  **截圖確認 MROUND(10,3)=9、SIGN(-5)=-1、REPT("■",4)=■■■■**
- L3 tsc 乾淨、build、docker -u 升級含 extra_functions.js 無誤

## 結果
o-spreadsheet 18.0.48 未內建的 CHOOSE/MROUND/REPT/SIGN 全數 shim 完成 → 匯入含這些公式的 xlsx 即時運算。
