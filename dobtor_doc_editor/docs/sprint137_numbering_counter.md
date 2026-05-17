# Sprint 137 — numberingCounter 純函式狀態機（Phase 4.3 補強）

**日期**：2026-05-18
**類型**：code change（純函式新模組、無 wire-up）
**規畫書對應**：§Phase 4.3「numFmt 編號展開」延伸 — counter state machine
**autonomous_roadmap.md 對應**：階段 B cluster 完工後續、Sprint 136 audit §後續候選 A.「Phase 4 wire-up」第一階段

---

## Hypothesis（驗證對象）

Sprint 136 audit §後續推薦方向 A：

> Phase 4 wire-up — numberingFormatter / textAlignment / framePr 整合到 mapper/renderer

Sprint 132 已交付 `numberingFormatter.ts`（16 numFmt + expandLvlText 純函式、50 test），但：
- **無 caller**：mapper `ToCanvasEditor.ts:25` 註明「Phase D.1 暫不映射」、layout 只有 numId 註解
- **缺 state machine**：expandLvlText 需要 `counters[]` 參數、但沒人維護「文件走訪時的計數器演化」

本 sprint hypothesis：抽出 counter state machine 為**純函式新模組**、不破壞既有 VR baseline、為 Sprint 138+ wire-up 鋪路。

---

## Method

### 1. Scope 對齊（紀律 #18）

- 規畫書 Phase 4.3 已列「numFmt 展開」、本 sprint 補完 counter state machine 為其前置依賴
- autonomous_roadmap.md 階段 B cluster 7 結尾後續、Sprint 136 audit §後續 A. Phase 4 wire-up
- 本 sprint scope = **純函式新模組** + 完整 unit test，**不** wire-up 到 mapper/layout（紀律 #18 PR-size、避免破 VR byte-identical 軌道）
- 留下 Sprint 138 候選：mapper convert() 簽章加 numbering + counter、appendParagraph 入口處對 numId 段落 emit 編號前綴

### 2. Probe（紀律 #22 應用）

開工前 probe：

| 檢查項 | 結果 |
|---|---|
| NumberingResolver 已就緒？ | ✅ Sprint 既有、產 `NumberingMap = Map<numId, AbstractNumbering>` |
| numberingFormatter 已就緒？ | ✅ Sprint 132 交付、formatNumber + expandLvlText |
| ParagraphParser 寫入 numId？ | ✅ `static/src/core/ooxml/document/ParagraphParser.ts:335` |
| Mapper 是否消費 numbering？ | ❌ `ToCanvasEditor.ts:25` 註明「Phase D.1 暫不映射」 |
| Layout 是否消費 numbering？ | ❌ `static/src/core/layout/types.ts:111` 只有「numId 渲染用」comment |
| 跨段落 counter state 邏輯？ | ❌ **缺**（本 sprint scope） |

→ Probe 確認 Sprint 137 應做 counter state machine、且**不應**碰 mapper wire-up（會破 VR）。

### 3. 設計

`numberingCounter.ts`（+178 行）：

```ts
export class NumberingCounterState {
  private state = new Map<number, number[]>();  // numId → counters[ilvl] (-1 = 未初始化)

  advance(numId, ilvl, abstractNumbering): AdvanceResult {
    // 1. 取得/初始化此 numId 的 9 元素 counters 陣列
    // 2. 取 levels[ilvl]、缺失 fallback placeholder (decimal/start=1)
    // 3. 推進此 ilvl 的 counter（首次 = start、後續 = +1）
    // 4. Reset 所有 ilvl' > ilvl 的深層 counter（除非該 level lvlRestart=0）
    // 5. 組裝 counters[0..ilvl] + numFmts[0..ilvl]（紀律 #21 不掛深層 undefined）
  }
  reset(): void                     // 整檔重啟
  resetNum(numId: number): void     // 單 numId 重啟（sectPr 強制）
  snapshot(): Map<...>              // debug/test
}
```

### 4. OOXML §17.9 規則覆蓋

| 規則 | 實作 |
|---|---|
| §17.9 多層編號 | counters[ilvl] 0–8 獨立 |
| §17.9.31 lvlRestart=0 | 深層保留、跨章節連續 |
| §17.9.31 預設 lvlRestart=ilvl+1 | advance 此 ilvl 時 reset 深層 |
| §17.9 多 numId 獨立 | numId → 獨立 counters 陣列 |
| 跳層（ilvl 0 → 2） | 中間層用 start 當顯示值、不污染 state |
| 缺失 abstractNumbering | placeholder level fallback、不 crash |
| 缺失 ilvl 對應 level | 同上 |

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 Vitest** | ✅ **1156 + 1 skipped**（+20 新 test from numberingCounter.test.ts、淨增 20）|
| **L2 VR v14** | ✅ **mean 0.073191、126 pages、0 failed**（**第 13 次連續 byte-identical**）|
| **L3 Spot check** | ✅ TypeScript build PASS（main bundle 29.5s + VR pipeline 23.2s）|
| **L4 Odoo backend** | **跳過**（無 backend 變動）|

紀律 #1.a 第 13 次連續 byte-identical 驗證（含本 sprint 新模組純函式無 wire-up）。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/numbering/numberingCounter.ts` | **新增 +178 行** | counter state machine |
| `static/src/core/ooxml/numbering/index.ts` | +3 行 | export NumberingCounterState / AdvanceResult / formatter helpers |
| `tests/unit/numberingCounter.test.ts` | **新增 +260 行 / 20 test** | 完整覆蓋 OOXML §17.9 規則 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | bundle 同步（byte-identical 內容）|
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | VR pipeline 同步（byte-identical 內容）|
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `docs/sprint137_numbering_counter.md` | 本 audit doc | 紀錄設計 + probe 結果 |
| `docs/autonomous_roadmap.md` | Sprint 137 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + §0.2 Phase 4 進度 | 同步 |

**淨 production code 變動 = 181 行新增（純函式 + index export）+ 260 行 test**。0 既有 source 變動。

### Test 數變動

- Sprint 136 結尾：vitest 1136 + 1 skipped
- Sprint 137 結尾：vitest **1156 + 1 skipped**（+20 from numberingCounter.test.ts）

### VR 數變動

- Sprint 136 結尾：mean 0.073191（byte-identical）
- Sprint 137 結尾：mean **0.073191**（byte-identical、第 13 次連續）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style：85% → **86%**（counter state machine 為 Phase 4.3 wire-up 前置依賴）

### Test 覆蓋

20 test 分組：
1. 單一 numId / 單一 ilvl — 4 test
2. 多 ilvl 深層 reset — 3 test
3. 多 numId 互相獨立 — 1 test
4. lvlRestart=0 跨章節連續 — 2 test
5. 缺失防禦 — 3 test
6. lifecycle (reset/resetNum/snapshot) — 3 test
7. 紀律 #21 counters 長度收斂 — 2 test
8. expandLvlText 串接整合預演 — 2 test

---

## 紀律

### 紀律 #1.a 第 13 次連續驗證（含 Sprint 137）

| Sprint | 改動類型 | VR |
|---|---|---|
| 121-126 | parser / utility 補完 | 0.073191 ×6 |
| 130-134 | Phase 4 補完 | 0.073191 ×5 |
| 135 | probe（no code）| 0.073191 |
| 136 (revert) | revert byte-identical | 0.073191 |
| **137** | **純函式新模組無 wire-up** | **0.073191** |

紀律 #1.a 適用範圍延伸到「純函式新模組無 wire-up」類別、仍堅持跑全 VR 確認。

### 紀律 #21 第 5 次正式應用

> optional 欄位空集合不掛 key、避免 AST diff noise + 保 cache key 穩定

本 sprint 應用：`AdvanceResult.counters` / `numFmts` 只取 `0..ilvl` 長度、**不**掛深層 undefined（即使 levels 陣列有 5 個、ilvl=0 時只回 1 個元素）。確保 expandLvlText 串接時的 placeholder 行為一致。

### 紀律 #22 第 4 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

本 sprint 開工前 probe 6 個檢查項（NumberingResolver / numberingFormatter / ParagraphParser / mapper / layout / counter 缺口）。Probe 結果直接決定 scope：
- 確認 mapper wire-up 會破 VR → 拉回到「純函式新模組」
- 確認 counter state machine 是真正缺口（不是 redundant duplicate）
- 確認 expandLvlText 已備 → 設計直接串接（test 第 8 組）

→ Probe 成本：~10 分鐘讀 5 個檔。避免成本：可能 ~2-4 hr 撞 mapper wire-up 後 revert（Sprint 136 模式）。

### 紀律 #18 持續

PR-size 守住：本 sprint 1 個新模組 + 1 個 index export edit + 1 個新 test 檔案 + audit/roadmap docs。**0 既有 production source 修改**。完全符合「不為 Sprint 138 預留 scaffold」原則（NumberingCounterState 是真正可用的單元、不是 placeholder）。

---

## 後續

### Sprint 138 候選（autonomous 推薦）

**Sprint 138 = numbering wire-up Phase 1**（mapper 整合）：

| 候選 | 預期收益 | 風險 |
|---|---|---|
| **A. 整合 NumberingCounterState 到 ToCanvasEditor** | 高（canvas-editor 開始顯示真實編號 prefix）| **中**：必破 VR byte-identical（如 fixture 有 numId 段落）|
| B. 整合到 Layout / BoxBuilder | 高 + 進入 Layout 路徑（最終 metric anchor） | 中：VR 受影響範圍更大 |
| C. 兩者並行 + feature flag | 中（漸進式）| 低（但開發成本高、紀律 #18 PR-size 違反）|

**autonomous 推薦 A**（mapper 整合）：
1. mapper 是 canvas-editor 路徑的 first consumer、不影響 VR pipeline（VR 用 visual_regression_pipeline.iife.js 走 layout 路徑）
2. canvas-editor 顯示 list 編號是規畫書 Phase 4 一級目標
3. PR-size 中等：~50 行 mapper 變動 + test 擴充

Sprint 138 開工前 probe（紀律 #22）：grep fixture 是否有 numId 段落 → 預測 mapper 改完後 canvas-editor 顯示差異規模。

### Sprint 139+ 候選

- Phase 4 textAlignment wire-up（Sprint 134 capture 後續）
- Phase 4 framePr wire-up（同上）
- Phase 5 開工（OMML / SmartArt / 追蹤修訂）
- 階段 C 重生 goldens（Sprint 137 對應 autonomous_roadmap.md 原排）

### 提案紀律 #1.b 跨 sprint 驗證進展

> spike 翻車必完整 revert byte-identical、不微調 retry（Sprint 110 / Sprint 136 共 2 次）

Sprint 137 = **正面範例**：probe 確認 wire-up 會破 VR → 主動 scope down 到「純函式新模組」、避免重演 Sprint 136 翻車。雖然不直接驗證 #1.b（無 spike 翻車）、但驗證**前置條件「先 probe scope 再實作」可防範**。

跨 sprint 驗證進展 = 1（Sprint 110）+ 2（Sprint 136）= 2/3、Sprint 138+ 若再遇 spike 翻車可完成第 3 次驗證升正式 #1.b。

---

## Sprint 137 結尾累積指標

- vitest **1156 passed + 1 skipped**（+20 from numberingCounter.test.ts）
- VR mean **0.073191** / failed 0 / compared 126（**第 13 次連續 byte-identical**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style 85% → **86%**
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**（#20 集中索引、#1.b 候選 2/3）
- Sprint audit doc 136 → **137**
- 階段 B cluster 7 後續：Phase 4 wire-up 第一階段（state machine 就緒、wire-up defer Sprint 138）

---

## File-level summary

```
A  addons/dobtor_doc_editor/static/src/core/ooxml/numbering/numberingCounter.ts  (+178 行純函式 state machine)
M  addons/dobtor_doc_editor/static/src/core/ooxml/numbering/index.ts  (+3 行 export)
A  addons/dobtor_doc_editor/tests/unit/numberingCounter.test.ts  (+260 行 / 20 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild byte-identical 內容)
M  addons/dobtor_doc_editor/tools/dist/visual_regression_pipeline.iife.js  (rebuild byte-identical 內容)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  addons/dobtor_doc_editor/docs/sprint137_numbering_counter.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 137 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 4 進度)
```

**淨變動 = 純函式新模組 + 完整 test + rebuild 同步**。為 Sprint 138 mapper wire-up 鋪路（不預留 scaffold）。
