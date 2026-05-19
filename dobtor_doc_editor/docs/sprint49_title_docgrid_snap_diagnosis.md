# Sprint 49 — 全套管照片 Y 偏高診斷（docGrid snap 全域實驗翻車 + 真根因定位）

**期間**：2026-05-14
**主軸**：規劃書 §11.15 路線 A — 診斷全套管 row 內照片 Y 偏高 ~26pt 殘餘
**結論**：**精準定位真根因 = golden 對「無 spacing.line」的 body 標題段落 snap 到 docGrid（render 不 snap）；實驗移除 Sprint 29 guard → VR 全域翻車（02_std_table +3.61pp、total +0.27pp）→ 已 revert。** VR 維持 Sprint 48 baseline 0.0749（無損害）。

---

## 1. 診斷：照片 vAlign 置中正確，26pt 偏差 = 標題塊高度

trace 全套管 table 結構（[sprint49_photo_y_trace.test.ts](../tests/integration/sprint49_photo_y_trace.test.ts)）：

```
line y=28.4 h=26.4   ← 標題 p0「任泰技術顧問有限公司」sz=44(22pt)
line y=54.8 h=21.6   ← 標題 p1 line1 sz=32/36
line y=76.4 h=21.6   ← 標題 p1 line2
TABLE at y=98.0
  row0 y=98.0 h=266.8
    c0 vAlign=center contentH=307.2（rowSpan=2 anchor，工程名稱長文字）
    c2 vAlign=center contentH=226.8（照片）floats=1（日期 textbox）
```

照片 Y 計算（vAlign=center）：`98(rowtop) + (266.8 - 226.8)/2 = 118` → render photo y=118 ✅ **vAlign 置中正確**。

→ render photo y=118、golden photo y=144（Sprint 48 Pillow）。**26pt 偏差 = table 起點差**（render table y=98、golden ~124）= **table 前 2 段標題塊高度差**（render 69.6pt vs golden ~96pt）。

## 2. 真根因：golden snap 無 spacing.line 標題段落到 docGrid

Pillow 精測標題各行 line advance（center-to-center）：

| | render | golden |
|---|---|---|
| p0（22pt 字）| 26.4pt | **35.8pt** |
| p1 line（18pt 字）| 21.6pt | **36.0pt** |

**golden 兩行皆 = 36pt = 2 × docGrid pitch（18pt）**。render natural：
- p0：22 × 1.2 = 26.4 → `ceil(26.4/18)×18 = 36` ✅ 精確命中 golden
- p1：18 × 1.2 = 21.6 → `ceil(21.6/18)×18 = 36` ✅ 精確命中 golden

→ **golden 對「無 spacing.line」的 body 標題段落同樣 snap 到 docGrid**。但 render 的 `applyDocGridSnap` 有 Sprint 29 的 guard `if (!para.props.spacing?.line) return height` → 不 snap。

標題段落 XML 確認：`<w:pPr>` 無 `<w:spacing>`、無 `<w:pStyle>`；styles.xml `<w:pPrDefault/>` 為空 → 確實無任何 spacing.line 來源。

## 3. 實驗：移除 Sprint 29 的「無 spacing.line → 不 snap」guard → 翻車

ECMA-376 §17.3.1.32 snapToGrid 本與 spacing.line 正交（snapToGrid 預設 on 即 snap），Sprint 29 的 guard 是經驗 hack。移除它 + 2 prep test，VR 全 42 fixture：

| 分類 | Sprint 48 | 實驗 | Δ |
|---|---|---|---|
| **02_std_table** | **0.0915** | **0.1276** | **+3.61pp** ✗✗ |
| 03_complex_table | 0.1316 | 0.1194 | -1.22pp ✓ |
| 04_with_image | 0.1251 | 0.1239 | -0.12pp |
| **TOTAL** | **0.0749** | **0.0776** | **+0.27pp** ✗ |

→ 03 全套管 title 修對（-1.22pp），但 **02_std_table 災難退化（+3.61pp）** = Sprint 29 comment 的「大量誤觸」應驗——02 有無 spacing.line 段落**不該** snap。net +0.27pp 淨退化 → **已 revert**（production code byte-identical Sprint 48；VR 重跑確認回 0.0749）。

## 4. 真根因確認 = 又一個「snap 判別子」地雷

| Sprint | snap 議題 | 全域改動結果 |
|---|---|---|
| 46 | exact 行該不該 snap | 全域不 snap → 04 +19.86pp 翻車 |
| **49** | **無 spacing.line 段落該不該 snap** | **全域 snap → 02 +3.61pp 翻車** |

兩者同構：**snap 行為深度 fixture-dependent，沒有乾淨的全域開關**。
- 全套管 title 段落（無 spacing.line）**該** snap
- 02_std_table 段落（無 spacing.line）**不該** snap
- 兩者 OOXML 結構上都「無 spacing.line」→ 找不到結構判別子

## 5. Sprint 50 候選

### A. 找「無 spacing.line 段落該不該 snap」的真判別子
- 比對全套管 title vs 02_std_table 段落的差異（font? 是否 body 直屬 vs in-table? jc=center? 是否有負縮排?）
- 高風險、需第八層紀律全 fixture VR

### B. 接受殘餘、轉商業化（規劃書 §11.15 路線 B）
- total 0.0749 = 穩 A- 級
- 全套管殘餘 0.23-0.26 的 26pt 偏差 = 已知 docGrid-snap edge case
- 轉 Phase 6 產品打磨

### C. 其他 VR gap
- 監造會議記錄過分頁（Sprint 47 殘餘）— 同屬 snap 地雷
- opentype.js 真實字型 metric — 大工程、高風險

**建議**：路線 B。Sprint 46 + 49 已兩次證實 snap 是無乾淨解的地雷區；total 0.0749 穩 A- 級已可商用。snap 判別子可排入長期 backlog，待累積更多 fixture 對比資料再攻。

## 6. vitest

**866 passed + 1 skipped**（+2 net：sprint49 trace test + Sprint 49 lock test「無 spacing.line → 不 snap」；實驗的 prep test 已隨 revert 改為鎖定正確行為）。
Sprint 12/16 baseline **未變動**（code 已 revert 回 Sprint 48）。

## 7. 工作摘要

```
（production code 無淨變更 — 實驗已 revert，applyDocGridSnap byte-identical Sprint 48）
M  static/src/core/layout/LineBreaker.ts          | applyDocGridSnap 註解補 Sprint 49 翻車記錄
M  tests/unit/layout/LineBreaker.test.ts          | 實驗 prep test 改為鎖定「無 spacing.line → 不 snap」
+  tests/integration/sprint49_photo_y_trace.test.ts | 全套管 table/cell/photo Y trace（診斷保留）
+  docs/sprint49_title_docgrid_snap_diagnosis.md   | 本文件
```

VR v14：**維持 Sprint 48 baseline 0.0749（實驗 revert，無損害）**。
vitest 866 passed + 1 skipped。

## 8. Sprint 33-49 收斂軌跡

| Sprint | 視覺收斂 | 關鍵 |
|---|---|---|
| 44 | -1.73pp | image-only line baseline |
| 45 | -1.81pp | trHeight omitted-hRule = atLeast |
| 46 | 0（翻車 revert）| exact-snap 全域改動翻車；診斷定位 |
| 47 | 0（架構正確）| naturalUnsnapped 基礎建設 |
| 48 | -0.24pp | 含 image 列 honors trHeight val |
| **49** | **0（翻車 revert）** | **無 spacing.line snap 全域改動翻車；精準定位真根因 = golden snap 標題段落** |

**心得**：Sprint 46 與 49 都是「snap 全域開關翻車」——一個方向翻一邊（exact 不 snap → 04 爆）、另一個方向翻另一邊（無 spacing.line snap → 02 爆）。這強烈暗示 docGrid snap 的正確規則是**段落層級條件式**、非全域開關，且判別子尚未找到。診斷投資累積中：Sprint 49 已精確量化「全套管 title 該 snap、02 不該」這組對比，是 Sprint 50+ 找判別子的素材。
