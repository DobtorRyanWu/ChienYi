# Sprint 14 Visual Regression — 自家 pipeline 像素級驗證基礎建設

**狀態**：W11+ 主線 Sprint 14 — Visual Regression infrastructure + 第一份 baseline
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §0.5 / §5.6](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint13_docprops_knuth_plass.md](sprint13_docprops_knuth_plass.md)

---

## 1. 範圍

Sprint 13 完成 docProps 自動讀取 + K-P opt-in 後，Sprint 14 進入 audit doc §7 建議優先 1：**Visual Regression 基礎建設**。

兩條既有 visual regression 通路差異：

| 通路 | 出處 | 現狀 | 用途 |
|---|---|---|---|
| 老路（Sprint 1 補完） | `scripts/visual_regression.mjs` + `parse_docx_cli.cjs` + `canvas-editor` UMD | 251 份 PNG golden | 驗 IElement[] 邏輯（`@hufe921/canvas-editor` 視覺） |
| **新路（Sprint 14）** | `scripts/visual_regression_v14.mjs` + `tools/dist/visual_regression_pipeline.iife.js` + 自家 `BrowserCanvasRenderContext` | **本次新增** | 驗 OoxmlParser → Layout → CanvasRenderer 真實像素輸出 |

老路保留：可比對 IElement[] 對接邏輯；新路是「我們 Sprint 8-13 累積的渲染管線是否真能畫出像樣的 PNG」的最終檢核點。

---

## 2. 落地檔案

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `tools/visual_regression_pipeline.entry.ts` | A | 瀏覽器 IIFE 入口；attach `window.__dobtorPipeline = { render, parse, layout }` |
| `rollup.visual_regression.config.js` | A | rollup IIFE 設定 + `node:module` browser stub plugin |
| `tsconfig.visual_regression.json` | A | 擴 tsconfig；含 tools/visual_regression_pipeline.entry.ts |
| `tools/dist/visual_regression_pipeline.iife.js` | A（產物） | 578KB IIFE bundle，自含 OoxmlParser + Layout + Render + BrowserCanvasRenderContext |
| `scripts/visual_regression_v14_harness.html` | A | puppeteer 載 file:// 用；提供 `__bootDobtorPipeline(b64, opts)` |
| `scripts/visual_regression_v14.mjs` | A | CLI；puppeteer + pixelmatch；輸出 `tests/fixtures/visual_regression_v14_report.json` |

**測試**：

| 類別 | 數量 | 狀態 |
|---|---|---|
| 全 42 fixtures boot smoke（`--no-diff`） | 42/42 | **rendered=42/42, bootFailed=0** |
| 全 42 fixtures pixel diff baseline（`--max-diff 1.0`） | 100 頁 | **comparedPages=100, failedPages=0**（loose threshold） |
| vitest 全套（既有護欄） | 45 files / 699 tests | **未動，全綠** |
| Python | 54 cases | **未動，全綠** |

---

## 3. 關鍵設計決策

### 3.1 為何不用 pixelmatch 鎖死門檻

當前 251 份 golden PNG 是 `@hufe921/canvas-editor` 的渲染結果，與我們自家 `BrowserCanvasRenderContext` 的視覺風格本來就不同：

- 行高基準（canvas-editor 用 `measureText` 自算，我們用 EstimateMetrics）
- 字距 / glyph anti-alias（瀏覽器 Canvas2D 與 canvas-editor 的 sub-pixel 處理不同）
- 邊框端點（細線 0.5pt 在 Canvas2D 會 anti-alias，canvas-editor 強制 1px）
- shading / 灰階填色

預期 Sprint 14 的 baseline diff 不可能 < 5%。所以 Sprint 14 **不假設 pass/fail**，而是建立「diff% 隨 sprint 進展逐步收斂」的趨勢追蹤儀器。

### 3.2 IIFE 而非 ESM

Puppeteer 載 `file://` HTML，無 module bundler、無 import map。IIFE 自動 attach 到 `window`，最小相依、最快啟動。bundle 大小（578KB）對手動觸發的 visual regression 不是熱點。

### 3.3 `node:module` browser stub

`static/src/core/ooxml/font/FontMetrics.ts` 頂層 `import { createRequire } from 'node:module'` 讓瀏覽器 IIFE bundle 載入時 throw（`node:module` 在瀏覽器不存在）。

兩個方案評估：

| 方案 | 優點 | 缺點 | 採用 |
|---|---|---|---|
| 改 FontMetrics.ts lazy 化 createRequire | 邏輯純 | 影響 vitest / cli / umd 三條既有通路 | ❌ |
| rollup 加 stub plugin（攔 'node:module'） | 只動瀏覽器 bundle | bundle 內 `localRequire` 仍存在但是 stub | ✅ |

stub 在 caller 真呼叫 `readFontMetrics()` 時 throw 合理錯誤；瀏覽器 IIFE 預設 `EstimateMetrics` 路徑不會走到此，bundle 安全載入。

### 3.4 base64 而非 ArrayBuffer 傳遞 docx

Puppeteer `page.evaluate(fn, arg)` 用結構化複製，不接 ArrayBuffer。base64 是 JS-friendly 的最簡傳輸；docx 通常 < 200KB，base64 膨脹 33% 仍可接受（< 300KB），不影響效能。

### 3.5 每頁一張 `<canvas class="ce-page">`

與老 harness 的 selector 一致（`page.$$('.ce-page')`），CLI 不需改 page 列舉邏輯。一頁一個 canvas 也讓單頁 screenshot 直接到位（不需 crop 主 canvas）。

### 3.6 BrowserCanvasRenderContext 用 96 DPI

與既有 251 份 golden 對齊（canvas-editor 也是 96 DPI）。A4：
- pt 21cm × 29.7cm = 595 × 842 pt
- 96 DPI = 794 × 1123 px

驗證：實際渲染 PNG 確實是 794 × 1123，與 golden 完全對齊。

---

## 4. Baseline 數據（2026-05-08 首次跑）

`scripts/visual_regression_v14.mjs --max-diff 1.0`：

| 類別 | fixtures | 頁 | 平均 diffRatio | 最大 | 解讀 |
|---|---|---|---|---|---|
| 01_simple | 7 | 13 | **0.1152** | 0.1633 | 簡單段落，主要差異在字距 / 行高 |
| 02_std_table | 8 | 13 | **0.2187** | 0.4892 | 含工地密度表（簡單）+ 週報（複雜表格）；分布雙峰 |
| 03_complex_table | 8 | 9 | **0.2281** | 0.3644 | 混凝土查驗表 / 履約查對表，巢狀表 + 細邊框 |
| 04_with_image | 6 | 16 | **0.2606** | 0.4059 | 圖片+表格混排，圖片填色暫無實作 |
| 05_header_footer | 10 | 42 | **0.0504** | 0.0935 | header / footer 自主檢查表，相對最穩 |
| 06_template | 3 | 7 | **0.0325** | 0.0848 | 缺失改善 / 試驗管制樣板，最簡 |
| **總計** | **42** | **100** | **0.1291** | — | 整體 ~13% 差異 |

**詮釋**：12.91% 平均不是「壞」，是合理的基準線：
- 最低差異（06_template 3.25%）= 我們 pipeline 對純表格 / 文字場景已能高度貼近
- 最高差異（04_with_image 26.06%）= 圖片填充未真做（drawImage no-op，BrowserCanvasRenderContext 預設 imageResolver=undefined）
- 02 / 03（22-23%）= 複雜表格的細線 anti-alias + 文字對齊差距

未來 sprint 重點工作對應的可預期降幅：
- HarfBuzz 接通 → 字距精準 → 預期 01_simple / 05_header_footer / 06_template 降 2-3%
- 圖片真渲染 → 04_with_image 降 8-10%
- 邊框 anti-alias 對齊 canvas-editor → 02 / 03 降 5-8%

---

## 5. 已知限制

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| 圖片填充未真渲染（drawImage no-op） | BrowserCanvasRenderContext 預設 imageResolver=undefined | Sprint 15+ 加 imageResolver（讀 OoxmlPackage 的 word/media/）|
| pixelmatch threshold 寬鬆（0.1） | 容忍 anti-alias / sub-pixel 抖動 | 待 pipeline 收斂後可降至 0.05 |
| 無「golden 與 v14 並列預覽」HTML | 只有 diff PNG，要分別開 image viewer 看 | Sprint 15+ 加 report.html（並列 三 PNG）|
| 不在 vitest / CI default | puppeteer 太重，現只手動觸發 | CI 加 nightly job 跑 v14（W11+ 補強衝刺項） |
| 部分 fixture 頁數差異 | 我們 pipeline 排版可能比 canvas-editor 多 / 少一頁 | 比對 page count 在 report.json 內，後續 sprint 對齊 |
| K-P 預設關 | Sprint 13 維持 greedy；K-P 對西文段落更平均 | Sprint 15+ 用 v14 baseline 評估 K-P 預設化 |

---

## 6. 對 Sprint 1-13 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | **完全不變** | 2 case 全綠 |
| Sprint 13 unit tests | 無 | 22 case 全綠 |
| Python integration | 無 | 54 case 全綠 |

**vitest 全套**：45 files / **699 tests pass**（與 Sprint 13 完全一致；Sprint 14 不動 vitest 護欄，純加新 CLI / bundle）。

---

## 7. 驗證指令

```bash
# 1. 編譯瀏覽器端 IIFE bundle（首次或改 entry/Layout/Render 程式碼後執行）
npx rollup -c rollup.visual_regression.config.js

# 2. 跑 Sprint 14 visual regression（全 42 fixtures，loose diff baseline）
node scripts/visual_regression_v14.mjs --max-diff 1.0

# 3. 限制範圍快速驗證
node scripts/visual_regression_v14.mjs --filter 01_simple --max-fixtures 3 --no-diff
node scripts/visual_regression_v14.mjs --filter 05_header_footer --max-diff 0.1

# 4. 既有 vitest（確認 Sprint 14 沒影響其他護欄）
npm test

# 5. Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

**輸出位置**：

- `tests/fixtures/.visual_regression_tmp/v14/<basename>-N.rendered.png` — 我們 pipeline 渲染結果
- `tests/fixtures/<cat>/golden/<basename>-N_v14_diff.png` — pixelmatch diff 圖（只在超過 maxDiff 時寫）
- `tests/fixtures/visual_regression_v14_report.json` — 完整 report

---

## 8. 下個 Sprint（Sprint 15+）建議

Sprint 14 把 visual regression 基礎建設好，後續 sprint 可用 v14 baseline 持續追蹤改進效果：

1. **圖片真渲染** — `BrowserCanvasRenderContext` imageResolver 讀 OoxmlPackage word/media/；預期 04_with_image 降 8-10%
2. **HarfBuzz async 接通** — Sprint 8 已開 BoxBuilder 介面，補上 ShapingEngine real call；預期文字密集類降 2-3%
3. **註腳 / 尾註** — 解析 footnotes.xml + Paginator 預留 footnote 區
4. **wrapTight polygon** — drawing.xml polygon path 解析 + per-y lineWidth
5. **K-P 預設化評估** — 用 v14 baseline 跑兩次（greedy / k-p），決定是否切預設
6. **report.html 並列預覽** — `<table>` 並列 `golden` / `v14 rendered` / `diff`，方便人工 review 哪些差異是「我們對」哪些是「我們錯」

**建議優先順序**：1（最大 diff 收斂源）→ 2 / 3（pipeline 完整度）→ 4 / 5（精度收尾）→ 6（review 工具收尾）

---

**附註**：Sprint 1-14 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值
- Sprint 12：完整 field 系統（DATE/TIME/AUTHOR/FILENAME）+ Renderer ops fingerprint regression
- Sprint 13：OOXML docProps/core.xml 自動讀取 + Knuth-Plass 斷行器（opt-in）
- **Sprint 14：自家 pipeline IIFE bundle + puppeteer harness + 42 fixture / 100 頁 baseline（mean diff 12.91%）**

到 Sprint 14，Parser 端能完整還原 OOXML、Layout 端兩種斷行算法、Renderer 端能直接畫到瀏覽器 Canvas2D 並截圖比對。Sprint 15 起進入「逐項收斂 baseline」階段。
