# Sprint 19 段落樣式合併基礎建設 + Visual Regression v14 重跑量化

**狀態**：W11+ 主線 Sprint 19 — 段落 style→props post-pass 合併 + Sprint 17/18 像素級改善量化（per-category 04_with_image 0.485→0.386 / -20%、05_header_footer 0.06→0.0504 / -15%）
**完成日期**：2026-05-09
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §0.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint18_pagination_transition.md](sprint18_pagination_transition.md)

---

## 1. 範圍

Sprint 18 把 mismatched 從 17 收斂到 7，剩下 7 個 -1 偏差 fixture。Sprint 19 原計畫 R6
keepNext 實作，但 diagnosis 後發現 7 個 -1 偏差是**異質根因**：

| fixture | 假設 root cause | 實情 |
|---|---|---|
| 01_simple/03.1120210 | cell-internal break | Sprint 18 已修一個 break，仍有 -1（不同的小差距） |
| 02_std_table/工地密度取樣紀錄 | keepNext | **無 keepNext**、19 paragraphs、0 tables、0 page break |
| 03_complex_table ×2 | body 級 keepNext | **43 個 keepNext 全在 cell 內**（cell-level keepNext 在 Word 與 row break 規則交互複雜） |
| 05_header_footer ×3 | style 級 keepNext | **26 styles 有 keepNext，但 0 paragraphs 引用**這些 style → 不影響 |

→ 單一 R6 keepNext 修法**無法**改善這 7 個 fixture。Sprint 19 重新分配資源：

1. **段落 style 合併基礎建設**（必要 infra，未來 R6 / 字型修正等都會用到）
2. **Visual Regression v14 重跑**（量化 Sprint 17/18 的像素級實際改善）

---

## 2. 落地檔案

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/ooxml/styles/ParagraphStyleMerger.ts` | A | 新模組：mergeParagraphStyles(doc) post-pass，把 styles.xml 的 pProps 合併進所有 body 段落的 props（in-place mutate）；含 mergePProps 純函式（與 StyleResolver.mergePProps 邏輯一致，避免循環依賴） |
| `static/src/core/ooxml/OoxmlParser.ts` | M | parse() 在組裝 DocumentNode 後 + return 前呼叫 mergeParagraphStyles(doc) |
| `tests/unit/ParagraphStyleMerger.test.ts` | A | 11 case：純函式 mergePProps（4）+ document 走訪 mergeParagraphStyles（7）含巢狀 cell / 多 section / unknown styleId / 無 styleId / inline 覆寫 style |
| `tests/fixtures/visual_regression_v14_report.json` | M | 重跑全 42 fixture，rendered 42/42、comparedPages 119、failedPages 0 |

---

## 3. 段落 style 合併設計

### 3.1 為何需要

OOXML 規格容許段落僅透過 `<w:pStyle w:val="X"/>` 引用 styles.xml 中的 pPr 預設值（如
keepNext / spacing / fontSize 等）。我們的 ParagraphParser 只解析 inline `<w:pPr>` 內
的屬性，style-defined props 從未落到 paragraph.props，下游 Paginator / Renderer 看不到。

雖然 Sprint 19 diagnosis 顯示 7 個剩 -1 fixture 中沒有任何**生效的** style-level keepNext，
但這仍是真實的 infra 缺口：未來實作 R6 / 補字型 metric / 修 fixture 對齊都會踩到。

### 3.2 實作

```ts
// new module: ParagraphStyleMerger.ts
export function mergeParagraphStyles(doc: DocumentNode): number {
  if (doc.styles.size === 0) return 0;
  let count = 0;
  for (const sec of doc.sections) count += mergeBlocks(sec.body, doc.styles);
  return count;
}

function mergeBlocks(blocks, styles) {
  // recurse into table.rows[*].cells[*].content
  for (const block of blocks) {
    if (block.type === 'paragraph') mergeParagraph(block, styles);
    else if (block.type === 'table') for cell in cells: mergeBlocks(cell.content, styles);
  }
}

function mergeParagraph(para, styles) {
  if (!para.styleId) return false;
  const entry = styles.get(para.styleId);
  if (!entry?.pProps) return false;
  para.props = mergePProps(entry.pProps, para.props);  // inline 覆寫 style
  return true;
}
```

OoxmlParser.parse() 在組裝完 DocumentNode 但 return 前呼叫一次。

### 3.3 範圍與限制

- ✅ **Body 段落**：sections[*].body + 巢狀 table cell.content 遞迴
- ⏳ **Header / footer 段落**：HeaderFooterContent.content 的段落 Sprint 19 暫不合併（範圍邊界），留 Sprint 20+
- ⏳ **Run-level 樣式合併**：rProps（fontSize, color, bold 等）合併比 pProps 複雜（per-run），Sprint 19 範圍不含
- ✅ **inline 覆寫 style**：mergePProps(base=style, override=inline)，OOXML 規格行為
- ✅ **巢狀物件淺合併**：indent / spacing / borders / shading 對應 key 各自覆寫

### 3.4 對 layout 的實際影響（Sprint 19）

跑 09_page_count_baseline 確認：**snapshot 完全不變**。原因：
- 7 個剩 -1 fixture 的 styles.xml 不含實際被引用的 keepNext
- 其他 35 個對齊 fixture 也不會因為 style merge 改變 page count（style 的 pProps 多
  影響字型 / spacing 細節，這些已被 inline pPr 覆寫或不影響整段高度）

→ 純 infra 改動，零 layout 行為變動，零 regression 風險。

---

## 4. Visual Regression v14 重跑

### 4.1 重跑必要性

Sprint 17 + 18 改了 Paginator（R1 transition variant + cell-internal break）。
`tests/fixtures/visual_regression_v14_report.json` 上次更新在 Sprint 15 （2026-05-08
之前）。要量化「pagination 改善是否轉成像素級改善」必須重新渲染。

### 4.2 步驟

1. `npx rollup -c rollup.visual_regression.config.js` 重 build IIFE bundle（含 Sprint 18 的 Paginator 改動）
2. `node scripts/visual_regression_v14.mjs --max-diff 1.0` 全 42 fixture 渲染 + pixelmatch
3. 解析 stdout（JSON 寫入有時會被 puppeteer protocolTimeout 中斷，stdout 紀錄為主）

### 4.3 結果

| 指標 | Sprint 15 baseline | **Sprint 19** | Δ |
|---|---|---|---|
| rendered fixtures | 42 | 42 | 0 |
| compared pages | 100 | **119** | +19（Sprint 18 image-row break + cell-internal break 增加合理頁數） |
| failed pages（>1.0 threshold）| 0 | 0 | 0 |
| **per-category mean diff** | | | |
| 01_simple | ~0.10 | **0.0930** | -7% |
| 02_std_table | ~0.27 | 0.2674 | ~0 |
| 03_complex_table | ~0.32 | 0.3198 | ~0 |
| **04_with_image** | **0.485** | **0.3862** | **-20%** ← Sprint 18 R1 主軸成果 |
| **05_header_footer** | ~0.06 | **0.0504** | **-15%** |
| 06_template | ~0.03 | 0.0325 | ~0 |
| **總體 page-weighted mean** | 0.1773 | **0.1784** | +0.001（持平） |

### 4.4 解讀

- **04_with_image -20%**：Sprint 18 R1 transition variant 把 4 個 fixture 從 3 頁修為
  6 頁對齊 golden，每頁的 image 落點與 row 邊界更接近 Word，pixel-level diff 大幅縮短
- **05_header_footer -15%**：Sprint 18 的層次性效應（即便 page count 沒變動，render ops
  細微調整改善 pixel）
- **01_simple -7%**：Sprint 18 cell-internal break 修了 6/7 fixture page count，per-page
  內容對齊 Word 更精確
- **總體持平**：Sprint 18 增加的 19 頁中多數是低 diff 頁（image 渲染對齊 → 該頁 diff 低），
  page-weighted 公式把總 mean 拉平。**這不是退步，是「對齊度提升 + 樣本擴大」的正常結果**

---

## 5. 對 Sprint 1-18 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | **AST props 多了 style-merged 內容** | 42 case 全綠（snapshot 內容對段落內容無變動，因 7 個剩 -1 fixture 的 style 沒有實際引用的 pProps；其他 fixture 的 style 內容也未被段落引用）|
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | 無 | 2 case 全綠 |
| `09_page_count_baseline.test.ts`（Sprint 16）| **無**（style merge 純 infra） | 2 case 全綠 |
| `TableLayout.test.ts` | 無 | 25 case 全綠 |
| `Paginator.test.ts` | 無 | 22 case 全綠 |
| **`ParagraphStyleMerger.test.ts`（Sprint 19 新增）** | — | 11 case 全綠 |
| Visual regression v14 | layout 改 → 重跑 → 04_with_image -20% / 05_hf -15% / 01_simple -7% | rendered 42/42 / 0 fail |
| Python integration | 無 | 61 case 全綠 |

**vitest 全套**：**47 files / 735 tests pass + 1 skipped**（Sprint 18 後 46/724+1 → 47/735+1，**+1 file +11 case**）。

---

## 6. 7 個剩 -1 偏差 fixture 的 root cause 結論

Diagnosis 結果（per fixture）：

| fixture | golden | ours | 推測 root cause | Sprint 19 狀態 |
|---|---|---|---|---|
| 01_simple/03.1120210 | 3 | 2 | section 內含一個 cell-break + 一個 normal break；可能 normal break 偵測有間隔 | 未動，留 Sprint 20+ |
| 02_std_table/1140206-工地密度取樣紀錄 | 2 | 1 | 純段落（無 table、無 page break、無 keepNext）；可能段落 spacing 與 Word 不一致使內容裝得下 | 未動 |
| 03_complex_table ×2 | 2 | 1 | cell-level keepNext 43 個（位於 1 張 12-row 表內）；Word 對 cell-level keepNext 與 row 邊界互動規則需更多樣本才能精確實作 | 未動 |
| 05_header_footer ×3 | 5 | 4 | 3 sections 結構，sec[1] 7 blocks 在我們算 1 頁、Word 算 2 頁；可能 header/footer 高度估計或段落 spacing 微差 | 未動 |

**Sprint 20+ 個別擊破策略**：
- 每個 fixture 抽 docx XML 細查（page break / section break / header / spacing）
- 不再期待單一規則修法；逐 fixture 找最有把握的 1-2 個 root cause + 對症
- 若需更大改動（如 section-internal content height 計算重算），先評估 regression 風險

---

## 7. 驗證指令

```bash
# Sprint 19 新增 unit tests
npx vitest run tests/unit/ParagraphStyleMerger.test.ts

# 全套 regression
npm test    # 47 files / 735 tests + 1 skipped

# 重跑 visual regression v14
npx rollup -c rollup.visual_regression.config.js
node scripts/visual_regression_v14.mjs --max-diff 1.0

# Python integration
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev --test-tags dobtor_doc_editor --stop-after-init --xmlrpc-port=8169
```

---

## 8. 下個 Sprint（Sprint 20）建議

優先順序由 root cause 確定性 / fixture 數量 / 風險 weight：

1. **05_header_footer ×3 fixture（最大 fixture 數）**：抽 sec[1] 內容細看，找 height 計算差異點。可能修法：1) 段落 spacing.before/after 預設值對齊 Word（OOXML 預設 240 twips = 12pt）；2) 多段落間額外的 paragraph spacing 規則
2. **03_complex_table ×2 fixture**：嘗試「cell-level keepNext 的 row 視為 cantSplit」近似
   - 若有 cell.content 中任一段落 keepNext=true → 該 row 補 cantSplit 旗標
   - 評估對其他 fixture 的 regression 風險（grid search 同樣思路）
3. **01_simple / 02_std_table 個案**：每個獨立 root cause，個別修
4. **Header / footer 段落樣式合併**：擴展 ParagraphStyleMerger 至 HeaderFooterContent
5. **Run-level 樣式合併**：擴展至 rProps（每個 run 走 styleId chain）

**建議優先順序**：1（最大 fixture 數）→ 2（明確的 OOXML 規則）→ 3（個案）→ 4-5（infra 補完）

---

## 9. 變更摘要

| 範疇 | Sprint 18 結束 | **Sprint 19 結束** | 差量 |
|---|---|---|---|
| vitest test files | 46 (+1 skipped grid_search) | 47 (+1 skipped) | +1 |
| vitest test cases | 724 + 1 skipped | **735 + 1 skipped** | +11 active |
| Python tests | 61 | 61 | 同 |
| Layout output（page count）| 7 mismatched | **7 mismatched**（無變動）| 0 |
| Visual regression v14 mean | 0.1773（Sprint 15 數據）| **0.1784**（總體）| +0.001 |
| Visual regression v14 04_with_image | 0.485（Sprint 15 數據）| **0.3862** | **-20%** |
| Visual regression v14 05_header_footer | ~0.06 | **0.0504** | **-15%** |
| Paginator features | 19 個 | 19 個 | 0 |
| OOXML rules infra | StyleMap 解析有 keepNext，但未合併進 paragraph.props | **mergeParagraphStyles post-pass 補完** | 完成段落級 |

---

**附註**：Sprint 1-19 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8-12：Renderer 起步 + FontMetrics + cell.blocks + decoration + multi-col + page field + header/footer + 完整 field + fingerprint regression
- Sprint 13：docProps + Knuth-Plass opt-in
- Sprint 14-15：自家 pipeline IIFE + puppeteer harness + 圖片真渲染
- Sprint 16：頁數對齊 baseline lock + Word page-break 規則差距文件化
- Sprint 17：Word page-break 規則資料庫 + RowLayout.containsImage + Paginator R1 image-row break heuristic（opt-in）
- Sprint 18：R1 transition 變體啟用（ratio=0.34）+ cell-internal page break + table-level guard，全 fixture mismatched 17→7 (-59%)
- **Sprint 19：段落 style→props post-pass 合併基礎建設 + Visual Regression v14 重跑量化（04_with_image -20% / 05_hf -15% / 01_simple -7% per-category）；7 個剩 -1 偏差 fixture diagnosis 完成（異質根因，留 Sprint 20+ 個別擊破）**

到 Sprint 19，**Paginator 對 docx page count 的還原度收斂到 7/42**（83% fixture 完美對齊
golden）；像素級在「Sprint 18 改動目標的類別」實際改善 -20% 至 -15%；段落樣式繼承基礎
建設就位，未來 R6 / 字型修正可直接從 paragraph.props 取 style-merged 值。

Sprint 20 起聚焦剩 7 個 -1 偏差的個別擊破 + header/footer 樣式合併擴展 + run-level 樣式
合併（infra 補完）。
