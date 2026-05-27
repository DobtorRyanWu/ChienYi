# Sprint 297 — canvas-editor integration audit ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 純 audit doc / 0 行 code

**日期**：2026-05-27（週三）
**類型**：① follow-up — 純 audit doc，無 production code
**前置**：Sprint 288 LayoutPipeline 整合 façade

User 指令：「繼續執行」① honest gap「LayoutPipeline 未接 canvas-editor（Phase 6 自寫 Layout 完整範圍）」。

---

## 揭發狀態

Sprint 288 鋪了 `LayoutPipeline` façade（ShapingEngine + ShapingFontChain + FontMetrics
+ LineBreaker 整合 entry point）但 honest gap：「未接 canvas-editor / ctx.measureText」。

本 sprint = **pure audit doc**：掃 canvas-editor 結構、揭發整合點、評估方案 + 成本。
**0 行 production code**（紀律 #18 scope-down、紀律 #21 不污染 VR）。

---

## canvas-editor 結構掃描

### 檔案

| 檔案 | 角色 |
|---|---|
| `static/src/lib/canvas_editor/canvas-editor.umd.min.js` | 上游 minified bundle（核心引擎） |
| `static/src/lib/canvas_editor/canvas-editor-plugin-docx.umd.js` | docx import/export plugin |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | 本專案自訂層（ChienYi 擴充）|

### 文字量測流程（從 minified scan）

canvas-editor 內部有 `class bi`（minified 名）負責文字繪製，含：
- `cacheMeasureText: Map`：cache key = `${value}${font}`、value = `ctx.measureText` 結果
- `measureText(ctx, element)`：先查 cache、未命中則 `ctx.measureText(element.value)`
- 回傳屬性：`width, actualBoundingBoxLeft/Right, fontBoundingBoxAscent/Descent`

### 整合挑戰

canvas-editor 用瀏覽器 `CanvasRenderingContext2D.measureText`（純字元 advance、
**不**做 OpenType kerning / ligatures / CJK shaping）；ShapingEngine 用 HarfBuzz
WASM（**有**做 shaping、會跟 Word desktop 一致）。

差異會在以下場景顯現：
- 含 kerning pair 的西文（AV / To / Wo）：HB 寬度略小 → canvas-editor 換行多餘空間
- Arabic / Hebrew / Devanagari 等需 shaping 的腳本：canvas-editor 無 shaping → 亂碼
- 中日韓字寬：通常相近，但 OpenType `palt`/`vpal` proportional metrics 不同
- 帶 `cluster` 的 emoji / 變體字元：HB 正確、canvas-editor 拆字

---

## 整合方案評估

### 方案 A：Proxy ctx.measureText

```typescript
const originalMeasureText = ctx.measureText.bind(ctx);
ctx.measureText = (text) => {
  if (shapingEngine.isFontLoaded(currentFont)) {
    const metrics = shapingEngine.measureRunSync(text, currentFont, currentSize);
    return { ...originalMeasureText(text), width: metrics.widthPt * pxPerPt };
  }
  return originalMeasureText(text);
};
```

**優點**：透明、不改 canvas-editor 內部、relatively 小範圍
**缺點**：
- ShapingEngine.measureRun 是 **async**（HarfBuzz WASM）→ 不能塞同步 measureText
  - 需先 batch pre-warm shape cache、再走 sync lookup（Sprint 266 ShapingGlyphCache 鋪了基礎）
- `current font` 需從 `ctx.font` 字串解析（"12pt 'Noto Sans'" → size + family）— 易出錯
- canvas-editor 內部 cacheMeasureText 已 cache、proxy 後雙層 cache 浪費

**成本估計**：2-3 sprint

### 方案 B：取代 canvas-editor 的 measureText 函式

修補 minified bundle 直接是壞主意（升級會丟失）；改 source / fork canvas-editor
拿到原始碼後改 `class bi.measureText` → 接 ShapingEngine。

**優點**：精度最高、cache 整合最乾淨
**缺點**：
- canvas-editor 上游升級會破 fork
- 需熟悉 canvas-editor 原始 source（不是 minified bundle）
- 整合進 Odoo build pipeline 複雜

**成本估計**：5-8 sprint（含 maintenance overhead）

### 方案 C：旁路 — 自寫 Layout 完全取代 canvas-editor 文字段

把 ChienYi 監造文件用「自寫 Layout」渲染（PDF export / 自有 viewer）、編輯
保留 canvas-editor（編輯時用 browser measureText 沒問題、保存後用自寫 Layout
重新 render PDF）。

**優點**：
- 兩端各自最佳化、不互相干擾
- LayoutPipeline 用於 export 路徑（高保真）、canvas-editor 用於編輯 UX
- 與 Sprint 269/275 「production canvas-editor 未整合、Phase 6 自寫 Layout 時消費」精神相符

**缺點**：
- 編輯時 vs export 文件視覺差異（可接受、user 已知 trade-off）
- 需建自寫 Layout 的完整 paginator + 表格 + 圖片 + 樣式（巨大、Phase 6 範圍）

**成本估計**：Phase 6 全程（10+ sprint）

### 方案 D：兩者共存、不接

維持現狀：canvas-editor 用於 UI 編輯、LayoutPipeline 為 SDK 可被 export pipeline
或外部 PDF 工具消費，但**不**接到 canvas-editor。

**優點**：
- 0 成本、0 風險
- LayoutPipeline 仍有價值（給 SDK consumer / future Phase 6 用）
- 符合 Sprint 269 「Phase 2 API ready 銜接 Phase 6 自寫 Layout」精神

**缺點**：
- canvas-editor 內顯示與最終 export 不一致（如果有自寫 export 的話）
- 用戶 perception：「為何字距不對」（除非自寫 export pipeline 也跑 canvas-editor 同樣的 measureText）

**成本估計**：0 sprint

---

## 推薦

**方案 D（共存、不接）+ 未來方案 C 自寫 Layout for export**：

理由：
1. canvas-editor 編輯 UX 已穩定、13 Playwright E2E 過關（紀律 #21 不污染）
2. LayoutPipeline 是給 Phase 6 自寫 Layout 用的 API contract、Sprint 288 已驗證
3. 方案 A proxy 的 async/sync mismatch 是技術 trap、易出 race condition
4. 方案 B fork canvas-editor 維護成本高、不符 ROI
5. 對 ChienYi 監造文件實際需求：編輯時略有字距差異是 acceptable trade-off

---

## honest gap 留存項

未來若決定推進 Phase 6 自寫 Layout（方案 C），需先補：
1. PaginatorEngine：頁面斷裂 + section break + page header/footer
2. TableLayoutEngine：複雜表格 + cell vmerge / hmerge
3. ImageWrapEngine：浮動圖片 wrap（用 Sprint 296 polygon math）
4. PdfRendererBackend：自寫 Layout → PDF（不依賴 canvas-editor）
5. CanvasRendererBackend：自寫 Layout → Canvas（與 canvas-editor 視覺一致）

每項 3-5 sprint、合計 15-25 sprint。屬於下個大 milestone（Phase 6 真正啟動）範圍。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b 純 audit doc：0 行 code | ✅ |
| #14.b clean scope：commit 含 1 doc + snapshot 更新 | ✅ |
| #18 scope-down：不啟動 canvas-editor 整合（推薦方案 D）；honest 揭露 4 種方案 + ROI | ✅ |
| #21 不污染：完全 read-only audit、不動 production / VR / E2E | ✅ |
| #22 honest 報告：4 種方案各列優缺點 + 成本估計（Sprint 數）+ 推薦 + 未來路徑 | ✅ |

---

## End of Sprint 297

「繼續執行」honest gap 5 項全收口：

| Sprint | Honest gap | Strategy | +tests |
|---|---|---|---|
| 293 | ④a pPrChange + rPrChange + cellIns/Del/Merge | C+ capture-only | +14 |
| 294 | ⑥ NodeWorkerThreadDispatcher 真實實作 | A spike | +9 |
| 295 | ⑤ alignment guide visual indicator | C+ utility extraction | +12 |
| 296 | ③ wrapPolygon layout math | C+ utility extraction | +18 |
| **297** | **① canvas-editor integration audit** | **pure audit doc** | **0** |
| **合計** | **5 sprint** | | **+53 tests** |

vitest 2228（Sprint 292 結尾）→ 2281 hypothesis（Sprint 297 結尾 = Sprint 296 +18 / Sprint 297 不增）/ tsc 2 pre-existing 不增 / VR 第 68 連 maintained / 零 regression。

**STOP for user review**。
