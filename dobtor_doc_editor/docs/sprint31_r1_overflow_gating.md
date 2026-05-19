# Sprint 31 — R1 image-row break heuristic 加 overflow gating

**期間**：2026-05-11
**主軸**：Sprint 30 DPI 修正後 04_with_image 仍 dominant（28 pages × mean 0.38 包辦剩 48% 總 diff），逐 fixture 分析發現 Sprint 17-18 的 R1 transition rule 過度觸發
**結論**：給 R1 加上 **"would overflow current page"** 條件 — 只在 image row 與 prior content 加總真的會超頁時才強制 break；**04_with_image -24.8%**（0.3805 → 0.2862），總體 mean **0.1386 → 0.1176（-15.1%）**，零退化 + page count 仍 100% 對齊。

---

## 0. 入工前狀態（Sprint 30 後）

| 指標 | Sprint 30 |
|---|---|
| Page count mismatched | 0 / 42（不變）|
| Visual Regression v14 總體 mean | 0.1386 |
| 04_with_image | **0.3805**（dominant） |
| 03_complex_table | 0.1661 |
| 02_std_table | 0.1241 |

Top 10 worst pages 全部在 04_with_image：diff 0.39-0.41，皆為「安全衛生抽查照片」系列 fixture。

---

## 1. 根本原因：R1 過度觸發

### 1.1 偵測過程

讀 `6.環清表安全衛生抽查照片(再造)-(112.9.25.-9.29).docx` page 1 的 render vs golden：

| | Golden page 1 | 我們 page 1 |
|---|---|---|
| 標題列 | 任泰技術顧問有限公司 | 同 ✓ |
| 安全衛生抽查照片 | 有 | 有 ✓ |
| 工程名稱 row | 有 | 有 ✓ |
| 抽查地點/時間 row | 有 | 有 ✓ |
| **2 張照片** | **有** | **❌ 完全缺失** |

我們 page 1 只有 header 4 rows，photo cells 完全沒渲染。photo 跑到 page 2。

### 1.2 docx 結構與 fit 算

```
Table 0: 6 rows
  R0: 任泰技術顧問有限公司 (h≈39pt)
  R1: 安全衛生抽查照片 (h≈21pt)
  R2: 工程名稱 row (h≈21pt)
  R3: 抽查地點/時間 row (h≈21pt)
  R4: photo + timestamp (h≈327pt, image inline 368.3×276.1pt)
  R5: photo + timestamp (h≈309pt)
```

Content area：A4 595×842pt - margins (top 42.55 + bottom 28.35) = **content height 770pt**
Table total：39+21+21+21+327+309 = **738pt**

**738pt < 770pt → 整張表 fit 1 頁** ✓ 與 golden 一致

但我們把 R0-R3（header）放在 page 1，R4-R5（photos）放在 page 2 — **不應該的 split**。

### 1.3 Sprint 17/18 R1 rule 過度觸發

[`Paginator.ts:1014-1042`](../static/src/core/layout/Paginator.ts) Sprint 17 引入 R1，Sprint 18 加 transition 變體：

> 當下一個 row 是「大型 image row」（contains image + cantSplit + height ≥ 34% contentH），且與前面 row 是 std→image transition，**強制換頁**。

原意：把 image rows 集中到自己的頁，避免 image / std 混雜時 Word 的奇怪行為。

但此規則**沒檢查是否 overflow**：即使 R4 加上之前的 R0-R3 真的 fit 同一頁，R1 還是會 break。對 04_with_image 系列致命：每張表都被強制 split 成「header 頁 + photo 頁」，photo 永遠在第二頁、header 永遠單獨在第一頁。

### 1.4 為何 Sprint 17/18 當時這樣設計

Sprint 18 報告：「mismatched 17→13、totalDelta -26→-14、04_with_image 4 個 fixture 從 -3 完美對齊 0」。

當時 page count 嚴重失準（Sprint 16 baseline mismatched 17/42），R1 強制 transition break 是 page count correction 工具。Sprint 25-29 已用其他機制（spacing.line / docGrid / CJK 字寬）把 page count 修到 100% 對齊。R1 完成了它的 page count 任務，**但仍 active 並造成 visual 過度 split**。

---

## 2. 修法：加 overflow gating

[`Paginator.ts:1022-1042`](../static/src/core/layout/Paginator.ts)：

```diff
 const isLargeImageRow = row.containsImage
   && row.cantSplit
   && imageBreakRatio > 0
   && row.height >= ctx.contentHeight * imageBreakRatio;
 const hasPriorContent = pendingRows.length > 0 || ctx.entries.length > 0;
 const enterImageBlock = isLargeImageRow && !ctx.lastRowWasImage;
 const leaveImageBlock = !isLargeImageRow && ctx.lastRowWasImage;
-if ((enterImageBlock || leaveImageBlock) && hasPriorContent && imageBreakRatio > 0) {
+// Sprint 31：transition 加上 "would overflow current page" 條件
+const wouldOverflow = pendingHeight + row.height > availableHeight;
+if ((enterImageBlock || leaveImageBlock) && hasPriorContent && imageBreakRatio > 0 && wouldOverflow) {
   if (pendingRows.length > 0) flushTableEntry(/* more = */ true);
   nextColumnOrPage(ctx);
   ...
 }
```

**規則**：只當「transition + prior content + ratio > 0 + 此 row 真的塞不下」全部成立才觸發 R1。對「transition + 但全部 fit」的場景**不再 break**。

---

## 3. 三層 SOP 結果

### 3.1 Layer 1 — vitest 全套

```bash
NODE_OPTIONS="--max-old-space-size=2500" npx vitest run
```

**768/768 + 1 skipped**（Sprint 30 baseline 767 + 1 新 Sprint 31 test：「transition + 不 overflow → 不觸發 R1（04_with_image 場景）」）

Sprint 17/18 既有 6 個 R1 test 更新 expectation 對齊新規則：
- 把 imageRow 從 300pt 加大到 700pt 強制 overflow，保留 R1 觸發測試意圖
- 加新 case「transition + fit 不觸發」反映新行為

### 3.2 Layer 2 — Visual Regression v14

**rendered 42/42 / comparedPages 126 / failedPages 0**

| Category | Sprint 30 | **Sprint 31** | Δ |
|---|---|---|---|
| **04_with_image** | 0.3805 | **0.2862** | **-24.8%** ← 主要勝利 |
| 01_simple | 0.0700 | 0.0700 | 0.0% |
| 02_std_table | 0.1241 | 0.1241 | 0.0% |
| 03_complex_table | 0.1661 | 0.1661 | 0.0% |
| 05_header_footer | 0.0359 | 0.0359 | 0.1% |
| 06_template | 0.0224 | 0.0224 | -0.2% |
| **總體 mean** | 0.1386 | **0.1176** | **-15.1%** |

04_with_image 4 個 fixture 全改善（各 -22% 到 -28% range）。其他 category 完全不動 — 證明 R1 修法**只影響 image-heavy fixture**，零退化。

### 3.3 Layer 3 — 視覺 spot check

`6.環清表安全衛生抽查照片` page 1：

| | 修前 | **修後** |
|---|---|---|
| 標題 + header rows | ✓ | ✓ |
| 2 張照片 + timestamps | ❌（在 page 2）| **✓**（同頁）|
| 結構對齊 golden | 否 | **是** |
| 此 page 的 diff ratio | 0.41 | **0.29** |

Page count 仍 6 頁（不變），但每頁內容結構對齊 golden。

---

## 4. Sprint 31 後 top diff sources

```
diff=0.4070  page=3  04_with_image/6.環清表安全衛生抽查照片(112.9.25.-9.29)
diff=0.4067  page=3  04_with_image/06.環清表安全衛生抽查照片(112.10.23.-10.27)
diff=0.4040  page=5  04_with_image/...
...
```

剩 04_with_image 像素級差距：
- Photo aspect ratio：我們的照片比例 / 縮放與 Word 略不同
- Caption rows：cell 之間有「圖片標題」應該插在 photo 與下張 photo 之間
- Cell 內 image alignment：center vs left
- Pipeline 角落仍有「✓ 6 page(s), 6 image(s)」debug overlay

03_complex_table 全套管 0.30+ 的部分還需要個案分析（Sprint 32+ 候選）。

---

## 5. 量化結果

| 指標 | Sprint 30 | **Sprint 31** |
|---|---|---|
| Page count mismatched | 0/42 | 0/42（不變）|
| Visual Regression v14 comparedPages | 126 | 126 |
| Visual Regression v14 failedPages | 0 | 0 |
| **Visual Regression v14 總體 mean** | **0.1386** | **0.1176（-15.1%）** |
| 04_with_image per-cat | 0.3805 | **0.2862（-24.8%）** |
| 其他 5 個 category | 0.07-0.17 | 0.07-0.17（持平 ±0.2%）|
| vitest test files / cases | 49 / 767+1skip | 49 / **768+1skip** |
| Sprint 17/18 既有 R1 test | 6 個（synthetic）| 同 6 個，皆更新 imageRow 700pt 強制 overflow |
| 新增 test | — | **1 個「transition + 不 overflow 不觸發 R1」** |

---

## 6. Sprint 31 學到的工程教訓

### 6.1 過時的 heuristic 要持續審查

R1 是 Sprint 17-18 為了修當時嚴重的 page count 失準引入的。隨後 Sprint 25-29 用更精準的 OOXML 規則修了 page count，R1 完成了它的歷史任務。**但沒人 retire 它**。Sprint 31 觀察到 visual diff 在 image-heavy fixture 過高才回頭審查。

教訓：**每個 heuristic 都該標註「成立的歷史 context」+「retirement signal」**。當 page count 100% 對齊時，R1 的「強制 transition break」應自然弱化。

### 6.2 Synthetic tests 可能 lock in 過時 behavior

Sprint 18 的 R1 unit tests 用 300pt image row + 698pt contentHeight，content 明明 fit 但測試期待 R1 break。tests 描述了 R1 過去的行為，當行為應該演化時 tests 反而成阻礙。

教訓：**synthetic test 要持續 against fixture 校驗**。Fixture 一旦改善（如 page count 100% 對齊後），synthetic 假設可能失效。

### 6.3 Visual diff 高的根因 ≠ page count 問題

直覺以為 04_with_image 0.38 高 diff 是 photo 位置 / aspect ratio 問題，但實際是 **page structure** 問題（photo 跑錯頁）。**先看「每頁應該有什麼 vs 我們渲了什麼」再看細節**。

### 6.4 Diff 集中在 1 個 category 時，個案處理 ROI 高

04_with_image 包辦 48% 剩餘 diff（28 pages × 0.38）。修這個 category 比平均改善所有 category 大很多。**先攻最大山頭**，per-category mean 是好指標。

---

## 7. 規劃書同步項

- §0.5 加 Sprint 31 entry
- §0.5 文件清單補 [sprint31_r1_overflow_gating.md](sprint31_r1_overflow_gating.md)
- §0.6.13 「Sprint 31+ 優先級」→「Sprint 32+」；04_with_image 標 partial（24.8% → 仍主源但已下降）
- 完成度表加 Sprint 31 欄
- header 最後更新日期

---

## 8. Sprint 32+ 候選

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **04_with_image photo cell 細節**：image alignment（cell 內 center vs left）、aspect ratio fit、cell-internal caption 位置 | 04_with_image 0.2862 → 預估 0.15 |
| 2 | 🟡 **03_complex_table 全套管系列細節**：5 個 fixture page 1 mean 0.30，cell border / image embedding / merge | 03_complex_table 0.1661 → 預估 0.10 |
| 3 | 🟡 Visual Regression pipeline harness 修整：移除 page count / image count overlay（top-right "✓ N pages, M images"）| Visual cleanup |
| 4 | 🟡 opentype.js advanceWidth 接入（長期方案）| 長期正確性 |
| 5 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求）| 新功能 |

---

## 9. 距離目標（總體 mean 0.10）剩餘距離估算

| Sprint | 完成 | mean | 改善幅度 |
|---|---|---|---|
| Sprint 28 | CJK em 1.0→1.15 empirical | 0.1728 | baseline |
| Sprint 29 | docGrid + snapToGrid | 0.1705 | -1.3% |
| Sprint 30 | DPI 96→150 對齊 goldens | 0.1386 | -18.7% |
| Sprint 31 | R1 + overflow gating | **0.1176** | **-15.1%** |
| Sprint 32 | 預估 04_with_image image alignment | 預估 ~0.105 | ~-11% |
| Sprint 33 | 預估 03_complex_table cell border | 預估 ~0.095 | ~-10% |
| **目標達成** | mean ≤ 0.10 | **預估 Sprint 33 完工** | — |

**剩餘約 2 個 Sprint** 可達 mean ≤ 0.10。

---

**Sprint 31 一句話總結**：診斷 04_with_image diff 0.38 dominant 是 Sprint 17-18 R1 transition rule 過度觸發（把 fit 同頁的 header + photo rows 強制 split），R1 加上 **wouldOverflow** gate；04_with_image **-24.8%**（0.3805→0.2862）、總體 mean **0.1386→0.1176（-15.1%）**、其他 category 零變化、vitest 768+1skip / page count 仍 100% 對齊；剩 ~2 個 Sprint 可達 mean ≤ 0.10 目標。
