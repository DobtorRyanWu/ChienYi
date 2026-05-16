# Sprint 121 — trHeight 進階 row height 防禦性解析（階段 B 開工）

**日期**：2026-05-17
**類型**：code change（改善 / 防禦性 / Phase 1 OOXML 1.5 收口）
**規畫書對應**：§Phase 1.5.3 trHeight 邊界 + autonomous_roadmap.md 階段 B 行 1
**前置 sprint**：Sprint 45-48 連四 sprint val-as-min 邏輯落地（layout 端）。本 sprint 補 parser 端入口防禦。

---

## Hypothesis

`TableParser.parseRow()` 對 `<w:trHeight>` 的解析過於樂觀：

1. 不驗證 `w:val` 是非負整數（負值會變負 twip 進 layout）
2. `val=0` 配 `hRule=auto/缺` 仍記 height=0pt（auto 0 沒下限意義、會誤導下游）
3. `hRule="exact"/"atLeast"` 沒有有效 val 時、heightRule 仍記為強約束（TableLayout 走 `heightRule==='exact' && height` 分支會撞 undefined）
4. NaN val（`<w:trHeight w:val="abc"/>`）不會 throw 但會 silently 失敗

階段 B Phase 1.5 進階 row height scope 內、補入口防禦使下游 TableLayout 分支不需在 undefined 狀態下做 special case。

紀律 #1（renderer 變動跑全 VR）不嚴格適用本 sprint（parser 變動），但既然動到 OOXML pipeline、紀律 #5（vitest 通過不保證 bundle work）+ 自家保守：rebuild bundle + 跑全 VR 確認 0 regression。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 1：「121-123 | Phase 1 OOXML | 1.5 進階 row height（`<w:trHeight calcInternal>`）...」
- 規畫書 §Phase 1.5.3 trHeight：列 `hRule` = `exact` / `atLeast` / `auto`、Sprint 45-48 連四 sprint 突破（layout 端 val-as-min）
- 本 sprint scope = **入口防禦**（parser 邊界）、不動 layout、不擴 hRule 集合
- PR-size：parser +14 行 / unit test +96 行 / docs +1 audit

### 2. 真實 fixture 排查

```
grep `<w:trHeight` across 42 fixtures：
- val=正整數 + hRule="exact" → 大量出現
- val=正整數 + 無 hRule → 大量出現
- val=0 / 負值 / NaN / hRule="auto"明示 / 未知 hRule → **0 出現**
```

→ 預測 VR mean 0 變動（已驗證、見 §3）。本 sprint 是**前瞻防禦**、處理未來 fixture / 第三方 docx 生成器（OnlyOffice / LibreOffice / WPS）可能出現的邊界。

### 3. 修法（TableParser.ts parseRow）

```ts
// 原來
const valRaw = trHeightEl.getAttribute('w:val');
if (valRaw !== null) {
  const n = parseInt(valRaw, 10);
  if (Number.isFinite(n)) height = twipToPt(n);  // 沒檢負值
}
const ruleRaw = trHeightEl.getAttribute('w:hRule');
if (ruleRaw === 'exact' || ruleRaw === 'atLeast') heightRule = ruleRaw;
else heightRule = 'auto';  // val 缺也照記 hRule

// Sprint 121
const valRaw = trHeightEl.getAttribute('w:val');
if (valRaw !== null) {
  const n = parseInt(valRaw, 10);
  if (Number.isFinite(n) && n >= 0) height = twipToPt(n);  // ⊕ 非負檢查
}
const ruleRaw = trHeightEl.getAttribute('w:hRule');
if (ruleRaw === 'exact' || ruleRaw === 'atLeast') heightRule = ruleRaw;
else heightRule = 'auto';
// ⊕ val=0 配 hRule=auto/缺 → strip（auto 0 沒下限意義）
if (height === 0 && heightRule === 'auto') height = undefined;
// ⊕ hRule 強約束無有效 val → demote 'auto'（防 TableLayout 分支不一致）
if ((heightRule === 'exact' || heightRule === 'atLeast') && height === undefined) {
  heightRule = 'auto';
}
```

**關鍵設計**：保留「val=0 配 hRule=exact」原樣（合法零高度行、Word 真的渲染塌陷列）；只 strip auto 0。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **985 passed + 1 skipped**（從 976+1 起、+9 新 Sprint 121 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（與 Sprint 65 baseline byte-identical）|
| L3 Spot check | ✅ TypeScript build PASS（warning 為 pre-existing opentype.js types + ADR-008.1 lazy circular）|
| L4 Odoo backend | **跳過**（無 backend 變動）|

L1 指令：`npx vitest run --reporter=basic`（總 73.6s）
L2 指令：`node scripts/visual_regression_v14.mjs`（總 ~5 min、42 fixture × 126 pages）
L3 指令：`npm run build:frontend`（rollup → `static/src/lib/canvas_editor/canvas-editor-custom.umd.js`、35s）

### 5. Unit test 設計（9 個新 test）

| Test | 鎖定邊界 |
|---|---|
| trHeight 無 hRule（隱含 auto）保留 height | 真實 fixture 大宗 case |
| 顯式 hRule="auto" | 從「default fallback 路徑」獨立成 explicit 路徑 |
| val=0 配 hRule=exact 保留為合法零高度行 | Word 渲染塌陷列、不能 strip |
| val=0 配 hRule=auto/缺 strip height | auto 0 無下限意義 |
| 負 val 視為缺 val、hRule=exact 隨之 demote 為 auto | 防 layout 撞 undefined exact 分支 |
| hRule="atLeast" 無 val 時 demote 為 auto | 同上 |
| 未知 hRule 值 fallback 為 auto（不 throw）| 防第三方 docx 生成器擴 hRule 集 |
| NaN val（"abc"）視為缺 val | parseInt 對非數字回 NaN |
| 完全沒 trHeight 時兩值都 undefined | 不傷既有行為 |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/table/TableParser.ts` | +14 行（parseRow trHeight 區塊）| 入口防禦 4 項 |
| `tests/unit/TableParser.test.ts` | +132 行 / 9 新 test | 鎖定 9 個 edge case |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #5）| IIFE bundle 與 TS source 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp 變動、數值 byte-identical | VR re-run confirm 0 regression |
| `docs/sprint121_trheight_defensive_parsing.md` | 本 audit doc | 紀錄修法與防禦設計 |
| `docs/autonomous_roadmap.md` | 階段 B 行 1（121-123）部分 ✅ + 進度表 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

### Test 數變動

- Sprint 120 結尾：vitest 976 passed + 1 skipped / Odoo backend 31 passed
- Sprint 121 結尾：vitest **985 passed + 1 skipped**（+9）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 120 結尾：mean 0.073191 / failed 0 / compared 126
- Sprint 121 結尾：mean **0.073191** / failed 0 / compared 126（byte-identical、預測命中）

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML：72% → **73%**（+1%、進階 row height 入口邊界補完；1.5 進階仍待 OLE / field code 等項）

---

## Root cause

**為什麼 parser 邊界這麼久才補**：

1. Sprint 0-2 TableParser 落地時 focus 主流元素（gridSpan / vMerge / tcW），trHeight 走 happy path
2. Sprint 45-48 突破 trHeight val-as-min 是在 layout 端、parser 端的 edge case 沒被 trigger（真實 fixture 都是 well-formed）
3. Sprint 110 後階段 A 全 docs / security、不動 parser
4. 階段 B Sprint 121 第一個 code change sprint、補入口防禦是合理切入點

**為什麼 VR 0 變動仍值得做**：

- 真實 fixture 全 well-formed val、hit 不到 edge path（測試證實 mean byte-identical）
- 但未來 fixture（如 user 新提供 50+ 頁、或第三方 docx 生成器產出）可能 hit
- 紀律 #4：「負面結果 sprint 仍有結構價值」延伸 — 「VR 不變但揭示防禦缺口的 sprint 也有價值」
- 紀律 #18.d 子（Sprint 117）：read-design-intent-first — 本 sprint 對 TableLayout 「heightRule === 'exact' && height」分支讀後、發現 parser 端應對齊（防 undefined 進入 strong-constraint 分支）

---

## 紀律

### 紀律 #1 邊界澄清（Sprint 121 揭示候選）

紀律 #1 原文：「**改 BrowserCanvasRenderContext / CanvasRenderer 後**強制跑全 42-fixture VR」。

本 sprint 改 **TableParser**（不是 Renderer）、但仍跑全 VR + bundle rebuild。揭示：

> **紀律 #1 子候選**：**改 parser / style resolver / layout engine 任一層、即使預期 VR 不變、仍應 rebuild bundle + 跑全 VR 確認**。
>
> **Why**：parser → layout → renderer 三層任一變動都可能傳到 VR。Sprint 121 是 happy case（VR 真的不變），但「以為不變」與「跑了確認不變」差距是隱性 assumption 風險（紀律 #4 教訓）。
>
> **How to apply**：階段 B 後續 code change sprint 預設都跑 L2 VR、即使預期 0 變動。

候選未升正式紀律（需跨 3 sprint 驗證、Sprint 122/123 同型 code change 可驗證）。

### 紀律 #5 持續（Sprint 121）

紀律 #5「vitest 通過不保證 IIFE bundle 同 code 也 work」在 Sprint 121 套用：vitest 985 綠 → rebuild bundle → VR pipeline 用 bundle 跑 → byte-identical。三段都驗證、紀律 #5 應用到位。

---

## 後續

### Sprint 122（roadmap 階段 B 行 1 同 cluster）

Phase 1.8 OLE objects 降級渲染（placeholder + alt text）。同 cluster code change、預設套用 Sprint 121 揭示的紀律 #1 子候選（跑全 VR）。

### Sprint 121+ 候選

- 若紀律 #1 子在 Sprint 122/123 連跨 3 sprint 驗證、可升正式紀律 #1.a「改 parser/style/layout 層也跑 VR」
- trHeight 的 layout 端進階（Sprint 47 val-as-min unsnapped basis）是否有對應的 fixture-level edge 仍待 audit
- 第三方 docx 生成器 fixture（OnlyOffice / WPS / LibreOffice）若有 calcInternal-style 屬性、本 sprint 防禦正好接住

---

## Sprint 121 結尾累積指標

- vitest **985 passed + 1 skipped**（+9）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 72% → **73%**
- 21 ADR / 18 條紀律 + 6 子 + **2 候選**（+ #1 子候選 Sprint 121 parser-also-runs-VR）
- Sprint audit doc 數 120 → **121**
- 階段 B 第一個 sprint 完成、cluster Sprint 121-123 進度 1/3

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/table/TableParser.ts  (+14 行 防禦)
M  addons/dobtor_doc_editor/tests/unit/TableParser.test.ts  (+132 行 / 9 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (timestamp re-run、數值 byte-identical)
A  addons/dobtor_doc_editor/docs/sprint121_trheight_defensive_parsing.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 B 121-123 部分 ✅ + Sprint 121 進度表)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 73%)
```

無 model / view / ACL / rule 變動。階段 B 開工。
