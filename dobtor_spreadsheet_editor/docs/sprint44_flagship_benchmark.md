# Sprint 44 — 旗艦檔 capstone + benchmark（Phase 7 基準）

**日期**：2026-06-08｜**Phase**：7（基準量測）

## 目的
部署前驗證最大真實檔端到端可用，並建立效能基準。
**旗艦檔**：延壽橋至三合橋-契約詳細表（**16 sheet、shared formula 展開後 6.5 萬公式**）。

## Playwright capstone 結果
| 階段 | 時間 | 結果 |
|---|---|---|
| 解析 + HTML 預覽（我方 parser） | **1.3 秒** | 🟢 極快 |
| 開可編輯 o-spreadsheet（建記錄+載入+運算 6.5 萬公式） | **20.8 秒** | 🟢 成功、errs=none、無 o_error_dialog |
| 渲染 | — | 🟢 標題/合併格/16 sheet 分頁（民國年命名 114.01…）/樣式全到位 |

## 解讀
- **我方 parser 不是瓶頸**（16 sheet 解析 1.3s）；20.8s 主要是 **o-spreadsheet 端建立記錄 + 載入 +
  計算 6.5 萬公式**（S40 展開的真實重複公式）。
- 端到端**功能正確、無 crash**，惟大檔開啟偏慢（>20s）。

## Phase 7 效能機會（若優化）
- o-spreadsheet 載入時的公式批次計算為主成本 → 可評估：lazy sheet（先載首 sheet）、
  Web Worker parse（解析已快、效益有限）、或保留 cached 值不展開全部 shared formula（取捨即時運算 vs 開啟速度）。
- 建議：提供「快速模式」選項（只展開可視 sheet 的 shared formula）給超大檔。

## 結論
旗艦級真實檔（ChienYi 最大契約詳細表）端到端可用，整條高保真管線通過 capstone 驗證。
