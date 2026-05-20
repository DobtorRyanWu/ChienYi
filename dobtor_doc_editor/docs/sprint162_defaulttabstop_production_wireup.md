# Sprint 162 — `defaultTabStop` production 接線（Paginator/TableLayout）+ VR opt-in 量測

**性質**: Phase 1/3 wire-up sprint、layout production 接線 + VR pipeline opt-in（Strategy C 完整收口）
**範圍**: 規畫書 §5 Phase 1 §1.3 tab stops + Phase 3 Layout Engine — 把 Sprint 161 的 LineBreaker tab stop 引擎接到 `layoutDocument` 端到端、並以 VR opt-in 量測 delta
**前置 sprint**: [sprint161_defaulttabstop_linebreaker_engine.md](sprint161_defaulttabstop_linebreaker_engine.md)（LineBreaker 解析引擎、`LineBreakOptions.defaultTabStop`）

---

## 0. 開工前狀態（紀律 #14.b 第 0 步）

`git status -s .` = 空（Sprint 161 commit `fb7f240` 已收口、已 push）。working tree clean。

---

## 1. Hypothesis

Sprint 161 落地 LineBreaker tab stop 解析引擎、但**無 production caller**：`layoutDocument` / Paginator / TableLayout 都未把 `defaultTabStop` 傳給 `LineBreakOptions`。

開工前 probe（紀律 #22）確認 layout 消費者架構：
- `layoutDocument` / Paginator / Renderer 路徑的消費者 = **VR pipeline + DevTools CLI + 測試**；production canvas-editor 走 ToCanvasEditor mapper（Sprint 127 已揭「production 沒整合 Layout/Renderer 路徑」）。
- 故「production 接線」= 把 `defaultTabStop` 從 `LayoutOptions` 透傳到 `LineBreakOptions`，讓 `layoutDocument` 端到端可解析 tab；VR pipeline 是主要消費者。

**Hypothesis**：`LayoutOptions.defaultTabStop` → Paginator/TableLayout 3 個 `breakParagraph` 呼叫點 → `LineBreakOptions.defaultTabStop`；VR pipeline 以 opt-in flag 啟用、量測含 tab fixture 的 delta。caller 不傳 → byte-identical（Strategy C）。

---

## 2. Method

### 2.1 layout 接線（types + Paginator + TableLayout）

1. **[types.ts](../static/src/core/layout/types.ts)** `LayoutOptions` 加 `defaultTabStop?: Pt`。
2. **[Paginator.ts](../static/src/core/layout/Paginator.ts)**：
   - `PaginateContext` 加 `defaultTabStop?: Pt`（同 `numberingMap` 模式、跨 section 共用）。
   - `paginate` / `layoutDocument` 兩入口設 `ctx.defaultTabStop = options.defaultTabStop`。
   - body 段落 `layParagraph` 的 `breakParagraph` 傳 `defaultTabStop: ctx.defaultTabStop`。
   - header/footer 的 `renderBlocksToEntries` 的 `breakParagraph` 傳 `options.defaultTabStop`。
   - 表格透傳：`optionsWithGrid = { ...options }` 已 spread `defaultTabStop`。
3. **[TableLayout.ts](../static/src/core/layout/TableLayout.ts)**：cell 內段落 `breakParagraph` 傳 `options.defaultTabStop`。

> 接線過程踩一個錯：初版在 `layParagraph` 寫 `options.defaultTabStop`、但 `layParagraph` 只有 `ctx` 無 `options` → `ReferenceError`。改走 `ctx.defaultTabStop`（與 numbering 一致），紀律 #22 mental model 校正。

### 2.2 VR pipeline opt-in（Strategy C）

4. **[visual_regression_pipeline.entry.ts](../tools/visual_regression_pipeline.entry.ts)**：`RenderOptions` 加 `enableTabStops?: boolean`；`render()` 在 `enableTabStops` 為真時、從 `documentNode.settings.defaultTabStop`（無則 OOXML 預設常數 36pt）注入 `LayoutOptions.defaultTabStop`。
5. **[visual_regression_v14.mjs](../scripts/visual_regression_v14.mjs)**：加 `--tab-stops` flag → 傳 `enableTabStops: true` 給 harness（harness `Object.assign` 透傳、無需改 harness）。

→ 預設（無 `--tab-stops`）：VR pipeline 不注入 → `ctx.defaultTabStop` undefined → LineBreaker no-op → **baseline byte-identical**。

### 2.3 scope-down（紀律 #18）

- frontend bundle（`canvas-editor-custom.umd.js`）**不 rebuild**：production canvas-editor 走 ToCanvasEditor mapper、不經 Paginator；`LayoutOptions.defaultTabStop` 無 production caller（Sprint 157/161 同型「wire-up-without-production-consumer」）。
- `layout()` debug API 不改（caller 直接持 `LayoutOptions`、可自行傳 `defaultTabStop`）。

### 2.4 新測試（5 個，`tests/unit/layout/Paginator.tabStop.test.ts`）

端到端走 `layoutDocument`：
| Test | 驗證 |
|---|---|
| 未傳 defaultTabStop → body tab glue 維持空白寬 | Strategy C 預設路徑 |
| 傳 defaultTabStop → body tab 推進到 default stop | Paginator layParagraph 路徑 |
| 行首 tab → 推進到 36pt | x=0 起算 |
| 表格 cell 內段落 tab 被解析 | TableLayout 路徑 |
| cell 內未傳 → tab 維持空白寬 | TableLayout 預設路徑 |

---

## 3. Verification（三層 SOP）

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1353 → 1358 passed + 1 skipped**（+5 Paginator tab stop tests） |
| L2 VR v14 預設 | ✅ **byte-identical 第 26 連** | rebuild VR pipeline + 跑全 42 fixture、report（除 `runAt`/`bundlePath`）與 HEAD byte-identical；failedPages=0 |
| L2 VR v14 opt-in（`--tab-stops`） | ✅ 量測完成 | 見 §3.1 |
| L3 spot check | ✅ | layout 3 檔 + VR 2 檔 diff、新 test +約 130 行 |
| L4 Odoo backend | **跳過（誠實聲明）** | 純前端 TS、未改 controller / model |
| L5 frontend bundle | **跳過（誠實聲明）** | Paginator 路徑非 production canvas-editor render；`LayoutOptions.defaultTabStop` 無 production caller |

### 3.1 VR opt-in 量測結果（Strategy C 誠實聲明）

`node scripts/visual_regression_v14.mjs --tab-stops` vs 預設、全 42 fixture × 126 page：

| 指標 | 預設 | opt-in（`--tab-stops`） | Δ |
|---|---|---|---|
| aggregate per-page mean | 0.07319063 | 0.07319111 | **+4.76e-7**（可忽略） |
| 有 per-page diffRatio 變動的 fixture | — | **3 個** | — |

3 個變動 fixture（皆極微小、方向為輕微退化）：

| fixture | mean 變動 | Δ |
|---|---|---|
| 03.1120210-監造會議記錄-1120801.docx | 0.07544 → 0.07544 | +3.3e-6 |
| 03.1120919-監造會議記錄.docx | 0.06977 → 0.06977 | +3.3e-6 |
| 缺失改善(預設樣板).docx | 0.01394 → 0.01396 | +2.0e-5 |

**驗證 wire-up 真實生效**（非 no-op）：以 `--no-diff --tab-stops` 對 `03.1120210` 渲染、page 1 PNG md5 與預設**不同**（page 2/3 相同、tab 在 page 1）；單元 probe 確認 `layoutDocument({defaultTabStop:24})` 把該 fixture tab glue 寬度 2.84pt → 11.63pt。

**結論**：tab stop wire-up 正確且端到端生效，但**在現有 42-fixture VR 集上 aggregate delta 可忽略（+4.8e-7）**。原因：9 個含 tab 的 fixture 每份僅 1-2 個 tab（多為密集表格內 leader tab），golden（LibreOffice 渲染）本身在該區也偏離；解析 tab 後移動的 pixel 多半本來就計為「與 golden 不符」、relocate 不改變 mismatch 計數。

→ **Strategy C 判定**：保持 opt-in 預設關閉是正解 —— baseline byte-identical 維持、且量測證實 default-on 也只帶來 ~1e-5 級輕微退化、無 VR 收益。真實效益需 tab-heavy fixture（TOC / 表單），屬 Sprint 142「Phase 5 fixture」user 決策範圍。

### 3.2 typecheck

`npx tsc --noEmit`：4 個 pre-existing error（BoxBuilder fieldType ×2 / FontMetrics opentype.js / SettingsParser position），Sprint 162 新增 `LayoutOptions.defaultTabStop` / `PaginateContext.defaultTabStop` / `RenderOptions.enableTabStops` 皆**不引入新 error**。

### 3.3 紀律應用

| 紀律 | 應用 |
|---|---|
| #1.a 改 layout 跑全 VR | ✅ 改 Paginator/TableLayout/types → 跑全 42 fixture（預設 byte-identical + opt-in 量測） |
| #14 / #14.b docs 即時同步 + working tree 清零 | ✅ 第 0 步檢查；temp debug 檔/temp warning 收口刪除；report timestamp churn `git checkout` 還原 |
| #18 PR-size + scope-down | ✅ frontend bundle / `layout()` API 明確不動 |
| #22 probe before action | ✅ 開工前 probe layout 消費者架構（Paginator 非 production render）；接線時踩 `options` not in scope 即修正 mental model |
| Strategy C（Sprint 139 模式） | ✅ layout 接通 + VR pipeline opt-in；預設關閉 byte-identical、opt-in 量測誠實聲明 delta |

---

## 4. Result

### 4.1 檔案變動

```
M  static/src/core/layout/types.ts                       (+13：LayoutOptions.defaultTabStop)
M  static/src/core/layout/Paginator.ts                    (+約14：PaginateContext.defaultTabStop + 2 注入 + 2 call site)
M  static/src/core/layout/TableLayout.ts                  (+1：cell breakParagraph defaultTabStop)
M  tools/visual_regression_pipeline.entry.ts              (+約15：RenderOptions.enableTabStops + 常數 + render 注入)
M  scripts/visual_regression_v14.mjs                      (+約12：--tab-stops flag)
A  tests/unit/layout/Paginator.tabStop.test.ts            (5 新 test)
A  docs/sprint162_defaulttabstop_production_wireup.md     (本 audit doc)
M  docs/progress_snapshot.md / autonomous_roadmap.md / INDEX.md
```

### 4.2 累積指標

| 指標 | Sprint 161 結尾 | Sprint 162 結尾 | 變動 |
|---|---|---|---|
| vitest | 1353 passed + 1 skipped | **1358 passed + 1 skipped** | +5 |
| VR mean | 0.073191（byte-identical 第 25 連） | **0.073191（byte-identical 第 26 連）** | 0（opt-in 量測 Δ+4.8e-7） |
| Odoo backend | 31 passed | 31 passed（未跑、無 backend 變動） | 0 |
| Phase 1 §5 checklist | 52/65 [x] | 52/65 [x] | 0 |
| Sprint audit doc | sprint161 | **sprint162** | +1 |

> 規畫書 §1.3「tab stops」既已 `[x]`（指 parse）；defaultTabStop wire-up（Sprint 161-162）無專屬 checkbox，於 §1.3 加註記。

---

## 5. 與規畫書關係

§5 Phase 1 §1.3 tab stops：Sprint 161（LineBreaker 引擎）+ Sprint 162（layoutDocument 端到端接線 + VR opt-in 量測）完成 tab stop wire-up。§1.3 加 Sprint 161-162 註記（capture-only → 引擎 → production 接線三段式、同 numbering Sprint 137-139）。

---

## 6. 後續

### 6.1 tab stop wire-up 收束狀態

| 子工作 | 狀態 |
|---|---|
| LineBreaker 解析引擎 | ✅ Sprint 161 |
| layoutDocument / Paginator / TableLayout 接線 | ✅ Sprint 162 |
| VR pipeline opt-in + 量測 | ✅ Sprint 162（delta 可忽略、Strategy C 維持 opt-in） |
| center / right / decimal tab 對齊 | ⏳ 未做（罕用、`resolveTabStops` 只解 left；待真實 fixture 需求） |
| 貪婪斷行 buf 累寬用未解析寬度（Sprint 161 §6.2 hypothesis） | 未觀察到 reflow（量測 0 page-count 變動）；維持近似 |

### 6.2 hypothesis — tab stop VR 收益需 tab-heavy fixture

現有 42-fixture VR 集 tab 過少（9 fixture × 1-2 tab）、delta ~1e-5。tab stop 對 TOC / 報表表單 / 對齊欄位等 tab-heavy 文件才有顯著視覺效益。

- **建議**：Sprint 142「Phase 5 fixture」user 決策若補 fixture、可納入 tab-heavy 樣本、屆時 opt-in 重量測。

### 6.3 三個 user 決策仍在桌上（不自行開工）

- Sprint 141 (B)：階段 C goldens 重生（換 VR baseline anchor、需 user GO）
- Sprint 142 (C)：Phase 5 fixture（含 tab-heavy fixture 缺口、需 user 提供 + 優先序）
- Sprint 140 (A)：textAlignment / framePr wire-up（< pixelmatch resolution、DEFER user 手動 GO）

---

## File-level summary

```
M  static/src/core/layout/types.ts                        (+13)
M  static/src/core/layout/Paginator.ts                     (+約14)
M  static/src/core/layout/TableLayout.ts                   (+1)
M  tools/visual_regression_pipeline.entry.ts               (+約15)
M  scripts/visual_regression_v14.mjs                       (+約12)
A  tests/unit/layout/Paginator.tabStop.test.ts             (5 test)
A  docs/sprint162_defaulttabstop_production_wireup.md      (本 audit doc)
M  docs/progress_snapshot.md / autonomous_roadmap.md / INDEX.md
```

**淨 production code 變動 = +約 28 行**（layout 接線）、VR pipeline +約 27 行（opt-in plumbing）、vitest 1353 → 1358、VR mean 0.073191 byte-identical 第 26 連（opt-in delta +4.8e-7 可忽略、Strategy C 維持 opt-in 關閉）。
