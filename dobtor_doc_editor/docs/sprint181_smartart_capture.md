# Sprint 181 — SmartArt 圖表 capture（Phase 5.2）

**日期**：2026-05-22
**類型**：新 parser 模組 + document-level capture（Phase 5.2 SmartArt、mc:Fallback 壓縮、capture-only）
**規畫書對應**：§5 階段 D Phase 5.2「SmartArt fallback（規畫書建議優先走 `mc:Fallback` 圖片）」
**前置**：Sprint 179-180（Phase 5.1 OMML 完成）；決策 C（user 2026-05-21 GO 全 6 子功能、Phase 5 大三項採 mc:Fallback 壓縮）

---

## Hypothesis

Phase 5.1 OMML 已收尾（capture 179 + render 180）。本 sprint 推進 Phase 5.2 SmartArt
capture。

**SmartArt 結構勘查**（4 個 `08_smartart/` 真實 fixture）：
- SmartArt 在 document.xml 以 `<w:drawing><wp:inline><a:graphicData
  uri=".../diagram">` 表示，圖本身**不內嵌** document.xml。
- `<dgm:relIds r:dm r:lo r:qs r:cs>` 以 rId 指向 4 個獨立部件：
  data（資料模型）/ layout / quickStyle / colors。
- **4 個 fixture 皆無 `<mc:AlternateContent>` / `<mc:Fallback>`** —— 規畫書原設想的
  「mc:Fallback 內嵌圖片」在這批真實檔不存在；SmartArt 圖形以
  `diagrams/dataN.xml`（資料模型）+ Microsoft 擴充的 `diagrams/drawingN.xml`
  （預渲染 `dsp:` shape 樹）儲存。

**mc:Fallback 壓縮策略的實際對應**（user 2026-05-21 拍板「接受降級保真度」）：
- SmartArt 無 fallback 圖 → 降級策略 = 取**資料模型的語意文字**（同 OMML 無
  fallback 圖時改線性文字的處理）。
- 本 capture 取 `diagrams/dataN.xml` `<dgm:dataModel>` 的內容點文字 + 版面類型
  識別碼；**不重建**圖形版面、節點幾何、連接線（degraded fidelity）。
- 圖形精確 render（消費 `drawingN.xml` 的 `dsp:sp` 幾何）留未來 optional sprint。

---

## 修法

### 1. 新型別 `SmartArtNode`（types.ts、+約 34 行）

```ts
interface SmartArtNode {
  rId: string;            // 對應 diagramData 關係 rId
  layoutType?: string;    // <dgm:pt type="doc"><dgm:prSet loTypeId>（紀律 #21 無則不掛）
  texts: string[];        // 內容點文字（已過濾 presentation 點與空白）
}
```

`DocumentNode.smartArts?: SmartArtNode[]` —— optional（紀律 #21、多數 docx 無
SmartArt）；比照 `background` / `watermark` 的 conditional spread。

### 2. 新模組 `diagram/DiagramParser.ts`（+約 130 行）

`parse(xml, rId)`：解析 `diagrams/dataN.xml`。
- root 非 `<dgm:dataModel>` / XML 解析失敗 / undefined → 回 undefined（不 throw）。
- 走訪 `<dgm:ptLst>` 直屬 `<dgm:pt>`：
  - `type="doc"` → 抓 `<dgm:prSet loTypeId>` 為 `layoutType`，不貢獻文字。
  - `type ∈ {pres, parTrans, sibTrans}` → presentation / 連接點，跳過。
  - 其餘（無 `type` 或 `type="node"`）→ 內容點，抓 `<dgm:t>` 文字。
- `<dgm:t>` 文字：各 `<a:p>` 段落以 `\n` 串接、段落內 `<a:t>` 依序拼接、trim；
  空白點跳過。

### 3. OoxmlParser wire-up（+約 28 行）

- `REL_TYPE_DIAGRAM_DATA` 常數 + `diagramParser` 欄位。
- Step 8.6 `collectSmartArts`：走 mainDoc `.rels`、抓所有 `type=diagramData`
  關係（一份 docx 可含多個 SmartArt）、依 rels 順序解析為 `SmartArtNode[]`。
- `smartArts.length > 0` 才 spread 進 `DocumentNode`（紀律 #21）。

### 4. 測試（+21）

- `tests/unit/DiagramParser.test.ts`（+17）：防禦邊界（undefined / 壞 XML / 非
  dataModel / 空 ptLst）、內容點文字捕捉（單/多點 / 多 run 拼接 / 多段落換行 /
  空點跳過 / 無 `<dgm:t>` 跳過）、presentation 點跳過、layoutType（有/無
  loTypeId、紀律 #21、doc 點不貢獻文字）。
- `tests/integration/sprint181_smartart_capture.test.ts`（+4）：4 個真實
  `08_smartart/` fixture 經 OoxmlParser 端到端驗證——`smartArts` 捕捉、rId、
  layoutType（VerticalCircleList / LinedList / chevron2）、文字內容、文字皆非空白。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1577 → **1598 passed + 1 skipped**（+21） |
| L2 VR v14 | ✅ **byte-identical 第 41 連** | rendered 42/42、comparedPages 126、failedPages 0；0/42 baseline fixture 含 SmartArt → `smartArts` 皆 undefined → DocumentNode 形狀不變 |
| L3 visual spot check | ✅ capture-only | 4 個 `08_smartart/` fixture 各捕捉 1 個 SmartArt、文字與版面類型正確（degraded fidelity、無圖形 render） |

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js / SettingsParser
  position enum）、**無新增**。
- frontend bundle 重建（DiagramParser / OoxmlParser 在 frontend 依賴樹）。
- VR IIFE bundle（`tools/dist/visual_regression_pipeline.iife.js`）重建後再跑 VR
  ——VR 走獨立 bundle、含 OoxmlParser 變更。

**4 個真實 fixture 捕捉結果**：

| fixture | layoutType | 文字節點數 |
|---|---|---|
| 系統操作介紹(簡略版).docx | VerticalCircleList | 9 |
| 系統操作介紹(簡略版)_2.docx | VerticalCircleList | 9 |
| 1140831磺港溪C-B中央補助款-V1.docx | LinedList | 11 |
| 磺港溪C-B中央補助款20250904-V6.docx | chevron2 | 7 |

---

## 紀律

- **#1.a**：改 parser 跑全 42 fixture VR；capture-only、DocumentNode layout/render
  不消費 `smartArts` → byte-identical 第 41 連。
- **#1.b / Strategy C**：`smartArts` 只在文件真含 SmartArt 時掛 key；0/42 baseline
  fixture 含 SmartArt → DocumentNode 形狀不變 → byte-identical 維持。
- **#21**：`DocumentNode.smartArts` / `SmartArtNode.layoutType` 無值不掛 key
  （比照 `background` / `watermark` conditional spread）。
- **#14（DRY）**：DiagramParser 自成 `diagram/` 子目錄（比照 `omml/` /
  `watermark/` / `comments/`）；`collectSmartArts` 比照 `collectWatermark` /
  `collectComments` 的 rels 走訪模式；`parseXml` 防禦比照 CommentsParser。
- **#18 scope-down**：capture 資料模型文字 + layoutType；圖形版面 / 節點幾何 /
  連接線 / `drawingN.xml` 預渲染 shape / render wire-up 留未來 optional sprint。
  **與 user mc:Fallback 壓縮決策一致**（接受降級保真度）。
- **#8 / 決策 C**：4 個 `08_smartart/` 真實 fixture（混合策略的「真實」部分）
  經 integration test 端到端覆蓋；非 baseline 42 fixture（已排除於 VR）。
- **#22**：勘查 4 個真實 fixture 確認「無 mc:Fallback 圖、SmartArt 走 dgm 資料
  模型」後才定 capture 策略，未在錯誤心智模型上動工。

---

## 後續

- Phase 5.2 SmartArt render wire-up（線性文字 fallback 或 `drawingN.xml` 幾何
  render）— 未來 sprint。
- 下一步：Phase 5.3 Charts mc:Fallback capture（`07_chart/` 8 個真實 fixture
  已就緒）。

---

## Sprint 181 結尾累積指標

- vitest **1598 passed + 1 skipped**（`npm test` 全套；+21）
- VR mean **0.073191**（byte-identical 第 41 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 180 → **181**
- Phase 5.2 SmartArt capture 完成（render 留未來）

---

## File-level summary

```
M  static/src/core/ooxml/ast/types.ts              SmartArtNode + DocumentNode.smartArts?（+約 34）
A  static/src/core/ooxml/diagram/DiagramParser.ts   新模組 dgm 資料模型解析（+約 130）
A  static/src/core/ooxml/diagram/index.ts           re-export
M  static/src/core/ooxml/OoxmlParser.ts             collectSmartArts + Step 8.6 wire-up（+約 28）
A  tests/unit/DiagramParser.test.ts                 +17 test
A  tests/integration/sprint181_smartart_capture.test.ts  +4 test（真實 fixture）
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
M  tools/dist/visual_regression_pipeline.iife.js    VR bundle 重建
```

**淨 production code 變動 = +約 190 行**、capture-only、VR byte-identical 第 41 連、
Phase 5.2 SmartArt capture 完成。
