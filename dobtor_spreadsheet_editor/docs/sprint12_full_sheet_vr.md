# Sprint 12 — 全 sheet render + 消尺寸假性差異

**日期**：2026-06-07
**Phase**：4（VR pipeline 保真度第一輪收斂）
**對齊**：Sprint 11 baseline 偏高的根因拆解

---

## Root cause（開工前假設）

Sprint 11 baseline 45-88% 偏高。拆解後假設兩大「假性差異」來源：
1. **截斷**：html_render 上限 60 列 × 40 欄，但 golden 是 LibreOffice 渲染的**完整首 sheet** →
   我方圖只涵蓋部分內容、尺寸遠小於 golden → 大量非重疊區計入差異
2. **尺寸不匹配**：即使內容相同，我方 render 的絕對像素尺寸 ≠ golden（DPI/欄寬基準不同）→
   非重疊面積被當差異，灌大數字、掩蓋真實內容差異

## 修法（實際做的事）

### `vr/html_render.ts`
- 改用 `worksheetBounds(ws)`（dimension 全 used range）決定 render 範圍，而非僅「有值 cell」的 maxRow/maxCol
- 安全上限放寬 60×40 → **500×80**（涵蓋完整首 sheet）
- `nRows = min(500, max(bounds.rows, maxRow, 1))`、`nCols` 同理

### `vr/pixel_compare.ts`
- 新增 `scaleToMatch` 選項：尺寸不匹配時用**最近鄰縮放**把兩圖對齊到交集尺寸再 pixelmatch
  → 消除尺寸假性差異、只量「內容差異」
- 預設仍為交集 + 非重疊計入差異（raw）；scaleToMatch 為純內容差異

## 三層 SOP 結果

- **L1 vitest**：**505 passed**（unit 174 + integration 331）
  - `pixel_compare.test.ts` +2：**scaleToMatch 同色不同尺寸 → ratio 0**（無尺寸假性差異）、異色 → ~1
- **L2 VR baseline**（`VR_BASELINE=1` 手動）：
  | fixture | Sprint 11 raw | 全 sheet raw | **content(scaled)** |
  |---|---|---|---|
  | 估驗差異表 11309 | 87.9% | 47.2% | **11.7%** |
  | 變更金額分析 | 84.2% | 84.2% | **13.8%** |
  | C-A土單 | 45.5% | 45.5% | **20.4%** |
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過

## 解讀（紀律 #4）

- **全 sheet render** 對「內容未填滿截斷範圍」的檔（11309）raw 大降（87.9%→47.2%）；
  對本就在範圍內的檔（變更金額分析）raw 不變——證明截斷是 11309 的主因之一。
- **scaleToMatch content diff 11.7-20.4%** 才是我方 render 的**真實視覺保真度**：
  尺寸假性差異剝離後，內容差異遠低於 raw。這是驅動 <5% 的有意義指標。
- 剩餘 12-20% 內容差異來源（下一輪收斂標的）：字型不同（瀏覽器 fallback vs LibreOffice CJK）、
  欄寬/列高未精算對齊、number format 未渲染（千分位/貨幣顯示成原始數字）、文字 clip/對齊細節。

## 對齊進度

| 項目 | Sprint 11 | Sprint 12 |
|---|---|---|
| VR 管線 | 🟢 建立 | 🟢 |
| 全 sheet 範圍 render | ❌ 截斷 60×40 | 🟢 dimension 全範圍 |
| 尺寸假性差異 | 計入（raw 灌大） | 🟢 scaleToMatch 剝離 |
| content diff baseline | — | 🟡 11.7-20.4% |
| <5% 終極 | ⚪ | ⚪ 多 sprint |

## 負面結果 / 待解

1. **content diff 仍 12-20%**：主因字型 + 欄寬 + number format 渲染，待後續 sprint。
2. **最近鄰縮放**：scaleToMatch 用最近鄰（快、無插值模糊），可能對細線邊框略有取樣誤差；
   足夠作為趨勢指標，精確像素比對仍以同尺寸 raw 為準。
3. **僅首 sheet**：多 sheet golden 比對待補。

## 下一步（Sprint 13）

content diff 收斂最高槓桿：
- **number format 完整渲染**（千分位/貨幣/百分比）→ cell 顯示文字對齊 golden（目前顯示原始數字）
- **欄寬/列高精算 + LibreOffice 同款字型**（換 `font-family` 為實際 CJK 字型、量測對齊）
- 或轉 **o-spreadsheet headless render**（用目標引擎根本對齊）
