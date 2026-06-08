# Sprint 31 — Chart 解析（Phase 5.2 / 5.3）

**日期**：2026-06-08｜**Phase**：5

## 修法（解析鏈：worksheet rels → drawing → chart）
- `chart_parser.ts`：chartN.xml（chartSpace）→ ChartAst
  - 類型映射：bar/bar3D→bar、line/area/stock→line、pie/doughnut→pie、scatter/bubble→scatter
  - series：c:ser → categoriesRef(c:cat)/valuesRef(c:val) 的 c:f；排除 #REF!
  - title：c:title>tx>rich 遞迴收 a:t
- `drawing_parser.ts`：drawingN.xml → twoCellAnchor from/to 格座標 + graphicFrame 的 chart r:id
- `chart_compiler.ts`：ChartAst + anchor → o-spreadsheet figure（{id,x,y,width,height,tag:chart,data:{type,title,dataSets,labelRange,legendPosition,…}}）；
  resolveSheetCharts 串全鏈
- `to_ospreadsheet.ts`/`index.ts`：每 sheet 解析 figures（用 rel.resolvedTarget）→ sheet.figures

## 關鍵 bug 修正
- **rel.target vs resolvedTarget**：getRels 回傳的 target 是原始相對路徑（`../drawings/...`），
  resolvedTarget 才是解析後（`xl/drawings/...`）。原用 target → hasPart 失敗 → 無 figure。改用 resolvedTarget。

## 三層 SOP
- L1 vitest **569 passed**（+8：類型映射/series cat-val/#REF! 過濾/title/drawing anchor/chart→figure/真實自檢表匯入產生 figure）
- L2 Playwright（自檢表總表單，bar3D chart）：**CHART_GRID_MOUNTED errs=none**、無 o_error_dialog → o-spreadsheet 接受 figure
- L3 tsc 乾淨、build 通過、docker -u 升級無誤

## 待解
- chart 匯出回 xlsx（Phase 6）；Pivot；圖片/shape import（drawing 只取 chart anchor）；
  axes/legend 細節、strCache 內嵌資料、anchor EMU 精準定位（目前格座標×估算 px）
