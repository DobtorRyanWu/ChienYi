# Sprint 46 — 監造會議記錄過分頁診斷（A2 假設實測翻車 + 真根因定位）

**期間**：2026-05-14
**主軸**：修 Sprint 45 殘餘 — 6 個監造會議記錄 fixture 過分頁 +1
**結論**：**實測「exact 行不 snap」假設（Sprint 43 §5 A2）→ VR 災難退化 04（0.1250 → 0.3236，+19.86pp）→ 已 revert。** 但診斷精準定位真根因 = **exact-snap 把 natural 撐到 trHeight val 之上、卡住 Sprint 45 的 val-as-min**。VR 維持 Sprint 45 baseline 0.0774（無損害）。

---

## 1. 診斷：過分頁不是 Sprint 45 val-as-min 造成的

trace 監造會議記錄第一張 table（[sprint46_meeting_record_trace.test.ts](../tests/integration/sprint46_meeting_record_trace.test.ts)）對比 Pillow 量測 golden：

| row | trHeight | render（Sprint 45）| golden | 判定 |
|---|---|---|---|---|
| 0 | - | 36.0 | 26.2 | render +9.8（auto+docGrid）|
| 1 | 16.65 | 36.0 | 24.7 | render +11.3（exact-snap）|
| 4 | 44.9 | 72.0 | 44.9 | **render +27.1（exact-snap）** |
| 6 | 22.4 | 22.4 | 22.1 | ✅ val-as-min 命中 |
| 7 | 23.75 | 23.8 | 24.0 | ✅ |
| 8 | 21.05 | 21.1 | 21.1 | ✅ |
| 9 | 38.75 | 38.8 | 38.4 | ✅ |
| 13 | 46.45 | 46.5 | 46.6 | ✅ |

**rows 6-15（Sprint 45 val-as-min 套用處）精確對齊 golden** → Sprint 45 修法正確。
過分頁來自 **rows 0/1/3/4/5/11 的 natural 過高**（render 36-72pt vs golden 24-45pt），這些 row `val < natural` → val-as-min 不觸發 → 用 natural。

**Sprint 45 副作用機制**：Sprint 45 前 rows 6-15 偏矮（未套 val）、rows 0-11 偏高（exact-snap），兩誤差互相抵消 → 巧合 3 頁。Sprint 45 修正 rows 6-15 → 抵消消失 → 過分頁暴露。

## 2. 實測假設 A2（exact 行不 snap）— 翻車

Sprint 43 §5 假設 A2：OOXML §17.3.1.33 `lineRule=exact` = 精確行高，docGrid 不應覆蓋。
監造會議記錄證據看似支持：row1 `line=460 exact`（23pt）被 snap 成 36pt；row4 `2×line=400 exact`（40pt）被 snap 成 72pt。

修 `applyDocGridSnap`（exact rule → 不 snap）+ 3 prep test，trace 確認 row4 72.0 → **44.9（精確命中 golden）**、row1 36.0 → 23.0。

**但 VR 全 42 fixture 實測 — 災難退化**：

| 分類 | Sprint 45 | A2 實驗 | Δ |
|---|---|---|---|
| **04_with_image** | **0.1250** | **0.3236** | **+19.86pp** ✗✗✗ |
| 03_complex_table | 0.1599 | 0.1882 | +2.83pp ✗ |
| 02_std_table | 0.0915 | 0.0987 | +0.72pp ✗ |
| **TOTAL** | **0.0774** | **0.1025** | **+2.51pp** ✗ |

04 頁數 28 → 16：環清表 exact 行 unsnapped 後表變太矮、**under-paginate**。

→ **Sprint 29 對主流 04 案例的 snap-exact 是對的；Sprint 45「A2 證偽」結論正確。** 監造會議記錄的 exact-snap 看似錯只是「natural 偏高」這個更深問題的表象。**已 revert**（production code byte-identical Sprint 45；VR 重跑確認回 0.0774、comparedPages 126）。

## 3. 真根因（診斷收穫）

監造會議記錄 row4：
- `golden = 44.9pt = trHeight val 44.9`（golden honors trHeight，Sprint 45 已證實此機制）
- `render natural = 72pt`（2 × exact-400-twip 行，各 20pt 被 docGrid snap 成 36pt）
- Sprint 45 val-as-min 條件 `val > natural`：`44.9 > 72` = **false** → 不套 val → render 用 natural 72pt

**真根因 = exact-snap 把 natural（72）撐到 trHeight val（44.9）之上，使 Sprint 45 的 `val > natural` 判斷失效。**
若 natural 用「未 snap 的真實內容高」（40pt），則 `44.9 > 40` = true → 套 val 44.9 = golden。

環清表與監造會議記錄能同時成立的原因：兩者 golden 都 honors trHeight val，差別只在 render 的 natural 是否被 exact-snap 撐過 val。環清表 row 2/3 natural（20.9）< val（34.9）→ Sprint 45 已正確套用；監造會議記錄 row4 natural 被撐到 72 > val 44.9 → 卡住。

## 4. Sprint 47 候選（真修法方向）

**val-as-min 的 `natural` 比較基準應改用「未經 docGrid snap 的內容高」**：
- layoutRow 算 rowHeight 時，同時保留一份 `naturalUnsnapped`（cell lines 用 applySpacingLine 但不過 applyDocGridSnap 的高度和）
- val-as-min 判斷改 `!rowHasImage && val > naturalUnsnapped` → 套 `val`
- 最終 render 高度仍可選 snapped 或 val（取較合理者）

需第七層紀律：prep test 驗證 row4 naturalUnsnapped = 40pt、val 44.9 > 40 → 套 val；且 VR 驗證不退化環清表（環清表 row 2/3 naturalUnsnapped 仍 < val）。

替代方案（風險較高）：
- B：偵測「row 有 trHeight val 且 cell 全為 exact 行」→ 直接用 trHeight val（視 trHeight 為 exact row height）
- C：`line=360 auto` 的 docGrid 互動另查（rows 0/3/5：render 36pt vs golden 26pt，auto × 1.5 multiplier 後 snap 過度膨脹）

## 5. vitest

**860 passed + 1 skipped**（+2 net：sprint46 trace test +1；LineBreaker 「exact 仍 snap」鎖定 test +1，原 3 prep test 已隨 revert 移除）。
Sprint 12/16 baseline **未變動**（code 已 revert 回 Sprint 45 狀態）。

## 6. 工作摘要

```
（production code 無淨變更 — A2 實驗已 revert，applyDocGridSnap byte-identical Sprint 45）
M  static/src/core/layout/LineBreaker.ts          | applyDocGridSnap 註解補 Sprint 46 翻車記錄
M  tests/unit/layout/LineBreaker.test.ts          | A2 prep test 移除，改鎖定「exact 仍 snap」正確行為
+  tests/integration/sprint46_meeting_record_trace.test.ts | 監造會議記錄 row height trace（診斷保留）
+  docs/sprint46_meeting_record_diagnosis.md       | 本文件
```

VR v14：**維持 Sprint 45 baseline 0.0774（A2 實驗 revert，無損害）**。
vitest 860 passed + 1 skipped。

## 7. Sprint 33-46 失敗模式累積

| Sprint | 視覺收斂 | 關鍵 |
|---|---|---|
| 33-43 | 0 / 退化 | 規格先行、選錯 type/細節/位置/fixture/precondition |
| 44 | -1.73pp | image-only line baseline |
| 45 | -1.81pp | trHeight omitted-hRule = atLeast；containsImage 二分 |
| **46** | **0（A2 翻車 revert）** | **實測 > 推測：A2 在監造會議記錄看似對、全域 VR 災難退化 04；但診斷定位真根因 = exact-snap 卡住 val-as-min** |

**教訓**：Sprint 46 是「第八次驗證紀律」案例 — prep test 通過（exact 不 snap 確實改 row height）、trace 確認 row4 命中 golden，**但 prep test / trace 只驗「目標 fixture」，未驗「全 fixture 不退化」**。第七層紀律（precondition 在 fixture data 上驗證）需擴充第八層：**修法在全 fixture VR 上驗證才算數，單 fixture trace 命中 ≠ 全域正確**。Sprint 45 的 containsImage 二分之所以成功，正因它隔離了「含 image / 不含 image」兩類；Sprint 46 的 exact-snap 是全域開關、無隔離 → 環清表與監造會議記錄被綁在一起。
