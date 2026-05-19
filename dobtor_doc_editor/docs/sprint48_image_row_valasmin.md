# Sprint 48 — 含 image 列同樣 honors trHeight val（移除 Sprint 45 image 區分）

**期間**：2026-05-14
**主軸**：規劃書 §11.14 路線 B — 診斷 + 修 03 全套管殘餘 gap（0.29-0.32，當前最大 VR gap）
**結論**：**🎉 03_complex_table 0.1598 → 0.1316（-2.82pp）、total 0.0773 → 0.0749（-0.24pp）、零退化。** 全套管 5 fixture 全部 -5~-7pp。診斷確認 golden 對含 image 的列同樣 honors trHeight val，修法 = 移除 Sprint 45 的「含 image → ratio>3」區分。

---

## 1. 診斷（grid_analysis + Pillow + trace 三路徑）

### 1.1 grid_analysis
1121229-全套管 overall diff 29.29%；Top 12% worst cells（mean ratio 98.97%）集中在 px y 225-551（= 第一張照片區域內）。

### 1.2 docx 結構
- body：2 標題段落 + 1 table（2 rows × 3 cols）
- 每 row 的 c2：1 inline 照片 + 1 `mc:AlternateContent`（Choice = DrawingML anchored textbox 含 rect 邊框、顯示日期；Fallback = VML，正確忽略）+ date 段落
- row trHeight：row0 = 266.8pt、row1 = 278.45pt，**無 `w:hRule`**

### 1.3 Pillow 實測（render vs golden）
| | RENDER | GOLDEN |
|---|---|---|
| 照片 1 起點 | px 204（pt 98）| px 300（pt 144）|
| 照片排列 | **連續 944px 無間隔** | 各 468px + **88px(~42pt) 間隔** |
| 照片 2 起點 | px 677 | px 856 |

→ **golden photo 1↔2 間距 267pt ≈ trHeight val 266.8pt**。render row = 226.8pt（≈ 僅照片高度）。

### 1.4 真根因
golden 對含 image 的 row 同樣 honors trHeight val（row0 = 266.8pt）。render 用 natural ~226.8pt，因為：
- floatTextBox（日期框）被 extractFloats 抽出 → 不計入 contentHeight
- date 段落貢獻少
→ row 偏矮 ~40pt → 照片過高、照片間無間隔 → 29% diff。

**Sprint 45 的「含 image → ratio>3」guard 卡住了它**：全套管 row val/natural = 266.8/226.8 ≈ 1.18 < 3 → val-as-min 不套 → 用 natural。

## 2. 修法（layoutRow，~移除 4 行分支）

[static/src/core/layout/TableLayout.ts:layoutRow](../static/src/core/layout/TableLayout.ts)：

```typescript
// Sprint 45（舊）：
// if (!rowHasImage && val > rowHeightUnsnapped) applyValAsMin = true;
// else if (val > rowHeightUnsnapped * 3) applyValAsMin = true;

// Sprint 48（新）：移除 image 區分
if (row.props.height > rowHeightUnsnapped) {
  applyValAsMin = true;
}
```

**演進史**：
- Sprint 26：`val > natural × 3` magic number
- Sprint 45：改「含 image」二分（無 image → val > natural；含 image → ratio>3）
- Sprint 47：比較基準改 `rowHeightUnsnapped`（未經 docGrid snap）
- **Sprint 48：移除 image 區分** — Pillow 實測 golden 全套管 photo 列同樣 honors trHeight val；Sprint 26 的 autosave-cache 顧慮，在 Sprint 47 的 naturalUnsnapped 基準下已自然化解（`val > naturalUnsnapped` 只在 val 真的大於內容時才觸發、autosave 快取 val ≈ natural 時不觸發）

## 3. Prep test（第七層紀律）

[tests/unit/layout/TableLayout.test.ts](../tests/unit/layout/TableLayout.test.ts) 更新 3 個 image-row 測試 + 新增 1 個：

| test | Sprint 45（舊）| Sprint 48（新）|
|---|---|---|
| 含 image row + val > natural | 不套（ratio<3 保留）| ✅ 套 val |
| 含 image row + val 顯著 > natural | 套（ratio>3）| ✅ 套（不變）|
| 含 image row + val ≤ natural（autosave 快取型）| — | ✅ 不套（新增，驗證 autosave-cache 顧慮的正解）|
| 含 image 全套管 row（val > natural）| 不 inflate（被證偽）| ✅ honors trHeight val |

trace（[sprint48_quantanguan_trace.test.ts](../tests/integration/sprint48_quantanguan_trace.test.ts)）確認照片間隔：0 → **45.8pt**（golden ~42pt）。

## 4. 視覺收斂 (VR v14) — 第八層紀律全 fixture 驗證

### 4.1 總體

| 分類 | Sprint 47 | Sprint 48 | Δ |
|---|---|---|---|
| 01_simple | 0.0692 | 0.0692 | 0 |
| 02_std_table | 0.0915 | 0.0915 | 0 |
| **03_complex_table** | **0.1598** | **0.1316** | **-2.82pp** |
| 04_with_image | 0.1250 | 0.1251 | +0.01pp（噪音）|
| 05_header_footer | 0.0355 | 0.0355 | 0 |
| 06_template | 0.0222 | 0.0222 | 0 |
| **TOTAL** | **0.0773** | **0.0749** | **-0.24pp** |

### 4.2 03 全套管 per-fixture

| Fixture | Sprint 47 | Sprint 48 | Δ |
|---|---|---|---|
| 1121229-全套管 | 0.2938 | 0.2292 | **-6.46pp** |
| 1130105-全套管 | 0.2996 | 0.2362 | **-6.34pp** |
| 1130109-全套管 | 0.3111 | 0.2387 | **-7.24pp** |
| 1130112-全套管 | 0.3166 | 0.2627 | **-5.39pp** |
| 1130516-共月橋 | 0.2884 | 0.2326 | **-5.58pp** |

**零退化驗證**：04_with_image +0.01pp（pixelmatch 噪音）、comparedPages = 126（不變）、Sprint 16 page count baseline **PASS**（無分頁變化、全套管仍 1 頁）。Sprint 26 的 autosave-cache 過分頁顧慮 = 未發生（naturalUnsnapped 基準正確隔離）。

## 5. vitest

**864 passed + 1 skipped**（+2 net：image-row 測試更新 + 1 新增 + trace test）。
Sprint 16 page count baseline 未變動；Sprint 12 fingerprint snapshot 已更新（全套管 row 高度 226.8 → 266.8/278.45 刻意變更）。

## 6. 殘餘 gap（Sprint 49 候選）

全套管仍 0.23-0.26（從 0.29-0.32 降）。Pillow 顯示 render photo 1 仍 pt 118 vs golden pt 144（~26pt 偏高）——row 高度修對了，但 row **內**照片的 Y 位置仍偏高。可能來源：
- cell c2 內 floatTextBox / date 段落的相對位置
- 照片在 266.8pt row 內的 vAlign / 起始 offset
- 標題段落（body 前 2 段）高度

## 7. 工作摘要

```
M  static/src/core/layout/TableLayout.ts        | layoutRow 移除 image 區分（~-4 行 +註解）
M  tests/unit/layout/TableLayout.test.ts        | 3 image-row 測試更新 Sprint 48 語意 + 1 新增
+  tests/integration/sprint48_quantanguan_trace.test.ts | 全套管 ops/結構 trace（診斷保留）
M  tests/integration/08_render_ops_trace.test.ts | fingerprint snapshot 更新（全套管 row 高度變）
+  docs/sprint48_image_row_valasmin.md           | 本文件
```

VR v14：**total 0.0773 → 0.0749（-0.24pp）；03 -2.82pp（全套管 -5~-7pp）；零退化**。
vitest 864 passed + 1 skipped。

## 8. Sprint 33-48 收斂軌跡

| Sprint | 視覺收斂 | 關鍵 |
|---|---|---|
| 44 | -1.73pp | image-only line baseline |
| 45 | -1.81pp | trHeight omitted-hRule = atLeast；containsImage 二分 |
| 46 | 0（A2 翻車 revert）| 診斷定位真根因 |
| 47 | 0（架構正確、零退化）| naturalUnsnapped 比較基準 + 只重排 val 勝出 row |
| **48** | **-0.24pp** | **移除 image 區分；golden 含 image 列同樣 honors trHeight val；Sprint 47 的 naturalUnsnapped 基準讓 autosave-cache 顧慮自然化解** |

**心得**：Sprint 45-48 是一條「val-as-min 演進鏈」——Sprint 45 用 image 二分（當時的最佳猜測）、Sprint 47 建 naturalUnsnapped 基礎建設、Sprint 48 用 Pillow 實測推翻 image 二分。每一步的「過度保守假設」都被下一步的實測修正。Sprint 47 看似 VR 平、無收斂，但它建立的 naturalUnsnapped 基準正是 Sprint 48 能安全移除 image 區分的前提（化解 Sprint 26 autosave-cache 顧慮）。基礎建設的價值在後續 sprint 才兌現。
