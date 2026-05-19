# Sprint 10 欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke

**狀態**：W11+ 主線 Sprint 10 — Renderer 端真實還原小步收尾
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.6 Phase 5 / §3.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint9_browser_canvas_blocks_decoration.md](sprint9_browser_canvas_blocks_decoration.md)

---

## 1. 範圍

Sprint 9 完成 BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾後，Sprint 10 收尾三項：

1. **A. 欄分隔線（OOXML `<w:cols w:sep="true"/>`）**
   - SectionParser 解析 `w:sep` 屬性 → `SectionNode.columns.separator`
   - Paginator 在 multi-column 頁面填入 `Page.columnLayout`（含 startX / widths / separator）
   - CanvasRenderer 在 `separator=true` 時於相鄰欄之間 colSpace 中央畫垂直 drawLine
2. **B. PAGE / NUMPAGES 欄位真值回填**
   - `Box.fieldType` 標記
   - BoxBuilder 把 `FieldNode` 轉為單一不可拆 Box，記錄 fieldType + placeholder text（`##`）
   - Paginator 排版完所有頁後 post-pass，把 `fieldType='PAGE'` 的 Box.text 換為所屬 `page.pageNumber`，`'NUMPAGES'` 換為 `pages.length`
   - 範圍：line entry 內 Box + table cell 內 lines + 巢狀表 cell 內（深層遞迴）
3. **C. 全 fixture Render smoke 整合測試**
   - `tests/integration/07_render_smoke.test.ts`：42 fixture 各跑 Layout → Renderer，斷言 `beginPage/endPage` 對稱、`fillText >= 1`、表格類 fixture 至少 50% 有 `drawLine`，並輸出每類 fixture 的 Renderer ops 平均到 console（debug 觀察）

落地：

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | M | `SectionNode.columns.separator?` |
| `static/src/core/ooxml/section/SectionParser.ts` | M | `parseColumns` 讀 `w:sep` 屬性 |
| `static/src/core/layout/types.ts` | M | `Page.columnLayout?` + `Box.fieldType?` |
| `static/src/core/layout/Paginator.ts` | M | `PaginateContext.columnSeparator`、`flushPage` 補 `columnLayout`、`buildColumnLayout`、`resolvePageNumberFields` post-pass |
| `static/src/core/layout/BoxBuilder.ts` | M | FieldNode 改為單一 tagged Box；新增 `defaultFieldPlaceholder` |
| `static/src/core/render/CanvasRenderer.ts` | M | `renderColumnSeparators` 畫多欄垂直線 |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/Sprint10.test.ts`（新檔） | 10 | columnLayout / separator 解析 / Renderer drawLine / PAGE / NUMPAGES / 多頁 |
| `tests/integration/07_render_smoke.test.ts`（新檔） | 44 | 42 fixture 整體 + 表格邊框統計 + ops 統計輸出 |

**全套**：vitest 39 files / **643 tests pass**（Sprint 9 後 37/589 → 39/643，+2 files +54 case）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 為何 `Page.columnLayout` 而非 Renderer 自行算？

每頁的 columnLayout 來自 PaginateContext 當時狀態（多欄不等寬 / 不等距時尤其重要）；Renderer 拿 Page 看不到 PaginateContext，自己 reconstruct 等於 layout 邏輯複製一份。

把資訊帶在 `Page` 上（單欄頁 undefined）是最小副作用的做法：
- 不影響 Sprint 2-9 既有 fixture（單欄頁 `columnLayout=undefined`）
- Renderer 端取資訊很直接：`if (page.columnLayout?.separator) drawSeparators()`
- 未來 PDF / SVG renderer 也能直接消費

### 2.2 PAGE / NUMPAGES 為何 post-pass 而非 inline？

Paginator 跑單一線性 pass，「當前頁碼」可知，但「總頁數」必須等所有頁排完才知道。所以 NUMPAGES 必然是 post-pass。

選擇把 PAGE 也放 post-pass 是因為：
- 一致性（兩種欄位同樣處理流程）
- 避免在 layParagraph 裡傳 ctx.pageNumber 進 BoxBuilder（會把 layout 邏輯滲進 builder）

代價：placeholder 寬度與真實值寬度有差距。Sprint 10 用 `##` 固定 placeholder（estimate 寬度 ≈ 13pt），實際 page number 大多 1-3 位數，誤差肉眼看不出來。Word 也用類似策略（field 寬度先估、後校正）。

### 2.3 Box.fieldType vs Box.text 比對

備案是「post-pass 用 box.text 是否 = `'{PAGE}'` / `'{NUMPAGES}'` 來決定要不要回填」，但這對「使用者 cachedValue 已存好真值」的情境會誤改：
- W:fldSimple `<w:fldSimple w:instr=" PAGE "><w:r><w:t>5</w:t></w:r></w:fldSimple>` 內已有 cachedValue=5
- post-pass 看到 box.text='5' 不知道是 cachedValue 還是 placeholder

加 `fieldType` 標記（包含 cachedValue 也是 'PAGE'）讓 post-pass 永遠覆寫，這符合 Word 的「重排版時 PAGE 一定刷新」行為。

### 2.4 欄分隔線位置 = colSpace 中央

OOXML 沒明定 separator 確切 X 位置；觀察 Word 行為是畫在欄之間 space 中央。實作：
```ts
const colEnd = startX[i] + widths[i];
const nextStart = startX[i + 1];
const xMid = (colEnd + nextStart) / 2;
```

線寬 `0.5pt` 黑色細線（Word 預設不可調，OOXML spec 也沒提供）。

### 2.5 全 fixture Render smoke ops 統計

console 輸出每類 fixture 的 Renderer ops 平均（非 assertion）：

```
01_simple: avgFillText=1134.0, avgDrawLine=580.0, avgFillRect=25.6
02_std_table: avgFillText=253.8, avgDrawLine=108.0, avgFillRect=12.4
03_complex_table: avgFillText=307.5, avgDrawLine=63.5, avgFillRect=7.1
04_with_image: avgFillText=179.2, avgDrawLine=109.3, avgFillRect=2.7
05_header_footer: avgFillText=947.0, avgDrawLine=304.8, avgFillRect=4.2
06_template: avgFillText=335.3, avgDrawLine=81.0, avgFillRect=2.3
```

讀法：
- `01_simple` 有大量段落 → fillText 數量最多
- `02_std_table` / `03_complex_table` drawLine 比 fillRect 多 → cell 邊框遠多於 cell shading
- `06_template` fillRect 少 → 樣板多用透明 cell
- `04_with_image` drawLine = 109.3（不是因為圖片，是表格內含照片+ caption + cell 邊框）

這不是 assertion，但提供「Renderer 端統計觀察基線」，未來 Sprint 11+ 跑 Visual Regression 時能對比 Word render 的 op 量級是否合理。

---

## 3. fixture 影響

Sprint 10 不改 Layout 演算法（columnLayout / fieldType 是新增欄位、不影響舊計算）；fixture-level avgPages 與 Sprint 7-9 一致：

| 類別 | Sprint 9 avgPages | Sprint 10 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.1 | 1.1 |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 2.3 | 2.3 |

PAGE / NUMPAGES post-pass 在沒有 FieldNode 的 fixture 完全 no-op；有 field 的 fixture 文字內容才會變（不影響 Layout）。

---

## 4. Sprint 10 已知限制

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| Page header / footer 渲染 | Layout 還沒把 header/footer 當 entries（headerRefs 在 SectionNode 但 Paginator 不消費） | Sprint 11 §5.6 |
| PAGE / NUMPAGES 在 header/footer 內 | 同上 | Sprint 11 |
| placeholder `##` 寬度與真值差距 | 簡化版 | Sprint 11+（用 metric 估「最大可能值」寬度 + 對齊調整）|
| DATE / TIME / AUTHOR / FILENAME 真值 | 需要文件 metadata 注入 | Sprint 11+ |
| 欄分隔線 style / 顏色不可調 | OOXML spec 沒定義；Word 也是固定黑細線 | 不補 |
| Visual regression（瀏覽器像素級比對 251 PNG） | 需 Playwright + image diff lib | Sprint 11 主軸 |
| HarfBuzz async batch shape | 仍走 estimate width | Sprint 11+ Phase 2 |
| wrapTight polygon | 仍降級 square | Sprint 11+ §3.4 |
| Knuth-Plass 精細斷行 | 仍貪婪 | Sprint 11+ §3.1 |

---

## 5. 對 Sprint 1-9 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | `SectionParser` 加 separator 解析；fixture 可能有 `<w:cols w:sep="true"/>` | 42 case 全綠（snapshot 內 separator 為 optional 不在輸出時不寫） |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無（columnLayout 是 optional 新欄位） | 48 case 全綠 |
| Sprint 2-9 unit tests | 無 | 全綠 |
| Sprint 9 Renderer tests | 無破壞（separator default false，不畫 vertical line） | 全綠 |
| Python integration | 無 | 54 case 全綠 |

**vitest 全套**：39 files / **643 tests pass**（Sprint 9 後 37/589 → 39/643，新增 54 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（37 → 39 files；589 → 643 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 10
npx vitest run tests/unit/layout/Sprint10.test.ts \
              tests/integration/07_render_smoke.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 11）建議

到 Sprint 10，Layout / Renderer / 全 fixture roundtrip 已 stable。Sprint 11 主軸建議：

1. **Page header / footer 渲染** — 把 SectionNode.headerRefs / footerRefs 解析的 HeaderFooterParser 結果接到 Paginator，每頁固定區域繪 header/footer，內含 PAGE 自動套真值
2. **Visual regression（Playwright）** — 真瀏覽器跑 BrowserCanvasRenderContext，截圖 vs 251 份 golden PNG（已備齊）；需 image diff（pixelmatch / odiff）+ tolerance 配置
3. **HarfBuzz async batch shape** — BoxBuilder 改 async pre-shape，replaces estimate width；行高 + advance 都接真實 metrics
4. **Knuth-Plass 精細斷行** — `LayoutItem` model 已用 K-P 結構；換 algorithm 即可
5. **wrapTight polygon** — drawing.xml 的 polygon path 解析 + LineBreaker per-y lineWidth

**建議優先順序**：1（fixture 含 header/footer 占比高、立即還原度提升）→ 2（驗證 Sprint 8-10 還原）→ 3, 4, 5（精度收尾）

---

**附註**：Sprint 1-10 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸（Box/Glue/Penalty + 表格 + section break + float wrap + 多欄 + 巢狀 + cell 順序 + column break + mid-row break）
- Sprint 8：Renderer 起步（介面 + Mock + CanvasRenderer flat lines）+ FontMetricsAdapter + CellLayout.borders 透傳
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- **Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke**

到 Sprint 10，Renderer 已能在瀏覽器產出帶 multi-column separator、自動 PAGE / NUMPAGES、shading、巢狀表、文字裝飾的真實畫面，且全 42 fixture 通過 Layout → Renderer roundtrip smoke 測試。Sprint 11 起進入 header/footer + Visual Regression 階段。
