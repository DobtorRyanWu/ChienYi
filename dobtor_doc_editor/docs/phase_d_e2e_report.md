# Phase D — End-to-End 整合報告

**完成日期**：2026-05-05
**範圍**：Sprint 2-3 加速：DocumentNode → canvas-editor IElement[] mapper、HarfBuzz WASM 整合驗證、字型度量 pipeline、第一份 fixture 端到端 mapper 整合測試

## 已交付

### D.1 — ToCanvasEditor mapper

新檔：[`static/src/core/ooxml/mapper/ToCanvasEditor.ts`](../static/src/core/ooxml/mapper/ToCanvasEditor.ts)

把 `DocumentNode`（OoxmlParser 輸出）轉為 `@hufe921/canvas-editor` 的 IElement[] 扁平陣列。涵蓋：

- Run 文字逐字拆 + RunProps 樣式套用（font / size / bold / italic / underline / strike / color / highlight）
- 段落對齊（rowFlex）+ 段距（rowMargin）+ 段落終止符 `\n`
- Break：line / page / column → `\n` / pageBreak
- Field：用 cachedValue（fldSimple 預先快取的字面值）
- InlineImage / FloatImage：rId 透過 media map 解析成 dataURL → type=image
- Hyperlink：type=hyperlink + url + valueList
- Table：colgroup + trList + tdList（gridSpan→colspan、anchor.rowSpan→rowspan、isContinuation cell 跳過）
- Section：多 section 之間插 pageBreak

**測試**：[`tests/unit/ToCanvasEditor.test.ts`](../tests/unit/ToCanvasEditor.test.ts) — 20 個單測涵蓋上述所有路徑。

### D.2 — HarfBuzz WASM + Font Metrics Pipeline

新檔：
- [`static/src/core/ooxml/font/ShapingEngine.ts`](../static/src/core/ooxml/font/ShapingEngine.ts)
- [`static/src/core/ooxml/font/FontMetrics.ts`](../static/src/core/ooxml/font/FontMetrics.ts)
- [`static/src/core/ooxml/font/index.ts`](../static/src/core/ooxml/font/index.ts)

#### HarfBuzz WASM Spike — **整合可行（5/5 tests pass）**

**結論**：harfbuzzjs WASM 在 Node 18+/20 + vitest 環境**完全可用**。

**關鍵踩坑**：直接 `await import('harfbuzzjs')` 會 throw `Method Promise.prototype.then called on incompatible receiver [object Module]`（vitest ESM/CJS 互通缺陷）。**解法**：用 `createRequire(import.meta.url)` 取 CJS module.exports 直接 await。詳見 ADR-009。

**Spike 驗證 4 條 path 全綠**：
1. ✅ harfbuzzjs 模組載入並回傳 hb instance（含 createBlob/createFace/createFont/shape）
2. ✅ 載入 TTF 字型 byte buffer → blob → face → font
3. ✅ shape "Hello" 產 5 個 glyph，每個 advance > 0
4. ✅ shape 中英混排（Hello 世界）不 throw（中文字未支援會產 .notdef glyph 0）

#### ShapingEngine — 簡易封裝

提供 API：
```ts
const engine = new ShapingEngine();
engine.loadFont('Times New Roman', fontBytes);
const glyphs = await engine.shape('Hello world', 'Times New Roman', 12);
// → ShapedGlyph[] 含 { glyphId, xAdvance, yAdvance, xOffset, yOffset, cluster }
```

#### FontMetrics — opentype.js 純 JS metrics

不需 WASM 即可讀字型 unitsPerEm / ascender / descender / lineGap。即使 HarfBuzz 整合失敗，metrics-only 路徑仍可用。

```ts
const metrics = readFontMetrics(fontBytes);
const lh = lineHeightPt(metrics, 12); // (asc + desc + gap) * 12 / unitsPerEm
```

**測試**：[`tests/unit/HarfBuzzSpike.test.ts`](../tests/unit/HarfBuzzSpike.test.ts) (5) + [`tests/unit/Font.test.ts`](../tests/unit/Font.test.ts) (8) = **13 tests**。

#### 為何 ShapingEngine **不接到 OoxmlParser 主流程**

1. **Bundle 體積**：harfbuzzjs WASM ~200KB；接到主 bundle 會大幅 inflate
2. **canvas-editor 不接受外部 metrics**：它 Renderer 內部用 Browser `ctx.measureText()`，要接 HarfBuzz 必須 fork 整個 Renderer pipeline → 屬於 Phase 6+ 工作
3. **預備 Phase 6 自寫 Layout Engine**：當該 Phase 啟動時，ShapingEngine + FontMetrics 已就緒可直接使用

font/ 模組**不從** [`static/src/core/ooxml/index.ts`](../static/src/core/ooxml/index.ts) 重新匯出，rollup tree-shaking 確保它們不進主 bundle。

### D.3 — fixture 端到端 mapper 整合測試

新檔：[`tests/integration/03_e2e_mapper.test.ts`](../tests/integration/03_e2e_mapper.test.ts)

對所有 41 份 fixture .docx 跑：
```
.docx → OoxmlParser.parse() → ToCanvasEditor.convert() → IElement[]
```

**驗收**：
- ✅ 41/41 fixture 不 throw、輸出非空 IElement[]
- ✅ 每份 fixture 至少有一個段落終止符 `\n`
- ✅ 監造會議記錄 fixture 含中文字元（監造/會議/出席/工程；內容多在表格 cell 內，需遞迴 flattenText）
- ✅ 02_std_table 週報含 type=table IElement
- ✅ 03_complex_table/送審管制.docx：colgroup ≥ 14 欄
- ✅ 04_with_image 含 type=image，每張 width/height/dataURL 正確

新增 47 個整合測試。

### Node CLI Tool（Phase E 預備）

新檔：[`tools/parse_docx_cli.ts`](../tools/parse_docx_cli.ts)

```bash
node parse_docx_cli.js <input.docx> <output.json> [--ast | --elements]
```

- `--elements`（預設）：輸出 IElement[]（給 canvas-editor 初始化）
- `--ast`：輸出完整 DocumentNode JSON（除錯/檢查）

**Phase E 用途**：Python `doc_controller.py` 將以 `subprocess.run(['node', cli_path, ...])` 呼叫此 CLI 取 JSON，給前端 `doc_editor.js` 元件初始化。

## 不在此交付（明確 deferred）

| 規劃任務 | 狀態 | Defer 原因 |
|---|---|---|
| pixelmatch vs LibreOffice golden PNG | ❌ | 需 puppeteer + canvas-editor headless 渲染環境；屬 §6.2 Visual Regression Pipeline |
| ShapingEngine 接入 OoxmlParser 主流程 | ❌ | canvas-editor Renderer 內部用 measureText，接 HarfBuzz 需 fork 該 Renderer → Phase 6+ |
| CJK fallback 鏈（FontFallback / CJKFallback / GlyphCache） | ❌ | 沒有 Layout Engine 消費端，先做不到「使用」階段 |
| 巢狀表格 cell.content（BlockNode[]） | ❌ | AST 設計仍限 ParagraphNode[]；ADR-008.2 已標 |
| 段內 sectPr 的 pgSz / pgMar 切換 | ⚠️ 部分 | walkBodyAsSections 已切 section，但 SectionParser 套到對應 section 已就緒 |

## 量化指標

| 維度 | Phase B 結束 | Phase D 結束 |
|---|---|---|
| 測試數量 | 183 | **284** |
| Bundle 體積（IElement mapper 加入後） | 126KB | **151KB** |
| 模組數量 | 9 (parser) | 9 + 1 (mapper) + 2 (font) = **12** |
| node_modules 新增依賴 | — | harfbuzzjs / opentype.js / @types/node |
| Fixture 端到端通過 | 41/41 不 throw（解析） | 41/41 不 throw（解析+mapper） |

## 接下來（Phase E）

Backend 並行通道：
1. `doc_controller.py` 加 `?engine=ts|libreoffice` query param
2. `engine=ts` 路徑：subprocess 呼叫 `parse_docx_cli.ts` → 取 IElement[] JSON → 餵給前端 `doc_editor.js`
3. `engine=libreoffice` 維持原 LibreOffice fallback（無 regression 風險）
4. Audit log 比對兩條路徑輸出，方便 chichi 評估 TS 路徑成熟度

進入 Phase E 前的關卡：本 Phase D 全套通過 ✅，可開始。
