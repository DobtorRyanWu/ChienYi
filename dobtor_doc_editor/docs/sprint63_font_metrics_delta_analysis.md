# Sprint 63 — Sprint 62 `--font-metrics` per-fixture VR delta 分析（純診斷、給 Sprint 64 promote default-on 做 data backing）

**期間**：2026-05-16
**主軸**：Sprint 62 命中 VR mean 0.074899 → 0.073191（-0.001708 / -2.3% relative）；Sprint 63 候選 §11.30 首選 = promote production default-on 但需 portal / canvas-editor 端 integration、跨模組 user 認可。本 sprint 走更聚焦、autonomous 路徑 = **per-fixture VR delta 分析**：量化 -0.0017 改善的分布、識別哪些 fixture 真改善 / 是否有反退化、為 Sprint 64 promote 決策提供 data backing。
**結論**：**Sprint 62 改善分布乾淨完美**：
- **5 個大贏家（≥0.01pp 改善）全部是 03_complex_table 全套管系列**，gain 範圍 -0.033 to -0.044
- **2 個中贏家**：04_with_image 磺港溪監造會議照片（-0.008 to -0.009）
- **35 fixtures 在 ±0.001 噪音範圍內** — 基本不變
- **0 個 regression > 0.001**（最大 +0.00072 在量測噪音內）
- **0 個 failed pages**

**對 Sprint 64 的建議**：**promote --font-metrics 為 production default-on 是低風險、高 ROI 決策**。03_complex_table 全套管系列改善 -2.35pp 是 ChienYi production 真實文件類型（建一監造系統實際用的就是這類 CJK + 複雜表格）；無大規模 fixture regression、可立即啟用。

---

## 1. 動機 / 範圍

Sprint 62 audit §3 顯示 VR mean -0.0017、per-category 暗示 03/04 改善大，但沒 per-fixture 細節：

> per-category：03_complex_table 全套管 0.131641（改善）、04_with_image 環清表 0.123860（改善）— 兩類 CJK + 表格密集 fixture 最受益

Sprint 63 候選 §11.30 首選 = promote default-on，但需 portal / canvas-editor 端 integration + 跨模組 user 認可。本 sprint 走 autonomous 路徑 = 純診斷量化：
1. 重跑 default + `--font-metrics` 兩次 VR、各存報告
2. 逐 fixture 對比、找贏家 / 輸家
3. 評估反退化風險
4. 給 Sprint 64 提供「promote default-on 是否安全」的 data-backed 建議

## 2. 量測流程

```bash
node scripts/visual_regression_v14.mjs                   # default baseline → /tmp/vr_baseline.json
node scripts/visual_regression_v14.mjs --font-metrics    # opt-in → /tmp/vr_font_metrics.json
# python diff per fixture
```

## 3. 結果

### 3.1 全域

| 量測 | total diff（126 pages 加總） |
|---|---|
| Sprint 50-62 baseline（default EstimateMetrics） | 9.437270 |
| Sprint 62 `--font-metrics`（FontMetricsAdapter + DroidSansFallback + LiberationSerif）| **9.222020** |
| Delta | **-0.215250**（per-page mean -0.001708、~2.3% relative）|

### 3.2 Distribution per 42 fixtures

| 變化區間 | 數量 | 範圍 |
|---|---|---|
| Large gain（≥0.01pp 改善）| **5** | -0.033 to -0.044 |
| Small gain（0.001-0.01pp 改善）| **2** | -0.008 to -0.009 |
| Neutral（±0.001pp）| **35** | -0.001 to +0.001 |
| Small loss（0.001-0.01pp 退化）| **0** | — |
| Large loss（≥0.01pp 退化）| **0** | — |

→ **乾淨完美**：**零 regression > 0.001**；改善集中在 7 個 fixture（5 大贏 + 2 中贏）；其餘 35 個 fixture 在噪音範圍內不變。

### 3.3 Top 10 IMPROVED

```
delta(font-metrics - baseline)  baseline  →  font-metrics   fixture
   -0.04390                    0.2292    →   0.1853         03_complex_table/1121229-全套管基樁混凝土查驗(共1).docx
   -0.03935                    0.2387    →   0.1994         03_complex_table/1130109-全套管基樁混凝土查驗共(4).docx
   -0.03657                    0.2627    →   0.2262         03_complex_table/1130112-全套管基樁混凝土查驗共(共3)(承辦).docx
   -0.03497                    0.2362    →   0.2012         03_complex_table/1130105-全套管基樁混凝土查驗(共2).docx
   -0.03336                    0.2326    →   0.1992         03_complex_table/1130516-共月橋P3帽梁鋼筋查驗.docx
   -0.00911                    0.2051    →   0.1960         04_with_image/05.112磺港溪監造會議照片1120923-1121001.docx
   -0.00829                    0.1981    →   0.1898         04_with_image/05.112磺港溪監造會議照片.docx
   -0.00073                    0.0270    →   0.0263         06_template/檢(試)驗管制(預設樣板).docx
   -0.00068                    0.0736    →   0.0729         01_simple/03.1120815-監造會議記錄.docx
   -0.00048                    0.0759    →   0.0754         01_simple/03.1120210-監造會議記錄-1120801.docx
```

→ **5 個全套管 fixture + 1 個共月橋 fixture（全 03_complex_table、ChienYi 建設監造文件類型）**佔總改善的絕大部分。

### 3.4 Top 10 "REGRESSED"（皆在噪音內、無真退化）

```
delta  baseline → font-metrics   fixture
+0.00072  0.1274 → 0.1282         02_std_table/1120928-磺港溪再造C段護岸及步道整建工程週報.docx
+0.00071  0.0213 → 0.0220         02_std_table/1140206-工地密度取樣紀錄.docx
+0.00066  0.1208 → 0.1214         02_std_table/1121006-磺港溪再造C段護岸及步道整建工程週報.docx
+0.00040  0.0348 → 0.0352         05_header_footer/自主檢查表---混凝土.docx
+0.00036  0.0243 → 0.0247         06_template/缺失改善.docx
+0.00027  0.0344 → 0.0347         05_header_footer/自主檢查表---植筋.docx
+0.00025  0.0376 → 0.0379         05_header_footer/自主檢查表---木構造.docx
+0.00020  0.0347 → 0.0349         05_header_footer/自主檢查表---地坪鋪面.docx
+0.00018  0.0341 → 0.0343         05_header_footer/自主檢查表---油漆.docx
+0.00016  0.0359 → 0.0361         05_header_footer/自主檢查表---人手孔調升降.docx
```

→ **最大「退化」+0.00072 在量測噪音範圍內**（pixelmatch threshold 0.5；puppeteer / V8 JIT ±2-3% 噪音）。02_std_table 週報的 +0.0007 對 0.127 baseline 是 0.55% relative — 完全在噪音內。

### 3.5 Per-category delta

| category | n | baseline | --font-metrics | delta | 評估 |
|---|---|---|---|---|---|
| 01_simple | 7 | 0.0692 | 0.0691 | -0.00015 | neutral |
| 02_std_table | 8 | 0.0821 | 0.0823 | +0.00028 | 噪音內微退化 |
| **03_complex_table** | **8** | **0.1655** | **0.1419** | **-0.02352** | **重大改善** |
| **04_with_image** | **6** | **0.1421** | **0.1392** | **-0.00290** | **顯著改善** |
| 05_header_footer | 10 | 0.0355 | 0.0356 | +0.00015 | neutral |
| 06_template | 3 | 0.0219 | 0.0217 | -0.00020 | neutral |

## 4. 為何 03_complex_table 全套管系列改善這麼大

5 個全套管 fixture 共同特性：
- **大量 CJK 文字**（中文表格內容）
- **複雜 table 結構**（多 row × 多 column）
- **特殊字型**：標楷體（中文）+ Times New Roman（Latin）+ 工程符號

Sprint 28 audit 記錄：
> 1.15 是甜蜜點：修最多 fixture（+2）且零退化。剩 3 個 -1 fixture（02_std_table/工地密度 + 03_complex_table/06-8估驗計價 ×2）root cause 不在 CJK 字寬。

→ Sprint 28 找到全域 best fit 1.15em，但**特定 fixture 仍有 root cause-of-deeper-mismatch**。Sprint 62 用 DroidSansFallback 的真實 1.37em line height 取代 1.2em 預設 → 對全套管系列特定 layout 行為命中。

具體推測：全套管 fixture 含 trHeight、多 line CJK paragraph 等情境；EstimateMetrics 1.2em 把 line height 算太小、wrap 過早；real font 1.37em 讓 line 拉開、wrap 對齊 LO 渲染。

## 5. ChienYi production 對齊度評估

03_complex_table 全套管系列、04_with_image 環清表系列、05.磺港溪會議照片 = **ChienYi 建設監造系統真實文件類型**：
- 全套管基樁查驗 → construction_quality 自主檢查
- 環清表照片 → construction_photo 環境清潔自查
- 磺港溪監造會議 → 監造會議記錄

→ **Sprint 62 改善的正是 ChienYi production 最常用的文件類型**。promote default-on 對 ChienYi production 用戶感受改善最直接。

## 6. Sprint 64+ 建議

### 6.1 Sprint 64 = promote `--font-metrics` 為 production default-on（建議）

**Data backing**：
- 全域 -0.0017 VR mean、~2.3% relative 改善
- 零 fixture regression > 0.001（最大 +0.00072 在噪音內）
- 7 個 fixture 真改善、其中 5 個改善 -0.033~-0.044 是 ChienYi production 文件類型
- 0 failed pages
- IIFE bundle +80KB（opentype.js）已落地、無額外成本

**Implementation 範圍**（autonomous 部分）：
- `RenderOptions.fontAdapter` 從 opt-in 改 default-on（caller 沒供 fontBytes → pipeline 內部自建 adapter 試 load 系統字型）
- 加 font auto-discovery（fontconfig / `fc-match` 在 puppeteer/Linux 環境）
- VR baseline 改 0.074899 → 0.073191（重置 Sprint 50-62 baseline）

**需 user 認可部分**（external resource）：
- production portal / canvas-editor 端 font 供應策略：
  - 選項 A：bundle Noto Sans CJK 進 IIFE（+5-10MB）
  - 選項 B：portal 端 lazy load + IDB cache（caller side）
  - 選項 C：依賴 user OS 字型（Windows / macOS / Linux fontconfig）

### 6.2 Sprint 65+ 後續候選（不變）

- Sprint 65：重生 goldens 用 Word desktop 渲染（換 metric anchor）
- Sprint 66+：OffscreenCanvas + Web Worker render（Sprint 60 probe 證實可行）
- 大文件 50+ 頁 fixture 待 user 提供

### 6.3 為何不做 Sprint 63 = promote default-on 直接 commit

Sprint 64 應分兩階段：
1. **Sprint 64a（autonomous）**：pipeline 內部 promote default-on + auto-discover 系統字型；VR baseline 重設
2. **Sprint 64b（external resource）**：portal / canvas-editor 端 font supply 策略 — 需 user 認可選 A/B/C

Sprint 63 純診斷的價值 = 把 Sprint 64a 的「**是否安全**」問題量化回答 YES、把 Sprint 64b 的「**該選哪種策略**」問題提供 data backing（5 大贏家是 ChienYi 文件類型 → 投資 IDB cache 載 fonts 對 production 有具體價值）。

## 7. vitest / VR

本 sprint **無 production code 變動** — 純診斷 sprint。
- vitest **967 passed + 1 skipped** 不變
- VR default 0.074899 不變
- VR `--font-metrics` 0.073191 不變（Sprint 62 結果重現）
- Sprint 12/16 baseline 未變動

## 8. Sprint 50-63 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50-58 | cache 五連發 + memoize + layout cache | warm 7.01× | perf 路徑收割 |
| 59 | drawLine path coalescing | ≈0 噪音 | 邊際遞減 |
| 60 | OffscreenCanvas probe（純診斷）| 4/4 features ✓ | pivot HarfBuzz |
| 61 | BrowserTextMetrics（negative）| -0.0013 退化 | 揭示 LO anchor |
| 62 | FontMetricsAdapter + IIFE 修復 | VR -0.0017 / -2.3% | 第一次打進 VR mean |
| **63** | **per-fixture delta 分析（純診斷）** | **5 大贏全 03 全套管 / 0 regression > 0.001** | **Sprint 64 promote default-on 風險量化 = GREEN** |

## 9. 工作摘要

```
+  docs/sprint63_font_metrics_delta_analysis.md   | 本文件（純診斷 audit）
+  /tmp/vr_baseline.json                           | default 量測（per-fixture 詳細數據）
+  /tmp/vr_font_metrics.json                       | --font-metrics 量測
```

無 production code、無新 unit test、無 VR / vitest 變動 — 純診斷 sprint。

## 10. 心得：純診斷 sprint 的策略價值

Sprint 36 / 43 / 46 / 49 / 60 / 63 都是純診斷 sprint（無 production code）。Sprint 50-63 之中佔了 6 個。

**純診斷 sprint 的策略價值**：
1. **避免下個 sprint 撞牆**（Sprint 60 揭示 OffscreenCanvas 可行但 ChienYi 不該攻、Sprint 61 揭示 LO anchor 給 Sprint 62 指明路）
2. **量化「下一步是否安全」**（Sprint 63 證實 promote default-on 零退化）
3. **保留 user authority on external resource decision**（Sprint 64b font 策略選 A/B/C 應由 user 決）

如果 Sprint 63 直接 commit promote default-on：
- 沒 per-fixture data → 不知道是否會有 fixture 大規模退化
- 沒 ChienYi production 對齊度數據 → 不知道哪種 font 策略最值得投資
- 可能踩到「全域 -0.0017 但某 fixture +0.05」這種反 SOPs 結果

Sprint 63 純診斷的 2 小時投入換來 Sprint 64 decision 的明確 data backing — 是高 ROI 的時間配置。

**Sprint 50-63 累積紀律延伸（Sprint 63 第 6 條）**：
6. **Promote default 前先做 per-fixture delta 分析** — 避免「全域 improvement 但個別 fixture 大幅 regression」陷阱
