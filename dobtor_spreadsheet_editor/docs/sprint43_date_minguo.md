# Sprint 43 — 日期格式碼 / 民國年顯示渲染（§2.3）

**日期**：2026-06-08｜**Phase**：2

## 緣由
ChienYi 大量用**民國年**日期格式（`[$-404]e"年"m"月"d"日"` 26、`[$-404]e/m/d` 6、`gge` 3…）。
原本日期格一律顯示 ISO（2025-12-10），失去 Excel 原貌（114年12月10日）。

## 修法（僅顯示路徑，提取/golden 不變）
- `number_format.ts`：`formatExcelDateByCode(serial,code)` / `formatYmdByCode(ymd,code)`
  - token：yyyy/yy（西元）、**e/ee（民國年 = y−1911）**、**gg/g（→「民國」）**、m/mm（月）、d/dd（日）、
    "字面"/\跳脫/其餘字元原樣；去 [$-xxx] locale、取 ';' 前第一段；非日期回 undefined
- `to_ospreadsheet.ts`（可編輯）：日期格 → 以 cell.raw 序號 + 格式碼覆蓋 ISO 顯示
- `vr/html_render.ts`（預覽）：raw 已是 ISO 字串 → 解回 ymd → formatYmdByCode（預覽與編輯一致）

## 三層 SOP
- L1 vitest **643 passed**（+7 date_format：民國 e/ee/gg、西元、m月d日、非日期）；提取率 **99.998% 不變**
- L2 整合：真實「新增單價議定書」匯入 → **114年12月10日**；
  Playwright **PREVIEW_MINGUO_COUNT=1 + MINGUO_GRID_MOUNTED errs=none**；**截圖確認 row5「議價日期 114年12月10日」**
- L3 tsc 乾淨、build、docker -u 升級無誤

## 結果
ChienYi 民國年日期在預覽與可編輯試算表皆顯示原貌（114年12月10日 / 114/12/15 / 民國114年…）。

## 待解
- 時間 token（hh/mm/ss/AM-PM）、條件色彩 [Red]、月名 mmm/mmmm（ChienYi 用 CJK 字面、罕用英文月名）
