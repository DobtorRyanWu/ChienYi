# Sprint 172 — header VML 浮水印 shape capture（Phase 5.6 浮水印）

**日期**：2026-05-21
**類型**：parser（capture-only、Phase 5.6 浮水印 + 背景）
**規畫書對應**：§5 階段 D Phase 5.6「浮水印 + 背景」
**前置**：Sprint 171（Phase 5.6「背景」）；決策 C（user 2026-05-21 GO）；user 同意 synthetic fixture
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Phase 5.6 含「背景」+「浮水印」兩塊。Sprint 171 完成背景；本 sprint 做浮水印。

Word 浮水印（「設計 → 浮水印」）儲存為 **header part 內 `<w:pict>` 的 VML `<v:shape>`**：
- 文字浮水印：`<v:shape type="#_x0000_t136">` WordArt、含 `<v:textpath string="DRAFT">`
- 圖片浮水印：`<v:shape id="WordPictureWatermark...">`、含 `<v:imagedata r:id="...">`

現況：header 內 `<w:pict>` 被 ParagraphParser 降級為 `[圖片(VML)]` placeholder（Sprint 122）、
浮水印文字（textpath `string`）完全遺失。本 sprint capture 浮水印 shape 進 AST。

tests/fixtures/ 無 Phase 5 樣本（user 確認）→ synthetic XML 驗 parser。

---

## 修法

### 1. `DocumentWatermark` 型別 + `DocumentNode.watermark?`（types.ts、+34 行）

`kind`（'text' / 'image'）+ `text` / `font` / `imageRId` / `rotation`。
optional（多數 docx 無浮水印、紀律 #21）。

### 2. 新檔 `static/src/core/ooxml/watermark/WatermarkParser.ts`（+147 行）

`parse(headerXml) → DocumentWatermark | undefined`：
- `getElementsByTagName('v:shape')` 掃所有 VML shape、逐一 `parseShape`
- **文字浮水印偵測**：shape 含 `<v:textpath>` 且 `string` 非空 → `kind:'text'`、
  text = textpath string、font = textpath style font-family（去引號）、
  rotation = shape style rotation（度）
- **圖片浮水印偵測**：shape `id` 含 "watermark"（Word 命名 `WordPictureWatermark*`）
  且含 `<v:imagedata>` → `kind:'image'`、imageRId = imagedata `r:id`
- 偵測準則的取捨：textpath 在 header 內幾乎必為浮水印 → 不要求 id；圖片 VML 可能是
  logo → 要求 id 含 "watermark" 才視為浮水印（避免誤判）
- 區域 helper：`firstByTag` / `styleProp`（CSS-like style 解析）/ `parseRotation` / `stripQuotes`

### 3. `OoxmlParser` Step 8.5 + `collectWatermark` helper（+約 25 行）

`collectWatermark` 走訪所有 `REL_TYPE_HEADER` part、對每個 raw header XML 跑
WatermarkParser、回傳第一個找到的浮水印。DocumentNode literal 以
`...(watermark !== undefined ? { watermark } : {})` 條件掛入（紀律 #21）。

### Scope-down（紀律 #18）

- **capture-only**：render（每頁繪旋轉半透明浮水印）留 Sprint 173。
- 只 capture 第一個浮水印 shape；不區分 default / first / even header。
- 不解析 VML fill 透明度（`<v:fill opacity>`）、shape 尺寸 / 位置。
- 圖片浮水印的 image bytes 解析沿用既有 media 收集（imageRId 已可對應 `DocumentNode.media`）。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1424 → 1434 passed + 1 skipped**（+10 WatermarkParser）。涵蓋文字浮水印 text / font 去引號 / rotation / 空 textpath 不算；圖片浮水印 id+imagedata / 一般 logo 圖不誤判；多 shape 取第一個；無 shape / 空 / XML 失敗防禦 |
| **L2 VR v14** | frontend + VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 32 連）。capture-only、layout/render 0 變更 → byte-identical by construction |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.6 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 重建（OoxmlParser 在依賴樹內、production mapper 不消費 watermark、僅保產物同步）。
- flake8：不適用（0 行 Python）。

---

## Root cause

浮水印自始未被 capture——header 的 `<w:pict>` 走 ParagraphParser 的 Sprint 122 VML
placeholder 路徑（`[圖片(VML)]`）、丟失 textpath 文字。Phase 5.6「浮水印」需在
header part 層級辨識 watermark VML shape 並抽出結構。本 sprint 以獨立 WatermarkParser
掃 raw header XML（不走 ParagraphParser 的 inline 降級路徑）、capture 進
`DocumentNode.watermark`。capture-only、無 layout/render 影響 → VR byte-identical。

---

## 紀律

- **#1.a / Strategy C**：capture-only、layout/render 0 變更 → 42 fixture VR byte-identical
  第 32 連（同 Sprint 145-153 capture-only archetype）。
- **#21**：`watermark` optional、無浮水印不掛 key；DocumentNode literal 條件掛入。
- **#14（模組化）**：WatermarkParser 自成 `watermark/` 子目錄、與其他 OOXML part parser 一致。
- **#18 scope-down**：capture-only（render 留 Sprint 173）、第一個 shape、不解析透明度/尺寸。
- **#8 / 決策 C**：synthetic XML 驗 parser（user 同意、tests/fixtures 無 Phase 5 樣本）。

---

## 後續

- **Sprint 173**：浮水印 render wire-up —— CanvasRenderer 每頁繪浮水印（旋轉 + 半透明
  文字 / 圖片）。需 RenderContext 的 save/translate/rotate（已具備）。同 Sprint 171
  background 的 render wire-up 模式（opt-in、Strategy C）。
- Phase 5.6 完整收尾後 → Phase 5.4 追蹤修訂 / 5.5 註解。
- `<w:background>` themeColor→hex 解析、`<v:background>` 圖片背景、framePr Sprint 171
  optional 邊緣項仍待。

---

## Sprint 172 結尾累積指標

- vitest **1434 passed + 1 skipped**（+10）
- VR mean **0.073191**（byte-identical 第 32 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 171 → 172
- 新檔 `watermark/WatermarkParser.ts`、新型別 `DocumentWatermark`
- Phase 5.6「浮水印」capture 完成；render wire-up 留 Sprint 173
