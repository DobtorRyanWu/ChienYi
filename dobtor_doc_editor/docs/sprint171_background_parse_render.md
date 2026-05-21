# Sprint 171 — `<w:background>` 文件背景 parse + render wire-up（Phase 5.6）

**日期**：2026-05-21
**類型**：parser + render wire-up（Phase 5.6 浮水印 + 背景、Strategy C）
**規畫書對應**：§5 階段 D Phase 5.6「浮水印 + 背景」
**前置**：決策 C（user 2026-05-21 GO 全 6 子功能）；user 同意用 synthetic fixture 驗 parser
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

決策 C（Phase 5 進階功能）user GO，工作順序「可控部分先做」第一項 = Phase 5.6
浮水印 + 背景。Phase 5.6 含兩塊：(a)`<w:background>` 頁面背景色、(b) header VML
浮水印 shape（DRAFT / 機密 文字）。本 sprint 取較小、定義最清晰的 (a)。

tests/fixtures/ 無 Phase 5 樣本（user 確認）→ 用 synthetic XML 驗 parser。

---

## 修法

### 1. `DocumentBackground` 型別 + `DocumentNode.background?`（types.ts、+22 行）

`<w:background>`（OOXML §17.2.1）是 `<w:document>` 直接子元素、`<w:body>` 的 sibling、
描述頁面背景色（Word「設計 → 頁面色彩」）。`background` 為 optional（多數 docx 無此
元素、紀律 #21）。

### 2. 新檔 `static/src/core/ooxml/background/BackgroundParser.ts`（+88 行）

`parse(documentXml) → DocumentBackground | undefined`：
- `w:color` → `color`（6-hex 驗證 + 大寫正規化；`"auto"` / 非法 → 不掛）
- `w:themeColor` → `themeColor`（capture raw、未解析為 hex）
- 無 `<w:background>` / 無有效屬性 / XML 失敗 → `undefined`（紀律 #21）

自帶 `parseXml` / `directChild` 區域 helper（同 SettingsParser 等 parser 的自含模式）。

### 3. `OoxmlParser` Step 8.4（+6 行 + parser 實例）

`backgroundParser.parse(documentXml)` → DocumentNode literal 以
`...(background !== undefined ? { background } : {})` 條件掛入（紀律 #21、optional 不掛空 key）。

### 4. render wire-up：`CanvasRenderer.pageBackgroundColor`（+11 行）

`CanvasRenderOptions.pageBackgroundColor?: string`（預設 `'FFFFFF'`）。
`renderPage` 頁底 `fillRect` 由寫死 `'FFFFFF'` 改為 `this.opts.pageBackgroundColor`。

### 5. VR pipeline entry 端到端接線（+6 行）

`paintPage` 讀 `documentNode.background?.color`、有值才傳
`{ pageBackgroundColor: bgColor }` 給 `CanvasRenderer`（避免 `undefined` 覆寫 DEFAULTS）。
→ parser → `DocumentNode.background` → VR pipeline → `CanvasRenderer` → `fillRect` 全鏈接通。

### Strategy C（紀律 #1.b）

無 `<w:background>`（42 fixture 全數）→ `documentNode.background` undefined →
`bgColor` undefined → 不傳 option → `CanvasRenderer` 用 DEFAULTS `'FFFFFF'` →
與 Sprint 0-170 byte-identical。背景色只對「真有 `<w:background>` 的 docx」生效。

### Scope-down（紀律 #18）

- `w:themeColor` 只 capture raw、不解析為 hex（render 用 `color`；只有 themeColor 時
  退回預設白底）。themeColor → hex 解析留後續。
- `<v:background>` VML 圖片填充背景留後續 sprint。
- Phase 5.6 的另一半（header VML 浮水印 shape）留 Sprint 172。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1410 → 1424 passed + 1 skipped**（+14：BackgroundParser 12 + CanvasRenderer 2）。涵蓋 w:color 6-hex / 小寫正規化 / "auto" 不掛 / 非法 hex / w:themeColor / color+themeColor 並存 / 無元素 / 空輸入 / XML 失敗 / 空屬性不掛；renderer pageBackgroundColor 預設白 + 指定色 |
| **L2 VR v14** | frontend bundle + VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 31 連）。42 fixture 全無 `<w:background>` → 驗證 Strategy C |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.6 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- **frontend bundle 重建**：OoxmlParser 變動（新增 BackgroundParser）在 frontend bundle
  依賴樹內 → `canvas-editor-custom.umd.js` 重建（含 BackgroundParser；production mapper
  不消費 `background`、行為不變、僅保持 committed 產物與 source 同步）。
- flake8：不適用（0 行 Python）。

---

## Root cause

`<w:background>` 自始未被解析（OOXML parser 涵蓋 14 子目錄但無 background）。Phase 5.6
「背景」即此元素。本 sprint 把它接成完整一鏈：parser 產 `DocumentNode.background`、
renderer 以 `pageBackgroundColor` 消費、VR pipeline entry 串接——非 capture-only stub，
而是真實端到端 wire-up（grep 看得到 callsite）。Strategy C 保 byte-identical：背景色
只在 docx 真有 `<w:background>` 時改變輸出。

---

## 紀律

- **#1.b / Strategy C**：renderer `pageBackgroundColor` 預設 `'FFFFFF'`、無 `<w:background>`
  → 不傳 → byte-identical by construction。第 31 連。
- **#1.a**：改 render 路徑跑全 42 fixture VR。
- **#21**：`background` optional、無有效屬性不掛 key；DocumentNode literal 條件掛入。
- **#14（模組化）**：BackgroundParser 自成 `background/` 子目錄、與其他 OOXML part parser 一致。
- **#18 scope-down**：themeColor → hex 解析 / VML 圖片背景 / header 浮水印 shape → 後續。
- **#8 / 決策 C**：synthetic XML 驗 parser（user 同意、tests/fixtures 無 Phase 5 樣本）。

---

## 後續

- **Sprint 172**：Phase 5.6 另一半 —— header VML 浮水印 shape（`<w:pict>` + `<v:shape>`
  WordArt textpath、DRAFT / 機密 文字浮水印）。比 background 複雜（VML shape 解析）。
- `w:themeColor` → hex 解析（用 OoxmlParser 既有 themeMap）、`<v:background>` 圖片背景。
- 之後 Phase 5.4 追蹤修訂 / 5.5 註解（決策 C 可控部分剩餘）。

---

## Sprint 171 結尾累積指標

- vitest **1424 passed + 1 skipped**（+14）
- VR mean **0.073191**（byte-identical 第 31 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 170 → 171
- 新檔 `background/BackgroundParser.ts`、新型別 `DocumentBackground`
- Phase 5.6「背景」完成；「浮水印」（header VML）留 Sprint 172
