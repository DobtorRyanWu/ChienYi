# Sprint 183 — SmartArt / Chart render wire-up（Phase 5.2 / 5.3 收尾）

**日期**：2026-05-22
**類型**：DrawingParser 增強 + mapper render wire-up（Phase 5.2 SmartArt + 5.3 Charts、線性文字 fallback）
**規畫書對應**：§5 階段 D Phase 5.2「SmartArt fallback」+ Phase 5.3「Charts fallback」
**前置**：Sprint 181（SmartArt capture）、Sprint 182（Chart capture）；決策 C（user 2026-05-21 GO、Phase 5 大三項採 mc:Fallback 壓縮）

---

## Hypothesis

Sprint 181-182 完成 SmartArt / Chart 的 capture（`DocumentNode.smartArts` /
`charts`），但兩者在文件流中仍 render 為空白圖片 —— DrawingParser 對
`<a:graphicData uri=".../diagram|chart">` 的 graphic frame 落 fallback path、
產出 `rId=''` 的 InlineImageNode → ToCanvasEditor render 成 `[圖片缺失]`。

本 sprint 把已 capture 的資料 render 出來，一個 sprint 收 5.2 + 5.3 render
（兩者同走 `<w:drawing>` graphic frame 路徑、render 策略相同）。

**render 策略 — 線性文字 fallback**（同 Sprint 180 OMML、與 user mc:Fallback
壓縮決策一致）：
- SmartArt → 各內容點文字以 ` / ` 串接。
- Chart → `標題 數列名: 類別=值, …; …` 格式呈現數值快取。
- 圖形版面 / 座標軸 / 連接線不重繪（degraded fidelity）；全保真圖形 render 留
  未來 optional。

---

## 修法

### 1. `InlineImageNode.graphic?`（types.ts、+12 行）

`graphic?: { kind: 'diagram' | 'chart'; relId: string }` —— DrawingML graphic
frame 內嵌的非圖片內容。`relId` 指向獨立部件（diagram → `<dgm:relIds r:dm>`、
chart → `<c:chart r:id>`）。紀律 #21：一般圖片無此欄位。

### 2. DrawingParser graphic frame 偵測（+約 38 行）

`parseInlineImage` 加 `parseGraphicFrame`：掃 `<a:graphicData uri>` ——
- uri = `.../diagram` → 取 `<dgm:relIds r:dm>` → `{ kind: 'diagram', relId }`
- uri = `.../chart` → 取 `<c:chart r:id>` → `{ kind: 'chart', relId }`
- 其他 uri / 缺 relId → 不掛 `graphic`（一般 pic blip 圖片不受影響）。

### 3. render 文字化函式（DiagramParser / ChartParser、+約 35 行）

- `smartArtToText(node)`：`node.texts.join(' / ')`。
- `chartToText(node)`：逐數列 `名稱: 類別=值, …`、以 `; ` 串接、前綴標題；
  null 數值只顯類別、完全空白點跳過。
- 比照 Sprint 180 `ommlToLinearText` 放在 parser 同檔、經 index.ts re-export。

### 4. ToCanvasEditor render wire-up（+約 35 行）

- `convert()` 開頭建 `smartArtsByRId` / `chartsByRId` 查表（每次重建、不跨文件殘留）。
- `appendImage`：`img.type==='inlineImage' && img.graphic` 時 →
  `graphicFallbackText(graphic)` 查表：
  - 查到節點 → 非空 append 線性文字、空內容不 emit、**return 不走圖片路徑**。
  - 查無節點（`undefined`）→ 落原圖片路徑（`[圖片缺失]`）。

### 5. 測試（+20）

- `tests/unit/DrawingParser.test.ts`（+5）：SmartArt / Chart graphic frame
  偵測、一般 pic 圖片不掛 `graphic`、未知 uri、diagram 缺 r:dm。
- `tests/unit/DiagramParser.test.ts`（+3）：`smartArtToText`（空 / 單 / 多節點）。
- `tests/unit/ChartParser.test.ts`（+7）：`chartToText`（無數列 / 僅標題 / 單數列 /
  多數列 / null 值 / 空白點跳過 / 無數列名）。
- `tests/unit/ToCanvasEditor.test.ts`（+5）：SmartArt / Chart graphic frame
  render 線性文字、查無節點落圖片路徑、空 SmartArt 不 emit、一般圖片不受影響。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1621 → **1641 passed + 1 skipped**（+20） |
| L2 VR v14 | ✅ **byte-identical 第 43 連** | rendered 42/42、comparedPages 126、failedPages 0；0/42 baseline fixture 含 SmartArt/Chart graphic frame → `graphic` 皆 undefined → render 新分支 0 觸發 |
| L3 visual spot check | ✅ 線性文字 fallback | SmartArt 以 ` / ` 串接、Chart 以 `數列名: 類別=值` 呈現（degraded fidelity、無圖形 render） |

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js / SettingsParser
  position enum）、**無新增**。
- frontend bundle + VR IIFE bundle 重建（DrawingParser / ToCanvasEditor 在依賴樹）。

---

## 紀律

- **#1.b / Strategy C**：render 新分支只在 `inlineImage.graphic` 存在時觸發；
  0/42 baseline fixture 含 SmartArt/Chart graphic frame → `graphic` 皆 undefined
  → render 路徑不變 → byte-identical 第 43 連。
- **#1.a**：改 parser + mapper 跑全 42 fixture VR。
- **#21**：`InlineImageNode.graphic` 無 SmartArt/Chart graphic frame 時不掛 key。
- **#14（DRY）**：`smartArtToText` / `chartToText` 比照 Sprint 180 `ommlToLinearText`
  放 parser 同檔、index.ts re-export；ToCanvasEditor 複用既有 `appendChars` /
  `mapRunProps`；graphic frame 偵測複用 DrawingParser 既有 `getElementsByTagName`。
- **#18 scope-down**：線性文字 fallback（非全保真圖形 render）；行內精確位置沿用
  capture-only 近似；圖片浮水印式的 FloatImageNode graphic frame 留後續
  （fixture 皆 wp:inline）。**與 user mc:Fallback 壓縮決策一致**。

---

## 後續

- SmartArt / Chart 全保真圖形 render（版面引擎 / 座標軸繪製）— 未來 optional sprint。
- **Phase 5 大三項（5.1 OMML / 5.2 SmartArt / 5.3 Charts）capture + render 全數
  完成**（OMML 179-180、SmartArt capture 181 + render 183、Chart capture 182 +
  render 183）。
- 下一步：Phase 6 docx export 對稱性，或 Phase 5 全保真 render optional。

---

## Sprint 183 結尾累積指標

- vitest **1641 passed + 1 skipped**（`npm test` 全套；+20）
- VR mean **0.073191**（byte-identical 第 43 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 182 → **183**
- Phase 5 大三項 capture + render 全數完成

---

## File-level summary

```
M  static/src/core/ooxml/ast/types.ts               InlineImageNode.graphic?（+12）
M  static/src/core/ooxml/drawing/DrawingParser.ts    parseGraphicFrame 偵測（+約 38）
M  static/src/core/ooxml/diagram/DiagramParser.ts    smartArtToText（+約 11）
M  static/src/core/ooxml/diagram/index.ts            export smartArtToText
M  static/src/core/ooxml/chart/ChartParser.ts        chartToText（+約 24）
M  static/src/core/ooxml/chart/index.ts              export chartToText
M  static/src/core/ooxml/mapper/ToCanvasEditor.ts    graphic frame render wire-up（+約 35）
M  tests/unit/DrawingParser.test.ts                  +5 test
M  tests/unit/DiagramParser.test.ts                  +3 test
M  tests/unit/ChartParser.test.ts                    +7 test
M  tests/unit/ToCanvasEditor.test.ts                 +5 test
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
M  tools/dist/visual_regression_pipeline.iife.js     VR bundle 重建
```

**淨 production code 變動 = +約 120 行**、線性文字 fallback render、VR byte-identical
第 43 連、Phase 5 大三項 capture + render 全數完成。
