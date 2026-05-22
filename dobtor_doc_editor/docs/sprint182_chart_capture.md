# Sprint 182 — Chart 圖表 capture（Phase 5.3）

**日期**：2026-05-22
**類型**：新 parser 模組 + document-level capture（Phase 5.3 Charts、mc:Fallback 壓縮、capture-only）
**規畫書對應**：§5 階段 D Phase 5.3「Charts fallback（規畫書同 SmartArt 策略）」
**前置**：Sprint 181（Phase 5.2 SmartArt capture）；決策 C（user 2026-05-21 GO 全 6 子功能、Phase 5 大三項採 mc:Fallback 壓縮）

---

## Hypothesis

Phase 5.2 SmartArt capture 已收尾（Sprint 181）。本 sprint 推進 Phase 5.3 Charts
capture。

**Chart 結構勘查**（8 個 `07_chart/` 真實 fixture）：
- Chart 在 document.xml 以 `<w:drawing><wp:inline><a:graphicData
  uri=".../chart"><c:chart r:id>` 表示，圖本身**不內嵌** document.xml。
- `r:id` 以 rId 指向獨立的 `charts/chartN.xml`（`<c:chartSpace>` root）。
- **8 個 fixture 皆無 `<mc:AlternateContent>` / `<mc:Fallback>`** —— 同 Sprint 181
  SmartArt：規畫書原設想的「mc:Fallback 內嵌圖片」在真實檔不存在。
- 圖表資料存於 `chartN.xml` 的**數值快取**：`<c:strCache>` / `<c:numCache>`
  （Word 為離線顯示而存的資料副本），`<c:ptCount val>` + 稀疏 `<c:pt idx>`。

**mc:Fallback 壓縮策略的實際對應**（user 2026-05-21 拍板「接受降級保真度」）：
- Chart 無 fallback 圖 → 降級策略 = 取**數值快取**（圖表型別 + 標題 + 各數列的
  類別 / 數值），同 Sprint 181 SmartArt 取資料模型文字、Sprint 180 OMML 線性文字。
- 不重繪座標軸 / 圖例 / 圖形（degraded fidelity）；圖形 render 留未來 optional。

---

## 修法

### 1. 新型別 `ChartNode` / `ChartSeries`（types.ts、+約 42 行）

```ts
interface ChartSeries {
  name?: string;               // <c:tx> 快取文字（紀律 #21 無則不掛）
  categories: string[];        // <c:cat> 快取（依 c:pt idx 對位、缺漏點 ''）
  values: (number | null)[];   // <c:val> numCache（依 idx 對位、缺漏點 null）
}
interface ChartNode {
  rId: string;
  chartType: string;           // barChart / bar3DChart / pieChart / lineChart …
  title?: string;              // <c:title> 文字（紀律 #21 無則不掛）
  series: ChartSeries[];
}
```

`DocumentNode.charts?: ChartNode[]` —— optional（紀律 #21）；比照 `smartArts` /
`background` / `watermark` 的 conditional spread。

### 2. 新模組 `chart/ChartParser.ts`（+約 175 行）

`parse(xml, rId)`：解析 `charts/chartN.xml`。
- root 非 `<c:chartSpace>` / 無 `<c:chart>` / 無 `<c:plotArea>` / 無圖表型別
  元素 / XML 解析失敗 / undefined → 回 undefined（不 throw）。
- 圖表型別：`<c:plotArea>` 直屬子元素中第一個 localName 以 `Chart` 結尾者。
- 標題：`<c:title>` 內所有 `<a:t>` 拼接、trim。
- 每個 `<c:ser>`：
  - 名稱 ← `<c:tx>` 內第一個 `<c:v>`。
  - 類別 ← `<c:cat>` 快取（字串陣列）。
  - 數值 ← `<c:val>` numCache（`Number()` 轉換、非有限數 → null）。
- `readCachePoints`：讀 `<c:ptCount val>` 決定長度（缺則退回最大 idx+1）、
  `<c:pt idx>` 稀疏對位（缺漏點：類別 `''` / 數值 `null`，保持 cat ↔ val 同長對齊）。

### 3. OoxmlParser wire-up（+約 30 行）

- `REL_TYPE_CHART` 常數 + `chartParser` 欄位。
- Step 8.7 `collectCharts`：走 mainDoc `.rels`、抓所有 `type=chart` 關係
  （一份 docx 可含多個圖表）、依 rels 順序解析為 `ChartNode[]`。
- `charts.length > 0` 才 spread 進 `DocumentNode`（紀律 #21）。

### 4. 測試（+23）

- `tests/unit/ChartParser.test.ts`（+18）：防禦邊界（undefined / 壞 XML / 非
  chartSpace / 無 chart / 無 plotArea / 無圖表型別）、型別與標題（barChart /
  bar3DChart / pieChart / lineChart、title、紀律 #21 無 title）、數列（單/多
  數列 / 無 `<c:tx>` 無 name / 無 `<c:ser>` 空陣列）、快取點對位（稀疏 idx 補
  空 / 非數值 null / ptCount 缺漏退回 maxIdx+1 / 小數負數）。
- `tests/integration/sprint182_chart_capture.test.ts`（+5）：5 個真實
  `07_chart/` fixture 經 OoxmlParser 端到端驗證——圖表捕捉、chartType
  （barChart / bar3DChart）、數列數、類別軸內容、cat ↔ val 等長、數值型別。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1598 → **1621 passed + 1 skipped**（+23） |
| L2 VR v14 | ✅ **byte-identical 第 42 連** | rendered 42/42、comparedPages 126、failedPages 0；0/42 baseline fixture 含 Chart → `charts` 皆 undefined → DocumentNode 形狀不變 |
| L3 visual spot check | ✅ capture-only | 8 個 `07_chart/` fixture 各捕捉 1 圖表、型別 / 數列 / 類別 / 數值快取正確（degraded fidelity、無圖形 render） |

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js / SettingsParser
  position enum）、**無新增**。
- frontend bundle + VR IIFE bundle 重建（ChartParser / OoxmlParser 在依賴樹）。

**8 個真實 fixture 捕捉結果**：

| fixture | chartType | 數列數 |
|---|---|---|
| 預定進度表(通河).docx | barChart | 2 |
| 土方統計(浤欣)1140829.docx | barChart | 1 |
| 北投監造及工程標進度-113.06.15(任泰北投).docx | barChart | 6 |
| 北投監造及工程標進度-113.09.30(任泰北投).docx | barChart | 6 |
| 磺港溪C-A自主檢查統計1130311 / 1130401 / 1130401_2 / 1130527.docx | bar3DChart | 1 |

---

## 紀律

- **#1.a**：改 parser 跑全 42 fixture VR；capture-only、DocumentNode layout/render
  不消費 `charts` → byte-identical 第 42 連。
- **#1.b / Strategy C**：`charts` 只在文件真含圖表時掛 key；0/42 baseline fixture
  含 Chart → DocumentNode 形狀不變 → byte-identical 維持。
- **#21**：`DocumentNode.charts` / `ChartNode.title` / `ChartSeries.name` 無值不掛
  key（比照 `smartArts` conditional spread）。
- **#14（DRY）**：ChartParser 自成 `chart/` 子目錄（比照 `omml/` / `diagram/` /
  `watermark/` / `comments/`）；`collectCharts` 比照 Sprint 181 `collectSmartArts`
  的 rels 走訪模式；`parseXml` 防禦比照 CommentsParser / DiagramParser。
- **#18 scope-down**：capture 數值快取（型別 + 標題 + 數列資料）；座標軸 / 圖例 /
  圖形 render / 組合圖（combo chart）多型別 / scatter 的 xVal/yVal 留未來 optional。
  **與 user mc:Fallback 壓縮決策一致**（接受降級保真度）。
- **#8 / 決策 C**：8 個 `07_chart/` 真實 fixture（混合策略的「真實」部分）經
  integration test 端到端覆蓋；非 baseline 42 fixture（已排除於 VR）。
- **#22**：勘查 8 個真實 fixture 確認「無 mc:Fallback 圖、Chart 走 chartN.xml
  數值快取」後才定 capture 策略（同 Sprint 181 SmartArt 的勘查結論）。

---

## 後續

- Phase 5.3 Chart render wire-up（座標軸 / 圖形繪製或表格化 fallback）— 未來 sprint。
- **Phase 5 大三項（5.1 OMML / 5.2 SmartArt / 5.3 Charts）capture 全數完成**。
- 下一步：Phase 5 render wire-up 收尾、或 Phase 6 docx export 對稱性。

---

## Sprint 182 結尾累積指標

- vitest **1621 passed + 1 skipped**（`npm test` 全套；+23）
- VR mean **0.073191**（byte-identical 第 42 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 181 → **182**
- Phase 5.3 Chart capture 完成（render 留未來）；Phase 5 大三項 capture 全完成

---

## File-level summary

```
M  static/src/core/ooxml/ast/types.ts              ChartNode/ChartSeries + DocumentNode.charts?（+約 42）
A  static/src/core/ooxml/chart/ChartParser.ts       新模組 chartN.xml 數值快取解析（+約 175）
A  static/src/core/ooxml/chart/index.ts             re-export
M  static/src/core/ooxml/OoxmlParser.ts             collectCharts + Step 8.7 wire-up（+約 30）
A  tests/unit/ChartParser.test.ts                   +18 test
A  tests/integration/sprint182_chart_capture.test.ts  +5 test（真實 fixture）
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
M  tools/dist/visual_regression_pipeline.iife.js    VR bundle 重建
```

**淨 production code 變動 = +約 247 行**、capture-only、VR byte-identical 第 42 連、
Phase 5.3 Chart capture 完成（Phase 5 大三項 capture 全數完成）。
