# Sprint 55 — Full-Warm Benchmark（AST + image cache 合用驗證）

**期間**：2026-05-15
**主軸**：Sprint 54 audit headline 推算「Sprint 51+54 疊加 8.1× speedup on image-heavy 重開」是估算值、未直接量測。本 sprint 加 `--full-warm` 模式（同時啟用 AST cache + image cache），對 42 fixture 做完整 cold-vs-warm 量測，驗證疊加效益並暴露 Sprint 54 推算的盲區。
**結論**：**全 42 fixture full-warm total speedup = 5.32×（cold 12150ms → warm 2282ms）**；parse 100% 消除、preload 99.8% 消除、render 63.4% 消除（render 大幅減少主要為 V8 JIT warm-up，不是 cache 效應）。**Sprint 54 預估的 8.1× 在 04/05.磺港溪監造會議照片 命中（8.86-9.78×），但 04/06.環清表 6p 系列實測只 1.39-4.50×** — Sprint 54 推算太樂觀，render 占 image-heavy 6p 文件 warm path 主成本，cache 救不了。

**重要意義**：Sprint 51-54 五連發 cache 層級到此告一段落 — 接下來的優化必須攻 render 段才能進一步提速；image-heavy 多頁文件 warm 後 render 仍是瓶頸。VR 維持 0.0749、vitest 896 passed（本 sprint 不增單元測試）。

---

## 1. 動機：驗證推算 vs 實測

Sprint 54 audit §4 表格寫了：

> | + Sprint 54 image cache | warm **~80ms**（parse 0 + preload 2 + render 78）= **8.1× speedup** |

這是 **推算值**：parse 0（AST cache）+ preload 2（image cache）+ render 78（cold 時 render 79）。隱含假設 = render 在 warm 等於 cold。

但實測 Sprint 54 --image-cache 結果 total 速度只 2.03×、Sprint 51 --cache 結果 4.79× — 兩者各別測都不到 8×。8.1× 是「合用」推算，**從未真量測**。本 sprint 補上。

## 2. 設計

### 2.1 `--full-warm` 模式

[scripts/perf_baseline.mjs](../scripts/perf_baseline.mjs) 加 `--full-warm` 旗標，等價於同時 `--cache --image-cache`，但加：
- `fullWarmSummary` 區段：總體 cold/warm + 各階段消除程度
- per-fixture 印表顯示 `(parse {X→Y} / preload {A→B} / render {C→D})` 三段對比
- 互斥：fullWarm 開時 cacheSummary / imageCacheSummary 自動 suppress，避免重複輸出

### 2.2 量測方法

同 Sprint 51 模式：每份 fixture 在同一 puppeteer page 跑 3 次：
- run 0：`clearCacheFirst:true, clearImageCacheFirst:true` → 雙 cache 都清掉、cold parse+preload
- run 1, 2：warm（雙 cache 命中）

`fx.cold = run 0`，`fx.warmMedian = median(run 1, run 2)`。

## 3. 結果

### 3.1 全域（42 fixture 加總）

| 階段 | cold | warm | 消除程度 |
|---|---|---|---|
| **parse** | 5271ms | **0.9ms** | **100.0%** |
| **preload** | 919.5ms | **1.8ms** | **99.8%** |
| **render** | 5443ms | **1991ms** | **63.4%** |
| layout | (~120) | (~184) | n/a（噪音）|
| hash（warm only）| — | 104ms | — |
| **total** | **12150ms** | **2282ms** | **5.32× speedup** |

### 3.2 分類速率

| 分類 | n | cold total | warm total | speedup |
|---|---|---|---|---|
| 01_simple | 7 | 2688ms | 710ms | **3.78×** |
| **02_std_table** | 8 | 2466ms | 231ms | **10.66×** |
| **03_complex_table** | 8 | 1484ms | 178ms | **8.34×** |
| 04_with_image | 6 | 1954ms | 554ms | **3.53×** |
| 05_header_footer | 10 | 3029ms | 534ms | **5.67×** |
| 06_template | 3 | 529ms | 74ms | **7.12×** |

### 3.3 Top speedup fixture（最樂觀情境）

| fixture | pc | cold | warm | speedup |
|---|---|---|---|---|
| 02_std_table/1121006-週報 | 2p | 431 | 30 | **14.51×** |
| 02_std_table/1121027-週報 | 2p | 420 | 29 | **14.47×** |
| 03_complex_table/1130516-鋼筋查驗 | 1p | 171 | 12 | 14.27× |
| 03_complex_table/1130105-全套管 | 1p | 167 | 13 | 12.63× |
| 02_std_table/1120928-週報 | 2p | 469 | 38 | 12.39× |

→ 小 1-2 頁 parse-heavy 文件達 12-15× speedup。

### 3.4 04_with_image 系列實測（揭穿 Sprint 54 推算）

| fixture | pc | imgs | cold | warm | speedup |
|---|---|---|---|---|---|
| 04/05.112磺港溪監造會議照片 | 2p | — | 238 | 27 | **8.86×** ← 命中 Sprint 54 預估 8.1× |
| 04/05.112磺港溪監造會議照片1120923 | 2p | — | 232 | 24 | **9.78×** ← 命中 |
| 04/06.環清表-(112.10.23.-10.27) | 6p | 6 | 296 | 213 | **1.39×** ← 大幅低於預估 |
| 04/06.環清表-(112.10.9.-10.13) | 6p | 6 | 409 | 111 | **3.68×** ← 低於預估 |
| 04/6.環清表-(112.10.2.-10.6) | 6p | 6 | 472 | 105 | **4.50×** ← 低於預估 |
| 04/6.環清表-(112.9.25.-9.29) | 6p | 6 | 308 | 74 | **4.14×** ← 低於預估 |

**Sprint 54 audit 預估 8.1× 在環清表 6p 系列 = 樂觀推算。實測平均 ~3.4×**。原因：環清表 6p 含 6 張大照片，**render 階段才是 warm 後主成本**，cache 救不了 render（圖照大、繪製 ops 多）。

## 4. 爭議點 / 重要發現

### 4.1 render 63.4% 消除來自何處

cache 沒打中 render（AST cache 跳過 parse、image cache 跳過 preload，但 CanvasRenderer.render 仍每次跑）。為何 render 從 5443ms 砍到 1991ms？

→ **V8 JIT warm-up**：warm runs 在同 page 內已 inline cached、hot path 編譯完成。這在 Sprint 51/54 各別量測時也看到（Sprint 54 total 2.03× 主要是 JIT 效應、非純 image cache）。

意義：**生產環境（每次重開 fresh JS context）拿不到這 63.4% render 消除**。Sprint 51 IDB persist 場景（page2 fresh JS）已驗證 — warm-from-IDB 比 warm-from-L1 慢 ~103ms/fixture，多的就是 V8 cold start 開銷。

### 4.2 Sprint 54 推算 8.1× 為何在 6p 環清表上不成立

Sprint 54 audit table 估算 04_with_image/06.環清表 cold 645ms → warm ~80ms。實測 cold 296-472ms（不是 645ms）、warm 74-213ms（不是 80ms）。

兩處錯誤：
1. **cold 數字選錯**：Sprint 54 audit 採 Sprint 50 baseline 量測（10.23-10.27 那份 645ms），但同 page 同 fixture 不同 puppeteer run 變異大；本 sprint 用合用模式直接量到 cold 296-472ms
2. **warm 推算忽略 render 變異**：80ms 估值來自「parse 0 + preload 2 + render 78」，但 render 在不同 6p 環清表變動 74-213ms

正確 headline 應為：「**Sprint 51+54 疊加：小 1-2p 文件 9-14× speedup；大 6p image-heavy 文件 1.4-4.5× speedup**」— 與 Sprint 51 各別量測比，combined 多出 1-4× 收益不等。

### 4.3 render 是新主成本：Sprint 56+ 該攻什麼

warm path 已是 render-bound（87.3% renderMs 占比）。下一步攻 render 的選項：
- **可視頁虛擬化**：Sprint 53 已做、payoff 受限於 fixture ≤6p、待 50+ 頁 fixture 真正放大
- **Image decode → ImageBitmap + IDB**：Sprint 56 候選；改用 createImageBitmap 拿可序列化 decode 結果進 IDB，跨 page reload 命中
- **CanvasRenderer fast path**：繪圖 ops 優化（避免重複 setState、合併連續 drawText）
- **HarfBuzz/opentype.js 真實字型 metric**：層級不同，主攻 VR 視覺，順帶 layout 收益

## 5. Sprint 56+ 候選

| 候選 | 打中的段 | 槓桿 | 風險 |
|---|---|---|---|
| **ImageBitmap + IDB 跨 page 持久化** | preload 跨 tab、warm 後 render | 跨 session 重開命中 + 解碼結果重用 | 中 |
| **可視頁虛擬化大文件 fixture 驗證** | render 多頁文件 | Sprint 53 預測 50+ 頁 payoff 放大 | 需內容 |
| **CanvasRenderer fast path** | render ops 直接優化 | warm 後最主成本（87.3%）| 中 |
| HarfBuzz / opentype.js | layout/render 質量 + VR mean | 預估 -1~2pp + 順帶 metric 提速 | 大 |

**建議 Sprint 56 = ImageBitmap + IDB**：Sprint 54 audit 已寫好計畫、技術風險可控（createImageBitmap 是標準 API）、production 價值具體（跨 tab 命中）。

## 6. vitest / VR

- **vitest 896 passed + 1 skipped**（本 sprint 不增單元測試 — 只動 perf_baseline.mjs 腳本、core/entry/IIFE 完全未變）
- **VR 0.0749 byte-identical**（IIFE 未 rebuild、行為與 Sprint 54 完全相同）
- Sprint 12/16 baseline 未變動

## 7. 工作摘要

```
M  scripts/perf_baseline.mjs                 | --full-warm 模式 + fullWarmSummary 區段 + per-fixture combined print；suppress duplicate summaries 當 fullWarm on
M  tests/fixtures/perf_baseline_report.json  | 加 fullWarmSummary
+  docs/sprint55_full_warm_benchmark.md      | 本文件
```

VR：**0.0749**。vitest **896 passed + 1 skipped**。**full-warm 5.32× total speedup**；分類速率 3.5-10.7×；6p image-heavy 1.4-4.5×；揭穿 Sprint 54 推算 8.1× 在 6p 環清表的盲區。

## 8. Sprint 50-55 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51 | L1 AST cache | warm 4.79× | 同 session 命中 |
| 52 | L2 IDB AST | 跨 page 2.38× / L1 7.41× | 跨 session 命中 |
| 53 | 可視頁虛擬化 | render 1.06× / 3p+ 1.16-1.43× | 多頁 payoff、≤6p 限制 |
| 54 | image decode L1 | preload 29.05× / image-bearing 100% hit | 重開含照片文件加速 |
| **55** | **合用驗證量測** | **full-warm 5.32× / 6p image-heavy 實測 1.4-4.5× / 小 1-2p 達 9-14×** | **暴露 render 是新主成本（87.3%）；下一步攻 render 段** |

**心得**：Sprint 55 是「對自己 audit 推算的誠實驗證」—— Sprint 54 audit 寫了 8.1× 推算 headline，本 sprint 直接量測發現只在 2p 文件命中、6p 環清表只 1.4-4.5×。這種「主動驗算自己推算」的紀律比繼續推進新功能更重要：把 Sprint 50-54 的 cache 五連發劃出明確邊界，標出 render 段才是 Sprint 56+ 的攻擊目標。
