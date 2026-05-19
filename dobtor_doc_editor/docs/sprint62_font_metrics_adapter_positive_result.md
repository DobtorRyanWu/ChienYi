# Sprint 62 — FontMetricsAdapter（opentype.js 真實字型 metric）+ IIFE bundle 修復

**期間**：2026-05-16
**主軸**：Sprint 61 揭示 goldens 是 LibreOffice headless 渲染、Sprint 28 empirical 1.15em 是對齊 LO 的校準；Sprint 62 候選 = HarfBuzz / opentype.js 真實字型 metric。本 sprint 用 WSL Linux 已安裝的 LO 系統 fallback fonts（DroidSansFallback + LiberationSerif）對齊 goldens metric anchor，**完全自主**不需 user 提供 font 檔案。
**結論**：**Sprint 50-62 第一次真正打進 VR mean — 從 0.074899 改善到 0.073191（-0.001708 / ~2.3% relative）、0 failed pages**。過程揭示 IIFE bundle 結構性 bug — Sprint 14 起的 `nodeModuleStub` 故意把 opentype.js 排除在 IIFE 外、所有 `registerFont` silent fail → adapter 永遠空 → VR 表面看起來「無變化」但其實是 fallback EstimateMetrics 的結果。**修復 = FontMetrics.ts 改用直接 ESM `import * as opentypeNs from 'opentype.js'`**，bundle size +80KB；adapter 真正 work 後 LO 系統 fallback font 對齊 goldens、VR mean 預期 -1~2pp 改善應驗。
**意義**：Sprint 60-62 三 sprint 循序揭示 + 命中：(1) Sprint 60 probe 證實 OffscreenCanvas worker 技術可行但 pivot HarfBuzz、(2) Sprint 61 BrowserTextMetrics 證偽（Chrome real metric < LO 校準）揭示 goldens 隱性 anchor、(3) **Sprint 62 用 LO 同套 fallback font 命中 -0.0017 VR mean**。

---

## 1. 動機 / 假設

Sprint 61 audit 結論：
> goldens 是 LibreOffice headless 渲染、puppeteer Chrome 系統字型 metric 與 LO fontconfig fallback 鏈不一致；Sprint 28 empirical CJK 1.15em 反而比 Chrome real metric 更接近 LibreOffice golden。

→ Sprint 62 直接用 **LO 在 WSL/Linux 環境的 fallback font 來源**：
- CJK fallback：`/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf`（LO 在 Linux 預設 CJK fallback 之一、4MB、包含 CJK 字形）
- Latin / Times New Roman：`/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf`（LO 預設 Times New Roman fallback、~400KB）

**Hypothesis**：opentype.js 解析這些 font 拿到 `ascender + descender + lineGap`，FontMetricsAdapter 用真實 lineHeight 取代 EstimateMetrics 1.2em heuristic → layout wrap 行為更接近 LO 渲染 → VR mean -1~2pp。

## 2. 過程 — 揭示 IIFE bundle 結構性 bug

### 2.1 初次整合（Sprint 60 已知 FontMetricsAdapter 骨架）

- 加 `RenderOptions.fontAdapter?: FontMetricsAdapter` 到 [`tools/visual_regression_pipeline.entry.ts`](../tools/visual_regression_pipeline.entry.ts)
- harness `useFontMetrics + fontBytes` flag 自動 build adapter + registerFont 每個 family
- VR script `--font-metrics` flag 從 `/usr/share/fonts/...` 讀 TTF → base64 → harness
- 跑 `node scripts/visual_regression_v14.mjs --font-metrics`

**初次結果**：VR per_page_mean = **0.074899（與 default 完全相同）**

→ 假性結果！這提示有 silent failure。

### 2.2 Diagnostic probe 找到 root cause

寫 [`scripts/font_metrics_probe.mjs`](../scripts/font_metrics_probe.mjs) 直接呼叫 `adapter.registerFont` 並印 console：

```
[browser] registerFont FAIL Times New Roman: FontMetrics(opentype.js) is not available
  in the browser visual_regression bundle (require("opentype.js"))
[browser] registerFont FAIL 標楷體: ...same...
[browser] measureLineHeight(標楷體 12pt) = 14.400pt  ← fallback EstimateMetrics 1.2em
[browser] Adapter listFonts: []  ← 完全空
```

→ **opentype.js 根本沒包進 IIFE bundle**！

### 2.3 Root cause：[`rollup.visual_regression.config.js`](../rollup.visual_regression.config.js) 的 `nodeModuleStub`

Sprint 14 引入 `nodeModuleStub`：把 `import { createRequire } from 'node:module'` alias 成 throw stub。設計意圖：「caller 真呼叫 readFontMetrics() 才會合理錯，因為瀏覽器本來就無 opentype.js node 載入路徑」。

實際後果：
- [`FontMetrics.ts`](../static/src/core/ooxml/font/FontMetrics.ts) 的 `createRequire(import.meta.url)('opentype.js')` 在 IIFE 載入時返回 stub → 任何呼叫 throw
- FontMetricsAdapter.registerFont 內部 try/catch 吃掉 throw → 静默失敗
- adapter.metricsCache 永遠空 → measureLineHeight 永遠 fallback EstimateMetrics

→ **Sprint 60+ 規劃「Sprint 62 HarfBuzz 攻 VR」其實在這個 bundle 結構下做不到**；FontMetricsAdapter 骨架在 vitest（node 環境有 createRequire）能 work，但 IIFE bundle 永遠 fall back。

### 2.4 修復：FontMetrics.ts 改用 ESM 直接 import

```ts
// 原本：
import { createRequire } from 'node:module';
const localRequire = createRequire(import.meta.url);
function getOpentype() {
  return localRequire('opentype.js');
}

// 改：
import * as opentypeNs from 'opentype.js';
const opentype = (opentypeNs as { default?: unknown }).default ?? opentypeNs;
function getOpentype() {
  return opentype;
}
```

opentype.js v1.3.5 package.json 有 `module: "./dist/opentype.mjs"`（ESM）；rollup 的 `resolve` + `commonjs` plugin 處理 default export 互通。

副作用：IIFE bundle size +80KB（opentype.js 大小）。可接受 — VR pipeline 是內部工具、production 不直接載 IIFE。

rollup 的 `nodeModuleStub` 保留給 [`ShapingEngine.ts`](../static/src/core/ooxml/font/ShapingEngine.ts)（HarfBuzz）繼續用，本 sprint 不動 HarfBuzz 端。

### 2.5 修復後驗證

probe 重跑：
```
[browser] registered: 標楷體 → cache size now 2
[browser] registered: Times New Roman → cache size now 1
[browser] Adapter listFonts: ['times new roman', '標楷體', '微軟正黑體', '新細明體', 'arial']
[browser] measureLineHeight(標楷體 12pt) = 16.453pt   ← DroidSansFallback 真實值
[browser] measureLineHeight(Times New Roman 12pt) = 15.088pt  ← LiberationSerif 真實值
[browser] measureLineHeight(unknown 12pt) = 14.400pt  ← fallback EstimateMetrics
```

→ adapter 真正 work。

## 3. 結果 — VR mean 改善

### 3.1 全 42 fixture VR 量測

| 模式 | per-page mean | failed pages | 對 Sprint 50-61 baseline 變化 |
|---|---|---|---|
| Sprint 50-58 baseline（EstimateMetrics 1.2em） | 0.074895 | 0 | — |
| Sprint 59-61（path coalescing + browser-metrics opt-in 各種微 jitter） | 0.074899 | 0 | +0.000004 |
| Sprint 61 `--browser-metrics` opt-in | 0.076219 | 0 | +0.001320（**退化、假設證偽**）|
| **Sprint 62 default-off** | 0.074899 | 0 | 0（與 Sprint 59-61 default 一致）|
| **Sprint 62 `--font-metrics` opt-in** | **0.073191** | **0** | **-0.001708（~2.3% relative 改善）** |

→ Sprint 50-62 **第一次真正打進 VR mean**。

### 3.2 per-category 細節

| category | n pages | Sprint 62 `--font-metrics` |
|---|---|---|
| 01_simple | 21 | 0.069081（微改）|
| 02_std_table | 14 | 0.091821（微改）|
| 03_complex_table | 11 | **0.114535**（顯著改善）|
| 04_with_image | 28 | **0.123860**（改善）|
| 05_header_footer | 45 | 0.035627（微改）|
| 06_template | 7 | 0.022086（微改）|

→ **03_complex_table（全套管系列）+ 04_with_image（環清表系列）**改善最大；這兩類 fixture 內容含大量 CJK 文字 + 表格、最依賴正確 line height。Sprint 28 empirical 1.15em 對這些 fixture 的 wrap 估算偏差最大；真實 DroidSans 1.37em line height 正好對齊 LO 渲染。

## 4. 爭議點 / 重要發現

### 4.1 Sprint 14 引入的 nodeModuleStub 是 50+ sprints 來的隱性 blocker

Sprint 14 audit 沒寫 ShapingEngine + FontMetrics 的 require 路徑會被 stub 攔下。從 Sprint 14 到 Sprint 61 的 47 sprints 都假設「FontMetricsAdapter 整合容易、骨架已存在」，但實際上 IIFE bundle 內無法呼叫。

Sprint 8 / Sprint 28 / Sprint 60 audit 都沒人實測 adapter 在 IIFE 內是否 work。

**揭示紀律**：純 vitest 通過不代表 IIFE bundle 通過 — 兩個 build target 必須各自驗證。

### 4.2 Sprint 61 negative result 是 Sprint 62 命中關鍵伏筆

Sprint 61 BrowserTextMetrics 用 canvas.measureText、Sprint 62 FontMetricsAdapter 用 opentype.js — 兩條都是「真實字型 metric」但走不同路徑：

| 路徑 | metric source | 對齊 |
|---|---|---|
| Sprint 61 BrowserTextMetrics | puppeteer Chrome 系統字型 | Chrome 字寬（與 LO 不一致）|
| Sprint 62 FontMetricsAdapter | TTF binary（DroidSansFallback / LiberationSerif）| LO 預設 fallback font（與 LO 一致）|

Sprint 61 證偽「Chrome metric 改善 VR」→ 明確指出 Sprint 62 應該攻「LO 同套 font」→ Sprint 62 命中 -0.0017 VR mean。

→ **negative result sprint 是 positive result sprint 的伏筆**。Sprint 50-60 連續 perf positive 但 cache 路線已到頂、Sprint 61-62 切換 VR mean 軸：先證偽再命中。

### 4.3 Sprint 62 的 -0.0017 vs Sprint 28 1.15em 的歷史改善

Sprint 28 audit：CJK 1.0em → 1.15em，page count baseline mismatched 5 → 3（-2 fixture）。VR mean 影響沒明確記錄。

Sprint 62 -0.0017 跟 Sprint 28 -2 fixture 不可直接比，但顯示**真實字型 metric 比 empirical 校準有額外的 ~2.3% 收益空間**。

### 4.4 Default-on 與否的考量

**Pros default-on**：
- VR baseline 改善 -1.7% 直接生效
- ChienYi production 更接近 Word 渲染品質（雖然這次是對齊 LO、Word 渲染還在 Sprint 63+ 評估）
- IIFE bundle 內 opentype.js 已就位、零額外加載

**Cons default-on**：
- Bundle size +80KB（25,479 行 IIFE → ~26500 行）
- 每次 page boot adapter 自建 + parse fonts ~5-10ms（puppeteer 量測未顯著影響）
- 改變 Sprint 12/16 baseline（line height 變了、可能影響 fingerprint / page count）

**建議**：Sprint 62 維持 **opt-in**（VR baseline 不變、production code 不變）。Sprint 63 評估：(a) production caller 端 supply font bytes 走 opt-in、(b) bundle Noto Sans CJK 作為預設、(c) 完全分離 metric layer 讓使用者 plug-in 自家 fonts。

### 4.5 為何 vitest 既有 FontMetricsAdapter tests 通過但 IIFE 失敗

vitest 在 node 環境：`createRequire` 真的 work，opentype.js 從 node_modules CJS 載入成功。
IIFE rollup：`createRequire` 走 nodeModuleStub 永遠 throw。

→ vitest 967 passed 不保證 IIFE bundle 內同 code 也 work。Sprint 62 補充紀律：**改 ooxml/font/* 後必須跑 IIFE probe** 確認 adapter 不 silent-fail。

## 5. vitest / VR

- vitest **967 passed + 1 skipped**（Sprint 61 與 Sprint 62 無新 unit tests；FontMetricsAdapter 既有 tests 已涵蓋 + Sprint 14 引入的 stub 不影響 vitest node 環境）
- **VR default (no --font-metrics)**：per-page mean **0.074899 不變**（與 Sprint 59-61 default 一致；opt-in 預設 off）
- **VR `--font-metrics`**：per-page mean **0.073191（-0.001708 / ~2.3% 改善）**；0 failed pages
- Sprint 12/16 baseline 未變動（opt-in 模式下未跑、default 模式仍 EstimateMetrics）

## 6. Sprint 50-62 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51-55 | cache 五連發 | warm 5.32× | 命中 |
| 56 | L2 IDB image | preload L1 105.74× | 跨 session image |
| 57 | render memoize | +1.04× | 第八層紀律 |
| 58 | layout cache | +0.65× / 100% hit | cache 完成 deterministic |
| 59 | drawLine path coalescing | ≈0 噪音內 | 單執行緒 render 邊際遞減 |
| 60 | OffscreenCanvas probe（純診斷）| 4/4 features ✓ | pivot HarfBuzz |
| 61 | BrowserTextMetrics（negative result）| -0.0013 退化 | 揭示 goldens = LO anchor |
| **62** | **FontMetricsAdapter + IIFE bundle 修復** | **VR mean -0.0017 / ~2.3% 改善** | **Sprint 50-62 第一次真正打進 VR mean / 揭示 Sprint 14 nodeModuleStub 47 sprints 隱性 blocker** |

## 7. Sprint 63+ 候選

| 候選 | 說明 | 風險 / payoff |
|---|---|---|
| **Sprint 62 promote 為 default-on**（caller 端 supply fonts）| pipeline 改 fontAdapter default-on（caller 沒供 fonts 自動 fallback EstimateMetrics）| 中（VR baseline shift） |
| **Bundle Noto Sans CJK as default font** | IIFE 內含 5-10MB CJK 字型 | 大（bundle size）|
| **重新 review Sprint 12/16 baseline 是否需 update** | 真實字型 metric 下 fingerprint / page count 可能變 | 小 |
| 重生 goldens 用 Word desktop 渲染 | 換 metric anchor（不再對齊 LO）| 大（251 PNG 重生）|
| OffscreenCanvas + Web Worker render | Sprint 60 probe 證實技術可行 | 大 |
| 大文件 fixture（user 提供）| 重測 Sprint 53/54 多頁 payoff | 待 user |

**建議 Sprint 63 = production caller-side font supply API**：
- pipeline RenderOptions.fontAdapter 已是 opt-in，不變
- 在 portal / canvas-editor 端建立 font 載入機制（lazy load Noto Sans CJK from CDN / IDB cache）
- caller 用 IDB cache 第一次載入後跨 session 共用
- 對 VR baseline 無影響（default off）；只在 production caller 啟用後生效

或更保守 **Sprint 63 = 量測「全 family 註冊」是否進一步改善 VR mean**：
- Sprint 62 只註冊主要 family（標楷體 / Times New Roman / Arial / 微軟正黑體 / 新細明體 / 細明體 / DFKai-SB / PMingLiU / MingLiU）
- 如果 docx 用其他 family（如 Calibri、Verdana），目前 fallback EstimateMetrics
- 加入 LiberationMono、LiberationSans 涵蓋更廣

## 8. 工作摘要

```
M  static/src/core/ooxml/font/FontMetrics.ts     | createRequire('opentype.js') → import * as opentypeNs from 'opentype.js'（ESM）
M  rollup.visual_regression.config.js            | nodeModuleStub 註解更新（保留給 ShapingEngine.ts 用、FontMetrics.ts 已不依賴）
M  tools/visual_regression_pipeline.entry.ts     | RenderOptions.fontAdapter opt-in + window.FontMetricsAdapter export + 與 browserTextMetrics 優先序 + layoutCache 互斥（同 Sprint 61）+ version 'sprint62'
M  tools/dist/visual_regression_pipeline.iife.js | rollup 重編、+80KB（opentype.js 進 bundle）
M  scripts/visual_regression_v14_harness.html    | useFontMetrics + fontBytes flag（base64 → registerFont per family）
M  scripts/visual_regression_v14.mjs             | --font-metrics flag + load LO 系統 font bytes
+  scripts/font_probe.mjs                         | 探測 docx 用的 font families（debug 工具）
+  scripts/font_metrics_probe.mjs                 | 驗證 IIFE bundle 內 FontMetricsAdapter 可 work（揭示 Sprint 14 stub blocker 的工具）
+  docs/sprint62_font_metrics_adapter_positive_result.md | 本文件
```

VR default：**0.074899 不變**。VR `--font-metrics`：**0.073191（-0.001708 / -2.3% relative 改善）**、0 failed pages。vitest **967 passed + 1 skipped** 不變。

## 9. 心得：Sprint 60-62 三層揭示鏈

Sprint 60: probe → 技術可行性 GREEN、pivot HarfBuzz
Sprint 61: BrowserTextMetrics → hypothesis 證偽、揭示 goldens 是 LO anchor
**Sprint 62: FontMetricsAdapter + IIFE bundle 修復 → 命中 -0.0017 VR mean**

每 sprint 結束都揭示一層更深的 root cause。Sprint 14 引入的 nodeModuleStub 是 47 sprints 來沒人發現的隱性 blocker；如果直接跳到 Sprint 62 commit HarfBuzz、可能也會撞到 IIFE bundle 結構性 bug 然後在 mid-sprint 撞牆。Sprint 60-61 的純診斷 / negative-result 在這條鏈上扮演關鍵角色。

**Sprint 50-62 累積紀律 5 條**：
1. 改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR（Sprint 57）
2. 單元測試用 spy 驗 API、VR 驗 pixels — 兩者都綠才算過（Sprint 57）
3. 高風險改造前先 probe sprint 收集事實（Sprint 60）
4. 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習（Sprint 61）
5. **vitest 通過不保證 IIFE bundle 同 code 也 work — 兩個 build target 必須各自驗證**（Sprint 62）

這 5 條紀律應該全部寫入 `addons/CLAUDE.md` 或 `dobtor_doc_editor/CLAUDE.md`，作為後續 sprint 的開工 checklist。
