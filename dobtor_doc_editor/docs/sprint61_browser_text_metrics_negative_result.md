# Sprint 61 — BrowserTextMetrics（負面結果、揭示 goldens 是 LibreOffice 渲染的隱性 metric anchor）

**期間**：2026-05-16
**主軸**：Sprint 60 probe 後重新評估 Sprint 61 = HarfBuzz / opentype.js 真實字型 metric；但 font 檔案 1-5MB 通常需 user 提供，本 sprint 走「canvas.measureText 真實字寬」alternative — 不需 font 檔案、用 browser 系統字型即可量真實 advance width。預期假設：真實字寬比 Sprint 28 empirical 1.15em 估算更準、VR mean -1~2pp 改善。
**結論**：**假設證偽** — `--browser-metrics` opt-in 模式 VR per-page mean **0.074899 → 0.076219（+0.0013、~1.8% relative 退化）**。原因揭示：**goldens 是 LibreOffice headless 渲染**（DPI 150、預設字型 fallback），與 puppeteer Chrome 系統字型 metrics 有 systematic offset；**Sprint 28 empirical CJK 1.15em 反而比 Chrome real metric 更接近 LibreOffice golden**。
**意義**：用 1 sprint 證偽 hypothesis、避開 Sprint 62 直接包 Chrome system fonts 的死路；指明真正的「VR 改善」必須讓 dobtor render path 與 LibreOffice 渲染對齊（HarfBuzz + 與 LO 預設相同的 font 檔案）。**BrowserTextMetrics architecture 完整保留為 opt-in**（pipeline / harness / unit tests 全部 working），不對 production 造成風險（default off, VR baseline 0.074899 不變）。

---

## 1. 動機 / 假設

Sprint 60 audit §3.2 評估 Sprint 61 候選兩條：
- HarfBuzz / opentype.js + font 檔案（需 user 提供）
- BrowserTextMetrics（不需 font）

選後者繞開 font 依賴。**Hypothesis**：用 canvas.measureText 取得真實字寬 → 取代 EstimateMetrics 1.15em（CJK）/ 0.5em（Latin）heuristic → layout 行寬計算更準 → wrap 行數更準 → VR mean 預估 -1~2pp。

## 2. 設計

### 2.1 [BrowserTextMetrics.ts](../static/src/core/layout/BrowserTextMetrics.ts)

```ts
class BrowserTextMetrics implements TextMetrics {
  // 用 canvas.measureText 量真實字寬；LRU 4096-entry cache
  measureWidth(text, props): Pt {
    if (!canvas) return fallback.measureWidth(...)  // node/vitest 環境
    key = "{bold}{italic}|{fontSize}|{family}|{text}"
    if cache.has(key): return cached + spacingExtra
    canvas.font = "{italic} {bold} {fontSize}pt {family}"
    width = canvas.measureText(text).width
    cache.put(key, width)
    return width + spacingExtra
  }
  measureLineHeight(props): Pt {
    return fallback.measureLineHeight(props)  // canvas API 不可靠
  }
}
```

**關鍵設計**：
- Sprint 28 empirical 1.15em 修正只在 fallback EstimateMetrics 內、不影響 BrowserTextMetrics
- 非 browser 環境（vitest happy-dom getContext 回 null）→ 自動 fallback
- spacing 後處理（cache key 不含 spacing、每次 measure 額外加）
- 14 個 unit tests 全綠（mock canvas + LRU + fallback + spacing）

### 2.2 pipeline 整合（opt-in）

[`tools/visual_regression_pipeline.entry.ts`](../tools/visual_regression_pipeline.entry.ts)：
```ts
RenderOptions.browserTextMetrics?: BrowserTextMetrics | boolean

// render() 內：
if (options.browserTextMetrics) {
  const metrics = options.browserTextMetrics instanceof BrowserTextMetrics
    ? options.browserTextMetrics
    : new BrowserTextMetrics();
  effectiveLayoutOptions = { ...effectiveLayoutOptions, metrics };
}
// 注意：layoutCache 與 browserTextMetrics 互斥（metrics 是 caller-injected instance、
// 序列化進 layoutOptions hash 不穩定 → 暫不快取此模式的 layout）
```

harness `useBrowserMetrics` flag + perf_baseline 走 `useBrowserMetrics: true` 經 pipeline 注入。

## 3. 結果 — Hypothesis 證偽

### 3.1 VR mean 量測

| 模式 | per-page mean | failed pages | 對 baseline 影響 |
|---|---|---|---|
| Sprint 50-58 baseline（EstimateMetrics） | 0.074895 | 0 | — |
| Sprint 59-60（path coalescing + probe） | 0.074899 | 0 | +0.000004 微 jitter |
| **Sprint 61 `--browser-metrics`（opt-in）** | **0.076219** | **0** | **+0.001320（~1.8% relative 退化）** |

**完全反向預期**：VR mean **變差** +0.0013，而非預期改善 -1~2pp。

### 3.2 per-category 比對

| category | n pages | --browser-metrics mean |
|---|---|---|
| 01_simple | 21 | 0.0696 |
| 02_std_table | 14 | 0.0917 |
| 03_complex_table | 11 | 0.1314 |
| 04_with_image | 28 | 0.1308 |
| 05_header_footer | 45 | 0.0354 |
| 06_template | 7 | 0.0221 |

→ 各 category 變化分散；表格密集（02/03）小幅改善、影像密集（04）小幅退化、純文字（05_header_footer）幾乎不變。淨值退化。

### 3.3 為什麼證偽：goldens 的隱性 metric anchor

關鍵發現：**goldens 是 LibreOffice headless 渲染**（[Sprint 14 audit](sprint14_visual_regression.md) 記錄 `libreoffice --headless --convert-to pdf` 路徑）。

意義：
1. LibreOffice headless 用 **自帶 fontconfig fallback 鏈**（Linux server 通常包 Noto Sans CJK / DejaVu）
2. puppeteer Chrome 用 **作業系統字型 fallback**（puppeteer 跑在 WSL2 Linux、Chrome bundled fonts + 系統可用字型）
3. 兩條 fallback 鏈雖然都 Linux、字型可用性與行為**不一致**
4. Sprint 28 的 1.15em CJK empirical 修正是針對「dobtor render 對齊 LibreOffice golden」校準
5. 換成 Chrome 真實 metric 等於把 dobtor 移向 Chrome 系統字型 — **離 LibreOffice golden 更遠**

→ **VR mean 衡量的是「dobtor 像不像 LibreOffice」，不是「dobtor 像不像 Word」**。

### 3.4 對 Sprint 28 empirical 1.15em 的重新認識

Sprint 28 audit 記錄：
> CJK em 1.00→1.10→1.15 三次測試；1.15 修最多 fixture（+2 修復）且零退化。剩 3 個 -1 fixture（02 工地密度 + 03 估驗計價 ×2）root cause 不在 CJK 字寬。

**Sprint 28 校準是針對 LibreOffice golden 的 best fit**。Sprint 61 的 Chrome real metric 比 1.15em 偏離 LibreOffice 更多 — 退化證實這點。

如果 goldens 改成 Word desktop 渲染（或 Word online），結果可能反向 — 但這需要重新生成全部 251 PNG goldens、且 Word render 對齊度也非保證。

## 4. 為何負面結果仍有價值

### 4.1 用 1 sprint 證偽避開 Sprint 62 直接包 Chrome system fonts 死路

原計劃 Sprint 61 = BrowserTextMetrics、Sprint 62 = 若 BrowserTextMetrics 有效則加 font 微調或 promote default。

實證 Sprint 61 退化 → **不需要 Sprint 62 follow-up**。直接跳到「攻 LibreOffice fallback 鏈」路徑。

### 4.2 揭示 goldens 的隱性 metric anchor — 後續決策依據

未來任何「攻 VR mean」sprint 都必須先回答：**目標是接近 LibreOffice golden、還是接近真實 Word 渲染？**
- 如果接近 LibreOffice：HarfBuzz + bundled Noto Sans CJK（LO 預設 CJK 字型）
- 如果接近 Word：可能需要 Word-installed font subset + Word's specific kerning rules
- 兩者結果不同；ChienYi production 用戶看到的是 Word render（user 用 Word 編輯），但 VR mean 是 LibreOffice anchor

→ 這個矛盾在 Sprint 50-60 都被「直接比 mean 數字」掩蓋；Sprint 61 透過實證揭示。

### 4.3 BrowserTextMetrics architecture 完整保留

雖然 default-off、Sprint 61 不 promote 為 default，但 architecture 完整：
- pipeline opt-in flag working
- 14 unit tests covering LRU / fallback / cache key
- harness flag for VR re-evaluation 未來 sprint
- 若未來 goldens 改用 Chrome 渲染（或更接近 Chrome 渲染的 fixture），BrowserTextMetrics 可立即激活

### 4.4 Sprint 50-60 紀律延伸：高風險改造前先 probe（Sprint 60）+ 假設證偽 sprint 仍有結構價值（Sprint 61）

Sprint 50-60 累積三大紀律：
1. 改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR（Sprint 57）
2. 單元測試用 spy 驗 API、VR 驗 pixels — 兩者都綠才算過（Sprint 57）
3. 高風險改造前先 probe sprint 收集事實（Sprint 60）

Sprint 61 補充：
4. **假設證偽 sprint 仍有結構價值** — opt-in、default off、infrastructure 留作可重啟，但記錄為 "假設未命中" 給後續 sprint 做 navigation

## 5. Sprint 62+ 候選（Sprint 61 結果重新評估）

| 候選 | 對應目標 | 評估 |
|---|---|---|
| **HarfBuzz + Noto Sans CJK font bundle** | 對齊 LibreOffice golden 渲染（LO 預設 CJK fallback = Noto Sans CJK）| 🟢 Sprint 62 首選 — 直接對齊 golden 的 metric source |
| OffscreenCanvas + Web Worker render | UI 不阻塞 | 🟡 Sprint 63+ — VR 收斂後再投資 perf 路徑 |
| 重生 goldens 改用 Chrome 渲染 | 換 metric anchor、激活 BrowserTextMetrics | 🔴 副作用太大（251 PNG 重生 + 失去 Sprint 28 校準） |
| EstimateMetrics 1.15em 微調 per-fontFamily | 在 LibreOffice anchor 內細調 | 🟡 邊際小 |
| 大文件 fixture 50+ 頁 | 重測 perf 多頁 payoff | 🟡 待 user 提供 |

**建議 Sprint 62 = HarfBuzz + Noto Sans CJK font bundle**：
- 直接對齊 LibreOffice golden 的 metric source（LO 預設 fontconfig fallback 鏈含 Noto Sans CJK）
- FontMetricsAdapter 骨架已存在（Sprint 8）
- 預估 VR mean -1~2pp 應該成立（這次的 metric 真的對齊 golden source）
- Bundle size 是 trade-off（Noto Sans CJK SC subset ~5-10MB；可 lazy load 或 server-side render）

## 6. vitest / VR

- vitest **953 → 967 passed + 1 skipped**（+14 BrowserTextMetrics 測試）
- **VR default behavior**：per-page mean 0.074899 不變（與 Sprint 59-60 完全一致；browserTextMetrics opt-in default off）
- **VR with `--browser-metrics` flag**：per-page mean 0.076219（**+0.001320 退化、假設證偽**）
- Sprint 12/16 baseline 未變

## 7. 工作摘要

```
+  static/src/core/layout/BrowserTextMetrics.ts   | 新增 ~155 行 — canvas.measureText 真實字寬、LRU cache、fallback EstimateMetrics
+  tests/unit/layout/BrowserTextMetrics.test.ts    | 14 unit tests（mock canvas + LRU + fallback + spacing）
M  tools/visual_regression_pipeline.entry.ts     | RenderOptions.browserTextMetrics opt-in + window.BrowserTextMetrics export + layoutCache 與 browserTextMetrics 互斥邏輯（避免 cache key 不穩）+ version 'sprint61'
M  tools/dist/visual_regression_pipeline.iife.js | rollup 重編
M  scripts/visual_regression_v14_harness.html    | useBrowserMetrics flag
M  scripts/visual_regression_v14.mjs             | --browser-metrics flag 傳給 harness
M  tests/fixtures/visual_regression_v14_report.json | Sprint 61 量測結果（with --browser-metrics）
+  docs/sprint61_browser_text_metrics_negative_result.md | 本文件
```

VR default：**0.074899 byte-identical 不變**。VR opt-in `--browser-metrics`：**0.076219（+0.001320 退化、hypothesis 證偽）**。vitest **967 passed + 1 skipped**。

## 8. 心得：負面結果是真實學習

Sprint 50-60 perf 路線連續 5 sprints 漂亮 +1.04× / +0.65× / ≈0 / probe；Sprint 61 是**第一個明確 negative result 的 sprint**。

如果只看 mean 數字，這 sprint 像「失敗」。但如果看「我們學到什麼」：
1. **goldens 是 LibreOffice 渲染、不是 Word／不是 Chrome** — 過去 50+ sprints 都沒人明確檢視這個 anchor
2. **Sprint 28 的 1.15em 不是隨意 magic number、是經驗校準 LibreOffice 的 best fit**
3. **未來 VR mean 改善必須對齊 goldens 的 metric source**（LO + Noto Sans CJK），不能用任意 real metric

這比「再多收割 0.5pp speedup」更有商業價值 — 因為 ChienYi production 的 VR mean 目標應該對齊 **Word real render**，不是 LibreOffice。Sprint 50-60 一直在校準錯誤的 anchor 卻沒人發現。

Sprint 62+ 路線值得重新考慮：
- 短期：HarfBuzz + Noto Sans CJK 對齊 LibreOffice goldens（VR mean 數字會好看）
- 中期：重生 goldens 用 Word desktop 渲染（VR mean 對齊真實使用者觀感）
- 長期：兩套 goldens 共存（VR-LO + VR-Word）作為雙軌品質衡量

這份 audit 不只是「Sprint 61 做了什麼」，更是 **Sprint 50-60 mean 數字的隱含假設揭示**。負面結果 + 隱性 anchor 揭示 = 結構價值。
