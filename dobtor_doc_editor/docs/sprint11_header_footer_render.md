# Sprint 11 Page header / footer 渲染

**狀態**：W11+ 主線 Sprint 11 — Renderer 還原度第三步：頁眉/頁腳
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.6 Phase 5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint10_column_separator_page_field.md](sprint10_column_separator_page_field.md)

---

## 1. 範圍

Sprint 10 完成欄分隔線 + PAGE 真值後，Sprint 11 把缺席的「頁首/頁尾渲染」補上。`HeaderFooterParser` 在 Sprint 1 早就解析好 header/footer 的 BlockNode[]，但 Paginator 一直沒消費；Sprint 11 把這條鏈接通：

1. **A. LayoutOptions 注入 headers/footers**
   - `LayoutOptions.headers?: Map<rId, HeaderFooterContent>`
   - `LayoutOptions.footers?: Map<rId, HeaderFooterContent>`
   - 沒傳 → 不繪 header/footer（Sprint 10 行為）
2. **B. Paginator 末 post-pass 排版頁眉/頁腳**
   - 對每頁依 sectionIndex 找對應 SectionNode
   - 依 OOXML 規則挑 rId（titlePage 第一頁 → first；evenAndOddHeaders 偶頁 → even；fallback default → first → even）
   - Header zone：`y` 起點 = `section.margins.header`；自上而下排版 paragraph + 表格
   - Footer zone：先以 y=0 起點排版取得 totalHeight，再整體下移到 `pageHeight - margins.footer - totalHeight`
3. **C. PAGE / NUMPAGES post-pass 自動覆蓋 header/footer**
   - Sprint 10 的 `resolvePageNumberFields` 走訪 `page.entries`；Sprint 11 把 header/footer entries 在此 pass 之前 append 進去 → 不必改 post-pass 邏輯，PAGE 在 header/footer 內也會被正確替換

落地：

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/layout/types.ts` | M | `LayoutOptions.headers` / `footers` |
| `static/src/core/layout/Paginator.ts` | M | `layoutHeadersFooters` / `pickHeaderFooterRId` / `appendHeaderEntries` / `appendFooterEntries` / `renderBlocksToEntries`（簡化版 block→entries） |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/Sprint11.test.ts`（新檔） | 10 | 預設 header/footer 套用所有頁、titlePage、evenAndOddHeaders、PAGE in footer、NUMPAGES in header、fallback 規則、fixture-level 整合 |

**全套**：vitest 40 files / **653 tests pass**（Sprint 10 後 39/643 → 40/653，+1 file +10 case）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 為何 header/footer 排版獨立於主 Paginator 流程？

主 Paginator 是「線性 pass：扔 block 進 ctx，跨頁就 flushPage」；header/footer 不同：

- 不該被斷頁（每頁固定區域）
- 不該觸發 PAGE / column break
- 沒 widow/orphan 概念
- 高度有上限（`margins.top - margins.header`）但 Sprint 11 簡化版不強制 clip

把它做成「post-pass + 獨立 mini-layout」（`renderBlocksToEntries`）比硬塞進主 Paginator 簡單很多，也避開所有狀態交叉污染。

### 2.2 `renderBlocksToEntries` 為何只處理 paragraph + table？

Header/footer 內最常見就是「公司名 / 文件標題 / PAGE 欄位 / Logo 表格」這幾類；浮動圖片在 header 罕用，Knuth-Plass widow/orphan 在頁眉幾無意義。Sprint 11 簡化版沒處理：

- Float image / wrapSquare（用主流程的需要 ctx.activeFloats，太重）
- 巢狀 section break / column break（header 不該觸發）
- 跨頁切（header 永遠在當頁完整顯示）

對 fixture 已足夠；異常情況（header 內含巨大表格）會超出 margin 區，但 Renderer 仍會繪出，只是視覺上跟 body 重疊。Sprint 12+ 補 clip 行為。

### 2.3 Footer 高度反推 — 為何先用 y=0 排再下移？

Footer 的 anchor 是「底部」，不是「頂部」。但排版流程對 paragraph 的高度是動態算出（每段行數依 lineWidth 而定），不能只算個總和就 anchor 上去。

兩階段做法：
```
Stage 1: renderBlocksToEntries(blocks, baseX, 0, innerWidth, options)
         → 取得 entries，每 entry 有 absolute y（從 0 起）
         → totalH = max(entry.y + entry.height)
Stage 2: targetTop = pageHeight - margins.footer - totalH
         entries.forEach(e => e.y += targetTop)
```

這比「先預測 totalH → 再排版」乾淨：排版邏輯只寫一份，footer 只是把結果整體 translate。

### 2.4 header/footer rId 選擇規則

OOXML §17.10：

```
if (titlePage && isSectionFirstPage && refs.first) → first
else if (evenAndOddHeaders && isEven && refs.even) → even
else → default
```

實作裡多了一道「fallback」：`refs.default ?? refs.first ?? refs.even`。理論上這違反 spec（沒 default 應該就不畫），但實務上 fixture 偶見「只設 first 沒設 default」的怪格式；fallback 最少不掉資訊。Sprint 11 留 warning 補完到 Sprint 12+。

### 2.5 PAGE / NUMPAGES post-pass 順序

正確順序：

```
1. paginate body content → page.entries（body 部分）
2. layoutHeadersFooters → page.entries 末尾 append header/footer entries
3. resolvePageNumberFields → 走訪所有 entries（含 body + header + footer）替換 PAGE / NUMPAGES
```

Sprint 10 的 post-pass 已經能 walk entries；Sprint 11 只是讓 entries 包含更多東西，不用改 post-pass 程式碼。

---

## 3. fixture 影響

Sprint 11 不改 Layout 演算法（header/footer 在 margin 區、不擠 body）；fixture-level avgPages 與 Sprint 7-10 一致：

| 類別 | Sprint 10 avgPages | Sprint 11 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.1 | 1.1 |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 2.3 | 2.3 |

差別在 **fixture-level Renderer ops 增加**（caller 傳入 headers/footers 時）：每頁多出 header/footer 的 fillText / drawLine。Sprint 11 unit test 在 05_header_footer fixture 看到大量 `y < 72`（margin top）的 line entry 即驗證有效。

---

## 4. Sprint 11 已知限制

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| Header / footer 內含巨大表格不 clip | 簡化版不處理高度上限 | Sprint 12+ |
| Header / footer 內 column break / page break | mini-layout 不處理 | 罕用，Sprint 12+ |
| Header / footer 內浮動圖片 wrapSquare | 簡化版不處理 | Sprint 12+ |
| `refs.default` 缺席的 fallback 鏈 | 違反 spec 但實務需要 | Sprint 12 加 warning |
| DATE / TIME / AUTHOR / FILENAME 欄位真值 | 仍是 placeholder | Sprint 12+ |
| Visual regression（Playwright vs 251 PNG） | 沒做 | Sprint 12 主軸 |
| HarfBuzz async batch shape | 仍 estimate | Sprint 12+ Phase 2 |
| waveline / 高階 underline style | 仍當實線 | Sprint 12+ |
| wrapTight / wrapThrough polygon | 仍降級 square | Sprint 12+ §3.4 |
| Knuth-Plass 精細斷行 | 仍貪婪 | Sprint 12+ §3.1 |
| 註腳 / 尾註 | Paginator 沒概念 | Sprint 12+ §3.6 |

---

## 5. 對 Sprint 1-10 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無（沒傳 headers/footers，Sprint 11 行為與 Sprint 10 完全一致） | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無（同上） | 44 case 全綠 |
| Sprint 2-10 unit tests | 無 | 全綠 |
| Python integration | 無 | 54 case 全綠 |

**vitest 全套**：40 files / **653 tests pass**（Sprint 10 後 39/643 → 40/653，新增 10 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（39 → 40 files；643 → 653 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 11
npx vitest run tests/unit/layout/Sprint11.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 12）建議

到 Sprint 11，Layout / Renderer / 全 fixture roundtrip 含 header/footer / PAGE 真值已 stable。Sprint 12 主軸建議：

1. **Visual Regression（Playwright）** — 真瀏覽器跑 BrowserCanvasRenderContext，截圖 vs 251 份 golden PNG（已備齊）；用 pixelmatch / odiff diff 工具，每類 fixture tolerance 配置
2. **HarfBuzz async batch shape** — BoxBuilder 改 async pre-shape，replaces estimate width；行高 + advance 都接真實 metrics
3. **Knuth-Plass 精細斷行** — `LayoutItem` model 已用 K-P 結構；換 algorithm 即可
4. **DATE / TIME 欄位真值 + 註腳 / 尾註** — 小但 demo 加分
5. **wrapTight polygon** — drawing.xml polygon path 解析 + LineBreaker per-y lineWidth

**建議優先順序**：1（驗證 Sprint 8-11 還原度）→ 2（精度核心）→ 3, 4, 5

---

**附註**：Sprint 1-11 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- **Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值**

到 Sprint 11，Renderer 已能處理 ChienYi 監造文件常見的「頁眉公司 logo + 文件名稱 + 頁碼footer」標準版型，且支援 titlePage / evenAndOddHeaders 兩種 OOXML 高階模式。Sprint 12 起進入 Playwright Visual Regression + HarfBuzz async shape 收尾階段。
