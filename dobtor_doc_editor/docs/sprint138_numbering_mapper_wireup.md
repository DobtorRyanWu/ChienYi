# Sprint 138 — numberingCounter wire-up 到 ToCanvasEditor（Phase 4 wire-up 第二階段）

**日期**：2026-05-18
**類型**：code change（mapper 整合、AST snapshot 預期變動）
**規畫書對應**：§Phase 4.3 numFmt 展開正式 wire-up + §Phase 4 一級目標「canvas-editor 顯示真實 docx 編號」
**前置 sprint**：Sprint 137（numberingCounter 純函式 state machine 就緒）

---

## Hypothesis（驗證對象）

Sprint 137 audit §後續推薦方向 A：

> 整合 NumberingCounterState 到 ToCanvasEditor — mapper 是 canvas-editor 路徑的 first consumer、不影響 VR pipeline（VR 用 visual_regression_pipeline.iife.js 走 layout 路徑）

驗證：
1. mapper 改動是否破壞 VR baseline byte-identical？（預期：**否**、因走不同路徑）
2. 8 個 numbered fixture 的 AST snapshot 是否如預期增加 prefix elements？（預期：**是**、變動可解釋）
3. canvas-editor 顯示是否真正出現「1.」「（一）」「第一章」等編號？（預期：**是**、新功能）

---

## Method

### 1. Scope 對齊（紀律 #18）

- 規畫書 Phase 4 一級目標「canvas-editor 顯示真實編號」
- Sprint 137 audit §後續 A. 推薦方向
- 本 sprint scope = ToCanvasEditor 內部建立 NumberingCounterState + appendParagraph 入口 emit prefix + tests 擴充 + AST snapshot regenerate
- PR-size: mapper.ts +50 行 / mapper.test.ts +160 行 / 8 個 AST snapshot regenerate

### 2. Probe（紀律 #22 應用 — 第 5 次）

開工前 probe 4 個關鍵點：

| Probe | 結果 |
|---|---|
| VR pipeline 是否走 ToCanvasEditor？ | ❌ 否 — VR 走 `OoxmlParser → layoutDocument → CanvasRenderer`（`tools/visual_regression_pipeline.entry.ts:25-29`）；mapper 是 canvas-editor 路徑的 fork |
| Mapper caller 是誰？ | `tools/parse_docx_cli.ts:90-91`（backend `/dobtor_doc/import?engine=ts` 路徑、chichi DevTools 比對用）|
| 含 numId 段落的 fixture 數？ | **8 個**（5 個 02_std_table 週報/簽到/取樣紀錄 + 1 個 02 工地密度取樣 + 2 個 03 估驗計價）|
| ParagraphProps.numId / ilvl 已就緒？ | ✅ types.ts:119-120、ParagraphParser.ts:335 已寫入 |

→ Probe 確認：mapper wire-up **不會破 VR**（紀律 #1.a 第 14 次連續可達成）、但**會破 AST snapshot**（預期、Sprint 138 主要 deliverable）。

### 3. 實作

`ToCanvasEditor.ts`（+50 行、含 import + 4 個 method 簽章擴充 + appendParagraph 入口 prefix emission）：

```ts
import { NumberingCounterState, expandLvlText } from '../numbering';

convert(doc: DocumentNode): CEElement[] {
  const counter = new NumberingCounterState();  // 跨 section 共用
  for (const section of doc.sections) {
    this.appendBlocks(elements, section.body, doc.media, doc.numbering, counter);
  }
}

appendParagraph(out, para, media, numbering, counter): void {
  // ... 既有 rowFlex / rowMargin ...
  if (para.props.numId !== undefined) {
    const ilvl = para.props.ilvl ?? 0;
    const abstractNum = numbering.get(para.props.numId);
    const result = counter.advance(para.props.numId, ilvl, abstractNum);
    const prefix = expandLvlText(result.level.text, result.counters, result.numFmts);
    if (prefix !== '') {
      const baseProps = (para.runs.find((r): r is RunNode => r.type === 'run')?.props)
        ?? result.level.runProps ?? {};
      const baseStyle = mapRunProps(baseProps);
      this.appendChars(paraElements, prefix, baseStyle);
      paraElements.push({ ...baseStyle, type: 'tab', value: '\t' });
    }
  }
  // ... 既有 runs append ...
}
```

**設計取捨**：
- **跨 section 共用 counter state**：OOXML §17.9 預設行為（sectPr 不強制 reset）；若 fixture 需要強制 reset 由 future sprint 加 hook
- **跨 cell 共用 counter state**：body 段落與 cell 內 numbered paragraph 共享計數（如 cell 內 P1 接 body P1 變 P2）— 這對 02_std_table 簽到表等含 cell 內列表的 fixture 是正確行為
- **降級為「前綴字串 + tab」**：canvas-editor 沒有 list 概念、無法用 listType/listStyle；直接嵌入段首為「字元 IElement + tab」是最簡可行映射
- **baseStyle 取第一個 run、fallback level.runProps**：保 prefix 字體與後續文字風格一致（避免 prefix 字體跟 body 文字字體脫節）
- **空 lvlText 跳過 emit**：避免 placeholder 段落產生空字串污染輸出

### 4. AST Snapshot 變動（預期、8 個 fixture）

| 類別 | Fixture | 變動 |
|---|---|---|
| 02_std_table | 1121013-磺港溪 C 段護岸週報 | +N 個 prefix elements + 1 tab/段 |
| 02_std_table | 1121020-磺港溪 C 段護岸週報 | 同上 |
| 02_std_table | 1121027-磺港溪 C 段護岸週報 | 同上 |
| 02_std_table | 1131202-工地密度簽到表 | 同上 |
| 02_std_table | 1140206-工地密度取樣紀錄 | 同上 |
| 02_std_table | 1140206-工地密度簽到表 | 同上 |
| 03_complex_table | 06-8 估驗計價（112年12月27日修訂）(1) | 同上 |
| 03_complex_table | 06-8 估驗計價（112年12月27日修訂）11409 | 同上 |

→ snapshot regenerate 命令：`npx vitest run tests/integration/04_ast_snapshot.test.ts -u`
→ Snapshot 檔位於 `tests/integration/__snapshots__/` 為 untracked（既有做法、不入 git、CI 自動產生）

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 Vitest** | ✅ **1166 + 1 skipped**（+10 from mapper.test.ts、AST snapshot regenerate 8 個重綠）|
| **L2 VR v14** | ✅ **mean 0.073191 / 0 failed / 126 pages**（**第 14 次連續 byte-identical**、預期 — VR 不走 mapper）|
| **L3 Spot check** | ✅ TypeScript build PASS（main bundle 30s + VR pipeline 29.1s）|
| **L4 Odoo backend** | **跳過**（無 backend 變動；ts CLI 自動同步用新 mapper、不需 odoo restart）|

紀律 #1.a 第 14 次連續 byte-identical 驗證（含本 sprint mapper 改動）— 證實「mapper 變動不影響 VR pipeline」mental model 正確。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/mapper/ToCanvasEditor.ts` | **+50 行** | NumberingCounterState import + convert/appendBlocks/appendParagraph/convertTable/convertRow/convertCell 簽章擴充 + prefix emission |
| `tests/unit/ToCanvasEditor.test.ts` | **+160 行 / 10 新 test** | numbering wire-up 完整覆蓋 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | bundle 同步（含 mapper 變動）|
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | VR pipeline 同步（byte-identical content、僅 timestamp）|
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `tests/integration/__snapshots__/04_ast_snapshot.test.ts.snap` | regenerate（**untracked**）| 8 fixture 預期變動已寫入新 baseline |
| `docs/sprint138_numbering_mapper_wireup.md` | 本 audit doc | 紀錄設計 + AST snapshot 變動 |
| `docs/autonomous_roadmap.md` | Sprint 138 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + §0.2 Phase 4 進度 | 同步 |

**淨變動 = mapper +50 行 + test +160 行 + 8 個 AST snapshot regenerate（預期）**

### Test 數變動

- Sprint 137 結尾：vitest 1156 + 1 skipped
- Sprint 138 結尾：vitest **1166 + 1 skipped**（+10 from new mapper tests）

### VR 數變動

- Sprint 137 結尾：mean 0.073191（byte-identical、第 13 次連續）
- Sprint 138 結尾：mean **0.073191**（byte-identical、**第 14 次連續**）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style：86% → **88%**（numbering wire-up 整合到 canvas-editor 路徑、Phase 4.3 一級目標完工）

### 新功能 — canvas-editor 顯示真實編號

8 個 fixture 在 backend `/dobtor_doc/import?engine=ts` 路徑（chichi DevTools 比對工具）將首次顯示真實 OOXML 編號：
- 02_std_table 5 個週報 / 取樣紀錄：decimal「1.」「2.」prefix
- 03_complex_table 2 個估驗計價：含 ideographTraditional「一、」+ decimal「1.」混合層級

→ 從「Phase D.1 暫不映射」（ToCanvasEditor.ts:25 註解 Sprint 138 前）變為「**正式 wire-up**」（已更新註解）

### Test 覆蓋分組（10 新）

1. 段落無 numId 回歸（不 emit prefix）— 1 test
2. 段落有 numId emit prefix + tab — 1 test
3. 連續同 numId counter +1 — 1 test
4. 多 ilvl 巢狀深層 reset — 1 test
5. 多 numId 互相獨立 — 1 test
6. 缺失 numbering placeholder fallback — 1 test
7. 中文章節「第%1章」+ chineseCounting — 1 test
8. Bullet「•」直接字元 — 1 test
9. 空 lvlText 跳過 emit — 1 test
10. Cell 內 numbered paragraph 共享 counter state — 1 test

---

## 紀律

### 紀律 #1.a 第 14 次連續驗證（含 Sprint 138）

| Sprint | 改動類型 | VR |
|---|---|---|
| 121-126 | parser / utility 補完 | 0.073191 ×6 |
| 130-134 | Phase 4 補完 | 0.073191 ×5 |
| 135 | probe（no code）| 0.073191 |
| 136 (revert) | revert byte-identical | 0.073191 |
| 137 | 純函式新模組無 wire-up | 0.073191 |
| **138** | **mapper wire-up（VR 不走 mapper、byte-identical）** | **0.073191** |

→ 紀律 #1.a 適用範圍延伸到「**mapper wire-up 改動 + AST snapshot 預期變動**」類別、仍堅持跑全 VR 確認、預測「不影響 VR」正確。

### 紀律 #22 第 5 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

本 sprint 開工前 probe 4 項：
- VR pipeline 走哪條（→ 確認不撞 mapper、可安全 wire-up）
- Mapper caller 是誰（→ 確認改動影響範圍 = 1 個 CLI + chichi DevTools）
- 含 numId fixture 數 + 名單（→ 預測 AST snapshot 8 個變動）
- ParagraphProps.numId / ilvl 已就緒（→ 不需擴 types.ts）

→ Probe 成本：~15 分鐘讀 5 個檔。收益：避免「不知道 VR 會不會破」的不確定性 + 避免「忘記 cell 內 paragraph 也要傳 counter」的 bug。

### 紀律 #18 持續

PR-size 守住：本 sprint 1 個檔 +50 行 + 1 個 test 檔 +160 行 + 1 個 audit + 1 個 roadmap 更新。不開新模組、不重構既有 mapper 結構、不為 Sprint 139 預留 scaffold。

### 提案紀律 #1.b 候選跨 sprint 驗證進展（更新）

> spike 翻車必完整 revert byte-identical、不微調 retry

| Sprint | 類型 | 結果 |
|---|---|---|
| 110 | 翻車 revert | 1 |
| 136 | 翻車 revert | 2 |
| **137** | **probe 主動 scope down**（預防範例）| 預防範例 +1 |
| **138** | **正常實作（probe 確認可行）** | 正面對照範例 +1 |

跨 sprint 驗證進展：2 次翻車 revert + 2 次正面預防/實作對照 → **#1.b 候選成熟、可考慮升正式**（Sprint 139+ 任一次 spike 結果可完成第 3 次直接驗證）。

---

## 後續

### Sprint 139 候選（autonomous 推薦）

| 候選 | 預期收益 | 風險 |
|---|---|---|
| **A. textAlignment / framePr wire-up**（Sprint 134 capture 後續）| 中（垂直對齊 + 浮動框 mapper 整合）| 低 |
| B. Sprint 110+ DocumentParser 簽章更新（讓 mapper 支援 sectPr 強制 reset numbering）| 低（fixture 不常用）| 低 |
| C. Layout 路徑 numbering wire-up（VR 也顯示編號、會破 VR baseline）| **高**（VR mean 可能改進）| **高**（會破 14 次連續 byte-identical）|
| D. Phase 5 開工（OMML / SmartArt）| 高 | 高（大 scope）|
| E. 階段 C 重生 goldens（autonomous_roadmap Sprint 136-138 原排）| 高 | 中 |

**autonomous 推薦 A**（textAlignment / framePr wire-up）：
- Sprint 134 capture 後 100% 沒人消費、與 numbering 同類別「capture-without-consumer」結構性技術債
- mapper wire-up 模式已驗證（Sprint 138 範本）
- 預期不破 VR（同 Sprint 138 邏輯）
- PR-size 中等

候選 C 的潛在風險：layout wire-up 後 numbering prefix 進入 layout 計算、可能改變 page break + line 度量，預期 VR 全 fixture 改變（類似 Sprint 136 但這次有可預測方向：增加 line 長度而非「snap」抽象變動）。**遵循紀律 #1.b 候選**：開工前 probe + 完整 VR 驗證 + 翻車就 revert。

### 階段 B cluster 8 候選綁定

Sprint 137-138 共同形成「numbering wire-up cluster」。Sprint 139（textAlignment/framePr wire-up）+ Sprint 140（其他 Phase 4 wire-up）可組成階段 B cluster 8 = Phase 4 全 wire-up 收口。

---

## Sprint 138 結尾累積指標

- vitest **1166 passed + 1 skipped**（+10 from mapper.test.ts）
- VR mean **0.073191** / failed 0 / compared 126（**第 14 次連續 byte-identical**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style 86% → **88%**
- 21 ADR / 紀律 **21 條** + 6 子 + **2 候選**（#20 集中索引、#1.b 候選 4 次驗證 = 2 次翻車 + 2 次預防/實作對照）
- Sprint audit doc 137 → **138**
- 階段 B cluster 「numbering wire-up」(137-138) **完成**：state machine + mapper integration、canvas-editor 8 fixture 首次顯示真實編號

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/mapper/ToCanvasEditor.ts  (+50 行 numbering wire-up)
M  addons/dobtor_doc_editor/tests/unit/ToCanvasEditor.test.ts  (+160 行 / 10 新 test、含 cell 內 numbered paragraph)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild、含 mapper 變動)
M  addons/dobtor_doc_editor/tools/dist/visual_regression_pipeline.iife.js  (rebuild byte-identical、僅 timestamp)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
?? addons/dobtor_doc_editor/tests/integration/__snapshots__/04_ast_snapshot.test.ts.snap  (8 fixture regenerate、untracked)
A  addons/dobtor_doc_editor/docs/sprint138_numbering_mapper_wireup.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 138 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 4 進度)
```

**Phase 4 wire-up 第二階段完成**。Mapper 從「Phase D.1 暫不映射」升級為「**正式 wire-up**」、canvas-editor 8 fixture 顯示真實 OOXML 編號（chichi 可於 DevTools 比對驗收）。VR baseline 第 14 次連續 byte-identical、印證 Sprint 137 probe 結論「VR 不走 mapper」正確。
