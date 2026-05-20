# Sprint 163 — `Box.fieldType` 型別對齊 AST（型別債清理）

**性質**: 型別債清理 sprint、純型別變更（emitted JS 不變）、byte-identical by construction
**範圍**: 規畫書 §5 Phase 1 §1.4 — layout 端 `Box.fieldType` 對齊 AST `FieldNode['fieldType']`
**前置**: [sprint160_v2_instrtext_render_wireup.md](sprint160_v2_instrtext_render_wireup.md) §6.1 揭示的 BoxBuilder fieldType 收窄技術債

---

## 0. 開工前狀態（紀律 #14.b 第 0 步）

`git status -s .` = 空（Sprint 162 commit `f476e68` 已收口、已 push）。

---

## 1. Hypothesis

Sprint 160 v2 §6.1 揭：Sprint 123 把 AST `FieldNode['fieldType']` 擴為 11 型（+SEQ/TOC/REF/HYPERLINK/STYLEREF），但 layout 端未同步：

- `layout/types.ts` `Box.fieldType` 仍是 7 型
- `BoxBuilder.ts` `defaultFieldPlaceholder` param 仍是 7 型

→ `BoxBuilder.ts` 把 `run.fieldType`（11 型）傳給 7 型參數 / 賦值給 7 型 `Box.fieldType` = **2 個 pre-existing `tsc` error**（TS2345 + TS2322）。

**事實**（非 hypothesis）：runtime 早已正確 —— `defaultFieldPlaceholder` 的 `default` 分支對 5 個擴充型回 `{<type>}`、`resolveFieldValues` 對非 PAGE/NUMPAGES/DATE/TIME/AUTHOR/FILENAME 型「保留原 placeholder」。**僅型別標註落後**。

**Hypothesis**：把兩處型別擴為 `FieldNode['fieldType']`（11 型）→ 消除 2 個 tsc error、emitted JS 不變、VR byte-identical。

---

## 2. Method

### 2.1 變更（2 production 檔、純型別）

1. **[types.ts](../static/src/core/layout/types.ts)**：import `FieldNode`；`Box.fieldType?: FieldNode['fieldType']`（7 → 11 型）。
2. **[BoxBuilder.ts](../static/src/core/layout/BoxBuilder.ts)**：import `FieldNode`；`defaultFieldPlaceholder(fieldType: FieldNode['fieldType'])`（7 → 11 型）。

`defaultFieldPlaceholder` 的 `switch` 主體**不動**：PAGE/NUMPAGES/DATE/TIME/AUTHOR/FILENAME 各自 case、SEQ/TOC/REF/HYPERLINK/STYLEREF/unknown 走 `default → {<type>}`。→ emitted JS byte-identical（TS 型別 erase）。

### 2.2 scope-down（紀律 #18）

- **不**改 placeholder 文字（不把 `##` 改 `[PAGE]` 對齊 Sprint 160 v2 mapper）—— 那會動 VR、屬另一個 Strategy C 決策。
- **不**為 5 個擴充型加專屬 case —— `{SEQ}` 已足夠、加 case 會改 runtime 輸出。
- 本 sprint 嚴格限定「型別標註對齊」、零 runtime 變更。

### 2.3 新測試（3 個，`BoxBuilder.test.ts`）

| Test | 驗證 |
|---|---|
| PAGE 無 cachedValue → `##` + `Box.fieldType='PAGE'` | 既有行為 lock-in |
| PAGE 有 cachedValue → 用 cachedValue | 既有行為 lock-in |
| SEQ/TOC/REF/HYPERLINK/STYLEREF → `{<type>}` + `Box.fieldType` 收下該型 | 5 擴充型型別 + placeholder lock-in |

---

## 3. Verification（三層 SOP）

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1358 → 1361 passed + 1 skipped**（+3 BoxBuilder fieldType tests） |
| L2 VR v14 | ✅ **byte-identical 第 27 連** | rebuild VR pipeline + 跑全 42 fixture、report（除 `runAt`/`bundlePath`）與 HEAD byte-identical（純型別變更、emitted JS 不變） |
| L3 spot check | ✅ | types.ts +2 行 import + 型別 / BoxBuilder.ts +1 import + param 型別 / test +約 30 行 |
| L4 Odoo backend | **跳過** | 純前端 TS |
| typecheck | ✅ **改善** | `tsc --noEmit` error **4 → 2**（BoxBuilder fieldType ×2 消除；剩 FontMetrics opentype.js 宣告 + SettingsParser position、皆與本 sprint 無關） |

### 紀律應用

| 紀律 | 應用 |
|---|---|
| #1.a 改 layout 跑全 VR | ✅ 改 layout/types.ts + BoxBuilder.ts → 跑全 42 fixture 確認 byte-identical（即使純型別、仍依紀律驗證） |
| #14 / #14.b | ✅ docs 即時同步、working tree commit 收口、VR report churn `git checkout` 還原 |
| #18 scope-down | ✅ 嚴格限「型別對齊」、placeholder 文字 / 專屬 case 明確不做 |
| #4 capture-without-consumer 反例 | 本 sprint 是「型別標註落後 runtime」的技術債類型（Sprint 133/134 是 shape vs parser、本 sprint 是 layout 型別 vs AST 型別） |

---

## 4. Result

```
M  static/src/core/layout/types.ts             (+2 import / 型別 7→11)
M  static/src/core/layout/BoxBuilder.ts        (+1 import / param 型別 7→11)
M  tests/unit/layout/BoxBuilder.test.ts        (+3 test)
A  docs/sprint163_box_fieldtype_alignment.md   (本 audit doc)
M  docs/progress_snapshot.md / autonomous_roadmap.md / INDEX.md
```

| 指標 | Sprint 162 結尾 | Sprint 163 結尾 | 變動 |
|---|---|---|---|
| vitest | 1358 passed + 1 skipped | **1361 passed + 1 skipped** | +3 |
| VR mean | 0.073191（byte-identical 第 26 連） | **0.073191（byte-identical 第 27 連）** | 0 |
| `tsc --noEmit` error | 4 | **2** | -2 |
| Sprint audit doc | sprint162 | **sprint163** | +1 |

---

## 5. 後續

### 5.1 剩餘 2 個 tsc error（不在本 sprint scope）

- `FontMetrics.ts`：`opentype.js` 無 `.d.ts` 宣告（TS7016）—— 需 `@types/opentype.js` 或自寫 `declare module`。
- `SettingsParser.ts`：`footnotePr/endnotePr` position 型別不符（Sprint 146）—— 需對齊 `DocumentSettings` 型別定義。

兩者各自獨立、可後續各一個小 sprint 清掉（達成 `tsc` 全綠）。

### 5.2 hypothesis — layout placeholder vs mapper placeholder 不一致

`BoxBuilder.defaultFieldPlaceholder` 用 `##`/`YYYY/MM/DD`/`{SEQ}`；`ToCanvasEditor.fieldPlaceholder`（Sprint 160 v2）用 `[PAGE]`/`[DATE]`。兩條 render path 風格不一。統一需動 VR（BoxBuilder placeholder 餵 VR render）、屬 Strategy C 決策、非本 sprint scope。

### 5.3 三個 user 決策仍在桌上（不自行開工）

- Sprint 141 (B) goldens 重生 / Sprint 142 (C) Phase 5 fixture / Sprint 140 (A) textAlignment

---

**淨 production code 變動 = 0 行 runtime**（純型別標註：types.ts + BoxBuilder.ts 各 import + 型別擴展）、vitest 1358 → 1361、VR byte-identical 第 27 連、`tsc` error 4 → 2。
