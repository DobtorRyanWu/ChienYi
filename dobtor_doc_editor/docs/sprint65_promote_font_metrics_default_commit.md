# Sprint 65 — Promote `--font-metrics` 為 VR default-on（commit + baseline 重設）

**期間**：2026-05-16
**主軸**：Sprint 60-64 五個 sprints data backing 完成；Sprint 64 audit 列出 commit 路徑；本 sprint 執行 mechanical commit — VR script default 改為 `--font-metrics` enabled、VR baseline 從 0.074899 重設為 0.073191、加 `--no-font-metrics` flag 保留 legacy 對照。
**結論**：
- ✅ VR script default 變更（`args.fontMetrics: false → true`）；新 `--no-font-metrics` flag 退回 legacy 0.074899 baseline
- ✅ **VR baseline 0.074899 → 0.073191（-0.001708 / -2.3% relative 改善 lock-in）**、0 failed pages
- ✅ Legacy mode 仍可用：`node scripts/visual_regression_v14.mjs --no-font-metrics` → 0.074899（與 Sprint 50-64 相容）
- ✅ vitest **967 passed + 1 skipped** 不變（vitest 走 layoutDocument 直接呼叫 + 預設 EstimateMetrics、不受影響）
- ✅ Sprint 12/16 baseline **未更新**（vitest integration tests 仍以 EstimateMetrics 校準、production-default 行為一致）
- ✅ production code 無實質改變：pipeline `RenderOptions.fontAdapter` 仍是 opt-in、caller 沒供 fontAdapter 就 fallback EstimateMetrics
- 🟡 Sprint 64b external = portal/canvas-editor font 供應策略 A/B/C 仍待 user 認可（不在本 sprint 範圍）

---

## 1. 範圍

Sprint 64 audit §4.2 列出 6 步 commit 路徑，但仔細審視後**精簡**為 mechanical VR baseline 重設：

| 步驟 | Sprint 64 audit 列出 | Sprint 65 實際 | 為何 |
|---|---|---|---|
| 1 | 修 entry.ts：fontAdapter 自動 try-build | ❌ 不做 | browser context 無 fs 讀字型、自動 try-build 在 puppeteer 環境會空、production 環境取決於 caller；保持 opt-in 更清楚 |
| 2 | 修 layoutOptions.metrics default | ❌ 不做 | layoutDocument 預設 EstimateMetrics 與 vitest 整合測試行為一致；production-default 不應強制改 |
| 3 | vitest -u Sprint 12 snapshot | ❌ 不做 | vitest 走 EstimateMetrics、fingerprint 不變；無需更新 |
| 4 | **VR baseline 0.074899 → 0.073191** | ✅ 做 | VR script default 改為 `--font-metrics` enabled；新 baseline lock-in |
| 5 | CI 跑 vitest confirm 967 | ✅ 做 | 已確認、不變 |
| 6 | 跑 VR confirm mean 0.073191 | ✅ 做 | 已確認 |

**簡化理由**：Sprint 64 audit 預期是「全鏈條 promote」，但實際分析：
- vitest 從不經過 puppeteer pipeline → 改 vitest 整合測試需另外注入 fontAdapter
- production code (`pipeline.render()`) caller 沒供 fontAdapter 就走 EstimateMetrics → 與 Sprint 50-64 完全相容
- **只有 VR script 是 metric-anchor 的衡量介面** — 改它的 default 等於「VR baseline 從此用 font-metrics 衡量」

Sprint 65 範圍 = **VR baseline 衡量基準的 commit**，不是 production code commit。

## 2. 變更內容

### 2.1 [`scripts/visual_regression_v14.mjs`](../scripts/visual_regression_v14.mjs)

**Diff**：
```js
const args = {
  filter: null, maxFixtures: Infinity,
  maxDiff: 0.5, noDiff: false, headful: false,
  browserMetrics: false,
- fontMetrics: false,
+ fontMetrics: true,  // Sprint 65 default
};
// argv loop:
+ else if (a === '--no-font-metrics') args.fontMetrics = false;
```

行為改變：
- `node scripts/visual_regression_v14.mjs` → 預設 load LO 系統 fonts (DroidSansFallback + LiberationSerif) + 注入 pipeline + VR mean = 0.073191
- `node scripts/visual_regression_v14.mjs --no-font-metrics` → 退回 EstimateMetrics + VR mean = 0.074899（legacy / debug 用）
- `--font-metrics` flag 仍接受（向後相容 Sprint 62 寫法）

### 2.2 production code 範圍 — **無實質改變**

| 模組 | Sprint 65 後行為 | 與 Sprint 64 比較 |
|---|---|---|
| `RenderOptions.fontAdapter` | opt-in、caller 沒供 → fallback EstimateMetrics | 完全相同 |
| `layoutDocument(sections, opts)` | opts.metrics 沒供 → EstimateMetrics | 完全相同 |
| `OoxmlParser` / `CanvasRenderer` | 完全不變 | — |
| IIFE bundle | 已含 opentype.js（Sprint 62 包入）| 大小不變 |
| vitest 整合測試 | 走 EstimateMetrics、967 passed | 不變 |

→ Sprint 65 **沒改 production code**；改的是「VR 衡量介面的 default 行為」。

### 2.3 Sprint 12/16 vitest baseline — **未更新**

Sprint 64 probe 顯示若 vitest 整合測試改用 FontMetricsAdapter，Sprint 12 fingerprint 會全 42 fixture 變化。**Sprint 65 不做這個改動**，理由：
- vitest 走 layoutDocument 直接呼叫、不經 puppeteer pipeline
- production caller 也走 layoutDocument 直接、default EstimateMetrics
- 若改 vitest integration test 默認注入 fontAdapter、會與 production caller 行為脫鉤
- 真要改、需要 user 認可：vitest 整合測試的 default metrics 是否應 follow VR baseline

→ Sprint 12/16 baseline 仍是 EstimateMetrics 校準、保留為 production-default 行為的 lock。Sprint 65 commit 只動 VR 衡量介面。

## 3. 驗證

| 驗證項 | 結果 |
|---|---|
| `node scripts/visual_regression_v14.mjs` | per_page_mean = **0.073191**、0 failed pages、42 rendered |
| `node scripts/visual_regression_v14.mjs --no-font-metrics` | per_page_mean = **0.074899**（legacy）、0 failed pages |
| `npx vitest run` | **967 passed + 1 skipped**（不變）|
| Sprint 12 fingerprint snapshot | 不變（vitest 不受影響）|
| Sprint 16 page count snapshot | 不變（vitest 不受影響）|
| production `pipeline.render()` 行為 | 不變（opt-in fontAdapter）|

## 4. 對 Sprint 50-64 baseline 的影響

| Sprint | 引用基準 | Sprint 65 後行為 |
|---|---|---|
| 50-58 perf 基準 | full-warm 7.01× speedup | **不變** — perf 路徑用 default 模式跑、VR 對 perf 是 byte-identical concern、不受 metric anchor 影響 |
| 59 path coalescing | VR shift +0.000004 | **不變** — micro-jitter 對 EstimateMetrics 和 FontMetricsAdapter 都同樣存在 |
| 60 OffscreenCanvas probe | 純診斷 | 不適用 |
| 61 BrowserTextMetrics negative | -0.0013 退化 | 仍 negative — 但意義從「對 0.074899 baseline 退化」變為「對 0.073191 baseline 更退化」 |
| 62 FontMetricsAdapter positive | -0.0017 改善 | **內化** — 改善已 lock-in 為新 baseline、不再是 opt-in delta |
| 63 per-fixture delta | 0 regression | 仍有效 — 5 大贏家分佈不變 |
| 64 baseline drift probe | page 0/42、ops 0/42、fp 42/42 | 仍有效 — 但 fp drift 不影響 vitest（vitest 不受改）|

→ Sprint 50-64 所有結論仍有效；只有「VR baseline 數字」從 0.074899 → 0.073191。

## 5. 對 Sprint 66+ 的指引

**Sprint 65 commit 後，未來 VR sprint 應該注意**：

1. **新 PR 的 VR mean 對標 0.073191**（不是 0.074899）
2. **Regression threshold**：個別 fixture 變化 > 0.001 視為值得 review；> 0.01 視為退化
3. **如果想對照舊基準**：`--no-font-metrics` 仍可重現 0.074899
4. **Sprint 12/16 baseline 仍是 EstimateMetrics 校準** — 改 vitest 行為前需 user 認可
5. **production caller 啟用 fontAdapter 後**：portal/canvas-editor 端載 fonts、用戶看到的 render 對齊 LO golden（與 VR mean 一致）

### 5.1 Sprint 66 候選（仍待 Sprint 64b user 認可）

- **Sprint 64b external（待 user）**：portal/canvas-editor font 供應策略 A/B/C
- **Sprint 66**：重生 goldens 用 Word desktop 渲染（換 metric anchor、副作用大）
- **Sprint 67+**：OffscreenCanvas + Web Worker render（Sprint 60 probe 已證實可行）
- **Sprint 55-original 延後**：大文件 50+ 頁 fixture 收集
- **長期 backlog**：Web Worker parse / docGrid snap 判別子 / GPU canvas / 雙軌 VR

## 6. Sprint 50-65 軌跡（VR mean 視角）

| Sprint | 量測 | 累積意義 |
|---|---|---|
| 50-58 | cache / memoize / layout cache | perf 路徑 warm 7.01× |
| 59 | drawLine path coalescing | 邊際遞減 |
| 60 | OffscreenCanvas probe | 純診斷、可行 GREEN |
| 61 | BrowserTextMetrics negative | -0.0013 揭示 LO anchor |
| 62 | FontMetricsAdapter + IIFE 修復 | VR -0.0017 第一次打進 |
| 63 | per-fixture delta（純診斷）| 5 大贏全 03 全套管、0 regression |
| 64 | baseline drift probe（純診斷）| page 0/42、ops 0/42、fp 42/42 |
| **65** | **VR baseline commit 0.074899 → 0.073191** | **Sprint 60-64 5 sprints data backing 的內化點** |

## 7. 工作摘要

```
M  scripts/visual_regression_v14.mjs              | fontMetrics default false → true；加 --no-font-metrics flag
M  tests/fixtures/visual_regression_v14_report.json | 新 default 跑出來的 0.073191 report
+  docs/sprint65_promote_font_metrics_default_commit.md | 本文件
```

無 production code 變動、無新 unit test、Sprint 12/16 baseline 未動。

## 8. 心得：mechanical commit 是 5 sprints 紀律的內化

Sprint 60-65 六個 sprint 圍繞「FontMetricsAdapter 從假設到 VR baseline」：

- Sprint 60 probe：技術可行性
- Sprint 61 negative result：揭示 LO anchor
- Sprint 62 IIFE bundle 修復：實際命中 -0.0017
- Sprint 63 per-fixture delta：量化零 regression
- Sprint 64 baseline drift probe：量化 page/ops 零變動
- **Sprint 65 mechanical commit：把 Sprint 60-64 的所有 data backing 內化為新 baseline**

Sprint 65 的「commit」本質上是 mechanical — 一個 flag default 翻轉。但這個翻轉**只能在 Sprint 60-64 5 sprints 全部通過之後做**。直接從 Sprint 59 跳到 Sprint 65 不可能 — 沒做 Sprint 61 negative result 不會知道要選 DroidSansFallback、沒做 Sprint 62 不會修 IIFE bundle、沒做 Sprint 63/64 不會知道 promote 是否安全。

**5 sprints 紀律性投資 = 1 sprint mechanical commit。** 這比「Sprint 60 直接 commit HarfBuzz + Noto Sans CJK」更穩、更便宜。

**Sprint 50-65 累積純診斷 sprint = 7 個**（36/43/46/49/60/63/64）= 全 66 sprints 內 ~11% 比例。健康工程紀律。

**Sprint 50-65 累積紀律 6 條全部驗證**：
1. ✅ 改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR（Sprint 57）
2. ✅ 單元測試用 spy 驗 API、VR 驗 pixels — 兩者都綠才算過（Sprint 57）
3. ✅ 高風險改造前先 probe sprint 收集事實（Sprint 60）
4. ✅ 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習（Sprint 61）
5. ✅ vitest 通過不保證 IIFE bundle 同 code 也 work（Sprint 62）
6. ✅ Promote default 前先做 per-fixture delta 分析（Sprint 63）

Sprint 65 補一條（第 7 條）：
7. **Mechanical commit 是多 sprint 紀律性投資的內化** — 不是 commit 才有 value、是 commit 之前的 5 sprints 才讓 commit 能站住腳
