# Sprint 14 — 字型保真（VR 收斂）

**日期**：2026-06-07
**Phase**：4（VR pipeline 保真度第二輪收斂）
**對齊**：Sprint 13 指出「字型為 VR 下一槓桿」

---

## Root cause（開工前假設）

VR content diff（~12-20%）由字型主導：我方 puppeteer Chrome render 用 `font-family:'新細明體',sans-serif`，
但 `,sans-serif` 通用 fallback 讓 Chrome 自選回退字型，可能與 golden（LibreOffice）所用不一致。

## 調查（環境事實）

- 系統 CJK 字型（fc-list）：僅 **WenQuanYi Zen Hei**、**Droid Sans Fallback**（無 新細明體/標楷體/Noto CJK serif）
- `fc-match` 替換（LibreOffice 與 Chrome 在 Linux 共用 fontconfig）：
  - CJK（新細明體/PMingLiU/標楷體/DFKai-SB/MingLiU）→ Noto Sans（latin、無 CJK 字形）→ CJK 字元再回退 WenQuanYi/Droid
  - **Calibri → Carlito**、**Arial → Liberation Sans**、**Times New Roman → Liberation Serif**（metric-compatible）

## 修法（實際做的事）

### `vr/font_map.ts`
- `fontFamilyStack(name)`：Excel 字型 → CSS font-family 堆疊
  - Latin → **metric-compatible 替換**（Carlito/Caladea/Liberation Sans|Serif|Mono）+ CJK 回退
  - CJK / 未知 → 原名（讓 fontconfig 比照 LibreOffice 替換）+ CJK 回退
  - 一致的 CJK 回退鏈 `'WenQuanYi Zen Hei','Droid Sans Fallback',sans-serif`（釘死、不讓 Chrome 自選）
- 接入 `vr/html_render.ts`：per-cell font-family + table 預設字型皆走 fontFamilyStack

## 三層 SOP 結果

- **L1 vitest**：**523 passed**（unit 192 + integration 331）
  - `font_map.test.ts`（5）：Latin 替換、CJK 保留原名+回退、無名→純回退、所有堆疊含 CJK 回退、單引號去除
- **L2 VR baseline**（字型保真前後）：
  | fixture | Sprint 13 | **Sprint 14** | Δ |
  |---|---|---|---|
  | 估驗差異表 11309 | 11.8% | **11.4%** | -0.4 |
  | 變更金額分析 | 14.4% | **12.4%** | **-2.0** |
  | C-A土單 | 20.4% | **19.3%** | -1.1 |
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（14.2s）

## 解讀（紀律 #4）

- **真實但溫和的改善**（-0.4 ~ -2.0）：metric-compatible Latin 字型（Carlito/Liberation）對**數字密集**的
  變更金額分析最有感（-2.0）；CJK 釘死回退對文字密集檔小幅改善
- **剩餘 11-19% 為佈局 metrics**：HTML `<table>` 與 LibreOffice 網格在「列高、cell 內距、baseline、
  欄寬精算」上的根本差異——字型對齊後，這成為主要殘差
- VR 軌跡：S11 raw 45-88% → S12 content 11.7-20.4% → **S14 content 11.4-19.3%**，穩定收斂

## VR 收斂軌跡與下一步

| Sprint | 措施 | content diff |
|---|---|---|
| 11 | 建管線 | raw 45-88% |
| 12 | 全 sheet + scaleToMatch | 11.7-20.4% |
| 13 | number format | 11.8-20.4%（≈） |
| 14 | 字型保真 | **11.4-19.3%** |

## 負面結果 / 待解

1. **改善溫和**：字型只是殘差之一；佈局 metrics 是更大塊（下一槓桿）。
2. **CJK 無 serif/kai 區分**：系統無細明/楷體，新細明體與標楷體都回退同一 WenQuanYi → 視覺上兩者
   在我方 render 中無分別（但 golden 同樣受系統字型限制，故影響對稱、非單方誤差）。
3. **最近鄰縮放噪音**：content diff ±0.5 內波動含縮放取樣噪音。

## 下一步（Sprint 15）

VR 收斂剩餘最高槓桿（佈局 metrics）：
- **列高精算**：LibreOffice 用字級推導列高（無 customHeight 時），我方目前固定 15pt → 換成依字級
- **cell 內距/baseline 對齊**：調 td padding、vertical-align baseline 對齊 LibreOffice
- 或根本解：**轉 o-spreadsheet headless render**（用目標引擎渲染、佈局自然對齊）
