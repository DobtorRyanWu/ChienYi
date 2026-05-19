# Sprint 44 — LineBreaker image-only line baseline=height（**12 sprint 來首次真實收斂、過 mean ≤ 0.10 標**）

**期間**：2026-05-14
**主軸**：依 Sprint 43 trace 確認的 root cause，修 LineBreaker.makeLine baseline 公式
**結論**：**🎉 突破！total mean 0.1128 → 0.0955（-1.73pp），首次過 mean ≤ 0.10 A- 級標準。**
Sprint 33-43 連 11 個 sprint 視覺收斂 = 0；Sprint 44 一個 9 行修改 + 4 prep test 收割 -1.73pp 總體、04 cat -5.74pp、02 cat -5.36pp。
關鍵成功因素：**Sprint 43 純診斷精準定位 + Sprint 44 prep test 先驗證 precondition 才開工**（第七層紀律生效）。

---

## 1. 規劃 vs 真實

| 規劃預估（高保真書 §11.10） | 真實結果 |
|---|---|
| photo y 偏差 -45.7pt（半解）| ✅ 達成（image-only line baseline 0.8h → h）|
| 04 cat 0.30 → ~0.25 | ✅ **04 cat 0.3013 → 0.2439（-5.74pp，比預估更好）** |
| 剩 56pt gap 留 Sprint 45 | 仍有殘餘（04 cat 0.24 ≠ 0），但已過總體標 |
| 總體達 mean ≤ 0.10 | ✅ **總體 0.1128 → 0.0955** |

## 2. 實作（核心 9 行）

[static/src/core/layout/LineBreaker.ts:makeLine](../static/src/core/layout/LineBreaker.ts)：

```typescript
let hasBox = false;
let isImageOnlyLine = true;
for (const it of items) {
  if (it.kind === 'box') {
    hasBox = true;
    if (it.height > height) height = it.height;
    if (!(it as Box).isImage) isImageOnlyLine = false;
  }
}
if (!hasBox) isImageOnlyLine = false;
// ...
// Sprint 44：image-only 行 baseline = height（image 無下緣 descender）
const baseline = isImageOnlyLine ? height : height * 0.8;
```

**原理**：
- 純文字行：`baseline = 0.8h`（ascender 80%、descender 20%）— 不變
- image-only 行：`baseline = h`（image 底邊對齊 baseline，無 descender）
- image + text 混合行：視為非 image-only，保留 0.8h（文字仍需 descender 空間）
- 空行：`hasBox=false` → `isImageOnlyLine=false` → 保留 0.8h（makeEmptyLine 另有路徑也不受影響）

**為何修這裡能收割**：

```
修法前：yBaseline = baseY + 0.8h → image y_drawn = yBaseline - h = baseY - 0.2h（被推到 cell padding 上方 0.2h）
修法後：yBaseline = baseY + h   → image y_drawn = yBaseline - h = baseY（image 從 cell padding.top 正確起點）
```

photo height 276pt → 修正 0.2 × 276 = **55.2pt 下移**，photo 落到正確位置。

## 3. Prep test（第七層紀律 — Sprint 42 教訓制度化）

開工前在 [tests/unit/layout/LineBreaker.test.ts](../tests/unit/layout/LineBreaker.test.ts) 寫 4 個 prep test，**precondition 驗證通過才進 production code**：

| test | 修法前 | 修法後 |
|---|---|---|
| image-only line：baseline === height | ❌ FAIL（220.8 ≠ 276）| ✅ PASS |
| 純文字 line：baseline === height × 0.8 | ✅ | ✅（不受影響）|
| image + text 混合 line：baseline = 0.8h | ✅ | ✅（混合行保留）|
| 空行 makeEmptyLine：baseline = 0.8h | ✅ | ✅（不受影響）|

prep test 第 1 條 FAIL（220.8 vs 276，diff 55.2pt = 0.2 × 276）→ **確認 precondition 滿足：修法會改 render output**。
其餘 3 條 PASS → **確認修法不誤傷文字 / 混合 / 空行路徑**。

## 4. 視覺收斂 (VR v14) — 突破性結果

### 4.1 總體

| 階段 | total mean | 對比 |
|---|---|---|
| Sprint 31 | 0.1176 | R1 overflow gating |
| Sprint 32-43 | 0.1127~0.1128 | **連 12 sprint 持平（0 收斂）** |
| **Sprint 44** | **0.0955** | **-1.73pp，首次過 mean ≤ 0.10 標** |

### 4.2 分類

| 分類 | Sprint 43 | Sprint 44 | Δ |
|---|---|---|---|
| 01_simple | 0.0699 | 0.0699 | 0（無 image）|
| **02_std_table** | **0.1533** | **0.0997** | **-5.36pp** |
| **03_complex_table** | **0.1728** | **0.1600** | **-1.28pp** |
| **04_with_image** | **0.3013** | **0.2439** | **-5.74pp** |
| 05_header_footer | 0.0357 | 0.0358 | +0.0001（噪音）|
| 06_template | 0.0219 | 0.0220 | +0.0001（噪音）|

### 4.3 04_with_image per-fixture

| Fixture | Sprint 43 | Sprint 44 | Δ |
|---|---|---|---|
| 05.112磺港溪監造會議照片 | 0.2766 | 0.2081 | -6.85pp |
| 05.112磺港溪1120923-1121001 | 0.2788 | 0.2162 | -6.26pp |
| 06.環清表(112.10.23-10.27) | 0.3015 | 0.2355 | -6.60pp |
| 06.環清表(112.10.9-10.13) | 0.3129 | 0.2597 | -5.32pp |
| 6.環清表(112.10.2-10.6) | 0.3002 | 0.2528 | -4.74pp |
| 6.環清表(112.9.25-9.29) | 0.3145 | 0.2593 | -5.52pp |

### 4.4 03_complex_table per-fixture（附帶收割）

03 全套管 5 fixture 也含 inline image（混凝土施工抽查照片）：

| Fixture | Sprint 43 | Sprint 44 | Δ |
|---|---|---|---|
| 1121229-全套管 | 0.3267 | 0.2938 | -3.29pp |
| 1130105-全套管 | 0.3286 | 0.2996 | -2.90pp |
| 1130109-全套管 | 0.3363 | 0.3111 | -2.52pp |
| 1130112-全套管 | 0.3432 | 0.3166 | -2.66pp |
| 1130516-共月橋 | 0.3033 | 0.2884 | -1.49pp |

→ image baseline 修法**同時收割 02 / 03 / 04 三個大類**，正是 Sprint 40 教訓「fixture 涵蓋率」的正面案例。

## 5. vitest

**855 passed + 1 skipped**（+4 prep test，全綠）。
Sprint 12 fingerprint snapshot / Sprint 16 page count baseline **未失敗** — 確認 image y 座標改變不影響 ops 指紋（fingerprint 只 hash 文字內容與 ops 種類，不 hash 座標）與 page count（image baseline 改變只移動 y、不改變分頁數）。

## 6. 殘餘 gap（Sprint 45+ 候選）

雖過總體標，但 03/04 cat 仍偏高：

| 分類 | 當前 mean | 目標 |
|---|---|---|
| 04_with_image | 0.2439 | <0.16 理想 |
| 03_complex_table | 0.1600 | <0.12 理想 |
| 02_std_table | 0.0997 | 已達標 |

Sprint 43 §5 列的剩餘 56pt gap 假設仍待驗證：
- A. row 0 trHeight=340 twip exact rule（render 給 38.9pt vs OOXML 17pt exact）
- B. empty paragraph `<w:spacing w:line="40" w:lineRule="exact"/>` 未實作（render 給 17pt vs OOXML 2pt exact）

但**總體已達 A- 級（mean ≤ 0.10）**，Sprint 45 可考慮：
1. 繼續壓 04/03（追 trHeight / lineRule exact）
2. 或轉商業化先行（B+ 級已可商用，A- 更穩）
3. 或補 Phase 3.6 註腳/尾註等新功能

## 7. 心路歷程：Sprint 33-44 的轉折

| Sprint | 視覺收斂 | 關鍵 |
|---|---|---|
| 33-35 | 0 | 規格先行假設失敗 |
| 36 | 0（純診斷）| grid analysis 工具落地 |
| 37-40 | 0 / 退化 | 修對方向但選錯 type/細節/位置/fixture |
| 41 | 0（純診斷）| 找候選 root cause（vAlign）但沒驗 precondition |
| 42 | 0 | vAlign 翻車（precondition 不滿足）|
| 43 | 0（純診斷）| trace 精準定位 LineBreaker baseline |
| **44** | **-1.73pp 突破** | **prep test 驗證 precondition + 精準修法** |

**成功公式 = Sprint 43 精準診斷（trace + Pillow 雙路徑）+ Sprint 44 prep test 先驗證 + 9 行精準修改**。

**教訓**：Sprint 33-42 浪費 10 個 sprint，但 Sprint 36（grid analysis 工具）+ Sprint 43（trace 方法）+ Sprint 42（prep test 紀律）累積的「診斷基礎建設」讓 Sprint 44 一擊命中。診斷投資不是浪費。

## 8. 工作摘要

```
M  static/src/core/layout/LineBreaker.ts       | +12  isImageOnlyLine 判斷 + baseline 三元
M  tests/unit/layout/LineBreaker.test.ts       | +55  4 個 Sprint 44 prep test
+  docs/sprint44_image_baseline_fix.md         | 本文件
```

VR v14：**total mean 0.1128 → 0.0955（-1.73pp，過 mean ≤ 0.10 標）**；04 -5.74pp、03 -1.28pp、02 -5.36pp。
vitest 855 passed + 1 skipped。Sprint 12/16 snapshot 未變動。
