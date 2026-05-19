# Sprint 45 — trHeight omitted-hRule = atLeast（containsImage 二分取代 Sprint 26 ratio>3）

**期間**：2026-05-14
**主軸**：依 Sprint 43 §5 假設 A1/A2，先驗 precondition 再修；A1/A2 原述法皆證偽，但找到真根因並修正
**結論**：**🎉 連兩 sprint 突破！total mean 0.0955 → 0.0774（-1.81pp）。04 cat 0.2439 → 0.1250（-11.89pp，環清表系列收斂）、02 cat -0.82pp、03 cat 持平（全套管 byte-identical）。**
成功公式延續 Sprint 43-44：精準診斷（trace + Pillow 雙路徑）+ 第七層紀律（prep test 驗 precondition）+ 精準修法。

---

## 1. Sprint 43 §5 假設驗證 — A1/A2 原述法皆證偽

| 假設（Sprint 43 §5） | 驗證方法 | 結果 |
|---|---|---|
| **A1：row 0 trHeight=340 twip exact rule 未實作** | 解 04 fixture XML 全部 `<w:trHeight>` | ❌ **證偽**：18 個 trHeight **全無 `w:hRule`**，TableParser 判 `auto`（非 exact）。TableLayout L301 早已正確處理顯式 `exact`，但 fixture 根本沒有 exact 可處理 |
| **A2：empty para `w:line=40 exact` 被算 17pt** | Pillow 量 render/golden row 0 文字 y | ❌ **證偽**：render row 0 文字 y=83.5pt **已對齊** golden y=82.6pt。empty para 確被 `applyDocGridSnap` 由 2pt snap 成 18pt，但這正好讓 render 對齊 golden — 移除 snap 反而退化 |

**第七層紀律生效**：A1/A2 都在「寫 production code 前」被 fixture 資料證偽，避免 Sprint 42 式翻車。

## 2. 真根因（診斷意外收穫）

Pillow 量 golden `06.環清表(112.10.23-10.27)-1.png` 偵測到水平邊框 y_pt = 145.9 / 180.7 / 212.6 → **row 高度 34.8 / 31.9pt**。

對照 04 fixture XML：`<w:trHeight w:val="698"/>` = 34.9pt、`<w:trHeight w:val="637"/>` = 31.85pt。

**34.8 ≈ 34.9、31.9 ≈ 31.85 — golden 精確把 trHeight val 當 row 高度渲染**，即使 `w:hRule` 省略。

但 render 給 row 2/3 = 20.9pt（natural content）。原因：
- TableParser：省略 `w:hRule` → `heightRule='auto'`
- TableLayout（Sprint 26）：`auto` 只在 `val > natural × 3` 才套 val-as-min
- row 2：val 34.9pt / natural 20.9pt，ratio **1.67 < 3** → 不套 → render 用 natural 20.9pt

**真 A1 = 「省略 hRule 的 trHeight，Word 實際以 atLeast 渲染；Sprint 26 的 ratio>3 magic number 過保守，漏掉 ratio ~1.7 的 sparse form row」。**

## 3. 修法（核心 ~12 行）

[static/src/core/layout/TableLayout.ts:layoutRow](../static/src/core/layout/TableLayout.ts)：用「row 是否含 image」二分取代 Sprint 26 的 `ratio > 3`：

```typescript
const rowHasImage = cellsContainImage(cells);
if (row.props.heightRule === 'exact' && row.props.height) {
  rowHeight = row.props.height;
} else if (row.props.heightRule === 'atLeast' && row.props.height) {
  rowHeight = Math.max(rowHeight, row.props.height);
} else if (row.props.height && rowHeight > 0) {
  // omitted / auto hRule：Word 實作以 val 為下限渲染
  if (!rowHasImage && row.props.height > rowHeight) {
    rowHeight = row.props.height;          // 無 image sparse form row：val 即下限
  } else if (row.props.height > rowHeight * 3) {
    rowHeight = row.props.height;          // 含 image row：保留 ratio>3 防膨脹
  }
}
```

**二分原理**：
- **無 image 的 sparse 表單列**（環清表 row 2/3、自主檢查表 sparse row）：val 是「設計高度」→ `val > natural` 即套 val-as-min
- **含 image 的列**（03 全套管 1121229 系列）：val 多為 Word autosave 快取（≈ natural，ratio ~1.07）→ 保留 `ratio > 3` 防過度膨脹引發過分頁

`cellsContainImage` 為既有 helper（Sprint 17），順帶把 `RowLayout.containsImage` 改用同一次計算結果。

## 4. Prep test（第七層紀律）

[tests/unit/layout/TableLayout.test.ts](../tests/unit/layout/TableLayout.test.ts)：

| test | 修法前 | 修法後 |
|---|---|---|
| 無 image row + val 略大於 natural（ratio 1.74）→ 套 val | ❌（取 natural ~14.4）| ✅（取 val 25）|
| 含 image row + val 略大於 natural（ratio 1.5）→ 不套 | — | ✅（保留 natural）|
| 含 image row + val 顯著大於 natural（ratio>3）→ 仍套 | — | ✅（取 val 200）|
| Sprint 26 protect：含 image 全套管 row（ratio<3）→ 不 inflate | ✅ | ✅（改 image cell 準確建模）|

並更新原 Sprint 26「ratio<3 取自然」斷言為 Sprint 45 新語意（該斷言已被 golden 04 環清表證偽）。

整合 trace test [sprint45_exact_snap_trace.test.ts](../tests/integration/sprint45_exact_snap_trace.test.ts) 確認修法後 row 2 = 34.9pt、row 3 = 31.9pt — **精確命中 golden Pillow 量測值（34.8 / 31.9pt）**。

## 5. 視覺收斂 (VR v14) — 連兩 sprint 突破

### 5.1 總體（per-page mean）

| 分類 | Sprint 44 | Sprint 45 | Δ |
|---|---|---|---|
| 01_simple | 0.0699 | 0.0696 | -0.03pp（噪音）|
| **02_std_table** | **0.0997** | **0.0915** | **-0.82pp** |
| **03_complex_table** | **0.1600** | **0.1599** | **持平（無退化）** |
| **04_with_image** | **0.2439** | **0.1250** | **-11.89pp** |
| 05_header_footer | 0.0358 | 0.0355 | noise |
| 06_template | 0.0220 | 0.0222 | noise |
| **TOTAL** | **0.0955** | **0.0774** | **-1.81pp** |

### 5.2 04_with_image per-fixture

| Fixture | Sprint 44 | Sprint 45 | Δ |
|---|---|---|---|
| 06.環清表(112.10.23-10.27) | 0.2355 | 0.0963 | **-13.92pp** |
| 06.環清表(112.10.9-10.13) | 0.2597 | 0.1066 | **-15.31pp** |
| 6.環清表(112.10.2-10.6) | 0.2528 | 0.1210 | **-13.18pp** |
| 6.環清表(112.9.25-9.29) | 0.2593 | 0.1256 | **-13.37pp** |
| 05.磺港溪會議照片 | 0.2081 | 0.1976 | -1.05pp |
| 05.磺港溪會議照片1120923 | 0.2162 | 0.2046 | -1.16pp |

→ 環清表 4 fixture 平均 -13.9pp（trHeight val-as-min 直接收割）；磺港溪會議照片 -1.1pp（同含 table 但結構不同，小幅收割）。

### 5.3 03_complex_table — 全套管 byte-identical（containsImage 保護驗證）

| Fixture | Sprint 44 | Sprint 45 |
|---|---|---|
| 1121229-全套管 | 0.2938 | 0.2938 |
| 1130105-全套管 | 0.2996 | 0.2996 |
| 1130109-全套管 | 0.3111 | 0.3111 |
| 1130112-全套管 | 0.3166 | 0.3166 |
| 1130516-共月橋 | 0.2884 | 0.2884 |

→ 全套管 5 fixture per-page diff **4 位小數完全相同** = containsImage 二分成功保護 autosave-cache row 不被 val-as-min 撐高。Sprint 26 的擔憂已由 containsImage 機制承接。

## 6. vitest

**858 passed + 1 skipped**（+3 net：2 新 prep test + 1 trace test；Sprint 26 舊斷言更新 1）。

Sprint 12 fingerprint snapshot / Sprint 16 page count baseline **本 sprint 有更新**（與 Sprint 44 不同）：
- 修法把 row 撐高 → table 高度變 → 分頁數變 → ops 指紋變。屬**預期內、刻意變更**，已 `vitest -u` 更新 baseline。
- 變更明細見 §7 殘餘。

## 7. 殘餘 gap（Sprint 46 候選）

### 7.1 監造會議記錄過分頁（已知代價，VR 不可見）

6 個 `01_simple/03.*監造會議記錄.docx` 從 golden 3 頁 → render 4 頁（page count baseline `mismatched` 4 → 6）。

根因：監造會議記錄也有單行 trHeight 列（row6 val 22.4pt、row7 val 23.75pt 等），無 image → 被 val-as-min 套用 → 每列微幅撐高累積 → 溢出第 4 頁（sliver）。

**但 Word golden 對監造會議記錄這些列不套 val**（golden=3 頁）。環清表單行列套、監造會議記錄單行列不套 — **兩者皆「無 image 單行文字列」，OOXML 結構上找不到乾淨判別子**。

- VR 影響：01_simple per-page mean 0.0699 → 0.0696（**幾乎無影響**，因 VR 只比 min(golden,ours) 頁；第 4 頁 sliver 不入比對）
- 但 page count baseline 是 regression guard，已記錄此退化

**Sprint 46 方向**：找「表單型 table（honors trHeight）vs 內容型 table（不 honors）」的真判別子。候選：
- 量 golden 監造會議記錄 row 高度，確認 Word 究竟怎麼處理
- 或以「整表是否為文件主體 form」「cell 是否單行」等更細特徵二分
- 或接受監造會議記錄為已知 trade-off（VR 不可見、淨值強正）

### 7.2 03 全套管仍 0.29-0.32（未動）

全套管 5 fixture 仍偏高，Sprint 45 的 containsImage 保護=不動它。其 gap 屬另一根因（floatShape / 字型 metric），留 Sprint 46+。

### 7.3 磺港溪會議照片 0.20（小幅收割未竟）

05.磺港溪會議照片 ×2 僅 -1.1pp，與環清表 -13.9pp 差距大 — 結構不同（會議照片 table 列多為 atLeast/auto 但 val≈natural），Sprint 46 可單獨 trace。

## 8. 工作摘要

```
M  static/src/core/layout/TableLayout.ts            | +14  containsImage 二分取代 ratio>3
M  tests/unit/layout/TableLayout.test.ts            | +50  3 新 prep test + 更新 Sprint 26 斷言/protect test
+  tests/integration/sprint45_exact_snap_trace.test.ts | trace row trHeight / spacing.line / 排版 height
M  tests/integration/08_render_ops_trace.test.ts    | snapshot 更新（分頁變）
M  tests/integration/09_page_count_baseline.test.ts | snapshot 更新（監造會議記錄 +1 頁）
+  docs/sprint45_trheight_valasmin_fix.md           | 本文件
```

VR v14：**total mean 0.0955 → 0.0774（-1.81pp）**；04 -11.89pp、02 -0.82pp、03 持平。
vitest 858 passed + 1 skipped。Sprint 12/16 baseline 已更新（刻意變更）。

## 9. Sprint 33-45 失敗模式累積

| Sprint | 視覺收斂 | 關鍵 |
|---|---|---|
| 33-43 | 0 / 退化 | 規格先行、選錯 type/細節/位置/fixture/precondition |
| **44** | **-1.73pp** | image-only line baseline；prep test 驗 precondition |
| **45** | **-1.81pp** | trHeight omitted-hRule = atLeast；A1/A2 原述法證偽但診斷找到真根因；containsImage 二分保護 03 |

**第七層紀律的價值**：Sprint 45 把 Sprint 43 §5 兩個假設**都證偽**了，但「驗證 precondition」的過程（解 XML + Pillow 量 golden）反而暴露真根因。診斷不是只為了確認假設，更是為了在假設錯時找到對的方向。
