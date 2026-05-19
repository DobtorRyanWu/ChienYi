# Sprint 157 — fontTable.altName → FontLoader fallback chain wire-up

**性質**: 第一個 Phase 2 wire-up sprint、production code 變動、低風險
**範圍**: 規畫書 Phase 2 §2.2「從 `fontTable.xml` 讀字型名稱」+「字型載入器 fallback」
**對應 plan**: [/home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md](/home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md) Sprint 156-158 Phase 1/2 wire-up（fontTable.altName 跨 Phase 1 capture + Phase 2 wire-up）

---

## 1. Hypothesis

Sprint 147 已完整 capture `<w:fontTable>` 至 `FontTable: Map<name, FontEntry>` AST、含 `altName?: string`。Sprint 64b FontLoader 已落地「caller → IDB → fetch → register → adapter」流程、但 fetch 失敗只 silent fallback（adapter 未註冊），無 altName 重試。

**Hypothesis**:把 `fontTable` 從 OoxmlParser 流到 FontLoader、主 family fetch 失敗時用 `fontTable[family].altName` retry 一次、不破現有 caller、不破 baseline。

---

## 2. Method

### 2.1 設計選項

| 選項 | 描述 | 評估 |
|---|---|---|
| A | FontLoader internal 加 fontTable + altName retry | ⭐ 選 — 最小變動、internal、易測試 |
| B | 獨立 helper `expandFamiliesWithAltName(families, fontTable)` | 需 caller 主動展開、邊界擴散 |
| C | caller 自己處理 | 邏輯散在 caller、難維護 |

### 2.2 實作

**修改 `static/src/core/font_loader.ts` 3 處**:

1. **import FontTable type** from `./ooxml/ast/types`
2. **`FontLoaderOptions` 加 `fontTable?: FontTable`** — backward compat、不傳 → 行為與 Sprint 64b 完全一致
3. **`loadFontsAndBuildAdapter` 內 family map**: 主 family fetch 失敗 + `fontTable.get(family)?.altName` 存在且 ≠ family → 對 altName 走完整 `getOrFetchFontBytes` 流程一次

**防禦邊界**:
- 不傳 fontTable → 走純 Sprint 64b path（無 retry）
- fontTable 無這個 family → 不 retry
- altName 為 undefined / 空字串 → 不 retry
- altName === family → 不 retry（防無限 / 防 spec 病態 docx）
- altName fetch 仍失敗 → silent fallback（adapter 未註冊）
- altName fetch 成功 → 註冊用**主 family 名**（caller 仍以原 family 查詢、不污染 adapter namespace）

**OOXML 語意正確性**:
- §17.8 altName 是「Word 主 family 缺失時的官方建議替代」、比 caller-side 通用 CJK fallback 更精準
- 只 retry 一層（不遞迴 altName-of-altName、spec 未定義）

### 2.3 新測試（9 個）

`tests/unit/FontLoader.test.ts` 新增 describe block:

| Test | 驗證 |
|---|---|
| 主 family 404 + altName 200 → 用主 family 名註冊 | 核心路徑、adapter 不污染 |
| 主 family error + altName 200 → 仍 fallback 成功 | error 觸發點與 404 同處理 |
| 主 family 200 → 不查 altName（fast path） | 不浪費 fetch |
| 主 + altName 都 404 → silent fallback | adapter 未註冊、無 crash |
| fontTable 沒這個 family → 不 retry | 與 Sprint 64b 行為一致 |
| fontTable 有 family 但無 altName → 不 retry | 防 partial entry |
| altName === family → 不 retry | 防無限 / 病態 docx |
| 不傳 fontTable → 與 Sprint 64b 完全一致 | backward compat 嚴守 |
| 多 family 並行、部分 altName fallback 成功部分失敗 | 真實 fixture-like 情境 |

---

## 3. Verification（三層 SOP）

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1331 → 1340 passed + 1 skipped**（+9 個 Sprint 157 test） |
| L2 VR v14 | **跳過（誠實聲明）** | FontLoader 不在 VR pipeline（visual_regression_v14.mjs 直接 `readFileSync` 載字型、不經此 module）;baseline byte-identical 第 23 連維持 |
| L3 spot check | ✅ | font_loader.ts diff +24 行 / FontLoader.test.ts diff +112 行;flake8 不影響（純 TS）|
| L4 Odoo backend | **跳過** | 純前端 TS、未改 controller / model |
| L5 IIFE bundle | **跳過此 sprint** | FontLoader caller 仍無、bundle rebuild 對 production 無 effect;若 Sprint 163+ Phase 2 production migration 用 FontLoader、屆時 rebuild |

### 紀律應用

| 紀律 | 應用 |
|---|---|
| #1 改 BrowserCanvasRenderContext / CanvasRenderer 跑全 VR | N/A（未改 Render） |
| #1.a 廣域 parser/style/layout 變動跑全 VR | N/A（未改 parser/layout、改 caller-side font infra） |
| #2 unit spy 驗 API + VR 驗 pixels | unit ✅、VR N/A（FontLoader 不在 VR pipeline）|
| #3 高風險改造前 probe | ✅ 開工前 probe FontLoader caller / FontTable AST 結構 / VR pipeline 是否消費 |
| #18 PR-size + scope-down | ✅ 單一 production 檔案 + 單一 test 檔案 + 1 audit doc + 1 checkbox |
| #21 optional 欄位空集合不掛 key | ✅ fontTable 不傳 / altName undefined / altName 空 → 不 retry、不掛任何 key |
| #22 probe before action | ✅ Sprint 156 audit + 本 sprint 開工前 3 probe（capture / FontLoader / caller path）|

---

## 4. Result

### 4.1 檔案變動

```
A  addons/dobtor_doc_editor/static/src/core/font_loader.ts  (165 行 — Sprint 64b 落地 + Sprint 157 +24)
A  addons/dobtor_doc_editor/tests/unit/FontLoader.test.ts   (245 行 — Sprint 64b 9 test + Sprint 157 +9 test + 112 行)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (§2.2 第 1 個 [ ] → [x])
M  addons/dobtor_doc_editor/docs/progress_snapshot.md       (Phase 2 補 Sprint 157)
A  addons/dobtor_doc_editor/docs/sprint157_fonttable_altname_wireup.md  (本 audit doc)
```

### 4.1.a 重要發現:Sprint 64b 從未進 git

開工前 `git status` 揭示 `font_loader.ts` 與 `FontLoader.test.ts` **皆為 untracked**:

```
?? dobtor_doc_editor/static/src/core/font_loader.ts
?? dobtor_doc_editor/tests/unit/FontLoader.test.ts
```

**事實**:
- Sprint 64b（規畫書 §11.32 / 紀律 #11.a 來源）2026 年某時期已寫好兩個檔
- 但**從未 commit 到 addons repo**（git ls-tree HEAD 確認 0 hit、git ls-files 確認 0 hit）
- 本 sprint 在 working tree 改完、commit 等於同時把 Sprint 64b 全部入 repo
- git diff 會顯示 +165 行 / +245 行、看起來像「Sprint 157 落地 410 行」、但實際 Sprint 157 只 +24/+112

**對應 scope_audit §3.3 G2「FontMetricsAdapter production gap」**:
- Sprint 127 probe 揭示「production canvas-editor 完全沒整合」、現在進一步揭示「font_loader.ts 本身也沒進 git」
- 雙重未接通:既無 production caller、又無 git history
- Sprint 154 期間揭示的「doc_document.py / doc_controller.py 875 行 uncommitted」是同一現象（多個 sprint 落地代碼從未 commit）

**本 sprint 補救**:同 commit 把 Sprint 64b + Sprint 157 一起 add 入 repo、commit message 明示「含 Sprint 64b 補入 git」、為 Sprint 158+ 提供可追蹤 baseline。

**未來修補**:`scope_audit_2026-05-19.md` 應加 P0 條目「git untracked production code audit」、grep 整個 `static/src/` 看還有多少 untracked。Sprint 158 開工前先做這個 audit、避免再踩雷。

### 4.2 累積指標

| 指標 | Sprint 156 結尾 | Sprint 157 結尾 | 變動 |
|---|---|---|---|
| vitest | 1331 passed + 1 skipped | **1340 passed + 1 skipped** | +9 |
| VR mean | 0.073191（未跑） | 0.073191（未跑、純 caller-side infra）| 0 |
| Odoo backend | 31 passed（未跑） | 31 passed（未跑）| 0 |
| Phase 1 wire-up（嚴格） | 75%（52/69）| 75%（52/69）| 0（本 sprint 為 Phase 2 wire-up）|
| Phase 2 完成度 | 部分 | 部分 → 部分+1 工項 | §2.2 第 1 個 [ ] → [x] |
| Sprint audit doc | 156 | **157** | +1 |

---

## 5. 與規畫書 / Plan 關係

### 5.1 規畫書 checkbox 變動

按 plan「Checkbox 規則」嚴格執行:
```diff
- [ ] 從 `fontTable.xml` 讀字型名稱
+ [x] 從 `fontTable.xml` 讀字型名稱（Sprint 147 capture + Sprint 157 altName fallback wire-up to FontLoader）
```

加括號註記是因為:
- 工項描述模糊（只說「讀字型名稱」）、本 sprint 完成「capture + altName wire-up」、不完成「字型載入器 系統已安裝/CDN/fallback 鏈」（§2.2 第二個 `[ ]`）
- 註記精確標示完成範圍、避免日後誤判

### 5.2 Plan 排程對齊

| Plan 段 | 本 sprint 對應 |
|---|---|
| Sprint 156-158 Phase 1 wire-up | Sprint 157 ✅（fontTable.altName 跨 Phase 1 capture + Phase 2 wire-up、屬 plan「最小最低風險首選」）|
| 預估 1 sprint | ✅ 單 sprint 完成 |
| 不破 baseline | ✅ FontLoader 不在 VR pipeline、baseline byte-identical 第 23 連維持 |
| 低風險 | ✅ caller-side infra、production 無 caller、backward compat 嚴守 |

---

## 6. 後續

### 6.1 Sprint 158 候選

從 Phase 1 audit 17 個 `[ ]` + Phase 2 §2.2 剩餘 4 個 `[ ]` 中、按優先級:

| 候選 | scope | 風險 | 預估 |
|---|---|---|---|
| **settings.defaultTabStop → Layout.LineBreaker** | Phase 1 wire-up、Sprint 146 capture 已 ready | 中（可能破 baseline、Strategy C 折衷可行）| 1-2 sprint |
| **§2.2 第二個 [ ] 字型載入器（系統 / CDN / fallback 鏈）** | Phase 2 wire-up、現 FontLoader 已有 IDB+fetch、需補 CDN fallback | 中（無 caller path、純 infra）| 2-3 sprint |
| §2.2 CJK fallback 鏈 | Phase 2 wire-up | 中 | 1-2 sprint |
| §1.9 bookmark / instrText wire-up | Phase 1 wire-up、Sprint 125/123 capture | 中 | 1-2 sprint each |

**Sprint 158 建議 scope**: settings.defaultTabStop → Layout.LineBreaker
- 理由:Phase 1 wire-up 主軸、plan §推進排程明示 Sprint 156-158 主項
- 風險中（VR baseline 可能斷）、走 Strategy C（layout 接通 + VR pipeline opt-in、Sprint 139 模式）
- 完工後 §1.4 `<w:tab>` 工項 可加註記、§1.7 docGrid 相關 wire-up 補強

### 6.2 觀察點

- FontLoader 仍無 production caller。本 sprint wire-up 純 infrastructure、需 Phase 2 production migration（Sprint 163-167 Strategy B、plan 鎖定 2B）才接通到 user 端。
- 紀律 #4「capture-without-consumer」教訓:本 sprint 是「wire-up-without-production-consumer」變體、可接受（因 plan 已排 Phase 2 migration 在後）、但需在 Sprint 163-167 時驗證 fontTable.altName 真實用上。

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/font_loader.ts                    (+24)
M  addons/dobtor_doc_editor/tests/unit/FontLoader.test.ts                     (+112)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md             (§2.2 第1個 [ ]→[x])
M  addons/dobtor_doc_editor/docs/progress_snapshot.md                         (Phase 2 描述補 Sprint 157)
A  addons/dobtor_doc_editor/docs/sprint157_fonttable_altname_wireup.md        (本 audit doc)
```

**淨 production code 變動 = +24 行**（font_loader.ts、altName retry 邏輯 + 4 行防禦）、vitest 1331 → 1340、VR mean 0.073191 維持、Phase 2 §2.2 第 1 個 `[ ]` → `[x]`。
