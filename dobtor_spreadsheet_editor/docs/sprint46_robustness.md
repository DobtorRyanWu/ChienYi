# Sprint 46 — 穩健性掃描 + 損壞檔處理（§4.5.4）

**日期**：2026-06-09｜**Phase**：4.5

## 內容
部署前穩健性驗證：①全 fixture 兩條路徑無丟錯 ②損壞輸入優雅降級。

## 修法 / 驗證
- 新 `tests/integration/robustness.test.ts`（永久回歸守門）：
  - 48 fixture 經 importXlsxToOSpreadsheetData + importXlsxToHtmlPreview **全部不丟錯**、
    每 cell 的 style/border id 指向有效池項
  - 損壞輸入（非 zip）→ 兩 API **乾淨丟 Error**（供 OWL try/catch）
- OWL 元件（xlsx_import.js）既有 try/catch 已涵蓋讀取/解析/匯出/開啟 → `state.error` 友善訊息
- 修 fixture 污染：corrupt 測試檔移出 tests/fixtures（避免被 corpus 測試掃到），改放 tests/playwright/fixtures

## 三層 SOP
- L1 vitest **655 passed**（+2 穩健性：48 fixture 掃描 0 失敗、損壞輸入丟錯）
- L2 Playwright（corrupt.xlsx）：**CORRUPT_ERR_SHOWN=true INPUT_ALIVE=true pageerrs=none**；
  **截圖確認紅色友善橫幅「解析失敗：Error: invalid zip data」、上傳 UI 完整可重試**
- L3 tsc/build/升級無誤

## 待解（§4.5.4 其餘）
- zip bomb 防護（解壓大小/sheet/cell 上限）、upload size 限制、明確 file magic check、OCA raw XML fallback
