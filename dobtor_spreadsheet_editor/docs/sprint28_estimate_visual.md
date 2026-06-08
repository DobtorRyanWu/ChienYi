# Sprint 28 — 估驗表視覺強化（表頭填色/右對齊/凍結）（Phase 8）

**日期**：2026-06-08｜**Phase**：8

## 修法（bridge _build_estimate_workbook_data）
- styles 擴充：
  - 2 表頭 {bold, align center, fillColor #D9E1F2 淺藍}
  - 3 數字右對齊 {align right}（套 D-J 資料）
  - 4 小計標籤 {bold, fillColor #FCE4D6 淺橘}、5 小計數字 {bold, align right, fill}
- **凍結窗格**：sheet `panes: {xSplit: 0, ySplit: 2}`（標題+表頭兩列固定，o_spreadsheet.js 確認 xSplit/ySplit 結構）

## 三層 SOP
- L1：N/A（純 Python）
- L2 Playwright（估驗 33）：GENERATE_GRID_MOUNTED（styles/panes 被 o-spreadsheet load 接受、無 #ERROR/crash）
- L3 docker -u 升級無誤

## 結果
181 列估驗表：表頭淺藍粗體置中、數字千分位右對齊、小計淺橘、卷動時標題+表頭固定。
（截圖渲染較小、視覺細節難逐一辨識；GRID_MOUNTED + 合法 o-spreadsheet 結構為證。）
