# Sprint 160 v2 — `<w:instrText>` 複雜欄位 → ToCanvasEditor render 消費 wire-up

**性質**: Phase 1 wire-up sprint、production code 變動、低風險（mapper 不在 VR pipeline）
**範圍**: 規畫書 §5 Phase 1 §1.9「`<w:instrText>` 複雜欄位（fldChar begin/separate/end）」render 端消費
**前置 sprint**: [sprint157_fonttable_altname_wireup.md](sprint157_fonttable_altname_wireup.md)（方向 A wire-up 範例）、[sprint158_working_tree_backfill_audit.md](sprint158_working_tree_backfill_audit.md)（紀律 #14.b 起點）
**開工狀態**: 上個 session 留下 in-progress（`ToCanvasEditor.ts` + test + 規畫書 checkbox）；本 sprint 接手補完並收口

---

## 0. 開工前狀態（紀律 #14.b 第 0 步）

`git status -s addons/dobtor_doc_editor/` 揭示分支 `sprint-160-v2-instrtext-fldchar-render` 有 3 個未 commit 的 in-progress 檔：

| 檔案 | 狀態 | 內容 |
|---|---|---|
| `dobtor_doc_editor_高保真匯入開發規劃.md` | M | §1.9 instrText checkbox `[ ]` → `[x]` |
| `static/src/core/ooxml/mapper/ToCanvasEditor.ts` | M | `field` case 改寫 + `fieldPlaceholder()` helper +48 行 |
| `tests/unit/ToCanvasEditor.test.ts` | M | +2 新 test（+40 行） |

**判定**：這是 Sprint 160 v2 本身的半成品（分支名即指 instrText/fldChar render）。**補完並 commit**，不 revert。

**接手時發現的兩個缺陷**（in-progress 未收口）：

1. `ToCanvasEditor.ts` L312 用 `FieldNode['fieldType']` 作型別註解、但 import block **未 import `FieldNode`** → `tsc --noEmit` 會多一個 TS2304 error。
2. `ToCanvasEditor.test.ts` import `ParagraphParser` 但兩個新 test 都不使用 → dead import。

兩者皆於本 sprint 修正。

---

## 1. Hypothesis

Sprint 123 已落地 `<w:instrText>` / fldChar begin-separate-end state machine、產出 `FieldNode { type:'field', instruction, fieldType, cachedValue? }` AST。但 `ToCanvasEditor`（DocumentNode → canvas-editor `IElement[]` mapper）的 `case 'field'` 舊行為是：

```ts
const text = node.cachedValue ?? node.instruction;
```

→ 無 `cachedValue`（複雜欄位 separate 段無 `<w:t>` 快取、或 fldSimple 無內嵌值）時，**把原始 instruction 字面值（如 ` PAGE `）逐字元 emit**，render 出醜陋的 ` PAGE ` 文字。

**Hypothesis**：把 `case 'field'` 的 fallback 從「raw instruction」改為「依 `fieldType` 產出 placeholder」（`[PAGE]` / `[DATE]` / …），讓無快取欄位 render 出可辨識的佔位符而非裸 instruction，且不破壞既有 `cachedValue` 優先路徑、不破 baseline（mapper 不在 VR pipeline）。

---

## 2. Method

### 2.1 設計

| 選項 | 描述 | 評估 |
|---|---|---|
| A | `case 'field'` 內 inline switch | 邏輯混在 convert loop、難測 |
| B | 抽 `fieldPlaceholder(fieldType, instruction)` private method | ⭐ 選 — 純函式、可獨立推理、`cachedValue` 優先路徑不變 |
| C | 在 parser 端就把 placeholder 寫進 `cachedValue` | 污染 AST、capture 與 render 責任混淆 |

### 2.2 實作（`ToCanvasEditor.ts`，淨 +48 行）

1. **`case 'field'` 改寫**：
   ```ts
   const textToRender = node.cachedValue
     ?? this.fieldPlaceholder(node.fieldType, node.instruction);
   ```
   `cachedValue` 仍最優先（fldSimple / 複合 separate 段有 `<w:t>` 時行為與舊版 byte-identical）。

2. **新增 `fieldPlaceholder()` private method**：依 `FieldNode['fieldType']` 11 型各回對應 placeholder：
   - `PAGE` / `NUMPAGES` / `DATE` / `TIME` / `AUTHOR` / `FILENAME` / `SEQ` / `TOC` / `REF` / `STYLEREF` → `[PAGE]` …等可辨識佔位符
   - `HYPERLINK` → 回退到 `instruction.trim()`（HYPERLINK 欄位 instruction 含 anchor/url、本身即可見資訊）
   - `unknown` / default → `instruction.trim() || '[FIELD]'`（保留未識別欄位的原始語意、空則退 `[FIELD]`）

3. **import 修正**：`FieldNode` 加入 `from '../ast/types'` import block（接手缺陷 #1）。

### 2.3 為什麼是 placeholder 而非真實值

真實動態欄位值（如即時頁碼 `PAGE`、總頁數 `NUMPAGES`）需 **layout pagination context** —— mapper 階段（DocumentNode → IElement，分頁尚未發生）無從得知。故 mapper 的責任邊界 = 「emit 可辨識佔位符讓 layout flow 不空白」，真實值計算屬未來 layout 端工作（紀律 #18 scope-down、不在本 sprint 越界做分頁）。

### 2.4 新測試（2 個，`ToCanvasEditor.test.ts`）

| Test | 驗證 |
|---|---|
| `fieldType='PAGE'` + `cachedValue=undefined` → `[PAGE]\n` | placeholder fallback 核心路徑 |
| `fieldType='PAGE'` + `cachedValue='12'` → `12\n` | `cachedValue` 優先、舊行為不破 |

接手缺陷 #2 修正：移除 test 檔未使用的 `ParagraphParser` import（兩個新 test 用合成 `FieldNode`、不經 parser；mapper unit test 範圍不需 parser，紀律 #18 scope-down）。

---

## 3. Verification（三層 SOP）

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1340 → 1342 passed + 1 skipped**（+2 個 Sprint 160 v2 test） |
| L2 VR v14 | **跳過（誠實聲明）** | `ToCanvasEditor` 是 DocumentNode → canvas-editor mapper、**不在 VR pipeline**（Sprint 138 已證實「VR 不走 mapper」、`visual_regression_v14.mjs` 走 Layout/Renderer 路徑）；baseline 0.073191 byte-identical 第 24 連不受影響 |
| L3 spot check | ✅ | `ToCanvasEditor.ts` diff +50 行、test diff +38 行（含 dead import 移除 -1）、規畫書 §1.9 1 checkbox + 註記 |
| L4 Odoo backend | **跳過（誠實聲明）** | 純前端 TS、未改 controller / model |
| L5 bundle rebuild | ✅ | `npm run build:frontend` 重建 `canvas-editor-custom.umd.js`(+`.map`)、production OWL component 取得本次 render 行為變更 |

### 3.1 typecheck 狀態（誠實聲明）

`npx tsc --noEmit` 收口前後跑：本 sprint 修正後 **4 個 pre-existing error**，皆**不在** `ToCanvasEditor.ts` / `ToCanvasEditor.test.ts`：

| 檔案 | error | 性質 |
|---|---|---|
| `layout/BoxBuilder.ts` ×2 | `fieldType` 收窄不符（BoxBuilder 只認 7 型、Sprint 123 已擴 11 型未同步） | pre-existing、見 §6 後續 |
| `ooxml/font/FontMetrics.ts` ×1 | `opentype.js` 無 `.d.ts` 宣告 | pre-existing |
| `ooxml/settings/SettingsParser.ts` ×1 | `footnotePr/endnotePr` position 型別不符（Sprint 146） | pre-existing |

→ 本 sprint **不引入新 typecheck error**（接手缺陷 #1 修正前會多 1 個 ToCanvasEditor TS2304、修正後 0）。typecheck 非三層 SOP 層、4 個 pre-existing 不在本 sprint scope（紀律 #18）。

### 3.2 紀律應用

| 紀律 | 應用 |
|---|---|
| #1 / #1.a 改 parser/style/layout/render 跑全 VR | N/A — 改 mapper、mapper 不在 VR pipeline（Sprint 138 證實）；非「退化走 Strategy C」情境 |
| #14 / #14.a docs 即時同步 | ✅ 規畫書 §1.9 checkbox + 註記、progress_snapshot、roadmap、本 audit doc 同 sprint 同步 |
| #14.b commit 前 working tree 清零 | ✅ 第 0 步檢查 → 補完 in-progress → commit 含 bundle、`git status -s .` 收口 |
| #18 PR-size + scope-down | ✅ 單一 mapper 檔 + 單一 test 檔 + bundle + 1 checkbox + 1 audit doc；placeholder ≠ 真實分頁值（不越界做 layout）；4 個 pre-existing typecheck error 不順手修 |
| #18.a「依規畫書繼續」是 scope 限制詞 | ✅ instrText 是 §1.9 既列工項、未發明新 scope |
| #21 optional 空集合不掛 key | N/A — 本 sprint 無新 optional 欄位 |
| #22 mental model 不確定先 probe | ✅ 接手後先 probe：`FieldNode` 型別定義（ast/types.ts L200）、parser fldChar state machine（ParagraphParser L141-159）、既有 field test、VR pipeline 是否走 mapper（Sprint 138 結論）|

---

## 4. Result

### 4.1 檔案變動

```
M  static/src/core/ooxml/mapper/ToCanvasEditor.ts            (+50：fieldPlaceholder() + case 'field' 改寫 + FieldNode import)
M  tests/unit/ToCanvasEditor.test.ts                         (+38：2 新 test、-1 dead import)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (bundle rebuild)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js.map  (bundle rebuild)
M  dobtor_doc_editor_高保真匯入開發規劃.md                     (§1.9 instrText [ ]→[x] + 註記)
M  docs/progress_snapshot.md                                  (Sprint 160 v2 指標)
M  docs/autonomous_roadmap.md                                 (進度追蹤表 backfill 156-160v1 + 160v2)
A  docs/sprint160_v2_instrtext_render_wireup.md               (本 audit doc)
```

### 4.2 累積指標

| 指標 | Sprint 158 結尾 | Sprint 160 v2 結尾 | 變動 |
|---|---|---|---|
| vitest | 1340 passed + 1 skipped | **1342 passed + 1 skipped** | +2 |
| VR mean | 0.073191（byte-identical 第 24 連） | 0.073191（mapper 不在 pipeline、不受影響） | 0 |
| Odoo backend | 31 passed | 31 passed（未跑、無 backend 變動） | 0 |
| Phase 1 §5 checklist | 51/65 [x] | **52/65 [x]** | §1.9 instrText [ ]→[x] |
| Sprint audit doc | 158 | **159（含 159 / 160v1 內聯、160v2 本檔）** | — |

> Sprint 159 / 160 v1 為 docs-only follow-up（§5 Phase 1 scope 重構 / footnote-endnote scope 釐清）、無獨立 audit doc；細節見 roadmap 進度追蹤表 backfill 列。

---

## 5. 與規畫書關係

### 5.1 規畫書 checkbox 變動

```diff
- - [ ] <w:instrText> 複雜欄位（fldChar begin/separate/end）（Sprint 123 capture 強化、render 端未完全消費）
+ - [x] <w:instrText> 複雜欄位（fldChar begin/separate/end）（Sprint 123 capture + Sprint 160 v2 ToCanvasEditor render 消費：cachedValue 優先、無快取則依 fieldType 產出 placeholder；真實動態值如即時頁碼需 layout pagination context、屬未來）
```

加註記理由（沿用 Sprint 157 模式）：本 sprint 完成「parser capture + mapper render 消費」、**不**完成「真實動態欄位值計算」（需 layout pagination context）。註記精確標示完成範圍、避免日後誤判 `[x]` = 即時頁碼已可運作。

### 5.2 wire-up 主軸定位

snappy-nova plan「Phase 1 captured parts 的 wire-up」主軸：Sprint 123 capture 的 `instrText` 是 §11.1 既列工項、Sprint 160 v2 完成其 render 端消費。屬「方向 A」（wire-up 不在 VR pipeline 的 module、不破 baseline、Sprint 157 範例）。

---

## 6. 後續

### 6.1 hypothesis：`BoxBuilder.ts` fieldType 收窄技術債

`tsc` 揭 `layout/BoxBuilder.ts` L111/L117 把 `FieldNode['fieldType']`（11 型）傳給只接受 7 型（`PAGE/NUMPAGES/DATE/TIME/AUTHOR/FILENAME/unknown`）的參數。Sprint 123 擴 `fieldType` 到 11 型（+`SEQ/TOC/REF/HYPERLINK/STYLEREF`）時、BoxBuilder 端的 layout 欄位型別未同步。

- **影響等級**：low（vitest 用 esbuild 不 type-check、runtime 不爆；僅 `tsc` 紅）
- **重現條件**：`npx tsc --noEmit`
- **不在本 sprint scope**（紀律 #18）；候選給後續 layout 端 field wire-up sprint 一併修（屆時 layout 真實消費 SEQ/TOC 等欄位、型別自然要對齊）。

### 6.2 Sprint 161 候選（wire-up 主軸續）

| 候選 | scope | 風險 | 備註 |
|---|---|---|---|
| `settings.defaultTabStop` → Layout.LineBreaker | Phase 1 wire-up、Sprint 146 capture ready | 中（可能破 baseline、走 Strategy C） | snappy-nova plan Sprint 156-158 原主項、被 158 P0 prep 推遲、159/160 又走 docs follow-up |
| `<w:bookmarkStart/End>` → mapper anchor wire-up | Phase 1 §1.9、Sprint 125 capture | 低（mapper 不在 VR pipeline、同本 sprint 模式） | bookmark 目前 `render 端不消費` |
| BoxBuilder fieldType 型別對齊 + layout 端 field 消費 | Phase 1/3 wire-up | 中（改 layout = 破 baseline 風險、Strategy C） | 連帶清 §6.1 技術債 |

### 6.3 三個 user 決策仍在桌上（不自行開工）

- Sprint 141 (B)：階段 C goldens 重生（換 VR baseline anchor、需 user GO）
- Sprint 142 (C)：Phase 5 fixture（6 子功能 42 fixture 0 覆蓋、需 user 提供 fixture + 優先序）
- Sprint 140 (A)：textAlignment / framePr wire-up（< pixelmatch resolution、DEFER user 手動 GO）

---

## File-level summary

```
M  static/src/core/ooxml/mapper/ToCanvasEditor.ts                (+50)
M  tests/unit/ToCanvasEditor.test.ts                             (+38)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js       (bundle rebuild)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js.map   (bundle rebuild)
M  dobtor_doc_editor_高保真匯入開發規劃.md                          (§1.9 instrText [ ]→[x])
M  docs/progress_snapshot.md                                      (Sprint 160 v2 指標)
M  docs/autonomous_roadmap.md                                     (進度追蹤表 backfill)
A  docs/sprint160_v2_instrtext_render_wireup.md                   (本 audit doc)
```

**淨 production code 變動 = +50 行**（`ToCanvasEditor.ts`：`fieldPlaceholder()` + `case 'field'` 改寫 + `FieldNode` import）、vitest 1340 → 1342、VR mean 0.073191 維持（mapper 不在 pipeline）、Phase 1 §5 checklist 51/65 → 52/65。
