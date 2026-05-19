# Sprint 9 BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾

**狀態**：W11+ 主線 Sprint 9 — Renderer 真實畫面 / 還原度核心
**完成日期**：2026-05-07
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.6 Phase 5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint8_renderer_fontmetrics.md](sprint8_renderer_fontmetrics.md)

---

## 1. 範圍

Sprint 8 把 Renderer 起步骨架建好（介面 + Mock + flat-lines CanvasRenderer）；Sprint 9 是 Phase 5 真實還原度核心：

1. **A. BrowserCanvasRenderContext**：把 `RenderContext` 接到瀏覽器 `CanvasRenderingContext2D`
   - pt → px scale（預設 96/72）
   - color hex → CSS string、font 字級 × scale → CSS px
   - imageResolver 注入點
   - clearRect / onPageEnd hook
2. **B. cell.blocks 視覺順序**：CanvasRenderer 從 flat `cell.lines` 升級為走訪 `cell.blocks`，正確處理 paragraph + 巢狀表格混排
3. **C. Cell shading + paragraph shading**：`fillRect` 在內容前送出
4. **D. 文字裝飾**：highlight（box 背景）+ underline（baseline 下方 drawLine，含 double）+ strike（fontSize × 0.3 上方 drawLine）

落地：

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/layout/types.ts` | M | `CellLayout.shading?` |
| `static/src/core/layout/TableLayout.ts` | M | `layoutCell` 透傳 `cell.props.shading`（含 vMerge continuation） |
| `static/src/core/render/types.ts` | M | `RenderTextStyle` 加 `underline` / `strike` / `highlight` |
| `static/src/core/render/CanvasRenderer.ts` | **重寫** | `renderCell` 用 `cell.blocks` + `renderRows` 共用給巢狀；shading + decoration 四類繪製 |
| `static/src/core/render/BrowserCanvasRenderContext.ts` | A | 包裹 `BrowserCanvas2D`；toCssColor / toCssFont 公開 |
| `static/src/core/render/index.ts` | M | export Browser context + 工具 |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/render/BrowserCanvasRenderContext.test.ts`（新檔） | 23 | toCssColor / toCssFont / scale / fillRect / drawLine / fillText / drawImage / clearRect / onPageEnd |
| `tests/unit/render/Sprint9.test.ts`（新檔） | 15 | shading 透傳 / cell.blocks 順序 / cell+paragraph shading / highlight / underline / strike / 整合 |

**全套**：vitest 37 files / **589 tests pass**（Sprint 8 後 35/551 → 37/589，+2 files +38 case）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 BrowserCanvasRenderContext — 為何抽 `BrowserCanvas2D` interface？

直接用 `lib.dom.d.ts` 的 `CanvasRenderingContext2D` 會在 vitest Node 環境吃 `window`/`document` 依賴；想避開 jsdom 的話，自己宣告 Canvas2D 子集介面就能：
- vitest Node 環境直接 `makeMockCanvas()` 測試
- 瀏覽器端：`document.querySelector('canvas').getContext('2d')` 結構天然符合 `BrowserCanvas2D`
- 未來 OffscreenCanvas / node-canvas 也能匿名實作此介面

只暴露 12 個 method + 6 個 property（fillStyle / strokeStyle / lineWidth / font / textBaseline / textAlign），夠 Renderer 用。

### 2.2 pt → px 換算

OOXML / Layout 全用 pt；Canvas API 全用 px。`BrowserCanvasRenderContext.scale` 預設 `96/72 ≈ 1.333`（web 標準 96dpi）。

**fontSize 雙重 scale 陷阱**：座標 scale 後字級也要 scale，否則「100pt 的位置」與「12px 的字」對不上。`toCssFont(style, scale)` 把 fontSize × scale 才轉 CSS px：

```ts
toCssFont({ fontSize: 12 }, 96/72)
// → "16.00px sans-serif"
```

`fillText` 內部呼叫 `toCssFont(style, this.scale)` 統一處理。

### 2.3 cell.blocks 視覺順序 — 為何 Sprint 9 才換？

Sprint 6 已建好 `CellLayout.blocks`（ordered list），但 Sprint 8 Renderer 為求速成用 flat `cell.lines`。fixture 裡只有少數有「paragraph + 巢狀表 + paragraph」的混排，先跑通主流程再修正巢狀視覺順序。

Sprint 9 升級後 `renderCell`：
```
Pass 1: cell shading 全 cell fillRect（背景）
Pass 2: 走訪 cell.blocks
   ├─ block.kind='lines'：每 line paragraph shading + line 內 boxes
   └─ block.kind='table'：renderNestedTable(t.rows) 遞迴
Pass 3: cell 4 邊邊框 drawLine（最上層避免被 shading 蓋）
```

`renderRows` 抽公共方法給「頂層 table」與「巢狀 table」共用，避免複製貼上。

### 2.4 highlight / underline / strike 座標

| 裝飾 | 座標 |
|---|---|
| highlight | `(boxX, baseline - fontSize × 0.85, boxWidth, lineHeight)` 矩形 |
| underline | `y = baseline + fontSize × 0.15` 水平線 |
| underline=double | 第 2 條 `y = underline.y + fontSize × 0.1` |
| strike | `y = baseline - fontSize × 0.3`（約 x-height 中點） |

裝飾線寬統一 `0.5pt`（Word 預設約 0.75pt，取近似）。雙線 / 浪線等高階 `underline` value 仍只當實線畫；waveline 留 Sprint 10。

### 2.5 三層渲染順序：shading → text → borders

Cell 內：
1. **背景層**：cell.shading + paragraph.shading + run.highlight（fillRect）
2. **文字層**：fillText
3. **裝飾層**：underline / strike（drawLine）
4. **邊框層**：cell 4 邊（drawLine）— 最後畫避免被 shading 覆蓋

Renderer Pass 1/2/3 拆分清楚就不會出錯。

### 2.6 為何測試不用 jsdom？

Mock `BrowserCanvas2D` 用 getter/setter 紀錄屬性、用閉包紀錄方法呼叫；vitest 直接斷言 ops 序列即可。優點：
- 測試啟動 < 50ms（jsdom + node-canvas 動輒 1-2 秒）
- CI 不用裝 native dependency（cairo / pango）
- 純 TS / vitest，跨 OS 一致

代價：實際瀏覽器端字體 metrics 看不出來。Sprint 10 計劃在 puppeteer / Playwright 環境跑 visual regression。

---

## 3. fixture 影響

Sprint 9 是 Renderer 端升級，Layout output 完全不變 → fixture avgPages 與 Sprint 7-8 一致：

| 類別 | Sprint 8 avgPages | Sprint 9 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.1 | 1.1 |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 2.3 | 2.3 |

CanvasRenderer ops 數量會因 cell shading / decoration 增加，但 Layout 不影響。

---

## 4. Sprint 9 已知限制

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| HarfBuzz async batch shape | 工程量大；measureWidth 仍 estimate | Sprint 10 Phase 2 |
| wrapTight / wrapThrough polygon | 仍降級 square | Sprint 10+ §3.4 |
| Knuth-Plass 精細斷行 | 仍貪婪 | Sprint 10+ §3.1 |
| 註腳 / 尾註 | Paginator 沒概念 | Sprint 10+ §3.6 |
| Float image + multi-column 同用 | activeFloat 不依 columnIndex 區分 | Sprint 10+ |
| Column balancing | 仍 first-fit | Sprint 10+ §3.5 |
| 邊框衝突 vMerge anchor / gridSpan corner 高階 | 簡化版 | Sprint 10+ §3.3 |
| 巢狀表跨頁切（內含 nested table 切兩半） | 仍整張上下移 | Sprint 10+ §3.3 |
| **Renderer 端**：Visual regression（瀏覽器渲染像素級驗證） | Mock 環境跑不出像素 | Sprint 10 Playwright |
| **Renderer 端**：waveline / 雙線 / dashed 高階 underline | 一律當實線 | Sprint 10+ |
| **Renderer 端**：textDirection ≠ lrTb | 忽略 | Sprint 10+ |
| **Renderer 端**：文字旋轉 / shadow / outline | 忽略 | Sprint 10+ |
| **Renderer 端**：欄分隔線（multi-column 中間 vertical line） | 沒畫 | Sprint 10 |
| **Renderer 端**：頁碼 / page number 欄位 | 仍是 PAGE 字串 | Sprint 10 |

---

## 5. 對 Sprint 1-8 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無（CellLayout.shading 是 optional 新欄位） | 48 case 全綠 |
| Sprint 2-8 unit tests | 無 | 全綠 |
| Sprint 8 CanvasRenderer.test.ts（13 case） | 無破壞性改動：blocks / shading / decoration 由 default options 開啟，舊測試不關心這些 ops | 13 case 全綠 |
| Python integration（54 case） | 無 | 全綠 |

**vitest 全套**：37 files / **589 tests pass**（Sprint 8 後 35/551 → 37/589，新增 38 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（35 → 37 files；551 → 589 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 9 兩檔
npx vitest run tests/unit/render/BrowserCanvasRenderContext.test.ts \
              tests/unit/render/Sprint9.test.ts

# 跑 Renderer 全套
npx vitest run tests/unit/render/

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 10）建議

Layout / Renderer 已大致 complete-able；Sprint 10 從還原度精度收尾：

1. **Visual regression（Playwright）** — 在真瀏覽器跑 BrowserCanvasRenderContext，截圖 vs golden PNG（已有 251 份 fixture）
2. **HarfBuzz async batch shape** — BoxBuilder 改 async pre-shape，replaces estimate width；行高 + advance 都接真實 metrics
3. **Knuth-Plass 精細斷行** — `LayoutItem` model 已用 K-P 結構；換 algorithm 即可
4. **wrapTight polygon** — drawing.xml 的 polygon path 解析 + LineBreaker per-y lineWidth
5. **欄分隔線 + page number 真值** — 多欄中間 vertical separator + PAGE 欄位實際值

**建議優先順序**：1（驗證 Sprint 8-9 是否還原）→ 5（小但 demo 加分）→ 2（精度核心）→ 3, 4（高階優化）

---

**附註**：Sprint 1-9 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2：基礎 Layout Engine
- Sprint 3：cell-level 表格 + 跨頁
- Sprint 4：Section break / Float image / Widow-orphan
- Sprint 5：巢狀表格 + Multi-column
- Sprint 6：wrapSquare per-y + 不等寬欄 + Cell blocks ordered
- Sprint 7：Column break + 巢狀樣式 + Cell mid-row break
- Sprint 8：Renderer 起步（介面 + Mock + CanvasRenderer flat lines）+ FontMetricsAdapter + CellLayout.borders 透傳
- **Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾（highlight / underline / strike）**

到 Sprint 9，Renderer 已能在瀏覽器產出帶 cell shading / 巢狀表 / underline / strike / highlight 的真實畫面。Sprint 10 起進入 Visual Regression + HarfBuzz 收尾階段。
