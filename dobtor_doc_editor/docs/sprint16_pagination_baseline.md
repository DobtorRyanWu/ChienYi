# Sprint 16 Pagination 鎖死 + Word 規則差距分析

**狀態**：W11+ 主線 Sprint 16 — 頁數對齊診斷 + baseline lock，**刻意不動 Paginator**
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §0.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint15_image_render.md](sprint15_image_render.md)

---

## 1. 範圍

Sprint 15 揭露 4 個 04_with_image fixture 的 page count 差 -3。Sprint 16 原計畫修 Paginator 對齊 golden，但**深度診斷後決策不動 Paginator**：直接把當前 baseline 鎖到 vitest snapshot，把根因文件化，留待 Sprint 17+ 累積足夠 Word 規則樣本後再動。

理由見 §4「為何不修」。

---

## 2. 落地檔案

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `tests/integration/09_page_count_baseline.test.ts` | A | 全 42 fixture × pages.length × goldenCount baseline，鎖 vitest snapshot |
| `tests/integration/__snapshots__/09_page_count_baseline.test.ts.snap` | A（產物） | 寫入 17 個 mismatched fixture + delta + 總計指標 |

**測試**：

| 測試 | 結果 |
|---|---|
| 09_page_count_baseline (新增) | 2 case pass |
| Sprint 1-15 既有 vitest | 45 files / 699 tests pass（與 Sprint 15 完全一致） |
| **vitest 全套**：46 files / **701 tests pass** | **+1 file +2 cases** |
| Python integration | 61 cases pass |

---

## 3. 全 fixture page count 對照

`scripts/visual_regression_v14.mjs --no-diff` 全 42 fixtures：

### 對齊（25/42 fixture）
所有 06_template、部分 02_std_table、03_complex_table 與 05_header_footer 的 fixture，pages.length 等於 golden。

### 差距（17/42 fixture，全部我們 < golden）

| 偏差 | 數量 | 類別 | 主要原因 |
|---|---|---|---|
| **-3** | 4 | 04_with_image | 含 image 的 6-row table，每 image row 應獨佔頁面（Word 規則）|
| **-2** | 1 | 01_simple | 監造會議記錄首份（內容較長）|
| **-1** | 12 | 01_simple / 02 / 03 / 05 | 各種小幅偏差 |

**總體**：mismatched=17/42，total delta=-23（我們累計少 23 頁）。

---

## 4. 為何 Sprint 16 不動 Paginator

### 4.1 04_with_image 根因深度診斷

抓 `04_with_image/06.環清表.docx`（我們 3 頁 vs golden 6 頁）解構：

**docx 結構**：
- 1 個 section，body 14 blocks（3 paragraph 段 + 3 個 6-row table）
- 每個 table 共 18 個 `<w:tr>`（4 標題 row + 2 image row 6×3 = 18）
- 6 張 inline image 分布在 tr#4, tr#5, tr#10, tr#11, tr#16, tr#17（每 table 的 row[4]、row[5]）
- 每張 image 真實尺寸：`<wp:extent cx="4676820" cy="3506033"/>` ≈ **368×276 pt**（A4 約占半幅 + 1/3 高）

**每個 row 的 trPr**（從 docx XML 抽出）：
```
tr#0..3   trHeight=340 (17pt)   cantSplit
tr#4 IMG  trHeight=5159 (258pt) cantSplit
tr#5 IMG  trHeight=5159 (258pt) cantSplit
tr#6..9   trHeight=340 (17pt)   cantSplit
tr#10 IMG trHeight=5159 (258pt) cantSplit
tr#11 IMG trHeight=5159 (258pt) cantSplit
... 後續 3rd table 同上
```

**關鍵屬性**：
- `<w:trHeight w:val="5159"/>` 沒寫 `w:hRule` → 預設 `auto` → row 高 = max(258pt trHeight, content height 276pt + padding) ≈ 290pt
- 全部 row 都是 `cantSplit`（不切 cell 內部）

**我們當前 paginator 的處理**：
- contentHeight ≈ 742pt（A4 - 50 top margin - 50 bottom margin）
- pendingHeight 累加：91 (4 標題) + 301 (image row[4]) + 291 (image row[5]) = 683pt < 742pt → **整 6-row table 一頁裝得下**

**Word 的處理**（從 golden 6 頁推斷）：
- Word 顯然不是「容量裝得下就放」。它有 **「row 含 image 時，view-port 級的特殊邏輯」**：
  - 即便 row 高 290pt < 742pt 剩餘空間，Word 仍將每張 image row 推到獨立頁面
  - 推測規則：包含 floating drawing wp:anchor 的 row + cantSplit + 該頁同類前置 row 已存在 → 強制換頁

或更極端：每個 image 在 docx 內以 `mc:AlternateContent` 包了 `wp:anchor`（見 §4.2），Word 對 anchor drawing 有獨立的 wrap layout，可能讓 row 視覺高度大於我們算的 pure cell content height，從而觸發換頁。

### 4.2 wp:anchor vs wp:inline 混用

掃 docx 第 4 個 row 開頭結構：
```xml
<w:tr><w:trPr><w:cantSplit/><w:trHeight w:val="5159"/>...</w:trPr>
  <w:tc>...
    <w:p>
      <w:r>
        <mc:AlternateContent>
          <mc:Choice Requires="wps">
            <w:drawing>
              <wp:anchor distT="0" distB="0" ... behindDoc="0"
                         layoutInCell="1" allowOverlap="1">
                <wp:positionH relativeFrom="column">
                  <wp:posOffset>4069715</wp:posOffset>
                </wp:positionH>
                <wp:positionV relativeFrom="paragraph">
                  <wp:posOffset>3231515</wp:posOffset>
                </wp:positionV>
                <wp:extent cx="998220" cy="283845"/>
                ...
              </wp:anchor>
            </w:drawing>
          </mc:Choice>
          ...
        </mc:AlternateContent>
      </w:r>
      <w:r>
        <w:drawing>
          <wp:inline ...>
            <wp:extent cx="4676820" cy="3506033"/>
            ...
          </wp:inline>
        </w:drawing>
      </w:r>
    </w:p>
  </w:tc>
</w:tr>
```

Row 內**同時有 wp:anchor（Text Box overlay）+ wp:inline（主圖）**。我們當前 DrawingParser 兩者都解，BoxBuilder 也都生 isImage Box，但：
- `wp:anchor.posOffset` 的絕對定位邏輯是 floating drawing 的 wrap，layout 端把它放進同一個 paragraph 的 inline run 等於把 floating 當 inline 處理 — 不正確
- 真正修法：`wp:anchor` 應該走 `FloatImageEntry` 路徑（已支援），但目前 ParagraphParser 把 anchor / inline 都吐成同一條 RunNode 流，所以 BoxBuilder 把兩者並列推到 line items

### 4.3 修 paginator 的風險

要對齊 golden 6 頁有三條候選路徑：

| 方案 | 描述 | 風險 |
|---|---|---|
| A | 加 heuristic：row 含 image 且 height > pageHeight × N% → 主動換頁 | 5+ fixture 的 -1 偏差可能變 +1 / +2，整體更糟 |
| B | 真實實作 wp:anchor / wp:inline 區別、wrap layout、layoutInCell | 工程量大，需要分多 sprint |
| C | 觀察 golden 收集 Word 內部規則樣本後再動 | 慢但風險低 |

當前選 **C**，Sprint 17+ 累積 5 個以上 Word page-break 樣本後再實作 B 的縮減版。

### 4.4 寫 vitest snapshot 鎖死 baseline 的價值

- ✅ 任何修改 Paginator 的 PR，snapshot 變動必須 review，避免無意間退步
- ✅ Sprint 17 修改後預期 fixture 對齊變化能在 snapshot diff 一眼看出
- ✅ 寫測試的成本極低（已寫，46 files / 701 tests）

---

## 5. 對 Sprint 1-15 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | **完全不變** | 2 case 全綠 |
| `09_page_count_baseline.test.ts`（**Sprint 16 新增**） | — | 2 case 全綠 |
| Sprint 13 / 15 / 16 unit tests | 無 | 全綠 |
| Visual regression v14 | 未動 paginator → 與 Sprint 15 一致 | rendered 42/42, mean diff 0.1773 |
| Python integration | 無 | 61 case 全綠 |

**vitest 全套**：**46 files / 701 tests pass**（Sprint 15 後 45/699 → 46/701，+1 file +2 case）。

---

## 6. 已知限制（Sprint 17+ 補完）

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| 17/42 fixture page count 不對齊 | Word 內部 page-break 規則未實作（trHeight w:hRule, image row auto-break, anchor wrap 與 cantSplit 互動） | Sprint 17+ |
| `wp:anchor` 走 inline path 而非 FloatImageEntry | ParagraphParser 對 anchor / inline 沒分流 | Sprint 17+ |
| 04_with_image 04 個 fixture 的 -3 偏差 | row 高度未觸發換頁 | Sprint 17 主軸 |
| 01_simple 7 個 -1/-2 偏差 | 標題 + 段落間距與 Word 不完全相符 | Sprint 17+ 細修 |
| 缺少 Word 規則對照樣本資料庫 | 沒有系統性收集多 fixture 的 trPr / pPr | Sprint 17+（建立 word_rules.md）|

---

## 7. 驗證指令

```bash
# 跑新測試（鎖頁數 baseline）
npx vitest run tests/integration/09_page_count_baseline.test.ts

# 修改 Paginator 後重生 snapshot（強迫 review）
npx vitest run tests/integration/09_page_count_baseline.test.ts -u

# 全套 regression
npm test

# 重跑 visual regression（與 Sprint 15 結果一致）
node scripts/visual_regression_v14.mjs --max-diff 1.0
```

---

## 8. 下個 Sprint（Sprint 17）建議

Sprint 16 把現況凍結並深度診斷。Sprint 17 可選方向：

1. **04_with_image trHeight + cantSplit page break**（主修）
   - 在 Paginator 內加 row-level break heuristic：當 row.height + pendingHeight > pageHeight × N% 且 row 含 image 時 flush + nextPage
   - 用 Sprint 16 snapshot 驗證對齊改善
2. **wp:anchor / wp:inline 分流**
   - ParagraphParser 對 mc:AlternateContent 內的 anchor 改吐 FloatImageNode 而非當 inline
   - DrawingParser 已支援，差 paragraph 端的分流
3. **Word 規則對照樣本資料庫**
   - 收集 5+ fixture 的 trPr / pPr 結構，產出 `docs/word_pagebreak_rules.md`
   - 之後改 paginator 才有依據

**建議優先順序**：3（先建知識基礎）→ 1（最大 ROI）→ 2（精度收尾）

---

**附註**：Sprint 1-16 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值
- Sprint 12：完整 field 系統（DATE/TIME/AUTHOR/FILENAME）+ Renderer ops fingerprint regression
- Sprint 13：OOXML docProps/core.xml 自動讀取 + Knuth-Plass 斷行器（opt-in）
- Sprint 14：自家 pipeline IIFE bundle + puppeteer harness + 42 fixture / 100 頁 baseline
- Sprint 15：圖片真渲染（pre-load + imageResolver + async render）+ doc.template UI bug 完整修復（含 form view content_html 隱藏欄位 onchange 寫回）
- **Sprint 16：頁數對齊 baseline lock（vitest snapshot 鎖 17/42 mismatched fixture）+ Word page-break 規則差距文件化**

到 Sprint 16，「我們的渲染管線是否能畫出近似 Word 的結果」此問題的**衡量機制**完整：
- 結構性鎖：Sprint 12 fingerprint snapshot（render ops byKind）
- 頁數鎖：Sprint 16 page count snapshot
- 像素級基準：Sprint 14 baseline（42 fixture / 100 頁，mean diff 17.73%）

Sprint 17 起可有計畫地動 Paginator 而不擔心無意退步。
