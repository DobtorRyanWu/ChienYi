# Sprint 18 — 公式 round-trip（Phase 4.5）

**日期**：2026-06-07
**Phase**：4.5（產品化）/ Phase 3 起點
**緣由**：Sprint 16 content 用 cached 值（靜態）；本 sprint 改餵公式 → o-spreadsheet 即時運算、可編輯重算。

---

## Root cause

Sprint 16 餵 cached 值是為避開 o-spreadsheet 函數覆蓋率落差致 #BAD_EXPR。
但靜態值不是真正的試算表——改一格不會重算。本 sprint 補公式 round-trip，
關鍵是**只在安全時餵公式**（hybrid），避免不支援函數爆錯。

## 調查（兩邊盤點）

1. **ChienYi 公式函數**（88,023 公式 cell、24 種函數）：
   VLOOKUP(31381) IF(25940) IFERROR(21472) CHAR ROUND SUM SUMIFS COUNTIF ROW AND
   SUBSTITUTE CHOOSE WEEKDAY CELL COUNT COUNTA RIGHT LEN FIND ROUNDDOWN ROUNDUP COUNTIFS TODAY AVERAGE
2. **o-spreadsheet 支援度**（逐一對 o_spreadsheet.js 確認 `const NAME={`）：
   - 23/24 支援；**CHOOSE 未定義**（o-spreadsheet 18.0.48）→ 排除
   - 另確認常見函數 OR/NOT/LEFT/MID/MIN/MAX/SUMIF/DATE/TEXT… 皆支援

## 修法（`to_ospreadsheet.ts`）

- `SUPPORTED_FUNCTIONS`（45 個白名單 = 23 確認 + 常見安全函數，**排除 CHOOSE**）
- `formulaUsesOnlySupported(formula)`：抽函數名（`NAME(`）、去 `_xlfn./_xlws.` 前綴、比對白名單；
  **純算式（無函數，如 `A1+B2*2`）→ true**
- content 邏輯：`cell.formula && 安全 → "="+公式（去 _xl 前綴）`；否則 fallback cached 值
- style/format/border 不變（套用於公式結果）

## 三層 SOP 結果

- **L1 vitest**：**539 passed**（unit 205 + integration 334）
  - `to_ospreadsheet.test.ts` +4：SUM→`=SUM(A1:A2)`、純算式→`=A1+A2*2`、**CHOOSE→fallback cached `10`**、非公式數字→原值
- **L2 Playwright E2E**（fixture 改公式密集的 `0312磺港溪A標變更金額分析.xlsx`，173 公式）：
  - `OPEN_RESULT=GRID_MOUNTED`；截圖 `sse-02-editable.png`：
    - 複價欄 = 數量×單價 **正確運算**（100×1130=113000、1023.24×1100=1125564、85.27×3360=286507.2…）
    - 小計 1685081、單價計 16850.81（SUM/聚合）正確
    - **無 #ERROR / #BAD_EXPR**、6 sheet 分頁、cells 為**即時公式**（可編輯重算）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過、docker -u 升級+重啟無誤

## 對比

| | Sprint 17 | Sprint 18 |
|---|---|---|
| cell 內容 | cached 靜態值 | **安全公式 → 即時公式**；不安全 → cached |
| 改值重算 | ❌ | ✅（公式 cell） |
| #BAD_EXPR | — | 0（hybrid 防護） |

## 對齊進度

| 項目 | 狀態 |
|---|---|
| xlsx → o-spreadsheet（值/樣式/格式/合併/欄寬/邊框） | 🟢 |
| 公式 round-trip（hybrid） | 🟢 本 sprint |
| 匯出回 xlsx（openpyxl） | ⚪ Phase 6 |
| 持久化 / ChienYi 業務模組整合 | ⚪ Phase 8 |

## 負面結果 / 待解（紀律 #4）

1. **CHOOSE（93 公式）fallback cached**：o-spreadsheet 無 CHOOSE，這些 cell 顯示值但非即時。
   可後續做 CHOOSE→IFS shim 或 o-spreadsheet addFunction。
2. **白名單保守**：未列入的支援函數也會 fallback（寧可漏餵、不要爆錯）。可隨驗證逐步擴充。
3. **shared formula 未展開**：parser 對 `<f t="shared">` slave 格無 formula text → 走 cached 值（正確顯示、非即時）。
4. **跨 sheet / 特殊語法**：白名單只擋函數名，少數語法邊界（array、structured ref）仍可能 fallback 或誤餵；
   Playwright 實測本批 fixture 無誤，廣域待更多 fixture 驗證。

## 下一步（Sprint 19）

- CHOOSE shim（o-spreadsheet addFunction 或轉 IFS）擴大即時公式覆蓋
- 或匯出回 xlsx（Phase 6, openpyxl）達成雙向 round-trip
- 或持久化 + 與 ChienYi 估驗計價模組整合（Phase 8）
