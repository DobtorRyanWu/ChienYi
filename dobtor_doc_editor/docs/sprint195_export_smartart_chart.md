# Sprint 195 — SmartArt + Chart export（Phase 6 收尾、~99.8%）

**日期**：2026-05-24
**類型**：export 擴充（Phase 6 剩 watermark 一塊；SmartArt + Chart 補完）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-194（除 watermark / SmartArt / Chart 外其他全部完成）

---

## Hypothesis

Sprint 194 完成 OMML / 追蹤修訂 / 註解 / background export 後、Phase 6 達 ~99.5%。
本 sprint 收 SmartArt + Chart 兩個 Phase 5 子功能 export、把 Phase 6 推到 ~99.8%。

**watermark export 在本 sprint 視為 honest gap**：需要合成 header part 包 VML，
邏輯複雜（需處理「無既有 header」/「有既有 header」兩種情境的不同策略）；
ChienYi 監造文件實際很少使用浮水印；留 Sprint 196 optional。

---

## 修法

### 1. 6 個新常數（+12 行）

- 2 個關係型別常數（`REL_TYPE_DIAGRAM_DATA` / `REL_TYPE_CHART`）
- 2 個 graphicData URI 常數（`A_GRAPHIC_DIAGRAM_URI` / `A_GRAPHIC_CHART_URI`）
- 2 個命名空間常數（`DGM_NS` / `C_NS`）

### 2. SmartArt export（+約 50 行）

**graphicData 改寫**：`writeInlineImageRun` 依 `img.graphic.kind` 分派：
- 一般圖片 → 既有 `<pic:pic>` 路徑
- diagram → `<a:graphicData uri=".../diagram"><dgm:relIds r:dm/r:lo/r:qs/r:cs>`
- chart → `<a:graphicData uri=".../chart"><c:chart r:id>`

新增 `writeGraphicDataForPicture` 與 `writeGraphicDataForGraphicFrame` 兩個
分支函式。

**Diagram data 部件**：
- `SmartArtPartItem` 型別 + `collectSmartArts(doc)` 依 `doc.smartArts` 整理
  （流水檔名 `word/diagrams/dataN.xml`）
- `writeSmartArtPart(item)` — `<dgm:dataModel><dgm:ptLst>` 內 emit：
  - 一個 `<dgm:pt type="doc"><dgm:prSet loTypeId>` 帶版面類型（如有）
  - 每個內容點 `<dgm:pt modelId><dgm:t><a:p><a:r><a:t>text</a:t></a:r></a:p></dgm:t></dgm:pt>`
- 紀律 #18 scope-down：parser 把 4 個 SmartArt 部件（data/layout/quickStyle/
  colors）摺成一個 SmartArtNode；export 只需寫 data 部件（parser 走
  `type=diagramData` 解析）；layout/quickStyle/colors 留後續。
  `dgm:relIds` 的 dm/lo/qs/cs 四個 rId 暫指向同一個 data rId（只有 dm 是
  parser 必讀）。

### 3. Chart export（+約 70 行）

- `ChartPartItem` 型別 + `collectCharts(doc)` 依 `doc.charts` 整理
  （流水檔名 `word/charts/chartN.xml`）
- `writeChartPart(item)` — `<c:chartSpace><c:chart>`：
  - `<c:title><c:tx><c:rich><a:p><a:r><a:t>` 如有
  - `<c:plotArea><c:{chartType}>` 包 series
- `writeChartSeries(s)` — `<c:ser>` 內 tx / cat / val：
  - `<c:tx>` 用 strRef + strCache（name）
  - `<c:cat>` 用 `writeChartStrCache('cat', categories)` 共用 helper
  - `<c:val>` 用 `writeChartNumCache('val', values)` — **null 點不 emit
    `<c:pt>`、保稀疏對位**（與 parser readCachePoints 對稱）

### 4. `writeContentTypes` + `writeDocumentRels` 擴展（+約 16 行）

兩函式各加 SmartArt + Chart 兩條：
- Override：`drawingml.diagramData+xml` / `drawingml.chart+xml`
- Relationship：rId 從 `doc.smartArts/charts` 的 `node.rId` 原樣帶入

### 5. `OoxmlWriter.write()` 整合（+約 8 行）

- 開頭收集 `smartArtItems = collectSmartArts(doc)` /
  `chartItems = collectCharts(doc)`
- 把每個 SmartArt + Chart 部件寫進 zip parts

### 6. 測試（+11）

- `tests/unit/OoxmlWriter.test.ts` Sprint 195 區塊（+7）：
  - SmartArt → word/diagrams/data1.xml + Content_Types Override + rels
  - SmartArt graphicData → `<dgm:relIds r:dm>`（非 pic:pic）
  - Chart → word/charts/chart1.xml + Content_Types + rels
  - Chart graphicData → `<c:chart r:id>`（非 pic:pic）
  - Chart 數列 cat/val 對位（含稀疏 null 跳過）
  - 多個 SmartArt + Chart 各自編號
  - 無 SmartArt/Chart 不輸出對應部件
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 195 區塊（+4）：
  - SmartArt round-trip（texts + layoutType 保留）
  - Chart round-trip（chartType + title + series）
  - Chart 多 series round-trip
  - Chart null 值（稀疏）round-trip

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1855 → **1866 passed + 1 skipped**（+11） |
| L2 VR v14 | ✅ **byte-identical 第 55 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ SmartArt + Chart 4 案例 | texts/layoutType/chartType/series/null 對位 端到端對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（tree-shake 維持）。

---

## Phase 6 完成度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS / RunProps / ParagraphProps / Styles / 表格 / 多 section + numbering | ✅ | 185-191 |
| 圖片 / media | ✅ | 192 |
| 頁首頁尾 + sectPr refs + titlePg | ✅ | 193 |
| OMML / 追蹤修訂 / 註解 / background | ✅ | 194 |
| **SmartArt / Chart** | ✅ | **195** |
| watermark（header VML `<v:shape>`） | ⏳ | optional Sprint 196 |

**Phase 6 完成度估算：~99.5% → ~99.8%**

watermark 一塊以 honest gap 處理：
- parser capture（Sprint 172）+ render（Sprint 173）已完成
- export 需合成 header part 包 VML、複雜度高、ChienYi 監造文件實際很少使用
- 留 Sprint 196 optional、不影響 95% 以上實際 docx 使用情境

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 55 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：
  - graphicData 分派（`writeGraphicDataForPicture` vs
    `writeGraphicDataForGraphicFrame`）共用 `<wp:inline><wp:extent>` 包裝
  - Chart writers（`writeChartSeries` / `writeChartStrCache` /
    `writeChartNumCache`）模組化、cat/val 結構複用
  - 部件流水檔名（`diagrams/dataN.xml` / `charts/chartN.xml`）同
    collectMedia/collectHeadersFooters 模式
- **#18 scope-down**：
  - SmartArt data 部件只寫、不寫 layout/quickStyle/colors 三檔（parser 不需）
  - `dgm:relIds` 的 lo/qs/cs 三個 rId 暫指向 dm 同 rId（指向不存在的 rId
    對解析無影響、避免額外管理 4 個 rId）
  - watermark 留 Sprint 196 optional（honest gap）
- **#21**：`doc.smartArts` / `doc.charts` 為 undefined 或空 → 不輸出部件、
  Content_Types / rels 無條目
- **#2 magic number**：6 個新具名常數

---

## 後續

- **Sprint 196 (optional)**：watermark export
  - 合成新 header part 包 VML `<v:shape type="#_x0000_t136"><v:textpath string=>`
  - 對無既有 default headerRef 的 sections 注入該 header 為 default
  - 處理「既有 default header」情境的 lossy 行為
- Phase 6 達 100%（含 watermark）

---

## Sprint 195 結尾累積指標

- vitest **1866 passed + 1 skipped**（`npm test` 全套；+11）
- VR mean **0.073191**（byte-identical 第 55 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 194 → **195**
- Phase 6 完成度 ~99.5% → ~99.8%（SmartArt + Chart 完成、watermark 留 optional）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       SmartArt + Chart export 系列 + writeInlineImageRun graphicData 分派（+約 150）
M  tests/unit/OoxmlWriter.test.ts                    +7 test
M  tests/integration/sprint185_export_roundtrip.test.ts  +4 test
```

**淨 production code 變動 = +約 150 行**、SmartArt + Chart round-trip 對稱（含
texts/layoutType/chartType/title/series/null 稀疏對位）、VR byte-identical
第 55 連、Phase 6 完成度 ~99.8%。
