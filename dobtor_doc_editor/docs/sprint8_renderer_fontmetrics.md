# Sprint 8 Renderer 起步 + FontMetricsAdapter + 邊框衝突收尾

**狀態**：W11+ 主線 Sprint 8 — 轉 Renderer / Phase 2 (HarfBuzz) / Phase 4 (邊框衝突)
**完成日期**：2026-05-07
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.6 Phase 5 / Phase 2 / §3.3](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint7_midrow_colbreak_nested_style.md](sprint7_midrow_colbreak_nested_style.md)

---

## 1. 範圍

Sprint 7 完成 Layout Engine 主軸（Phase 3.2-3.5）後，Sprint 8 起點轉到三條主線：

1. **Phase 5 Renderer 起步**：建立 `core/render/` 模組，把 `DocumentLayout` 轉為平台無關的繪圖指令
2. **Phase 2 真實字型 metrics 注入 Layout**：用 opentype.js 讀字型 ascender / descender / lineGap 替代 EstimateMetrics 的 1.2 × fontSize
3. **Phase 4 / §3.3 表格邊框衝突收尾**：BorderConflictResolver 已於 Sprint 1-3 階段建好（`TableParser` 內呼叫 `resolveTableBorders`），Sprint 8 的工作是把 resolved borders 透傳到 Layout output（`CellLayout.borders`），讓 Renderer 端能直接消費

落地：

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/layout/types.ts` | M | `CellLayout.borders?: CellBorders` |
| `static/src/core/layout/TableLayout.ts` | M | `layoutCell` 從 `cell.props.borders` 透傳到 `CellLayout.borders`（含 vMerge continuation） |
| `static/src/core/layout/FontMetricsAdapter.ts` | A | 結合 EstimateMetrics（width）+ 真實字型 lineHeight；實作 `TextMetrics` 介面 |
| `static/src/core/layout/index.ts` | M | export `FontMetricsAdapter` |
| `static/src/core/render/types.ts` | A | `RenderContext` 介面（`fillRect` / `drawLine` / `fillText` / `drawImage` + `beginPage` / `endPage`） |
| `static/src/core/render/MockRenderContext.ts` | A | 把指令存陣列；附 `filter<T>()` / `counts()` / `reset()` |
| `static/src/core/render/CanvasRenderer.ts` | A | 走訪 `DocumentLayout` 把每 page entry → RenderContext 指令 |
| `static/src/core/render/index.ts` | A | 公開 API |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/FontMetricsAdapter.test.ts`（新檔） | 9 | 行高真實 / fallback / 大小寫 / registry |
| `tests/unit/render/CanvasRenderer.test.ts`（新檔） | 13 | 頁框架 / 文字行 / 表格 / borders / Mock counts |
| `tests/unit/layout/Sprint8.test.ts`（新檔） | 7 | borders 透傳 + 端到端整合 |

**全套**：vitest 35 files / **551 tests pass**（Sprint 7 後 32/522 → 35/551，新增 29 case）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 Renderer：`RenderContext` 介面而非直接綁 Canvas

**問題**：把 `CanvasRenderingContext2D` 直接灌入 Renderer 會綁死瀏覽器，未來想出 PDF / SVG / 圖片時還要重寫。

**決策**：抽 `RenderContext` 介面，現只實作兩個：
- **MockRenderContext**：op 陣列；vitest 全跑 Node 環境，不需 jsdom / canvas
- **BrowserCanvasRenderContext**：Sprint 9+ 補（需要 canvas-editor 整合策略）

未來再補 PdfKit / OffscreenCanvas / SVG 實作即可。

**API 7 個 method**：
```
beginPage(pageNumber, width, height)
endPage()
fillRect(x, y, w, h, color)
drawLine(x1, y1, x2, y2, style)
fillText(text, x, y, style)
drawImage(href, x, y, w, h)
```

座標單位 pt（與 Layout 一致）；座標系原點 = 頁面左上 (0,0)；`fillText` 座標 = baseline。

### 2.2 CanvasRenderer 對每 Box 各送一次 `fillText`

**Why per-Box not per-Line**：

`Line.items` 內每 Box 各帶 `runProps`（`fontFamily` / `bold` / `italic` / `color` 等）；如果整行串成一個字串送 `fillText`，會丟掉 per-run 樣式。Sprint 8 採 per-Box：

```ts
let cursor = baseX + (line.xOffset ?? 0);
for (const item of line.items) {
  if (item.kind === 'box') {
    ctx.fillText(box.text, cursor, baseY + line.baseline, runStyle);
    cursor += box.width;
  } else if (item.kind === 'glue') {
    cursor += item.width;
  }
}
```

Glue 不送指令，純 advance；penalty 不影響 cursor（width 通常 0）。

### 2.3 CellLayout.borders 透傳路徑

```
TableParser
  → resolveTableBorders(table)（mutate cell.props.borders 為 effective borders）
TableLayout.layoutCell
  → CellLayout.borders = cell.props.borders（淺拷貝）
CanvasRenderer.renderCell
  → drawCellBorders(x, y, w, h, cell.borders)
  → drawLine ×4（top / bottom / left / right）
```

Sprint 8 簡化決策：
- 邊框 `style: 'nil'` 或 `'none'` 不畫（`isVisibleBorder` 過濾）
- 相鄰 cell 邊不去重：cell1.bottom 與 cell2.top 都會送 `drawLine` → 同位置兩條線。理由：`resolveTableBorders` Pass 2 已把兩側調為一致，重畫不會視覺差異；嚴格去重等 Sprint 9 SVG 路徑要解時再做。

### 2.4 FontMetricsAdapter — 行高真實，寬度仍 estimate

**為何分開**：

| 度量 | 真實實作可行性 | Sprint 8 作法 |
|---|---|---|
| `measureLineHeight` | opentype.js 同步讀 OS/2 + hhea，輕量 | ✅ 真實計算 |
| `measureWidth`（per-glyph advance） | HarfBuzz `shape()` 是 async，TextMetrics 介面是 sync；改 sync 需要先 batch shape 整段 | ⏸ 仍走 EstimateMetrics |

行高直接決定整份文件的分頁位置（fixture-level 大幅影響），ROI 最高；寬度估算誤差 ±5% 對分頁影響小，留 Sprint 9+ 真要做時再改 BoxBuilder 為 async pre-shape。

**Adapter 介面**：
```ts
const adapter = new FontMetricsAdapter();
adapter.registerFont('Times New Roman', timesBytes);  // opentype.js 立即 parse + cache
adapter.registerMetrics('SimSun', preparsedMetrics);  // 也接受預解析的 metrics（測試 / metadata-only）
const layout = layoutDocument(sections, { metrics: adapter });
```

未註冊的 family → fallback EstimateMetrics（不 throw、不警告）。Sprint 9 規劃補 warning 收集器讓使用者知道哪些 family 用了估算。

### 2.5 邊框衝突 Sprint 8 的「補完」做了什麼

BorderConflictResolver `resolveCellEdge` / `mergeCellBorders` / `resolveTableBorders` 三組函式在 Sprint 1-3 已建好，TableParser 階段整合，13 個單測都綠。

Sprint 8 的補完工作：

| 工作 | 動機 |
|---|---|
| `CellLayout.borders` 透傳 | 過去 borders 留在 AST `cell.props.borders`，Renderer 必須回頭看 source AST 才拿得到。Sprint 8 把 resolved borders 拷到 Layout 輸出，Renderer 不再依賴 AST |
| Sprint 8 整合測試 | 證明「邊框 → Renderer drawLine」整條鏈，並且粗細邊（外框 2pt + insideH/V 0.5pt）都能正確分別繪出 |

未補完的邊框邊界案例（Sprint 9+）：
- vMerge anchor 的內部 horizontal edge 仍會被 Pass 2 協調（會畫到 anchor 的 mid 位置）
- gridSpan + 跨欄 corner 還沒測完整
- 雙線 / 浪線等高階 style 在 Renderer 端只當 single 畫

---

## 3. 整合 fixture 影響評估

Sprint 8 不改 Layout 演算法（CellLayout.borders 是新增欄位、不影響舊計算）；fixture-level avgPages 與 Sprint 7 一致：

| 類別 | Sprint 7 avgPages | Sprint 8 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.1 | 1.1 |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 2.3 | 2.3 |

FontMetricsAdapter 只在使用者顯式注入並 register 字型時才會改變行高；fixture 預設不 register 字型 → fallback estimate，分頁與 Sprint 7 完全一致。**這是刻意設計**：Sprint 8 不應改變既有 fixture 行為，只開新能力。

---

## 4. Sprint 8 已知限制（→ Sprint 9+ 補完）

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| `measureWidth` 仍走 estimate | HarfBuzz shape async、改造工程量大 | Sprint 9：BoxBuilder 預先 batch shape |
| Browser Canvas / PDF Context 實作未做 | Sprint 8 只做 Mock + 介面 | Sprint 9：BrowserCanvasRenderContext |
| 巢狀表格內部繪製 | Renderer 只跑 cell.lines flat list | Sprint 9：用 `cell.blocks` 走訪維持視覺順序 |
| 相鄰 cell 邊重畫 | drawLine ×4 per cell；同位置兩條 | Sprint 9：SVG 路徑時做 dedupe |
| 雙線 / 浪線 style | RenderContext.style.style 透傳；Mock/Browser 端詮釋 | Sprint 9 BrowserCanvas 補 |
| 段落 borders / shading | Renderer 不畫（Line.paragraphProps 含但跳過） | Sprint 9 |
| 底線 / 刪除線 | RenderTextStyle.underline/strike 透傳；Mock 不繪 | Sprint 9 BrowserCanvas |
| HarfBuzz 真實 shape advance | 工程量大 | Sprint 9-10 |
| 邊框衝突高階邊界（vMerge / gridSpan corner） | Pass 2 簡化版 | Sprint 9+ §3.3 補 |
| 表格 cell shading（背景色） | RenderContext.fillRect 已有 API；Renderer 還沒呼叫 | Sprint 9 |
| 圖片真實資料載入 | RenderContext.drawImage 只收 href（rId）；解析待 Context 端 | Sprint 9 BrowserCanvas |

---

## 5. 對 Sprint 1-7 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無（CellLayout 是 Layout 輸出，不影響 AST snapshot） | 42 case 全綠 |
| `05_parser_audit.test.ts`（Sprint 1） | 無 | 8 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無（CellLayout.borders 是新增欄位、optional） | 48 case 全綠 |
| `BorderConflictResolver.test.ts`（既有） | 無 | 13 case 全綠 |
| `Font.test.ts`（既有，opentype.js spike） | 無 | 8 case 全綠 |
| `HarfBuzzSpike.test.ts`（既有） | 無 | 5 case 全綠 |
| Sprint 2-7 unit tests | 無 | 全綠 |
| Python integration（54 case） | 無 | 全綠 |

**vitest 全套**：35 files / **551 tests pass**（Sprint 7 後 32/522 → 35/551，新增 29 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（32 → 35 files；522 → 551 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 8 三檔
npx vitest run tests/unit/layout/Sprint8.test.ts \
              tests/unit/render/CanvasRenderer.test.ts \
              tests/unit/layout/FontMetricsAdapter.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 9）建議

依 Sprint 7 audit 留下的 priority order「1 → 2 → 5 → 3, 4」：

1. ✅ Sprint 8 已做：邊框衝突收尾（CellLayout.borders 透傳）+ Phase 2 行高 + Renderer 起步（介面 + Mock）
2. **Sprint 9 候選**：
   - **A. BrowserCanvasRenderContext** — 把 RenderContext 接到瀏覽器 `<canvas>` / OffscreenCanvas，能在 Odoo Web Client 看到真實畫面（§5.6 Phase 5 第二階段）
   - **B. cell.blocks 視覺順序繪製** — 把 Renderer 從 flat `cell.lines` 升級為走訪 `cell.blocks` 保留 paragraph + 巢狀表格交錯順序
   - **C. Cell shading / 段落 shading** — RenderContext.fillRect 已有 API，補上 cell/paragraph 背景色
   - **D. HarfBuzz async batch shape** — 真正實作 `measureWidth` 用 advance；改 BoxBuilder 為 async pre-shape

**建議優先順序**：A → B → C → D
- A 最快讓使用者看到「真的畫出來了」（demo-able milestone）
- B 解決巢狀表 cross-page 的剩餘視覺順序問題
- C 還原度核心
- D 工程量大但精度提升小，留最後

---

**附註**：Sprint 1-8 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2：基礎 Layout Engine（Box/Glue/Penalty + 貪婪斷行 + 基礎分頁）
- Sprint 3：cell-level 表格 + 跨頁
- Sprint 4：Section break 全套 + Float image 基礎 + Widow/orphan
- Sprint 5：巢狀表格 + Multi-column
- Sprint 6：wrapSquare per-y + 不等寬欄 + Cell blocks ordered
- Sprint 7：Column break + 巢狀樣式 + Cell mid-row break
- **Sprint 8：Renderer 起步（介面 + Mock + CanvasRenderer）+ FontMetricsAdapter + CellLayout.borders 透傳**

Layout Engine 主軸（Phase 3.2-3.5）+ Phase 4 邊框衝突 已「可被 Renderer 消費的形式」收齊；Sprint 9 起轉 Phase 5 真實 Browser Canvas / PDF 路徑。
