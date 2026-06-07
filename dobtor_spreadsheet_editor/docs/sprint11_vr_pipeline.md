# Sprint 11 — VR Pipeline（Phase 4 視覺回歸管線）

**日期**：2026-06-07
**Phase**：4（測試與驗證體系）VR pipeline 基礎建設
**對齊**：規劃書 §6 測試體系（pixelmatch 對比 LibreOffice headless PNG）

---

## Root cause（開工前假設）

Sprint 1-10 已建完整 parser + 樣式具體化（ConcreteStyle），但所有驗證都是「結構/數值」層級
（cell value 提取率、樣式索引健全性），**沒有任何像素級視覺驗證**。要往「視覺保真」推進，
必須先有 render → pixelmatch → ratio 的管線。

**現實評估（紀律 #1）**：golden PNG 是 LibreOffice Calc 渲染。要 OUR render 對它 <5% 是規劃書估的
12-18 個月終極目標，**非單一 sprint**。本 sprint 範圍 = **建管線 + 建 baseline**，不誇稱 LibreOffice
像素對等。

## 修法（實際做的事）

三個 vr/ 模組（Node 端，不從 index.ts 匯出、不進 frontend bundle）：

### `vr/pixel_compare.ts`
- `comparePng(a, b, opts)` → `PixelDiff{ width, height, diffPixels, totalPixels, ratio, diffPng? }`
- pngjs 解碼 + pixelmatch 比對；**尺寸不匹配時取交集比對、非重疊區計入差異**（避免假性 0%）

### `vr/html_render.ts`
- `renderWorksheetHtml(ws, ss, styles, theme, opts)` → 完整 HTML 文件
- model → DOM：cell 值（buildValueMapStyled）+ ConcreteStyle → `<table>` inline CSS
  - 欄寬（columnWidthToPixels）、列高、**合併格 colspan/rowspan + covered 格跳過**、
    背景/字色/粗斜體/底線刪除線/對齊/邊框 CSS、HTML escape
- 上限保護（預設 60 列 × 40 欄）避免大表爆量

### `vr/render_png.ts`
- `launchBrowser()` + `renderHtmlToPng(browser, html)`（puppeteer，--no-sandbox 相容 WSL/CI，截 table 元素）

## 三層 SOP 結果

- **L1 vitest**：**503 passed**（unit 172 + integration 331）+ 1 VR baseline（skipIf 手動）
  - `pixel_compare.test.ts`（6）：相同→0、一像素→>0、全黑vs全白→~1、**尺寸不匹配計入差異**、
    emitDiff 產圖、**真實 golden 自比對→0**
  - `html_render.test.ts`（6）：HTML 結構、cell 值、**合併格 colspan + covered 跳過**、
    黃底/紅字/粗體/置中 CSS、欄寬 px、HTML escape
- **L2 VR baseline**（`VR_BASELINE=1` 手動跑、puppeteer 光柵化 vs golden）：
  | fixture | our 尺寸 | diff |
  |---|---|---|
  | 估驗差異表 11309 | 618×208 | 87.9% |
  | 變更金額分析 | 551×307 | 84.2% |
  | C-A土單 | 1124×795 | 45.5% |
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（14.1s、vr/* 未污染 bundle）

## Baseline 解讀（紀律 #4，**誠實**）

差異率 45-88% **偏高且符合預期**，原因（非 bug）：
1. **佈局引擎不同**：HTML `<table>` 流式佈局 vs LibreOffice Calc 固定網格，行高/欄寬/字距不一致
2. **字型不同**：瀏覽器 fallback 字型 vs LibreOffice 的 CJK 字型 metrics
3. **僅首 sheet + 限 60×40**：golden 為完整 sheet，尺寸與內容範圍不同 → 大量非重疊區計入差異
4. **我方 render 未做**：數字格式渲染（千分位/貨幣）、文字 clip、列印區、凍結窗格視覺

→ 這是**保真度爬升的起點**，非終點。管線已驗證可端到端運作（parse → HTML → PNG → pixelmatch → ratio），
後續 sprint 逐項收斂（換 LibreOffice 同款字型、精算欄寬、全 sheet render、number format 渲染）可降低差異率。

## 工程決策

1. **vr/* 不進 frontend bundle**：puppeteer/pngjs/pixelmatch 為 Node-only，不從 index.ts 匯出 →
   rollup tree-shake 不含；tsc 仍 typecheck（補裝 `@types/pngjs`）
2. **VR baseline 用 skipIf(!VR_BASELINE) 而非常規 test**：避免 puppeteer 拖慢/不穩 `npm test`；
   保持 503 tests 快速全綠，baseline 按需手動量測
3. **render 路徑選 HTML 而非自寫 canvas**：環境無 node-canvas；HTML+puppeteer 是最快可動的 render，
   且未來可平滑換成 o-spreadsheet headless（Phase 4.5）

## 對齊進度

| 項目 | 狀態 |
|---|---|
| VR 比對原語（pixelmatch wrapper） | 🟢 |
| model → render（HTML 路徑） | 🟢 |
| puppeteer 光柵化 | 🟢 |
| baseline 建立 | 🟢（45-88%） |
| 保真度收斂至 <5% | ⚪ 多 sprint 工程 |
| o-spreadsheet headless render（取代 HTML） | ⚪ Phase 4.5 |

## 負面結果 / 待解

1. **baseline 偏高**：見上方解讀；非缺陷、是起點。
2. **多 sheet 未 render**：僅首 sheet；多 sheet golden 比對待補。
3. **package.json 變動**：新增 devDep `@types/pngjs`。

## 下一步（Sprint 12）

降低 VR 差異率的最高槓桿項：
- **全 sheet + 正確尺寸 render**（消除非重疊區的假性差異，預期差異率大降）
- **欄寬/列高精算 + LibreOffice 同款字型**（cell 對齊）
- 或轉 **Phase 4.5 o-spreadsheet headless render**（用目標引擎本身渲染，根本對齊）
