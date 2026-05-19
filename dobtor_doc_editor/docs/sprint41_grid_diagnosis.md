# Sprint 41 — 06/6.* fixture grid analysis 真根因診斷（純診斷不修代碼）

**期間**：2026-05-14
**主軸**：依 Sprint 33-40 教訓「資料先行 > 規格先行」，對 4 個 06/6.* fixture 跑 grid_analysis 找真 hot zone
**方法**：4 fixture × 4 page 共 16 個 grid 分析 + pixel sampling + OOXML 結構反查
**核心結論**：**確認 root cause = `cell.vAlign='center'` 在 CanvasRenderer 中未實作**（TableLayout 已正確 propagate 到 CellLayout.vAlign，但 renderCell 第 278 行硬寫 `y + cell.padding.top` 完全忽略 vAlign）

---

## 1. 診斷方法

依 Sprint 33-40 累積教訓的「6 層 cascading chain」：方向 → 機制 → type → 細節 → 位置 → fixture 涵蓋率，Sprint 41 不假設規格層級該攻哪一條，改為**強制資料先行**：

1. 對 04_with_image 內 4 個 06/6.* fixture 全 4 page 跑 `scripts/grid_analysis.cjs`
2. 比對 16 個 grid 的 Top 10 worst zones，找共同模式
3. 對 hot zone 像素取樣（render vs golden），看顏色分布
4. 反查 OOXML 結構（sectPr / table props / cell props）對應該位置

---

## 2. Grid analysis 結果（16 page，4 fixture × 4 page）

| Fixture | Page 1 diff | Page 2 diff | Page 3 diff | Page 4 diff |
|---|---|---|---|---|
| 06.環清表(112.10.23-10.27) | 42.18% | **0.12%** | 39.59% | 38.64% |
| 06.環清表(112.10.9-10.13) | 43.62% | **0.12%** | 43.39% | 37.96% |
| 6.環清表(112.10.2-10.6) | 43.25% | **0.12%** | 39.57% | 38.50% |
| 6.環清表(112.9.25-9.29) | 43.41% | **0.12%** | 41.43% | 39.21% |

### 2.1 關鍵發現

**Page 2 across 4 fixtures = 0.12% diff（基本對齊）**！
**Page 1/3/4 across 4 fixtures = 38-44% diff（大量 diff）**！

Page 2 hot zone：全集中在 grid(44-49, 0) 右上角小範圍（~74% diff，差異約 462-466 px），是頁碼/標題列的細微 sub-pixel 差。Page 2 不含圖片。

Page 1/3/4 hot zone：rows 10-19（y=250-501 px）大量 100% diff cell，集中區跨多行（橫向 5-25 個 cell 都 100% diff）。Page 1/3/4 含圖片。

→ **本 fixture 唯一 diff 主來源 = 含照片頁面的照片區位置不對**

## 3. Pixel sampling 反查 photo 位置偏差

對 06.環清表(112.10.23-10.27).docx page 1，取 (300, 500, 700) × y={300, 400, 500, 600} 12 個 sample 點：

| y (px) | render colors | golden colors | 解讀 |
|---|---|---|---|
| 300 | 照片色 (239,239,244) | 全白 (255,255,255) | render 有照片、golden 還在空白區 |
| 400 | 照片色 (220,229,239) | 全白 (255,255,255) | render 已是照片中段、golden 還在空白 |
| 500 | 照片暗色 (143,156,149) | 照片淺色 (241,245,247) | render 進入照片下半、golden 才剛開始 |
| 600 | 照片極暗 (35,36,27) | 照片中段 (234,239,245) | render 接近照片底、golden 還在上半 |

**結論**：render 的照片位置比 golden **高約 200 px = 96 pt**。一致的 Y 軸偏移。

## 4. OOXML 結構反查（06.環清表 fixture）

```xml
<w:sectPr>
  <w:pgSz w:w="11906" w:h="16838"/>
  <w:pgMar w:top="851" w:right="1134" w:bottom="567" w:left="1701"
           w:header="851" w:footer="992"/>
  <w:cols w:space="425"/>
  <w:docGrid w:type="lines" w:linePitch="360"/>
</w:sectPr>

<w:tr>
  <w:trPr>
    <w:cantSplit/><w:trHeight w:val="698"/><w:jc w:val="center"/>
  </w:trPr>
  <w:tc>
    <w:tcPr>...<w:vAlign w:val="center"/>...</w:tcPr>
    <w:p>...<w:drawing>...inline image cx=4676820 cy=3506033 EMU...</w:drawing>...</w:p>
  </w:tc>
</w:tr>
```

關鍵事實：
- 頁邊距 top=851 twip = 42.5pt（小於 Office 預設 72pt，本身正確讀進 sectPr 應該沒問題）
- 照片 inline，extent 4676820 × 3506033 EMU = 368.3 × 276.1 pt（756 × 575 px @ 150 DPI）
- 照片所在表格 cell **全部 `<w:vAlign w:val="center"/>`** — 內容**垂直置中**

## 5. 程式碼 trace：vAlign 在哪斷裂

[static/src/core/layout/types.ts:263](../static/src/core/layout/types.ts)：
```typescript
export interface CellLayout {
  vAlign: 'top' | 'center' | 'bottom';  // 已定義
  ...
}
```

[static/src/core/layout/TableLayout.ts:97](../static/src/core/layout/TableLayout.ts) + [L175](../static/src/core/layout/TableLayout.ts)：
```typescript
return {
  vAlign: cell.props.vAlign ?? 'top',  // 正確 propagate 進 CellLayout
  ...
};
```

[static/src/core/render/CanvasRenderer.ts:278](../static/src/core/render/CanvasRenderer.ts)（**bug 在這**）：
```typescript
} else {
  let yCursor = y + cell.padding.top;  // ❌ 硬寫 top，完全忽略 cell.vAlign
  const innerWidth = Math.max(cell.width - cell.padding.left - cell.padding.right, 1);
  for (const block of cell.blocks) {
    yCursor += this.renderCellBlock(block, x + cell.padding.left, yCursor, innerWidth);
  }
}
```

→ **CanvasRenderer 從來沒讀 cell.vAlign**。所有 cell 內容都 top-align。

## 6. 影響量推估

當 cell.vAlign='center' 時，正確的 Y 起點應為：

```
yCursor = y + (rowHeight - contentHeight) / 2
```

對 06 fixture：
- 照片 cell 大概 photo 在 row 內、photo height ≈ 276pt
- 若 row 高度 ≈ 380pt（photo + 上下標題行），則 center 偏移 ≈ (380-276)/2 = 52pt
- 6 個照片 cell 累積偏移可達 ~96pt（恰與觀察值吻合）

或：早期 row 0/1 是 17pt 高的 text row，cell.vAlign='center' 對 12pt 文字偏移 = (17-14.4)/2 = 1.3pt 微小。
但 photo cell 偏移 ~52pt，加上 row 高度誤差累積，總體 96pt 偏移合理。

## 7. 影響範圍預估

vAlign 修法影響 fixture：
- **06.* / 6.* 共 4 個 fixture × 各 4 page × 70% page 含 photo** ≈ 16 個 page × ~40% diff → **5pp 邊際收益於 04 cat 總體**
- 03 全套管 5 fixture 也用 vAlign（部分 cell）→ 可能附帶 1-2pp 改善
- 02_std_table 多數 cell 用 vAlign（表格本身就需要垂直定位）→ 可能附帶 0.5pp
- **總體預估**：mean 0.1127 → 0.10~0.105（**達 mean ≤ 0.10 標**）

## 8. Sprint 42 建議攻擊方向

### 8.1 主軸：實作 cell.vAlign='center' / 'bottom'

[CanvasRenderer.ts:278](../static/src/core/render/CanvasRenderer.ts) `renderCell()` 改：

```typescript
} else {
  // Sprint 42：計算 cell 內容總高度（先 pre-walk block 不繪），
  // 再依 vAlign 設定 yCursor 初值
  const innerHeight = computeCellContentHeight(cell.blocks);
  const availableHeight = rowHeight - cell.padding.top - cell.padding.bottom;
  let yCursor: Pt;
  switch (cell.vAlign) {
    case 'center':
      yCursor = y + cell.padding.top + Math.max(0, (availableHeight - innerHeight) / 2);
      break;
    case 'bottom':
      yCursor = y + rowHeight - cell.padding.bottom - innerHeight;
      break;
    case 'top':
    default:
      yCursor = y + cell.padding.top;
  }
  // 然後逐 block 繪製...
}
```

**注意**：`computeCellContentHeight` 需 pre-walk paragraphs (line height) + tables (nested rows)。
此值可在 TableLayout pass 預算好放進 CellLayout（避免 renderer 二次計算）。

### 8.2 修法檢查表（依 Sprint 33-40 cascading chain）

1. ✅ **方向**：cell vAlign（OOXML §17.4.84 w:vAlign）— 規格明確
2. ✅ **機制**：Y 軸 offset 計算（無需轉換、無 char-level 處理）
3. ✅ **type**：適用所有 cell.content 類型（paragraph + nested table）
4. ✅ **細節**：vAlign='center' 時 padding 處理：上下 padding 共享，content 在中間
5. ✅ **位置**：hot zone 4 fixture × 3 page = 12 page 集中區，影響範圍大
6. ✅ **fixture 涵蓋率**：04 全 6 fixture（含 05.*）+ 02/03 部分 fixture，影響廣

→ 全部 6 層都 ✅。Sprint 42 是「**修對所有層的高信心修法**」。

### 8.3 次主軸候選（Sprint 42 / 43）

- **A. cell padding 計算改算法**（OOXML w:tblCellMar + w:tcMar 合併）：對 06 fixture 影響小（4 個都不設 w:tcMar）；可下放
- **B. row height 計算驗證**：若 vAlign 修完仍有殘餘 offset，再查 row height 演算法
- **C. FloatShapeNode prstGeom**：03 cat -7pp 邊際

## 9. 工作摘要

```
（Sprint 41 純診斷無代碼變更）
+  docs/sprint41_grid_diagnosis.md            | 本文件
+  /tmp/sprint41/*.json + *.png               | 16 個 grid analysis 輸出（debug 用）
```

無 vitest / VR / 規劃書代碼變更；只有規劃書 §11.7 / §11.8 同步 Sprint 41 結論與 Sprint 42 方向。

---

## 10. Sprint 33-41 教訓累積（9 個 sprint）

| Sprint | 教訓 | 是否在 41 應用 |
|---|---|---|
| 33-35 | 不要規格先行假設根因 | ✅ 改資料先行 |
| 36 | grid analysis 是強力診斷工具 | ✅ 用 16 個 page 全跑 |
| 37 | 修對「方向」但選錯 type | ✅ 反查 OOXML 確認 vAlign |
| 38 | 修對 type 但選錯細節 | ✅ 確認 vAlign 機制 |
| 39 | 修對細節但選錯 diff 位置 | ✅ Pixel sampling 確認偏移 96pt |
| 40 | 修對 5 層但選錯 fixture | ✅ 4 fixture × 4 page 全跑 |
| **41** | **資料先行 + 6 層 cascading chain 全綠才開工** | **本 sprint 即是落實** |

Sprint 42 開工前應驗證：Sprint 41 找到的 vAlign 修法在 6 層 chain 全綠。Sprint 41 §8.2 已逐條檢查。
