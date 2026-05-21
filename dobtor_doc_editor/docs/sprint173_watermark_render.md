# Sprint 173 — 浮水印 render wire-up（Phase 5.6 浮水印 收尾）

**日期**：2026-05-21
**類型**：render wire-up（Phase 5.6 浮水印 + 背景、Strategy C）
**規畫書對應**：§5 階段 D Phase 5.6「浮水印 + 背景」
**前置**：Sprint 172（浮水印 capture）；決策 C
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Sprint 172 把 header VML 浮水印 capture 進 `DocumentNode.watermark`（capture-only）。
本 sprint 補 render wire-up：CanvasRenderer 每頁繪浮水印，使 Phase 5.6 完整收尾
（背景 parse+render Sprint 171、浮水印 capture Sprint 172、浮水印 render 本 sprint）。

---

## 修法

### 1. `CanvasRenderOptions.watermark?`（+9 行含註解）

`watermark?: DocumentWatermark`。因 watermark 無合理預設值（undefined = 無浮水印）、
不進 `Required<>` defaulting —— `DEFAULTS` 型別改為 `Required<Omit<…, 'watermark'>>`、
class 另以 `private watermark?` 存（constructor `this.watermark = opts.watermark`）。

### 2. `CanvasRenderer.renderWatermark(page)`（+37 行）

`renderPage` 在背景填色後、內文 entries 前呼叫（浮水印在內容之下）：
- 只繪 `kind='text'` 文字浮水印（`kind='image'` 需 shape 尺寸、no-op、留後續）
- 字級反推：以參考字級 100pt 量測文字寬、縮放使文字寬 ≈ 頁寬 70%、上限 130pt
- `save` → `translate`(頁心) → `rotate`(`rotation`° → rad) → `fillText`（x 左推半字寬置中、
  y 加 `fontSize×0.35` 校正基線）→ `restore`
- 色：`WATERMARK_COLOR = 'C8C8C8'` 淺灰（RenderContext 無 alpha、以淺灰近似 Word washout）
- 具名常數：`WATERMARK_COLOR` / `WATERMARK_WIDTH_RATIO` / `WATERMARK_REF_FONT_SIZE` /
  `WATERMARK_MAX_FONT_SIZE`

### 3. VR pipeline entry 端到端接線（+6 行）

`paintPage` 讀 `documentNode.watermark`、有值才傳 `{ watermark }` 給 CanvasRenderer
（與 Sprint 171 `pageBackgroundColor` 同模式、conditional spread 避免 undefined 覆寫）。
→ WatermarkParser → `DocumentNode.watermark` → VR pipeline → CanvasRenderer → 繪 全鏈接通。

### Strategy C（紀律 #1.b）

無浮水印（42 fixture 全數）→ `documentNode.watermark` undefined → `this.watermark`
undefined → `renderWatermark` no-op → 無 save/translate/rotate/fillText → 與 Sprint
0-172 byte-identical。浮水印只對「真有浮水印的 docx」改變輸出。

### Scope-down（紀律 #18）

- **只繪文字浮水印**：`kind='image'` 圖片浮水印需 shape 尺寸 / 長寬比（Sprint 172
  WatermarkParser 未 capture）→ `renderWatermark` 對 image 直接 no-op、留後續
  （需先擴 WatermarkParser capture shape style 的 width/height）。
- RenderContext 無 alpha → 浮水印以淺灰近似、非真半透明。
- 字級反推為估算（EstimateMetrics），非 Word 精確 textpath 縮放。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1434 → 1439 passed + 1 skipped**（+5 CanvasRenderer 浮水印）。涵蓋無 watermark → 無 save/translate/rotate（byte-identical）/ 文字浮水印 → save+translate+rotate+fillText+restore / 浮水印繪於內文之前 / rotation 未設不送 rotate / 圖片浮水印 no-op |
| **L2 VR v14** | VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 33 連）。42 fixture 全無浮水印 → renderWatermark no-op → 驗證 Strategy C |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.6 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 不重建：Sprint 173 只改 CanvasRenderer（非 frontend bundle 依賴樹）
  + VR pipeline entry；OoxmlParser 未動 → 同 Sprint 167/170。
- flake8：不適用（0 行 Python）。

---

## Root cause

Sprint 172 capture 浮水印但無 render consumer。本 sprint 接通 render：CanvasRenderer
以 `watermark` 選項消費、每頁 `renderWatermark` 繪旋轉淺灰文字。複用 RenderContext
Sprint 34 既有的 `save/translate/rotate`（原為垂直文字 cell 設計）—— 浮水印的旋轉繪製
與垂直文字同構（紀律 #14）。Strategy C 保 byte-identical：無浮水印 → no-op。

Phase 5.6「浮水印 + 背景」三 sprint 收尾：背景 parse+render（171）、浮水印 capture
（172）、浮水印 render（173）。

---

## 紀律

- **#1.b / Strategy C**：`watermark` opt-in、無浮水印 → renderWatermark no-op →
  byte-identical by construction。第 33 連。
- **#1.a**：改 render 路徑跑全 42 fixture VR。
- **#14（DRY）**：旋轉繪製複用 RenderContext save/translate/rotate（Sprint 34 垂直文字
  既有 API）、不另造旋轉機制。
- **#2**：4 個浮水印參數具名常數。
- **#18 scope-down**：圖片浮水印 render no-op（需 shape 尺寸）、淺灰近似半透明、
  字級估算 —— 皆 honest declare。

---

## 後續

- **圖片浮水印 render**：需先擴 WatermarkParser capture `<v:shape>` style 的 width/height
  + `<v:imagedata>` 的長寬比，renderWatermark 才能正確置中縮放繪圖。
- **Phase 5.4 追蹤修訂**（`<w:ins>` / `<w:del>`）、**Phase 5.5 註解**
  （`<w:commentRangeStart>`）—— 決策 C 可控部分剩餘項。
- `<w:background>` themeColor→hex 解析、framePr Sprint 171 optional 邊緣項仍待。

---

## Sprint 173 結尾累積指標

- vitest **1439 passed + 1 skipped**（+5）
- VR mean **0.073191**（byte-identical 第 33 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 172 → 173
- **Phase 5.6「浮水印 + 背景」收尾**（背景 parse+render / 浮水印 capture+render；
  圖片浮水印 render 留後續）
