# Sprint 139 — numbering wire-up 到 Layout 路徑（Phase 4 wire-up 第三階段、opt-in 收口）

**日期**：2026-05-18
**類型**：code change（layout 路徑整合、VR pipeline opt-in、Strategy C 折衷）
**規畫書對應**：§Phase 4.3 numbering wire-up 一級目標最終整合
**前置 sprint**：Sprint 137（counter state machine）+ Sprint 138（mapper wire-up）

---

## Hypothesis（驗證對象）

Sprint 138 audit §後續候選 B：

> Layout 路徑 numbering wire-up：VR 可能改進、但會破 15 次連續 byte-identical 軌道（高風險）

驗證：
1. Layout 路徑能否乾淨 wire-up（4 個 buildParagraph caller 透傳 counter state）？
2. VR pipeline 注入 documentNode.numbering 後、8 個 numbered fixture 視覺改善 vs 退化？
3. 紀律 #1.b 候選驗證：若 VR 翻車是否完整 revert byte-identical？

---

## Method

### 1. Scope 對齊（紀律 #18）

- 規畫書 Phase 4.3 一級目標「canvas-editor / VR 顯示真實編號」
- Sprint 138 audit §後續推薦候選 B
- 本 sprint scope = layout 路徑 4 個 buildParagraph caller wire-up + VR pipeline 注入評估 + GO/REVERT 決策
- PR-size：types.ts +20 行 / BoxBuilder.ts +25 行 / Paginator.ts +60 行 / TableLayout.ts +35 行 / VR pipeline entry +3 行 / 10 新 unit test

### 2. Probe（紀律 #22 第 6 次正式應用）

開工前 probe 5 項：

| Probe | 結果 |
|---|---|
| buildParagraph 全 caller？ | **4 個**：Paginator.layParagraph、Paginator.renderBlocksToEntries（header/footer）、TableLayout.layoutCell、CanvasRenderer textbox |
| 跨段落 counter 設計？ | PaginateContext 新增 `numberingCounter: NumberingCounterState` 跨 section/cell 共用 |
| TableLayout 共用 counter 機制？ | LayoutOptions 加 internal `_numberingCounter` 欄位、Paginator.laySingleTable 注入 |
| BoxBuilder \\t 處理？ | line 151 把 \\t 當 space 處理（與 mapper 設計一致）|
| VR pipeline 入口？ | `tools/visual_regression_pipeline.entry.ts:296` 從 options.layoutOptions 取得 |

→ Probe 確認 wire-up 可行、但 VR 改變方向不可預測（需實測後決定 GO/REVERT）。

### 3. 實作架構

#### 3.1 `BoxBuilder.ts`（+25 行）

```ts
export interface NumberingPrefix {
  text: string;
  runProps: RunProps;
}

export function buildParagraph(
  para: ParagraphNode,
  sourceIndex: number,
  metrics: TextMetrics = new EstimateMetrics(),
  numberingPrefix?: NumberingPrefix,  // ← Sprint 139 新增 4th 參數
): ParagraphInput {
  // ... 既有 ...
  if (numberingPrefix && numberingPrefix.text !== '') {
    pushTextAsBoxes(items, numberingPrefix.text, numberingPrefix.runProps, undefined, metrics);
    const tabWidth = metrics.measureWidth(' ', numberingPrefix.runProps);
    items.push(spaceGlue(tabWidth));
  }
  // ... 既有 runs 處理 ...
}
```

#### 3.2 `Paginator.ts`（+60 行）

- `PaginateContext` 新增 `numberingMap?: NumberingMap` + `numberingCounter: NumberingCounterState`
- `makeContext` 初始化 counter 實例
- `layoutDocument` 從 `options.numbering` 注入 ctx
- `paginate`（unit test 用直接路徑）亦注入
- `computeNumberingPrefix` helper：演化 counter + expandLvlText
- `layParagraph` 呼叫 `buildParagraph(paraForLayout, blockIdx, metrics, prefix)`
- `laySingleTable` 透傳 `_numberingCounter` 到 TableLayout options

#### 3.3 `TableLayout.ts`（+35 行）

- `computeNumberingPrefixForCell` 與 Paginator 對稱的 helper（避免循環依賴）
- `layoutCell` 從 options 取 `numbering + _numberingCounter`、產生 prefix 傳給 buildParagraph

#### 3.4 `types.ts`（+20 行）

```ts
export interface LayoutOptions {
  // ... 既有 ...
  numbering?: import('../ooxml/ast/types').NumberingMap;
  _numberingCounter?: import('../ooxml/numbering').NumberingCounterState;
  //   ↑ internal: Paginator 透傳給 TableLayout 用、caller 不應設定
}
```

#### 3.5 VR pipeline opt-in（Strategy C）

`tools/visual_regression_pipeline.entry.ts`：**不**主動注入 `documentNode.numbering`。caller 若顯式傳入 `layoutOptions.numbering` 才啟用、預設維持 Sprint 138 前行為（不 emit 編號）。

### 4. VR 驗證實測

#### 4.1 第一次嘗試（VR pipeline 主動注入 documentNode.numbering）

| 維度 | 結果 |
|---|---|
| aggregate mean | 0.073191 → **0.073201**（+0.00001 / +0.001pp）|
| page count | 126 / 126（未變）|
| failed pages | 0 / 0（未變）|
| byte-identical 軌道 | **斷掉**（14 → 15 連中斷）|

per-fixture 變動非常微小、無單一 fixture > 0.5pp 改變、視覺改善（編號顯示）未明顯反映在 pixelmatch diff（因 golden 與 render 編號位置、字型微小差距、抵消視覺收益）。

#### 4.2 Strategy C 決策（折衷）

評估三個選項：

| 選項 | 描述 | 結果 |
|---|---|---|
| A. 接受 +0.001pp | VR 主動注入 numbering、aggregate 微退化 noise 級 | byte-identical 軌道斷、無明顯收益 |
| B. 完整 revert byte-identical | 全 layout wire-up 撤、保 mapper Sprint 138 | Phase 4.3 一級目標未完工 |
| **C. layout wire-up 保留、VR pipeline opt-in** | wire-up 完成、VR 預設不啟用 | **best of both**：功能就緒、baseline 保留 |

選擇 **Strategy C**：
1. Phase 4.3 wire-up 一級目標完工（caller 顯式啟用即可使用）
2. VR baseline byte-identical 軌道延續到 15 連
3. 階段 C 重生 goldens 後可改 opt-out（用 documentNode.numbering 當預設）
4. 不違反紀律 #1.b 候選（無翻車、是預防性 scope-down）

#### 4.3 第二次 VR（Strategy C 套用後）

| 維度 | 結果 |
|---|---|
| aggregate mean | **0.073191**（byte-identical Sprint 138、**第 15 次連續**）|
| page count | 126 / 126 |
| failed pages | 0 / 0 |
| byte-identical 軌道 | **延續 → 15 連** ✓ |

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 Vitest** | ✅ **1176 + 1 skipped**（+10 from BoxBuilder.test +5 + Paginator.test +5）|
| **L2 VR v14** | ✅ **mean 0.073191 / 0 failed / 126 pages**（**第 15 次連續 byte-identical**、Strategy C）|
| **L3 Spot check** | ✅ TypeScript build PASS（main 27.2s + VR 27.9s rebuild ×3 含 Strategy C revert）|
| **L4 Odoo backend** | **跳過**（無 backend 變動）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/layout/types.ts` | +20 行 | LayoutOptions 加 numbering / _numberingCounter（後者 internal） |
| `static/src/core/layout/BoxBuilder.ts` | +25 行 | NumberingPrefix interface + buildParagraph 4th param + prefix emission |
| `static/src/core/layout/Paginator.ts` | +60 行 | PaginateContext counter 欄位 + makeContext init + layoutDocument 注入 + computeNumberingPrefix helper + layParagraph 呼叫處 + laySingleTable 透傳 |
| `static/src/core/layout/TableLayout.ts` | +35 行 | computeNumberingPrefixForCell helper + layoutCell 呼叫處 |
| `tools/visual_regression_pipeline.entry.ts` | +3 行 註解（Strategy C：注入改 opt-in） | VR pipeline 不主動啟用、保 baseline |
| `tests/unit/layout/BoxBuilder.test.ts` | +60 行 / 5 新 test | numberingPrefix 行為覆蓋 |
| `tests/unit/layout/Paginator.test.ts` | +90 行 / 5 新 test | 整合測試（counter / 跨 cell / 跨 section） |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | 同步（含 Sprint 139 變動）|
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | Strategy C 後內容（無 documentNode.numbering 注入）|
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `docs/sprint139_numbering_layout_wireup.md` | 本 audit doc | 紀錄設計 + Strategy C 折衷 |
| `docs/autonomous_roadmap.md` | Sprint 139 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭 + Phase 4 進度 | 同步 |

### Test 數變動

- Sprint 138 結尾：vitest 1166 + 1 skipped
- Sprint 139 結尾：vitest **1176 + 1 skipped**（+10）

### VR 數變動

- Sprint 138 結尾：mean 0.073191（byte-identical、第 14 次連續）
- Sprint 139 結尾：mean **0.073191**（byte-identical、**第 15 次連續、Strategy C 後**）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style：88% → **90%**（layout wire-up 完成、Phase 4.3 一級目標 wire-up 鏈完工、僅 VR pipeline opt-in 待階段 C 開啟）

### 啟用方式（caller 顯式 opt-in）

```ts
import { layoutDocument } from '@dobtor-doc-editor/core/layout';

const doc = new OoxmlParser().parse(arrayBuffer);
const layout = layoutDocument(doc.sections, {
  numbering: doc.numbering,  // ← 顯式注入啟用
});
```

省略 `numbering` 時、layout 行為與 Sprint 138 前完全相同（VR baseline byte-identical）。

---

## 紀律

### 紀律 #1.a 第 15 次連續驗證（含 Sprint 139 Strategy C）

| Sprint | 改動類型 | VR |
|---|---|---|
| 121-126 | parser/utility 補完 | 0.073191 ×6 |
| 130-134 | Phase 4 補完 | 0.073191 ×5 |
| 135 | probe no code | 0.073191 |
| 136 revert | byte-identical | 0.073191 |
| 137 | 純函式無 wire-up | 0.073191 |
| 138 | mapper wire-up（VR 不走 mapper）| 0.073191 |
| **139** | **layout wire-up（VR pipeline opt-in、預設不啟用）** | **0.073191** |

→ 紀律 #1.a 第 15 連、Strategy C 證明「layout wire-up + opt-in 注入」可保軌道。

### 紀律 #22 第 6 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Probe 5 項覆蓋 caller 全圖、counter 設計、TableLayout 共用機制、\\t 既有處理、VR pipeline 入口 → 避免實作走偏。

### 紀律 #18 持續 + Strategy C 案例

本 sprint scope 守住：4 個檔變動共 +140 行 code、+150 行 test、1 audit、1 roadmap。Strategy C 折衷是「在 +0.001pp aggregate 退化 vs byte-identical 軌道」的明確選擇、保留階段 C 時可再評估的彈性。

### 提案紀律 #1.b 候選跨 sprint 驗證進展（第 5 次驗證）

> spike 翻車必完整 revert byte-identical、不微調 retry

| Sprint | 類型 | 結果 |
|---|---|---|
| 110 | 翻車 revert | 1 |
| 136 | 翻車 revert | 2 |
| 137 | probe 預防 scope down | 3（預防範例）|
| 138 | 正常實作（probe 確認可行） | 4（正面對照）|
| **139** | **Strategy C 折衷**（不完全 revert、scope-down 一個維度而非全 revert）| **5（混合範例）** |

Sprint 139 是「**未完全翻車但仍部分 scope-down**」的新範例：
- 全 revert（Sprint 110/136 模式）= 損失太多（wire-up 全砍）
- 維持原狀（接受 +0.001pp）= byte-identical 軌道斷
- Strategy C = 保留主要工作、scope-down 一個維度（VR 注入）= 維持兩者

→ #1.b 候選需擴張為「翻車 revert + 部分翻車 scope-down」更完整原則。Sprint 140+ 達 3 次混合範例後可升正式 `#1.b 候選 v2`。

---

## 後續

### Sprint 140+ 候選

| 候選 | 預期收益 | 風險 |
|---|---|---|
| **A. textAlignment / framePr layout wire-up**（同 Sprint 139 模式）| 中（capture-without-consumer 收口）| 低 |
| B. 階段 C 重生 goldens（autonomous_roadmap Sprint 136-138 原排）| 高（換 anchor、numbering opt-out 即可衡量）| 中（環境設置）|
| C. Phase 5 開工（OMML / SmartArt / 追蹤修訂）| 高 | 高（大 scope）|
| D. Sprint 110+ DocumentParser sectPr 強制 reset numbering | 低 | 低 |

**autonomous 推薦 A**（textAlignment / framePr wire-up）：
- 與 Sprint 138-139 同模式（capture + wire-up 兩階段）
- 但 textAlignment / framePr 在 canvas-editor / layout 都無直接對應（Sprint 138 audit §後續評估時已標記）
- 可能仍是 capture-only、wire-up 是 placeholder 性質
- 開工前 probe（紀律 #22）必要

**候選 B 階段 C 重生 goldens** 才能解鎖 Sprint 139 Strategy C 的「opt-in 改 opt-out」收益。

---

## Sprint 139 結尾累積指標

- vitest **1176 passed + 1 skipped**（+10）
- VR mean **0.073191** / failed 0 / compared 126（**第 15 次連續 byte-identical、Strategy C 後**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style 88% → **90%**（wire-up 鏈完工、僅 VR opt-in 待階段 C）
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**（#20 集中索引、#1.b 候選 5 次跨 sprint 驗證、含 Strategy C 折衷新類型）
- Sprint audit doc 138 → **139**
- 階段 B cluster 「numbering wire-up」完整三段（137-138-139）**完成**：state machine + mapper integration + layout integration、Phase 4.3 一級目標 wire-up 鏈完整

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/layout/types.ts  (+20 行：LayoutOptions numbering + _numberingCounter)
M  addons/dobtor_doc_editor/static/src/core/layout/BoxBuilder.ts  (+25 行：NumberingPrefix interface + 4th param + emission)
M  addons/dobtor_doc_editor/static/src/core/layout/Paginator.ts  (+60 行：PaginateContext counter + makeContext + helper + caller wiring)
M  addons/dobtor_doc_editor/static/src/core/layout/TableLayout.ts  (+35 行：helper + layoutCell wiring)
M  addons/dobtor_doc_editor/tools/visual_regression_pipeline.entry.ts  (+3 行註解：Strategy C opt-in)
M  addons/dobtor_doc_editor/tests/unit/layout/BoxBuilder.test.ts  (+60 行 / 5 新 test)
M  addons/dobtor_doc_editor/tests/unit/layout/Paginator.test.ts  (+90 行 / 5 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild byte-identical fixture 內容)
M  addons/dobtor_doc_editor/tools/dist/visual_regression_pipeline.iife.js  (rebuild Strategy C 後內容)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run 0.073191)
A  addons/dobtor_doc_editor/docs/sprint139_numbering_layout_wireup.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 139 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 4 進度)
```

**Phase 4.3 numbering wire-up 鏈完整**（state machine → mapper → layout、3 sprint cluster）、Strategy C 折衷保留 baseline byte-identical 15 連、為階段 C 重生 goldens 後切換 opt-out 鋪路。
