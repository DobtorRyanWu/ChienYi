# Sprint 47 — val-as-min 比較基準改用 naturalUnsnapped（架構正確修法、零退化）

**期間**：2026-05-14
**主軸**：依 Sprint 46 §4 路線 A — val-as-min 比較基準改「未經 docGrid snap 的內容高」
**結論**：**架構正確修法、零退化，但 VR 平（-0.01pp 噪音內）。** 精準修好監造會議記錄 row4（72pt → 44.9pt = golden）；**04_with_image 完全持平 0.1250（成功避開 Sprint 46 全域 unsnap 翻車）**。監造會議記錄過分頁未完全解（主因是 rows 0/1/3/5/11 的 exact/auto-snap，非 val-as-min，留 Sprint 48）。

---

## 1. Sprint 46 留下的真根因

監造會議記錄 row4：
- `golden = 44.9pt = trHeight val`（golden honors trHeight）
- `render natural（snapped）= 72pt`（`2×line=400 exact` 各 20pt 被 docGrid snap 成 36pt）
- Sprint 45 val-as-min 條件 `val(44.9) > natural(72)` = false → 不套 val → 用 72pt

**真根因 = docGrid snap 把 natural 從 40pt 撐到 72pt、撐過 trHeight val，使 val-as-min 的 `val > natural` 判斷失效。**

## 2. 修法（threading naturalUnsnapped）

### 2.1 Line / CellLayout 新增「未 snap 高」欄位

| 層 | 新增欄位 | 計算 |
|---|---|---|
| [Line](../static/src/core/layout/types.ts) | `heightUnsnapped?: Pt` | makeLine：applySpacingLine 後、applyDocGridSnap 前的高度 |
| [CellLayout](../static/src/core/layout/types.ts) | `contentHeightUnsnapped: Pt` | layoutCell：Σ line.heightUnsnapped（lines）+ Σ nestedTable.height（table 不 snap）|

### 2.2 layoutRow：比較基準改用 rowHeightUnsnapped

```typescript
let rowHeightUnsnapped = 0;
for (const c of cells) {
  // ...
  const cUnsnapped = c.contentHeightUnsnapped + c.padding.top + c.padding.bottom;
  if (cUnsnapped > rowHeightUnsnapped) rowHeightUnsnapped = cUnsnapped;
}
// val-as-min 判斷改用 rowHeightUnsnapped（非 snapped rowHeight）
if (!rowHasImage && row.props.height > rowHeightUnsnapped) applyValAsMin = true;
else if (row.props.height > rowHeightUnsnapped * 3) applyValAsMin = true;
```

### 2.3 關鍵：val 勝出的 row 用 docGridLinePitch=0 重排

```typescript
if (applyValAsMin && row.props.height) {
  rowHeight = row.props.height;
  // 重排 cells（不 snap）→ cell 內容回到 exact 值（2×20pt=40pt < val 44.9pt 可容）
  const unsnappedOpts = { ...options, docGridLinePitch: 0 };
  cells = row.cells.map((cell, ci) => layoutCell(cell, ..., unsnappedOpts, rowHeightHint));
}
```

**為何要重排**：只把 `rowHeight = val(44.9)` 不夠——cell 內 line 仍是 snapped 72pt，會溢出比 row 矮的空間。重排讓 line 回 exact 值（40pt）真正容得下。

**與 Sprint 46 全域 unsnap 翻車的關鍵差異**：
- Sprint 46：`applyDocGridSnap` 全域跳過 exact → **所有** exact 行都不 snap → 環清表 row 0（val 不勝出）也被 unsnapped + 表前 empty para 上移 16pt → 04 災難退化
- Sprint 47：**只重排 val 勝出的 row**。val 不勝出的 row（環清表 row 0：val 17 < unsnapped 32）完全不動、維持 snapped；body empty para 不是 table row、完全不受影響 → **環清表零退化**

## 3. Prep test（第七層紀律）

[tests/unit/layout/TableLayout.test.ts](../tests/unit/layout/TableLayout.test.ts) +2：

| test | 驗證 |
|---|---|
| exact 行被 snap 撐高，val-as-min 仍以未 snap 高判斷 → 套 val | row4 型：2×exact-20pt（snap 72 / unsnap 40），val 44.9 → 套 val、contentHeight < 50 |
| val < 未 snap 高 → 不套 val（不誤傷環清表 row 0 型）| 2×exact-16pt（unsnap 32），val 17 → 不套、row > 17、內容維持 snapped |

trace（[sprint46_meeting_record_trace.test.ts](../tests/integration/sprint46_meeting_record_trace.test.ts)）確認 row4：72.0 → **44.9pt（精確命中 golden）**。

## 4. 視覺收斂 (VR v14) — 第八層紀律：全 fixture 驗證

| 分類 | Sprint 45/46 | Sprint 47 | Δ |
|---|---|---|---|
| 01_simple | 0.0696 | 0.0692 | -0.04pp |
| 02_std_table | 0.0915 | 0.0915 | 0 |
| 03_complex_table | 0.1599 | 0.1598 | -0.01pp |
| **04_with_image** | **0.1250** | **0.1250** | **0（零退化）** |
| 05_header_footer | 0.0355 | 0.0355 | 0 |
| 06_template | 0.0222 | 0.0222 | 0 |
| **TOTAL** | **0.0774** | **0.0773** | **-0.01pp（噪音內）** |

comparedPages = 126（不變）。**第八層紀律重點**：04_with_image 零退化 = Sprint 47 的「只重排 val 勝出 row」精準避開了 Sprint 46 全域 unsnap 的 +19.86pp 災難。本 sprint 修法在全 42 fixture VR 驗證後才確認安全。

## 5. 為何 VR 平 — 監造會議記錄過分頁未完全解

Sprint 47 只修好「val 勝出但被 snap 卡住」的 row（監造會議記錄僅 row4）。仍 4 頁（golden 3）的主因：

| row | trHeight | render | golden | 問題 |
|---|---|---|---|---|
| 0 | - | 36.0 | 26.2 | `line=360 auto` ×2 段、無 trHeight val → val-as-min 無從觸發 |
| 1 | 16.65 | 36.0 | 24.7 | `line=460 exact`=23pt snap 成 36pt，val 16.65 < unsnap 23 → val-as-min 不套 |
| 11 | 10.9 | 72.0 | 37.4 | val 10.9 太小 |

這些 row 的根因 = **exact/auto 行被 docGrid snap，且 trHeight val 太小無法救**。golden 對監造會議記錄這些行**不 snap**，但 Sprint 46 已證實「全域不 snap」會災難退化環清表。需要的是「per-row 條件式不 snap」但**判別子不能是 val-as-min**（val 太小）→ 留 Sprint 48。

## 6. vitest

**862 passed + 1 skipped**（+2：Sprint 47 prep test）。
Sprint 16 page count baseline **未變動**（分頁不變）；Sprint 12 fingerprint snapshot 已更新（row4 高度 72→44.9 刻意變更）。

## 7. 工作摘要

```
M  static/src/core/layout/types.ts          | +Line.heightUnsnapped、+CellLayout.contentHeightUnsnapped
M  static/src/core/layout/LineBreaker.ts     | makeLine/makeEmptyLine 計算 heightUnsnapped
M  static/src/core/layout/TableLayout.ts     | layoutCell 累計 contentHeightUnsnapped；layoutRow val-as-min 改用 rowHeightUnsnapped + val 勝出 row 重排
M  tests/unit/layout/TableLayout.test.ts     | +2 Sprint 47 prep test
M  tests/integration/08_render_ops_trace.test.ts | fingerprint snapshot 更新（row4 高度變）
+  docs/sprint47_valasmin_unsnapped_basis.md  | 本文件
```

VR v14：**total 0.0774 → 0.0773（-0.01pp，噪音內）；04 零退化**。
vitest 862 passed + 1 skipped。

## 8. Sprint 33-47 失敗模式累積

| Sprint | 視覺收斂 | 關鍵 |
|---|---|---|
| 44 | -1.73pp | image-only line baseline |
| 45 | -1.81pp | trHeight omitted-hRule = atLeast；containsImage 二分 |
| 46 | 0（A2 翻車 revert）| 實測 > 推測；診斷定位真根因 |
| **47** | **0（架構正確、零退化）** | **naturalUnsnapped 比較基準；「只重排 val 勝出 row」精準避開 Sprint 46 全域翻車；第八層紀律全 fixture 驗證** |

**Sprint 47 的價值**：不是 VR 數字，而是 **(a) 修正了 val-as-min 用錯比較基準的潛在 bug、(b) 證明「targeted（只動 val 勝出 row）」能安全做到 Sprint 46「global（全動）」做不到的事、(c) 建立 heightUnsnapped / contentHeightUnsnapped 基礎建設供 Sprint 48 用**。診斷與基礎建設的投資不是浪費（Sprint 44 突破正是靠 Sprint 36-43 累積）。

## 9. Sprint 48 候選

監造會議記錄過分頁殘餘 = exact/auto 行被 snap、trHeight val 太小救不了。方向：
- A. 找「per-row 條件式不 snap」的判別子（非 val-as-min）——例如「row 有顯式 trHeight 且 cell 全 exact 行」→ 視 trHeight 為 row 高度上限、內部不 snap
- B. `line=360 auto`（rows 0/3/5）：auto × 1.5 multiplier 後 snap 過度膨脹（natural 21.6 → 36），查 auto+docGrid 正確互動
- C. 接受監造會議記錄過分頁為已知 trade-off（VR 不可見），轉 03 全套管殘餘 / 商業化
