# Sprint 47 — zip bomb / 上傳大小防護（§4.5.4）

**日期**：2026-06-09｜**Phase**：4.5

## 修法（不可信上傳防禦；具名常數）
- `package_reader.ts` PackageReader.fromBuffer：
  - 壓縮輸入 > **30MB** → 丟錯（unzip 前先擋）
  - part 數 > **8000** → 丟錯（海量 entry）
  - 解壓總大小 > **300MB** → 丟錯（**zip bomb** 防護）
  - file magic check：缺 `[Content_Types].xml` → 丟錯（既有）
- `xlsx_import.js` onFile：前端 file.size > **30MB** → 早期拒絕（不浪費讀取）

## 三層 SOP
- L1 vitest **658 passed**（+3 package_guard：壓縮過大丟錯、非 zip 丟錯、最大旗艦檔正常解析）
- L2 Playwright：正常上傳無回歸（GRID_MOUNTED + DOWNLOAD_OK）；損壞檔友善錯誤（S46）
- L3 tsc/build/升級無誤
- 安全餘裕：最大真實檔（契約詳細表）僅 2.3MB 壓縮 → 30MB 限制有 13× 餘裕

## §4.5.4 完成度
zip bomb / upload size / magic check / 異常處理（S46）皆完成；OCA raw XML fallback 仍待做。
