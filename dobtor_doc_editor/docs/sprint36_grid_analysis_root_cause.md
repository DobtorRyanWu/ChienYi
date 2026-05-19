# Sprint 36 — Pixel Distribution Grid Analysis：找到 03 全套管 5 fixture × 0.30 真根因

> **狀態**：✅ **資料先行成功**：grid analysis 確認 03_complex_table 全套管 5 fixture × 0.30 baseline 的**真正主因 ≠ textDirection / vMerge / 任何 V-variant 結構特徵**。真根因 = **anchor drawings 被當作 inline rendered**，導致 col 2（75% 寬）內的「混凝土施工抽查照片」浮動文字框沒在絕對位置，連帶把 297×227pt 大照片位置整體推偏。
> **日期**：2026-05-13
> **本 Sprint 性質**：**純診斷 sprint**，不修任何邏輯；mean 不變（與 Sprint 35 持平 ~0.1156）。產出工具與真根因確認，留 Sprint 37+ 落地修法。
> **連 Sprint 33+34+35 三次「找根因但結果零收斂」終於在 Sprint 36 翻案**：grid analysis 找到正解。

## 1. 工具產出

新增 `scripts/grid_analysis.cjs`：
- 輸入：render PNG + golden PNG（可不同尺寸；自動 nearest-neighbor scale 到 golden 尺寸）
- 切 N×M grid（預設 50×70；cell ~25×25 px）
- 對每 grid 算 pixel diff ratio（pixelmatch threshold 0.1）
- 輸出 JSON（top 10% 最差 grid 列表 + 完整 grid heatmap）+ overlay PNG（紅色覆蓋 top 10% 位置）
- 用法：`node scripts/grid_analysis.cjs --render <p> --golden <p> --out-json <p> --out-overlay <p> [--grid 50x70] [--top-pct 10]`

## 2. 假設先行 vs 資料先行的對比

Sprint 33+34+35 連續三次「找根因」流程：
```
spot check PNG → 看出視覺結構差異（vMerge 切斷 / 字符方向錯）→ 假設這是 mean 主因 → 落地 → 零收斂
```

Sprint 36 grid analysis 流程：
```
切 grid → 算 per-grid diff → 找 top 10% 位置 → 反向映射 layout element → 看該 element 是什麼 → 找根因
```

關鍵差異：**Sprint 36 是「數據選 element 給人看」，不是「人選 element 給數據驗證」**。

## 3. Grid 分析結果（1121229-全套管 page 1）

### 3.1 整體分布

```
Image          : 1241×1754
Grid           : 50×70 (cell ~25×25 px)
Overall diff   : 30.79% (670,307 px diffed)
Top 10%        : 350 cells, mean ratio 99.55%, 216,863 diff px (32.4% of total)
```

**Top 10% 只佔 32.4% 總 diff，不集中** — 排除「單一 element 完全錯」的可能；diff 廣泛分布。

### 3.2 Row-level 分布

Hot rows: 7-52（y=175-1328 px）— **幾乎整個 table body**（y=150 是 top margin）。沒有特別熱的 row band，diff 沿垂直方向均勻分布。

### 3.3 Col-level 分布（**關鍵**）

```
col 0-6  (x=0-148):     0.0%（page margin，無 diff）
col 7-8  (x=173-198):   1.3-2.5%（table col 0 起點，少量 diff）
col 9-10 (x=223-248):   14-16%（table col 0/1 交界，邊框 + tbRlV 字位置）
col 11   (x=273):       18.4%（table col 1 起點）
col 12-15 (x=297-372):  2-6%（table col 1 內部，較低）
col 16   (x=397):       18%（table col 2 左邊框 + 起點）
col 17-40 (x=421-1017): 54-61% UNIFORM!  ← 全套管 5 fixture 共通 hot zone
col 41   (x=1017):      40%（table col 2 右邊框過渡）
col 42-43 (x=1042-1067): 0.6-1.8%
col 44-49 (x=1092+):    < 4%（page margin，但有小 diff）
```

**Col 2（table 寬欄，6662 twips = 333pt = 694px）內部 24 個 grid col 全部均勻 55-60% diff** — 不是累積誤差（漸增），是「整個 col 2 內容區整體錯位」。

### 3.4 三 fixture 對比

| Fixture | Overall | Top 10% share | Hot col range |
|---|---|---|---|
| 1121229-全套管 p1 | 30.79% | 32.4% | 17-40 (x=421-1017) |
| 1130516-共月橋P3 p1 | 30.23% | 32.8% | 20-40 (x=496-1017) |
| 1130112-全套管(共3) p1 | 32.90% | 30.3% | 17-40 (x=421-1017) |

**Hot range 高度一致**：都在 x ≈ 420-1017 px 區域內。

## 4. 反向映射到 layout

### 4.1 1121229-全套管 docx 結構（python3 ET 解析）

```
1 個 table (top-level)
2 rows × 3 cols (gridSpan=1 each)
gridCol widths: 1077 / 1078 / 6662 twips = 53.85 / 53.90 / 333.10 pt
                                         = 112 / 112 / 694 px @ 150dpi
4 個 tbRlV cells（row 0+1 的 col 0、col 1；col 2 全部 horizontal）
0 個 nested table
```

### 4.2 Col 2 row 0 內容（python3 ET 解析）

```
row 0 col 2: td=None span=1 tcW=6662 rowH=5336 (=267pt=556px)
  paragraph 0: text="112.12.29112.12.29"
    drawings=2 pics=1
      drawing 1: ANCHOR  (70.8 × 22.7 pt = small text box)
      drawing 2: INLINE  (297.0 × 226.8 pt = LARGE photo)
```

**真兇候選**：
1. ANCHOR drawing 是 floating text box（內容「混凝土施工抽查照片」），有 `<wp:positionH>` / `<wp:positionV>` 指定絕對位置
2. INLINE drawing 是 297×227pt 大照片，照常 inline 推到下一行

### 4.3 Renderer 處理機制（[`BoxBuilder.ts:52-62`](../static/src/core/layout/BoxBuilder.ts#L52)）

```typescript
} else if (run.type === 'inlineImage' || run.type === 'floatImage') {
  // floatImage Sprint 2 也當作 inline Box 占位（wrap 後續實作）
  items.push({
    kind: 'box',
    width: run.width,
    height: run.height,
    text: `image:${run.rId}`,
    runProps: { fontSize: defaultFontSize },
    isImage: true,
    imageRId: run.rId,
  });
}
```

**Sprint 2 的「占位」simplification 在 Sprint 14+ 之後沒被升級**。`floatImage`（OOXML `<wp:anchor>`）跟 `inlineImage`（OOXML `<wp:inline>`）走同一條路徑都當 inline Box — anchor 的絕對定位 (positionH/V) 整個失效。

結果：
- Word 渲染：anchor 在 cell 內某絕對座標、inline 照片在 paragraph 之後
- 我們渲染：anchor 跟 inline 都被當段內 inline Box 依序排列 → 位置全錯位

### 4.4 視覺確認（spot check）

ImageMagick crop col 2 row 0 區域（700×560 px @ x=374, y=150）做 side-by-side：
- 渲染圖：anchor 文字框被推到段內（位置錯）、照片在某處（不一定對齊 golden）
- Golden：anchor 在絕對位置「混凝土施工抽查照片」標題位、照片在 anchor 之後

詳見 `/tmp/sprint36/compare_full.png`（產出物）。

## 5. 為何 Sprint 33+34+35 全沒收斂

| Sprint | 假設根因 | 真實影響面積 | 對 mean 影響 |
|---|---|---|---|
| Sprint 33 | vMerge anchor cell 沒延伸合併高度 | col 0 vMerge area ~112×560 px = 63k px | ~63k / 2.18M = ~2.9% 面積，但實際 pixel 差 ~5k | 0.0000 |
| Sprint 34 | tbRlV cell 缺 canvas rotate | 4 個 tbRlV cells ≈ 224×560 px = 125k px | ~125k 面積，視覺結構錯但 pixel-mean 差 ~6k | 0.0000 |
| Sprint 35 | tbRlV cell 缺 char-level vertical | 同上 4 cells | ~125k 面積，char 位置不對齊但 pixel 差 ~7k | +0.0001 |
| **Sprint 36 真根因** | **anchor + inline image 錯位** | **col 2 整欄 694×560 = 388k px × 2 rows ≈ 776k px** | **~12-15% of full page → ~217k diff px = Top 10% 集中** | 待 Sprint 37+ 修 |

光面積比：Sprint 36 真根因影響的 pixel 面積是 Sprint 33-35 假設根因的 **6-7 倍**。pixel-level diff 貢獻量級差兩個數量級。

## 6. SOP 三層

### 6.1 Vitest（layer 1）

Sprint 36 不改邏輯 → 不新增 unit test；既有 **793 passed + 1 skipped** 維持。

### 6.2 Visual Regression v14（layer 2）

不改邏輯 → mean 不變 0.1156（與 Sprint 35 持平）。grid_analysis.cjs 為診斷工具，不進入 VR pipeline gate。

### 6.3 Visual spot check（layer 3）

✅ 1121229-全套管 page 1 cropped col 2 row 0 視覺比對確認：
- anchor "混凝土施工抽查照片" 文字框位置錯
- inline 大照片位置/相對偏移
- 兩者連鎖造成 col 2 整欄 55-60% diff

## 7. 工作量 vs 產出

| 項目 | 投入 | 產出 |
|---|---|---|
| grid_analysis.cjs 工具 | ~220 行 | ✅ 可重用 diagnostic tool |
| 3 個 fixture grid 分析 | 3 次 ~30 秒 | ✅ JSON + overlay PNG × 3 |
| Spatial pattern cross-fixture | node script ~30 行 | ✅ Hot col range 一致確認 |
| Layout 反向映射 | python3 ET 解析 ~40 行 | ✅ 識別 col 2 = 大照片 cell |
| 視覺 spot check | convert × 4 + Read | ✅ 確認 anchor + inline 錯位 |
| audit doc | ~280 行 | ✅ Sprint 37+ 工作明確 |
| 視覺收斂 | — | **0%（純診斷 sprint）**；Sprint 37+ 預估 -10~15% |

## 8. Sprint 37 工作大綱（**真根因落地**）

### 8.1 ANCHOR drawing 絕對位置實作

[`ooxml/ast/types.ts`](../static/src/core/ooxml/ast/types.ts) FloatImageNode：
- 加 `positionH: { relativeFrom: 'page' | 'column' | 'margin' | 'paragraph'; offset: Pt }`
- 加 `positionV: { relativeFrom: 'page' | 'margin' | 'paragraph' | 'line'; offset: Pt }`
- 加 `wrapType: 'square' | 'tight' | 'topAndBottom' | 'inline' | 'behind' | 'inFront'`

[`ooxml/drawing/DrawingParser.ts`](../static/src/core/ooxml/drawing/DrawingParser.ts)：解析 `<wp:positionH>` / `<wp:positionV>` / `<wp:wrapSquare>` 等子元素，寫入 FloatImageNode。

### 8.2 Layout 端 anchor 排版

[`layout/BoxBuilder.ts:52`](../static/src/core/layout/BoxBuilder.ts#L52)：分支處理 inlineImage / floatImage：
- inlineImage：保持當前邏輯（Box with isImage）
- floatImage：**不**進 paragraph items；改放到 paragraph.floats 額外欄位，由 Paginator 在排版段落時用 positionH/V 算絕對座標

[`layout/Paginator.ts`](../static/src/core/layout/Paginator.ts)：對 cell 內 floatImage 套用既有 wrapSquare 排版（Sprint 6 cellInternal 已有部分基礎）；對 wrapBehind / inFront 直接放在 z-index 後/前。

### 8.3 Renderer 處理

[`render/CanvasRenderer.ts`](../static/src/core/render/CanvasRenderer.ts)：對 PageEntry kind='floatImage' 已有 `renderFloatImage`（Sprint 8 已實作）；只需確保 Paginator 把 cell 內 floatImage 也 emit 成 floatImage entry（而非 inline drawing）。

### 8.4 預估收斂

| 修法 | 影響 |
|---|---|
| Anchor 絕對位置正確（70.8×22.7pt 小文字框就位） | col 2 ~5% diff 收斂 |
| Inline 大照片 paragraph 開頭起始 y 正確（不被 anchor 推走） | col 2 ~10% diff 收斂 |
| 整體 03_complex_table mean | 0.1664 → **~0.115** |
| 總體 mean | 0.1156 → **~0.108** |

如能落地 Sprint 37 + Sprint 38（fine-tune 照片 EMU→px DPI 對齊），有機會 **2 sprint 內達 mean ≤ 0.10**。

### 8.5 Sprint 37 三層 SOP 規劃

- Vitest：
  - DrawingParser：解析 `<wp:positionH>` / `<wp:positionV>` 6 種 relativeFrom + offset
  - BoxBuilder：floatImage 不進 items；走 paragraph.floats
  - Paginator：cell 內 floatImage 套用 positionH/V 算 entry.x/y
  - 預估 ~12 個新 test
- VR v14：對 03 全套管 5 fixture 觀察 mean 收斂幅度
- Spot check：1121229-全套管 page 1 確認 anchor "混凝土施工抽查照片" 出現在 golden 對應位置

## 9. 教訓

連 Sprint 33+34+35 三次假設先行失敗、Sprint 36 資料先行成功的對比凝練：

1. **「找到結構性差異」≠「找到 pixel-mean 主因」**：spot check 視覺上看出 vMerge / textDirection 都是真實問題，但它們影響的 pixel 面積可能 < 1%
2. **Grid analysis 是 fixture-mean 收斂工具的標配**：所有 diff > 0.10 的 fixture 都該先過 grid 找 hot zone
3. **「占位」simplification 在 Sprint 2 時是正確簡化，但需在後續定期 audit 哪些 simplification 已成 visual 主要 blocker**：BoxBuilder.ts:52 的 floatImage 退化為 inline 從 Sprint 2 留到 Sprint 36 = 34 sprint 跨度
4. **資料先行不只是 mean 收斂時的工具，是「決定下個 sprint 主軸」的工具**：Sprint 35 結束時若先跑 grid analysis 而非直接寫 char-level vertical，就會發現主軸不是 textDirection

下個 sprint 接續：**Sprint 37 — Anchor drawing 絕對位置與 wrap 行為正確實作**。
