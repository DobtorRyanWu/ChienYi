# Dobtor Doc Editor — 高保真 docx 匯入開發規劃

**目標等級**：對標 OnlyOffice / Google Docs 的 docx 匯入還原度（95%+ 真實文件無跑版）
**適用模組**：`/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor`
**當前基礎**：Odoo 18 OWL Component + @hufe921/canvas-editor + canvas-editor-plugin-docx + 自製 OOXML Parser（TypeScript）

**產出日期**：2026-04-20 / **最後更新**：2026-05-17（Sprint 122 — ParagraphParser OLE / VML pict 入口降級 placeholder 8 新 test + bundle rebuild + VR 0.073191 byte-identical；Phase 1 73→74%）

**當前指標一覽**（Sprint 110 結尾）：
- vitest **976 passed + 1 skipped** ✓
- VR mean **0.073191**（-2.3% from 0.0749 baseline）✓
- Odoo backend **21 passed**（font_serve 12 + zip_guard 9）✓
- Phase 0 **100%** / Phase 3 **93%** / 20 ADR / 18 條開發紀律

---

## 0. 當前狀態

### 0.1 累積進度摘要

Sprint 0 → Sprint 110 為止累積完成：

- **OOXML Parser**（14 子目錄、Section / HeaderFooter / Drawing / Numbering 全覆蓋）
- **Layout Engine**（Knuth-Plass / 分頁 / Table layout / wrapSquare / multi-column / cell-internal）
- **Renderer + BrowserCanvas**（含 char-level CJK 直書、image srcRect、cell vAlign）
- **Visual Regression v14**（42 fixture × 251 PNG golden、pixelmatch、page count 100% 對齊）
- **產品化基礎建設**（CI/CD、Zip Bomb 防護、Portal 整合、OWL 升級、QWeb 共存、版本管理、AutoSave、PDF 引擎 LibreOffice headless）
- **FontMetricsAdapter**（Sprint 62-65 落地 default-on、LO 系統 fallback fonts、VR mean -2.3%）
- **Performance cache 五連發 + LayoutCache**（Sprint 51-58、AST L1+L2 / image L1+L2 / layout L1、warm path 7×）
- **font_serve.py**（Sprint 64b-69、12 backend test 含 path traversal / null byte / URL-encoded CJK）

VR mean 進展：**0.1728**（Sprint 28 baseline）→ **0.1156**（Sprint 33）→ **0.0955**（Sprint 44 首次突破）→ **0.0774**（Sprint 45）→ **0.0749**（Sprint 48）→ **0.073191**（Sprint 65 font metrics default-on）。

**逐 sprint root cause / 修法 / 三層 SOP 結果**完整保留在 `docs/sprintN_*.md`（見 [§12 歷史索引](#12-歷史索引sprint-audit-docs)）。

### 0.2 Phase 完成度

| Phase | 完成度 | 說明 |
|---|---|---|
| Phase 0 能力盤點 | 100% | CI ✅ / CONTRIBUTING.md ✅（Sprint 67 落地）|
| Phase 1 OOXML Parser | 74% | 主流元素已覆蓋；Sprint 121 補 trHeight 入口防禦 4 項；Sprint 122 補 `<w:object>` / `<w:pict>` 降級 placeholder（italic 文字 + ProgID / alt 文案） |
| Phase 2 Text Shaping | 部分（FontMetricsAdapter -1.7%）| opentype.js 已用於字型 metric;HarfBuzz 為長期方案 |
| Phase 3 Layout Engine | 93% | page count 100% / VR mean 0.073191 |
| Phase 4 Style Theme | 80% | Sprint 19 style merge 落地 |
| Phase 4.5 產品化基礎建設 | 100% | 見附錄 A.1 |
| Phase 5+（註腳 / 追蹤修訂 / OMML） | 未開始 | 待 mean ≤ 0.07 後啟動 |
| Phase 7 效能優化 | 84% | cache 五連發 + LayoutCache + path coalescing + OffscreenCanvas probe |

### 0.3 三層 SOP（自 Sprint 23 起所有 sprint 適用）

1. **Vitest layer**：unit + integration 測試覆蓋 root cause;新增測試與既有測試 100% 兼容
2. **Visual Regression v14**：`scripts/visual_regression_v14.mjs` + 42 fixture × 126 pages × pixelmatch;fixture-level mean 收斂量化
3. **Visual spot check**：human-readable 比對 render PNG vs golden;確認結構性差異消除

每個 sprint 的 audit doc（[§12 索引](#12-歷史索引sprint-audit-docs)）含三層 SOP 的具體數據。完整紀律集合見 [§6.5](#65-18-條開發紀律)。

---

## 目錄

1. [現實評估與心理建設](#1-現實評估與心理建設)
2. [還原度標準定義](#2-還原度標準定義)
3. [架構總圖](#3-架構總圖)
4. [核心技術棧](#4-核心技術棧)
5. [Phase 規劃（12-18 個月）](#5-phase-規劃12-18-個月)
6. [測試、驗證與開發紀律](#6-測試驗證與開發紀律)
7. [程式碼組織](#7-程式碼組織)
8. [風險與備案](#8-風險與備案)
9. [人力與時程矩陣](#9-人力與時程矩陣)
10. [閱讀與參考清單](#10-閱讀與參考清單)
11. [下一步候選](#11-下一步候選)
12. [歷史索引（Sprint Audit Docs）](#12-歷史索引sprint-audit-docs)

---

## 1. 現實評估與心理建設

### 1.0 開工前必讀:Scope 對齊

**規畫書真實 scope = docx 1:1 高保真匯入**。Phase 0-7 全部 docx 匯入相關,**無電子簽章 phase**。

開工任何大型新 feature 前,先對齊本規畫書真實 scope。**看到 user 參考 UI 圖 / 第三方範例不等於規畫書方向**;user 說「根據計劃書繼續執行」= 規畫書 scope 內推進、不是順便加新功能。

歷史教訓:Sprint 90-109 曾誤判 user 提供的 dobtor esign 模組 demo 為「esign-style UI 改造」、執行 20 sprint 連續 batch 後全 revert(Strategy A 並存策略救命、byte-identical 救回)。**新 feature scope 與規畫書不符時優先誠實 revert、不是合理化保留**。詳見 [docs/sprint90_to_109_revert.md](docs/sprint90_to_109_revert.md)。

此原則於 [§6.5](#65-18-條開發紀律) 列為紀律 #18。

### 1.1 這是什麼等級的工程

**OnlyOffice / Google Docs 級 docx 匯入 = 重寫 1/3 個 Word**。

| 產品 | 團隊規模 | 開發年期 | 結論 |
|---|---|---|---|
| Microsoft Word | 500+ 工程師 | 35+ 年 | 市場標竿 |
| Google Docs Canvas 版 | 100+ 工程師 | 3+ 年（2018-2021 重寫） | 95% 還原 |
| OnlyOffice DocumentServer | 50+ 工程師 | 12 年 | 95%+ 還原 |
| WPS Office | 200+ 工程師 | 25+ 年 | 98% 還原 |
| LibreOffice Writer | 志工 + 企業 | 25+ 年 | 95% 還原 |

**若要達到這個標準**：
- **最小團隊**：3-5 名資深工程師
- **最短時程**：12-18 個月（有前面所有產品當參考）
- **若 1 人**：**2.5-4 年**（完全可行但要長期投入）

### 1.2 為什麼這麼難

Word `.docx` 的 OOXML 規格 **ECMA-376 Part 1 有 5000+ 頁**，Part 4（相容性）另外 1500+ 頁。Word 實際使用的行為**超出規格書**（所謂「Microsoft Word 實作方言」），需要大量逆向工程：
- 規格說 A，Word 做成 A'
- 規格沒寫的邊界情況，各版 Word 行為不同
- 早期 Word 2007 產出的 docx vs Word 365 產出的 docx，部分屬性語意微妙不同

### 1.3 canvas-editor 作為基礎的限制

@hufe921/canvas-editor 的原始定位是「**中文表單系統**」，不是「Word 相容編輯器」。它的缺口：

| 能力 | canvas-editor 現況 | Google Docs 需要 |
|---|---|---|
| Canvas 文字渲染 | ✅ 完整 | ✅ |
| 游標、IME、選取 | ✅ 完整 | ✅ |
| 分頁 | ✅ 基本 | ✅ + 跨頁切分邏輯 |
| 表格 | ⚠️ 基本合併 | ❌ 跨頁表格、複雜合併、巢狀 |
| 圖文繞排 | ❌ 無 | ✅ 四種 wrap 模式 |
| 分欄 | ❌ 無 | ✅ |
| 頁首頁尾不同節 | ⚠️ 有限 | ✅ 奇偶頁、首頁、分節 |
| 註腳尾註 | ❌ 無 | ✅ |
| 追蹤修訂 | ❌ 無 | ✅ |
| 文字 shaping | ⚠️ Browser 原生 measureText | ✅ HarfBuzz 級 |
| Knuth-Plass 斷行 | ❌ 貪婪斷行 | ✅ |
| CJK 避頭尾 | ⚠️ 基本 | ✅ 完整 |
| 浮水印 / 浮動文字方塊 | ❌ | ✅ |
| 公式（OMML） | ❌ | ✅ |
| SmartArt / 圖表 | ❌ | ✅ |

**結論**：若要達到 OnlyOffice / Google Docs 等級，**canvas-editor 必須大幅 fork 或部分替換**——至少排版引擎、表格引擎、文字渲染管線三大塊需要重寫或增強。

---

## 2. 還原度標準定義

### 2.1 分級標準（ISO 29500 相容性分級 + 自訂）

| 級別 | 描述 | 可見差異 |
|---|---|---|
| **S 級（像素一致）** | 與 Word 原圖每像素相同 | 0%（實務不可達） |
| **A 級（視覺一致）** | 與 Word 原圖差異 <1%，非專業人士看不出來 | OnlyOffice 對常見文件的水準 |
| **A- 級（視覺高還原）** | 差異 <5%，偶有微調（字距、行距） | Google Docs 對複雜文件的水準 |
| **B 級（結構正確）** | 段落、表格、樣式結構對，版面有差 | 多數開源方案、你目前的水準 |
| **C 級（內容保留）** | 字都在，格式大亂 | mammoth.js 水準 |

**本專案目標**：**A- 級**，對常見台灣商業 / 政府文件類型（合約、報告、工程文件、履歷、論文、公文）達 A 級。

### 2.2 成功指標（量化）

對 **50 份真實台灣企業 / 政府 docx 樣本集**：
- **內容保留**：字元 100% 保留（廢話）
- **結構保真**：段落、表格結構 100% 正確
- **版面還原**：
  - 頁面尺寸、邊界、分頁位置：100% 一致
  - 欄位寬度：≤5% 誤差
  - 行距、段距：≤2px 誤差
  - 字型、字重、字色：100% 正確
  - 表格合併（gridSpan / vMerge）：100% 正確
  - 圖文繞排位置：≤10px 誤差
- **視覺差異**：
  - pixelmatch 對比 LibreOffice headless 渲染的 PNG，差異率 <2%
  - 人工盲測 20 位，平均「無法分辨 vs 原檔」>80%

---

## 3. 架構總圖

```
┌────────────────────────────────────────────────────────────────┐
│  Odoo 18 Owl Component（doc_editor.js — 保留現有整合層）        │
│  AutoSave + Leader Election + Offline + 欄位變數                │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  【新】Importer 入口：importDocx(ArrayBuffer) → Document IR     │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Layer 1: Package 解壓與載入                                    │
│  jszip → ContentTypes → Relationships → Parts 索引              │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Layer 2: OOXML AST Parser（★ 最核心）                          │
│  document.xml / styles.xml / numbering.xml / theme.xml /        │
│  settings.xml / fontTable.xml / footnotes.xml / headers*.xml    │
│  → 完整 Document AST（TypeScript 嚴格型別）                     │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Layer 3: Style Resolver                                        │
│  docDefaults → theme → basedOn chain → pStyle/rStyle →          │
│  direct formatting → 最終 flatten 後的屬性樹                    │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Layer 4: Layout Engine（★ 關鍵差異化）                         │
│  - Text shaping: HarfBuzz WASM + opentype.js                    │
│  - Line breaking: Knuth-Plass + CJK 避頭尾                      │
│  - Pagination: 溢位推進 + widow/orphan + keepWithNext            │
│  - Table layout: 完整 CSS2 table-layout + 跨頁 + 合併            │
│  - Float/wrap: square / tight / through / topAndBottom          │
│  - Multi-column: balanced / unbalanced                          │
│  - Footnotes: 頁底錨定 + 跨頁編號                               │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Layer 5: Canvas Renderer（fork 後的 canvas-editor 或自寫）     │
│  - DPR 處理、虛擬化（只畫可視頁）                               │
│  - 字型載入器（WOFF2 + fallback 鏈）                            │
│  - Glyph 快取、LRU                                               │
│  - 游標 / 選取層（保留 canvas-editor 的實作）                   │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  Layer 6: Interaction（幾乎可沿用 canvas-editor）               │
│  - IME（composition events）                                     │
│  - hit-testing、鍵盤 / 滑鼠處理                                  │
│  - Undo/Redo、Copy/Paste                                         │
└────────────────────────────────────────────────────────────────┘
```

### 架構決策關鍵

**為何保留 canvas-editor 但要 fork**：
- ✅ 游標、IME、選取、Undo/Redo、事件系統——這些寫一次要 6-12 個月
- ❌ 它的 Layout Engine 是「表單導向」，不足以應付 Word 複雜版式
- 💡 **最佳策略**：保留它的 Interaction + Canvas 基礎設施，**替換 / 增強 Layout Engine**

---

## 4. 核心技術棧

### 4.1 依賴清單

| 層次 | 套件 | 授權 | 用途 |
|---|---|---|---|
| 解壓 | `jszip` 或 `fflate` | MIT | docx unzip（fflate 快 3x） |
| XML | `fast-xml-parser` | MIT | OOXML → JS object |
| 文字 shaping | **`harfbuzzjs`** | MIT | Glyph shaping、kerning、ligatures |
| 字型解析 | `opentype.js` | MIT | 讀 OTF/TTF metrics、glyph paths |
| 字型 fallback | `fontkit` | MIT | 補 opentype.js 不足 |
| 斷行 | 自寫 Knuth-Plass（參考 `typeset`） | - | 中英文段落斷行 |
| 顏色 | `color-string` | MIT | theme color resolving |
| 圖片 | `browser-image-compression`（選用） | MIT | 大圖壓縮 |
| 公式 | `katex` 或 `mathjax` | MIT/Apache | OMML → MathML → 渲染 |
| 圖表 | `chart.js` 或自寫 SVG | MIT | 基本圖表類型 |
| 語言偵測 | `franc-min`（選用） | MIT | 字型 fallback 輔助 |
| 協作 CRDT（未來） | `yjs` | MIT | 協作編輯 |

### 4.2 WASM 模組

**HarfBuzz WASM** 是 Google Docs / Figma 使用的核心。整合方式：
```ts
import hbjs from 'harfbuzzjs'
const hb = await hbjs()
const face = hb.createFace(fontBlob)
const font = hb.createFont(face)
const buffer = hb.createBuffer()
buffer.addText("台灣 Taiwan")
buffer.guessSegmentProperties()
hb.shape(font, buffer)
const glyphs = buffer.json()  // 精確的 glyph advance、kerning
```

**不用 HarfBuzz 的代價**：
- `ctx.measureText()` 不處理 kerning pairs（Word 預設開啟）
- 不處理 ligatures（英文 fi、fl 連字）
- 複雜文字（阿拉伯、印度文）完全無法顯示
- CJK 字距微調錯誤

---

## 5. Phase 規劃（12-18 個月）

### Phase 0：能力盤點與架構決策（2 週）

**當前狀態**：100%（見 [§0.2](#02-phase-完成度)）。CI、fixtures、技術選型、CONTRIBUTING.md 全部落地。實際產出見 [附錄 A](#附錄-a phase-0-任務清單)。

---

### Phase 1：OOXML 完整 Parser（2-3 個月）

**當前狀態**：72%。`static/src/core/ooxml/` 已有 14 子目錄（document / table / styles / font / drawing / numbering / section / headerFooter ...）。主流元素已覆蓋:1.1 Package、1.2 Units、1.3 Styles（含 basedOn 多層繼承）、1.4 Paragraph/Run/Text（含 CJK 1.15 em empirical;Sprint 61 揭示為 LO render anchor 的經驗校準）、1.5 Tables（含 vMerge、tcBorders、textDirection 6 種值 Sprint 34 完整解析）、1.6 Numbering、1.7 Sections（含 docGrid + snapToGrid Sprint 29）、1.8 Drawings 基本 image render + image srcRect（Sprint 15、Sprint 40）。

**待補**：1.5 進階屬性（rowHeight calcInternal 細節）、1.8 OLE objects、1.9 進階結構（field code 部分、追蹤修訂、SDT、OMML）。

目標：**把任何合法 docx 100% 解析成 Document AST**，屬性無遺漏。

#### 1.1 Package 與 Relationships（1 週）
- `DocxPackage` class：載入 zip、暴露 `getPart(name)`
- 解析 `[Content_Types].xml` — 每個 part 的 MIME type
- 解析全部 `.rels` 檔：rId → target 映射
- 資源管線：圖片 / 字型 / 頁首頁尾 part 索引

#### 1.2 單位系統（2 天）
- `units.ts`：twips、dxa、half-points、EMU、points、pct → px
- DPI 處理（DPI 96 vs 72 vs 150）

#### 1.3 Styles 與繼承鏈（2 週）
- `StyleRegistry` 載入 `styles.xml`、`<w:docDefaults>` 預設值、`<w:style>` 各種類型
- `basedOn` 多層繼承 resolver（含迴圈偵測）
- 樣式 flatten：直接屬性 > pStyle / rStyle > docDefaults

#### 1.4 Paragraph / Run / Text（2 週）
- `<w:p>` + `<w:pPr>`：對齊、縮排、間距、行距、tab stops、tabs
- `<w:r>` + `<w:rPr>`：字型(rFonts 四屬性)、sz、b、i、u、strike、color、highlight、vertAlign（上下標）、spacing（字距）
- `<w:t xml:space="preserve">` 空白保留
- `<w:tab>`、`<w:br type="page|column|textWrapping">`、`<w:symbol>` / `<w:sym>`、`<w:ruby>`

#### 1.5 表格完整解析（3 週）★ 跑版的主戰場

##### 1.5.1 結構
- `<w:tbl>`、`<w:tr>`、`<w:tc>`、`<w:tblGrid>` + `<w:gridCol w:w="...">` 欄寬定義

##### 1.5.2 儲存格屬性
- `<w:tcW>` 三種 type：`dxa` / `pct` / `auto` / `nil`
- `<w:gridSpan>` 橫向合併、`<w:vMerge>` `restart` / 無值=continue 演算法
- `<w:tcBorders>` + `<w:tblBorders>` 衝突解決（ECMA-376 17.4.65 優先級表）
- `<w:shd>` 底色（含 theme color + tint/shade）
- `<w:tcMar>` 儲存格邊界、`<w:vAlign>` top / center / bottom（Sprint 42 落地）
- `<w:noWrap>`、`<w:hideMark>`、`<w:tcFitText>` — 自動縮字

##### 1.5.3 列與表屬性
- `<w:trHeight>`：`hRule` = `exact` / `atLeast` / `auto`（Sprint 45-48 連四 sprint 突破:val-as-min 比較基準改 naturalUnsnapped、含 image 列 honors trHeight val）
- `<w:tblHeader>` — 跨頁重複標題列
- `<w:cantSplit>` — 列不可跨頁拆分
- `<w:tblPr>` 完整屬性、`<w:tblStylePr>` — 條件樣式（15 種）
- 巢狀表格（cell 內又有 tbl）

##### 1.5.4 vMerge 演算法獨立模組
```ts
function resolveVerticalMerges(table: Table): Table {
  // 1. 建立 column index map（因 gridSpan 導致欄位不對齊）
  // 2. 遍歷每欄，找 vMerge=restart 的 anchor cell
  // 3. 從 anchor 往下掃，累計連續 vMerge=continue
  // 4. 設定 anchor rowspan = N，標記 continue cells 為 hidden
}
```
**關鍵細節**：vMerge 的 column 判定不能用欄位索引（會被 gridSpan 打亂），要用**累計 grid 位置**。

#### 1.6 Numbering（列表編號）（1 週）
- `<w:num>` + `<w:abstractNum>` 二層結構、多層級（`<w:lvl ilvl="0..8">`）
- 編號格式:decimal、lowerRoman、upperRoman、lowerLetter、upperLetter、bullet、ordinal、cardinalText、ordinalText、chineseCounting、chineseCountingThousand、ideographDigital、japaneseCounting、aiueo、iroha、taiwaneseCounting
- 重啟層級 / 局部覆寫 / 編號連續性（跨段落計算）

#### 1.7 Sections 與頁面（1 週）
- `<w:sectPr>`：`<w:pgSz>`、`<w:pgMar>`、`<w:pgBorders>`、`<w:pgNumType>`
- `<w:headerReference>`、`<w:footerReference>` type:`default` / `even` / `first`
- 頁首頁尾 parts 解析、`<w:cols>` 分欄、`<w:footnotePr>` / `<w:endnotePr>`、`<w:docGrid>` — CJK 行格

#### 1.8 Drawings 與 OLE（1.5 週）
- `<w:drawing>` > `<wp:inline>` 內嵌圖片
- `<w:drawing>` > `<wp:anchor>` 浮動圖片:positionH / positionV、wrap 五種、extent / effectExtent
- `<a:blip r:embed="rIdN">` → 從 rels 取得圖片 part
- 圖片裁切 `<a:srcRect>`（Sprint 40 落地）、圖片效果（陰影、外框）— 可選
- `<v:shape>` VML（舊 Word 的圖形） — 降級處理

#### 1.9 進階結構（2 週）
- `<w:footnoteReference>` + `footnotes.xml`、`<w:endnoteReference>` + `endnotes.xml`
- `<w:hyperlink>` + rels 查詢
- `<w:fldSimple>` / `<w:instrText>` 欄位（PAGE、DATE、SEQ、複雜欄位）
- `<w:bookmarkStart>` / `End`、`<w:sdt>` 結構化文件標籤
- `<w:ins>`、`<w:del>`、`<w:moveFrom>`、`<w:moveTo>` 追蹤修訂
- `<w:commentRangeStart>` + `comments.xml` 註解
- `<m:oMath>` 數學公式（OMML）— parser 出 AST，渲染留到 Phase 5
- `<mc:AlternateContent>` — 新舊版本相容選擇

**Exit Criteria**：
- Parser 對 50 份測試 docx 全部無 error
- AST dump 對照 OOXML 原文，屬性吻合率 >99%
- 有完整 TypeScript 型別

---

### Phase 2：Text Shaping 與字型管線（1-1.5 個月）

**當前狀態**:FontMetricsAdapter Sprint 62-65 已 default-on、VR mean -2.3% 命中(opentype.js + LO 系統 fallback fonts DroidSansFallback + LiberationSerif)。Sprint 14 nodeModuleStub 47-sprint 隱性 IIFE bundle blocker 已揭示並修復(FontMetrics.ts 改用 ESM `import * as opentypeNs`)。HarfBuzz 為長期方案;Sprint 60 OffscreenCanvas probe 證實 worker render 技術可行性 GREEN。Sprint 61 BrowserTextMetrics negative 揭示 goldens 是 LO render anchor — Sprint 28 1.15em 是經驗校準 LO。

**這是 Google Docs 級和 B 級方案的根本差異**。

#### 2.1 HarfBuzz WASM 整合（1-2 週）
- 整合 `harfbuzzjs` WASM
- `ShapingEngine` 封裝:input `(text, font, features)` → output `Glyph[]` with `(glyphId, xAdvance, yAdvance, xOffset, yOffset)`
- Script & Language 偵測（Unicode bidi class）
- Feature 開關:kerning (`kern`)、連字 (`liga`/`dlig`)、variant (`ss01`...)

#### 2.2 字型載入與 fallback（1-2 週）
- 從 `fontTable.xml` 讀字型名稱
- 字型載入器:系統已安裝直接用 / 系統沒有的嘗試用 WOFF2 CDN 補 / 仍缺 → fallback 鏈
- **CJK fallback 鏈**:原字型 → 思源黑體 / 微軟正黑體 → 新細明體 → 預設字型
- 字元涵蓋檢測:每個 codepoint 確認字型支援
- Glyph 快取(key: font+codepoint+size)
- Sprint 64b 落地 `/dobtor/fonts/*` backend + FontLoader frontend(Sprint 69 完成 candidate fallback chain;container 用 NotoCJK)

#### 2.3 Text Metrics 精確化（1 週）
- `opentype.js` 讀取字型的:ascender、descender、lineGap、x-height、cap-height
- 行高計算:`lineHeight = (ascent + descent + lineGap) * size / unitsPerEm`
- 替代 `ctx.measureText()` 為自己的 `measureRun(text, rPr)` ← Sprint 62 FontMetricsAdapter 落地

**Exit Criteria**：
- 同一段中英文混排，shaping 結果與 Word 的字距一致
- CJK 字型無缺字方塊
- ligatures 正常

---

### Phase 3：Layout Engine（3-4 個月）★ 決定還原度的核心

**當前狀態**:93% — page count 100% / VR mean 0.073191。Sprint 44-48 連四 sprint 突破(image-only line baseline=height / trHeight val-as-min / containsImage 二分 / val-as-min 比較基準改 naturalUnsnapped);Sprint 36 揭示「資料先行優於假設先行」、Sprint 43 揭示「Pillow 雙路徑診斷」、Sprint 49 揭示 docGrid snap 全域翻車需段落層級判別子。詳見 [§12](#12-歷史索引sprint-audit-docs) Sprint 34-49 子段。

#### 3.1 Knuth-Plass 斷行（2-3 週）
- 實作 boxes / glue / penalty 模型、可變行寬（float 附近行變窄）
- 中文避頭尾規則:行首禁止 `。、，；：！？、」』）】》`等;行尾禁止 `「『（【《`等;連續數字 / 英文不拆
- 齊行(justify):西文調 space、中文調字距
- 連字符號(hyphenation)— 英文可用 `hypher` library，中文不需要

#### 3.2 分頁引擎（2-3 週）
```
current_y = 頁首下緣
for each block in flow:
  measure block height
  if overflow:
    widow/orphan check
    keepWithNext / keepLinesTogether 檢查
    break page → 重設 current_y
  render block
  current_y += height
```
- 表格列跨頁:`cantSplit`、`tblHeader` 重複
- 段落被分頁時的續行規則、頁首頁尾 rendering、頁碼計算
- 分節符 section break 切頁並重設設定（`nextPage`、`continuous`、`evenPage`、`oddPage`）

#### 3.3 Table Layout 完整版（3-4 週）★ 跑版的根本解法
- CSS2 `table-layout: fixed` 完整實作、`auto`（啟發式，NP-hard 簡化）
- 合併儲存格寬度計算(gridSpan 合計 + vMerge 跨列)
- Border conflict resolution(OOXML 17.4.65 優先級表，共 8 級)
- 跨頁表格:切割位置計算 / 重複 header rows / 跨頁 border 處理
- 巢狀表格遞迴佈局、表格浮動

#### 3.4 Float / Wrap 浮動繞排（2-3 週）
- `wrapNone` / `wrapSquare`(最常用) / `wrapTopAndBottom` / `wrapTight`(緊密輪廓繞排，**最難**) / `wrapThrough`
- 多個浮動物件共存時的避讓邏輯、整合進 Knuth-Plass:行寬依 y 位置動態變化

#### 3.5 分欄（Multi-column）（1-2 週）
- 等寬欄與不等寬欄、欄間距、Column balancing、欄分隔線、Column break 強制換欄

#### 3.6 註腳與尾註（1-2 週）
- 註腳錨點文字 → 頁底註腳區、尾註累計到文件末 / 節末
- 編號格式（自動重啟 vs 連續）、註腳區與內文區的空間博弈
- 註腳間的分隔線(separator)

**Exit Criteria**：
- 50 份測試文件 pixelmatch vs LibreOffice 渲染差異 <5%
- 複雜表格 100% 結構正確

---

### Phase 4：Style & Theme 完整（1 個月）

**當前狀態**:80%。Sprint 19 style merge 落地。剩餘:Theme color tint/shade 演算法、tblStylePr 15 種條件樣式進階、編號樣式中文格式完整、Paragraph 進階（pBdr、tab stop leader / decimal、textAlignment）。

#### 4.1 Theme 系統（1 週）
- 解析 `theme1.xml` colorScheme(12 色)、fontScheme(6 組)
- Theme color resolver:`<w:color w:themeColor="accent1" w:themeTint="60"/>` → 具體 hex
- Tint/shade 演算法(HSL luminance 計算)

#### 4.2 Style 條件式與進階（1 週）
- `<w:tblStylePr>` 15 種條件、字元樣式 + 段落樣式的合併順序、樣式連結

#### 4.3 編號樣式（1 週）
- 編號文字的字型大小、顏色獨立於段落
- 編號與段落的間距(`<w:suff>` = `tab` / `space` / `nothing`)
- 中文編號格式完整支援、`<w:lvlText>` 模板解析

#### 4.4 Paragraph 進階（1 週）
- `<w:frame>` 段落框、`<w:pBdr>` 段落邊框 + 陰影、`<w:tab>` tab stop 進階、`<w:textAlignment>`

**Exit Criteria**：對測試文件的字型、顏色、編號、邊框 100% 吻合 Word 視覺。

---

### Phase 4.5：產品化基礎建設（10 週，**已落地**）

**當前狀態**：100%（Sprint 20-24 落地）。實際產出見 [附錄 A.1](#附錄-a1產品化補強清單)。

關鍵決策:
- **PDF 引擎**:LibreOffice headless(拒 Chromium headless:CJK 字型支援差 + 啟動慢 3x);PSNR + pHash 黃金檔比對 pipeline
- **與 QWeb 共存**:QWeb PDF(自動產出、固定樣板)/ dobtor(協作編輯、版本歷史);決策樹見 [docs/scope_decision.md](docs/scope_decision.md)
- **ChienYi mixin**:`doc.linked.mixin` 讓 construction_supervision_base / notification_slip / daily_log_sheet 繼承關聯文件
- **Zip Bomb 防護**:50MB 原檔 / 200MB 解壓 / ≤1000 entry / 深度 ≤16;OWASP corpus + nested-zip fixture 攔下
- **ACL**:portal user white-list per-doc / internal user 全局管理

---

### Phase 5：進階功能（2-3 個月）

**當前狀態**：未開始。待 VR mean ≤ 0.07 後啟動。

#### 5.1 數學公式（OMML → KaTeX/MathJax）（3-4 週）
- `<m:oMath>` AST 解析、OMML → MathML converter
- MathML → KaTeX / MathJax 渲染、inline vs display math 排版、無障礙 alt text

#### 5.2 SmartArt（1-2 個月）
- `diagram*.xml` 解析(data1 / layout1 / colors1 / quickStyle1)
- 常見佈局:list、cycle、hierarchy、relationship、matrix、pyramid
- Fallback:顯示預先 render 的圖片(`mc:Fallback` 內的 `w:pict`)
- **建議**:優先走 fallback 路線，只對最常見 3-5 種 layout 做原生渲染

#### 5.3 Charts（1-2 個月）
- `chart1.xml` 解析(DrawingML Charts 規格)
- 主要類型:bar、column、line、pie、scatter、area;套用 theme color
- **建議**:同 SmartArt，優先走 fallback 圖片路線

#### 5.4 追蹤修訂（1 週）
- `<w:ins>`、`<w:del>` 渲染、作者識別、UI 互動接受 / 拒絕修訂、Side panel

#### 5.5 註解（1 週）
- `<w:commentRangeStart>` / `End` 渲染、右側註解面板、回覆、解決狀態

#### 5.6 浮水印與背景（3-5 天）
- 頁首內 VML 浮水印解析、背景圖片 / 背景色(`<w:background>`)

**Exit Criteria**：公式顯示與 Word 視覺相符;SmartArt / 圖表至少有 fallback 圖片;追蹤修訂、註解功能堪用。

---

### Phase 6：匯出對稱性（1-2 個月，選做）

docx 匯出是 parser 的反向:Document IR → OOXML → zip。

- 各層 AST → XML serializer、relationship 自動產生、Content types 自動維護
- **黃金測試**:`import(export(doc)).should.equal(doc)`
- 圖片重打包、針對 Word / OnlyOffice / LibreOffice 三端驗證開啟

---

### Phase 7：效能優化與邊緣（持續）

**當前狀態**:84% — Sprint 50 基線量測(parse 60.7% 為瓶頸)、Sprint 51-58 cache 五連發 + LayoutCache(AST L1+L2、image L1+L2、layout L1;full-warm 7×、warm 94.1% render)、Sprint 59 drawLine path coalescing(架構為 worker postMessage 介面打底)、Sprint 60 OffscreenCanvas probe GREEN(puppeteer 4/4 features、postMessage ~5ms)。Sprint 57 揭示 unit spy 不反映 OOXML pixels(紀律 #1/#2)、aggressive fast path 翻車已 revert。

- 大文件優化:50+ 頁流暢開啟、>200 頁可用（**待 user 提供 50+ 頁 fixture**;Sprint 53 可視頁虛擬化已落地、當前 ≤6p fixture 限制全域 payoff）
- 虛擬化:只渲染可視頁 ± 2 頁(Sprint 53 IntersectionObserver 已落地)
- Web Worker 搬運:parser + shaping 在 worker 跑(Sprint 60 probe 證實可行;cache 已消除 parse 痛感、優先級下降)
- IndexedDB 快取 parsed AST(Sprint 52 落地;跨 page 2.38×)
- 增量渲染、邊緣 docx 相容(Word 2007 舊版、libreoffice、WPS)

---

## 6. 測試、驗證與開發紀律

### 6.1 測試金字塔

```
         ┌─────────────────┐
         │   Visual E2E    │   ← pixelmatch vs LibreOffice
         │   (50 fixtures) │
         ├─────────────────┤
         │  Golden File    │   ← AST dump diff
         │  (200+ cases)   │
         ├─────────────────┤
         │   Integration   │   ← parser + layout 端到端
         │   (500+ cases)  │
         ├─────────────────┤
         │   Unit tests    │   ← 每個 parser 函數
         │   (2000+ cases) │
         └─────────────────┘
```

### 6.2 Visual Regression Pipeline

```bash
# 每份 fixture docx 產出 3 組 PNG
npm run test:visual

# Step 1: LibreOffice headless → reference.png
libreoffice --headless --convert-to pdf fixture.docx
pdftoppm reference.pdf reference -png

# Step 2: Our Canvas renderer → actual.png
node render.js fixture.docx > actual.png

# Step 3: pixelmatch diff
pixelmatch reference.png actual.png diff.png
# → 失敗條件:差異 > 2%
```

### 6.3 Fixture Sets

| 類別 | 數量 | 來源 |
|---|---|---|
| 通用商業文件 | 10 | 合約、報價、報告範本 |
| 台灣政府公文 | 10 | 各部會公文範本、統一發票、工程表單 |
| 學術論文 | 5 | 論文 template（含註腳、公式） |
| 履歷 / 簡歷 | 5 | 複雜多欄排版 |
| 表格密集 | 10 | 財報、產品規格、工程表單 |
| 圖文混排 | 5 | 型錄、行銷文宣 |
| 邊界測試 | 5 | 極端嵌套、超大表格、特殊字型 |

當前 42 份 fixture 已備齊;50+ 頁大文件 fixture 待補(見 [§11.1](#111-待-user-決策))。

### 6.4 Benchmarking

- 效能：50 頁文件匯入 <3 秒、渲染首屏 <1 秒
- 記憶體：200 頁文件 <300MB
- 保真：pixelmatch 平均差異 <2%、最差 <5%

### 6.5 18 條開發紀律

紀律從 Sprint 50 → Sprint 110 累積萃取。完整版定義含「Why / How to apply」見 [CONTRIBUTING.md](CONTRIBUTING.md) 第 5 章「Sprint 紀律」與 [docs/sprint111_discipline_sync_after_revert.md](docs/sprint111_discipline_sync_after_revert.md)。

| # | 揭示 Sprint | 紀律 |
|---|---|---|
| 1 | 57 | 改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR — 單元測試 spy 不反映 OOXML pixels |
| 2 | 57 | 單元測試用 spy 驗 API、VR 驗 pixels — 兩者都綠才算過 |
| 3 | 60 | 高風險改造前先 probe sprint 收集事實 |
| 4 | 61 | 負面結果 sprint 仍有結構價值;揭示隱性 assumption 是真實學習 |
| 5 | 62 | vitest 通過不保證 IIFE bundle 同 code 也 work（nodeModuleStub 47-sprint blocker 教訓）|
| 6 | 63 | Promote default 前先做 per-fixture delta 分析 |
| 7 | 65 | Mechanical commit 是多 sprint 紀律性投資的內化、適用 docs / process |
| 8 | 64b | 架構發現的 sprint 也要記下來 — 開工前 grep 發現 production 路徑時誠實重定位 |
| 9 | 67 | §附錄 A `[ ]` 項是 autonomous sprint 優先選擇 — 規畫書列出但未做的事項也是 sprint 候選 |
| 10 | 68 | Catch-up sprint 應補到「與當前紀律標準對齊」，不只最低限度 |
| 11 | 69 | Controller 觸碰 filesystem 路徑時必須 cross-check production 環境（container）實際路徑、不是 dev 環境路徑 |
| 12 | 70-89 | 廣域應用:紀律應用於 controller / model / wizard / dev tool / ACL 五個 sub-domain |
| 13 | 70-89 | Backend test infra 需一鍵跑 + Makefile target |
| 14 | 70-89 | Docs 同步:CONTRIBUTING.md / glossary 紀律列表需 catch-up |
| 15 | 70-89 | Security 測試應與 happy path 並列 |
| 16 | 70-89 | Disabled / skipped 項應紀錄 rationale |
| 17 | 70-89 | ACL 變更必須有 backend test |
| **18** | **110** | **開工大型新 feature 前必須先對齊規畫書真實 scope — Sprint 90-109 esign UI revert 教訓（見 [§1.0](#10-開工前必讀scope-對齊)）** |

### 紀律 #14 子原則(累積)

- **#14.a**(Sprint 111):集中索引(CONTRIBUTING / glossary)必須在新紀律確立時即時更新、不是事後 catch-up
- **#14.b**(Sprint 113):**規畫書 §11 候選達 30+ sprint 規模時、應外部化為 roadmap doc**。本規畫書是「規劃」、roadmap 是「執行排程」、職責分離避免規畫書再度膨脹。詳見 [docs/autonomous_roadmap.md](docs/autonomous_roadmap.md)。
- **#15 子原則**(Sprint 114):**security test 要進 CI gate 才算「跑」**。local `make test-backend-*` 跑只算「能跑」、CI workflow 強制每次都跑才算 enforce。延伸出**漸進式 CI gate 模式**:dispatch v1(manual)→ 3 次穩定後 nightly v2(schedule cron)→ 3 次穩定後 push/PR gate v3。詳見 [docs/sprint114_ci_font_serve_gate.md](docs/sprint114_ci_font_serve_gate.md)。

完整版紀律定義含「Why / How to apply」見 [CONTRIBUTING.md](CONTRIBUTING.md) 第 5 章「Sprint 紀律」與 [docs/sprint111_discipline_sync_after_revert.md](docs/sprint111_discipline_sync_after_revert.md)、[docs/sprint113_autonomous_roadmap.md](docs/sprint113_autonomous_roadmap.md)。

---

## 7. 程式碼組織

```
dobtor_doc_editor/static/src/
│
├── lib/
│   ├── canvas_editor_fork/          ← fork 並 patch 的 canvas-editor
│   │   ├── PATCHES.md               ← 所有修改記錄
│   │   ├── UPSTREAM.md              ← 與 upstream 的 sync 流程
│   │   └── src/
│   │       ├── editor/core/draw/particle/table/   ← 大改
│   │       ├── editor/core/draw/LayoutEngine.ts   ← 新增（取代原流程）
│   │       └── ...
│   ├── harfbuzz_wasm/
│   └── third_party/
│
├── docx/                             ← 本次開發主體
│   ├── package/                      ← Layer 1
│   │   ├── DocxPackage.ts
│   │   ├── ContentTypes.ts
│   │   └── Relationships.ts
│   │
│   ├── parser/                       ← Layer 2
│   │   ├── DocumentParser.ts
│   │   ├── ParagraphParser.ts
│   │   ├── RunParser.ts
│   │   ├── TableParser.ts
│   │   ├── DrawingParser.ts
│   │   ├── NumberingParser.ts
│   │   ├── SectionParser.ts
│   │   ├── FootnoteParser.ts
│   │   ├── FieldParser.ts
│   │   ├── TrackChangeParser.ts
│   │   ├── OMathParser.ts
│   │   └── SmartArtParser.ts
│   │
│   ├── ast/                          ← 型別定義
│   │   ├── Document.ts
│   │   ├── Paragraph.ts
│   │   ├── Run.ts
│   │   ├── Table.ts
│   │   ├── Drawing.ts
│   │   └── index.ts
│   │
│   ├── style/                        ← Layer 3
│   │   ├── StyleRegistry.ts
│   │   ├── StyleResolver.ts
│   │   ├── ThemeResolver.ts
│   │   └── NumberingEngine.ts
│   │
│   ├── layout/                       ← Layer 4（★ 核心）
│   │   ├── LayoutEngine.ts
│   │   ├── TextShaper.ts             ← HarfBuzz 封裝
│   │   ├── LineBreaker.ts            ← Knuth-Plass
│   │   ├── CJKRules.ts               ← 避頭尾
│   │   ├── Paginator.ts
│   │   ├── TableLayout.ts
│   │   ├── FloatWrapper.ts
│   │   ├── ColumnLayout.ts
│   │   └── FootnotePlacer.ts
│   │
│   ├── font/                         ← 字型管線
│   │   ├── FontLoader.ts
│   │   ├── FontFallback.ts
│   │   ├── CJKFallback.ts
│   │   ├── GlyphCache.ts
│   │   └── FontMetrics.ts
│   │
│   ├── math/
│   │   ├── OmmlToMathML.ts
│   │   └── MathRenderer.ts
│   │
│   ├── chart/
│   │   └── ChartRenderer.ts
│   │
│   ├── smartart/
│   │   └── SmartArtFallback.ts
│   │
│   ├── mapper/                       ← AST → canvas-editor-fork IR
│   │   └── ToCanvasEditor.ts
│   │
│   ├── utils/
│   │   ├── units.ts
│   │   ├── colorResolver.ts
│   │   ├── scriptDetect.ts
│   │   └── xml.ts
│   │
│   └── index.ts                      ← importDocx(ArrayBuffer): Promise<Document>
│
├── components/
│   └── doc_editor/                   ← 保留現有 OWL 整合層
│       ├── doc_editor.js
│       └── doc_editor.xml
│
├── core/                             ← 保留 AutoSave / Leader / Offline
└── css/
```

---

## 8. 風險與備案

### 8.1 主要風險

| 風險 | 機率 | 影響 | 對策 |
|---|---|---|---|
| canvas-editor 渲染層天花板碰到 | 高 | 大 | Phase 0 盤點清楚，必要時走 Plan B |
| HarfBuzz WASM 整合複雜 | 中 | 中 | 先做 spike，有問題改用 `pdf.js` 的字型方案 |
| OOXML 邊界情況永無止境 | 高 | 中 | 建立 issue tracker，依使用者實際檔案優先 |
| 時程超過 18 個月 | 中 | 大 | 按 Phase 停損，任一 Phase 超 50% 重評估 |
| 效能不佳 | 中 | 中 | Worker + 虛擬化 + IndexedDB 快取從 Phase 1 就埋 |
| 人員流失 | 中 | 大 | 文件優先，每個模組有獨立 README |
| 被 Word 新版規格打敗 | 低 | 中 | 只支援 ECMA-376 1st / 2nd / 3rd edition 穩定部分 |
| **Scope drift（誤判 user 意圖偏離規畫書）** | **中** | **大** | **[§1.0](#10-開工前必讀scope-對齊) Scope 對齊;新 feature 與規畫書不符優先誠實 revert** |

### 8.2 Plan B：若自研版 Layout Engine 太吃重

**備案**：**分階段替換** canvas-editor，不一次打掉：
1. 第 1 年：專注 Parser 完善 + canvas-editor patch（目標 B+ 級還原度）
2. 第 2 年：新 Layout Engine 獨立開發，可選切換引擎
3. 第 3 年：新引擎為主力，canvas-editor 退役為選項

### 8.3 Plan C：若需要提前上線

- **前 6 個月**:達 B+ 級(結構正確、表格合併正確、常見格式對)
- **中 6 個月**:達 A- 級(字型、行距、分頁精確)
- **後 6 個月**:達 A 級(對複雜文件)

先產品化 B+ 級版本服務客戶，邊做邊升級。

---

## 9. 人力與時程矩陣

### 9.1 單人全職

| 到達水準 | 時程 |
|---|---|
| B 級（結構正確、常見 docx OK） | 6-8 個月 |
| B+ 級（字型樣式 OK） | 12 個月 |
| A- 級（視覺高還原） | 18-24 個月 |
| A 級（對標 Google Docs） | 30-36 個月 |

### 9.2 三人團隊（建議配置）

| 角色 | 專精 | 負責 Phase |
|---|---|---|
| 工程師 A | OOXML、XML、Node | Phase 1（Parser）、Phase 4（Style）、Phase 6（Export） |
| 工程師 B | Canvas、算法、排版 | Phase 2（Shaping）、Phase 3（Layout）、Phase 5 部分 |
| 工程師 C | 前端、測試、DevOps | Phase 0（基建）、canvas-editor fork patch、測試體系、Phase 5 UI 類 |

**時程**：10-14 個月到 A- 級。

### 9.3 五人團隊

**時程**：7-10 個月到 A- 級，12-15 個月到 A 級。
增加：2 位 Layout Engine 專職工程師（分 Paginator / TableLayout / FloatWrapper）。

### 9.3b 產品化緩衝（已落地，+10 週）

§9.1-9.3 純技術時程外，進入正式業務流程前需要 ~10 週的產品化補強衝刺(CI/CD、Zip Bomb、Portal ACL、OWL 升級、QWeb 共存、ChienYi mixin、版本管理 UI、AutoSave、Python tests、PDF 引擎)。Sprint 20-24 已落地;若跳過會在進入正式業務時被迫補回。詳見 [Phase 4.5](#phase-45產品化基礎建設10-週已落地) 與 [附錄 A.1](#附錄-a1產品化補強清單)。

**結論**:單人方案到 B 級從 6-8 個月變 8-10 個月;三人方案到 A- 級從 10-14 個月變 12-16 個月。

### 9.4 建議起手配置

**第 1-3 個月**:1 人先做 Phase 0 + Phase 1.1-1.5，把架構跑通、第一批 fixture 能解析。
**第 4 個月起**:招第二人加入做 Phase 2 + canvas-editor fork 準備。
**第 6 個月起**:第三人加入做測試體系、CI、DevOps。

---

## 10. 閱讀與參考清單

### 10.1 規格書（必讀）

- **ECMA-376 5th Edition Part 1** — WordprocessingML 規格
  - §17.3 段落與文字（必讀）
  - §17.4 表格（必讀，尤其 17.4.65 border conflict）
  - §17.6 節（必讀）
  - §17.7 樣式（必讀）
  - §17.9 清單編號（必讀）
  - §17.15 settings（選讀）
  - §17.17 Simple Types（參考字典）
- **ECMA-376 Part 3** — DrawingML（浮動、圖片、形狀）
- **ECMA-376 Part 4** — Transitional / Strict 相容性

### 10.2 參考原始碼

**ONLYOFFICE**（★ 最值得深讀）：
- `onlyoffice/core/OOXML/DocxFormat/Logic/Paragraph.cpp` — 段落解析
- `onlyoffice/core/OOXML/DocxFormat/Logic/Table.cpp` — 表格解析
- `onlyoffice/core/OOXML/DocxFormat/Logic/Vmerge.cpp` — vMerge 演算法
- `onlyoffice/core/OOXML/DocxFormat/Styles.cpp` — 樣式繼承
- `onlyoffice/sdkjs/word/Documents/` — Canvas 呈現層
- `onlyoffice/sdkjs/word/Drawing/` — Canvas 渲染

**canvas-editor（要 fork 的基礎）**：
- https://github.com/Hufe921/canvas-editor
- `src/editor/core/draw/Draw.ts` — 排版主流程
- `src/editor/core/draw/particle/table/TableParticle.ts` — 表格
- `src/plugins/docx/` — 現有 docx plugin
- `src/editor/interface/` — 資料格式

**其他社群方案**（**參考其弱點**）：
- https://github.com/mwilliamson/mammoth.js — 簡單但棄 layout
- https://github.com/VolodymyrBaydalka/docxjs — 中等還原度
- https://github.com/lalalic/docx4js — AST 設計思路

### 10.3 相關技術閱讀

- **Knuth-Plass 斷行原始論文**:Knuth & Plass, "Breaking Paragraphs into Lines" (1981)
- **Bram Stein, "The State of Web Typography"**(多篇 blog)
- **HarfBuzz 文件**:https://harfbuzz.github.io/
- **opentype.js**:https://opentype.js.org/
- **W3C CSS Text Module Level 4 / CSS Text Decoration Level 4** — CJK 規則現代化基礎
- **JIS X 4051 日文行組版規則書** — CJK 排版演算法的祖宗
- **W3C CLReq — Chinese Layout Requirements**:https://www.w3.org/TR/clreq/

### 10.4 測試資源

- **測試 docx 收集**:Office Fishbowl、GitHub docx test fixtures、LibreOffice regression suite
- **LibreOffice 作為 reference renderer**:`soffice --headless --convert-to pdf`
- **pixelmatch**:https://github.com/mapbox/pixelmatch

---

## 11. 下一步候選

> **歷史紀錄**:Sprint 0 → Sprint 110 的逐 sprint root cause / 修法 / 三層 SOP / 紀律揭示全部保留在 `docs/sprintN_*.md`，索引見 [§12](#12-歷史索引sprint-audit-docs)。本章節**只列前瞻候選**。

> **Sprint 113+ Autonomous Roadmap**:本章候選的詳細排序(階段 A-E、Sprint 113-175)外部化到 [docs/autonomous_roadmap.md](docs/autonomous_roadmap.md)。User 已授權 Claude 自主決策、跑到規畫書整份完成才停。每完成一 sprint Stop hook 自動觸發下個 sprint。Sprint 113 揭示紀律 #14.b 子原則(見 §6.5)。

### 11.1 待 user 決策

| 候選 | scope | 為什麼 |
|---|---|---|
| migrate doc_editor.js 走 production canvas-editor 整合 | Sprint 64b external | 自家 VR pipeline 已落地 FontMetricsAdapter -2.3%;real production 啟用同等 VR 改善需 portal / canvas-editor font 供應策略 |
| 重生 goldens 用 Word desktop 渲染 | 大改造 | 換 metric anchor — goldens 目前是 LibreOffice anchor、副作用大、需重生 251 PNG |
| OffscreenCanvas + Web Worker render | 3-5 sprint | Sprint 60 probe 技術可行性 GREEN(puppeteer 4/4 features、postMessage ~5ms);UI 非阻塞、Safari < 16.4 受限 |
| 50+ 頁 fixture 收集 | 待 user 提供 | Sprint 53 可視頁虛擬化、Sprint 55 full-warm benchmark 在當前 fixture ≤6p 限制下無法量化全域 payoff |
| Sprint 78 Finding B（portal company rule） | autonomous 範圍未收口 | Sprint 70-89 廣域 audit 揭示候選 |

### 11.2 長期 backlog

- opentype.js 真實字型 metric（替換 empirical 1.15 em）:1-2% VR 收斂
- Phase 3.6 註腳 / 尾註:30% 政府文件需求
- Phase 5 OMML 數學公式:學術論文 fixture 才用到
- Web Worker parse / docGrid snap 段落層級判別子 / GPU canvas / 雙軌 VR(VR-LO + VR-Word)
- i18n 7 missing translations、autonomous docs sprint(architecture_decision / glossary / sprint50_66_retro)

### 11.3 心理建設

原規劃寫的「12-36 個月旅程」當前進度:~13 個月(Sprint 0 → Sprint 110)已達 VR mean 0.073191、**A- 級邊緣(mean ≤ 0.07 待跨)**。Phase 5 為止仍需另 6-12 個月，但屆時可考慮商業化先行(B+ 級已可商用)。

---

## 12. 歷史索引（Sprint Audit Docs）

每個 sprint 的 root cause / 修法 / 三層 SOP 驗證 / 設計取捨完整記錄在獨立 audit doc。本節為索引、本規畫書不再重複紀錄個別 sprint 細節。

**Phase 1-3 主體（Sprint 2-33）**：
[sprint2 layout engine](docs/sprint2_layout_engine.md)、[sprint3 table layout](docs/sprint3_table_layout.md)、[sprint4 section/float/widow](docs/sprint4_section_float_widow.md)、[sprint5 nested multicol](docs/sprint5_nested_multicol.md)、[sprint6 wrapsquare unequal cols](docs/sprint6_wrapsquare_unequal_cols.md)、[sprint7 midrow colbreak nested style](docs/sprint7_midrow_colbreak_nested_style.md)、[sprint8 renderer fontmetrics](docs/sprint8_renderer_fontmetrics.md)、[sprint9 browser canvas blocks decoration](docs/sprint9_browser_canvas_blocks_decoration.md)、[sprint10 column separator page field](docs/sprint10_column_separator_page_field.md)、[sprint11 header footer render](docs/sprint11_header_footer_render.md)、[sprint12 field metadata ops fingerprint](docs/sprint12_field_metadata_ops_fingerprint.md)、[sprint13 docprops knuth-plass](docs/sprint13_docprops_knuth_plass.md)、[sprint14 visual regression](docs/sprint14_visual_regression.md)、[sprint15 image render](docs/sprint15_image_render.md)、[sprint16 pagination baseline](docs/sprint16_pagination_baseline.md)、[sprint17 pagination break](docs/sprint17_pagination_break.md)、[sprint18 pagination transition](docs/sprint18_pagination_transition.md)、[sprint19 style merge visual rerun](docs/sprint19_style_merge_visual_rerun.md)、[sprint20 CI/CD landing](docs/sprint20_cicd_landing.md)、[sprint21 ChienYi mixin](docs/sprint21_chienyi_mixin_landing.md)、[sprint22 ChienYi mixin round2](docs/sprint22_chienyi_mixin_round2.md)、[sprint23 Playwright admin E2E](docs/sprint23_playwright_admin_e2e.md)、[sprint24 meeting record host](docs/sprint24_meeting_record_host.md)、[sprint25 spacing line consume](docs/sprint25_spacing_line_consume.md)、[sprint26 row height heuristic](docs/sprint26_row_height_heuristic.md)、[sprint27 cell keepnext infra](docs/sprint27_cell_keepnext_infra.md)、[sprint28 CJK width empirical](docs/sprint28_cjk_width_empirical.md)、[sprint29 docGrid snap](docs/sprint29_docgrid_snap.md)、[sprint30 DPI alignment](docs/sprint30_dpi_alignment.md)、[sprint31 R1 overflow gating](docs/sprint31_r1_overflow_gating.md)、[sprint32 paragraph alignment](docs/sprint32_paragraph_alignment.md)、[sprint33 vMerge anchor render](docs/sprint33_vmerge_anchor_render.md)。

**Phase 3 收斂主軸（Sprint 34-49）**：
[sprint34 vertical text](docs/sprint34_vertical_text.md)、[sprint35 CJK vertical render](docs/sprint35_cjk_vertical_render.md)、[sprint36 grid analysis root cause](docs/sprint36_grid_analysis_root_cause.md)、[sprint37 anchor position](docs/sprint37_anchor_position.md)、[sprint38 anchor textbox](docs/sprint38_anchor_textbox.md)、[sprint39 textbox fine tune](docs/sprint39_textbox_fine_tune.md)、[sprint40 image srcRect](docs/sprint40_image_srcrect.md)、[sprint41 grid diagnosis](docs/sprint41_grid_diagnosis.md)、[sprint42 vAlign landing](docs/sprint42_valign_landing.md)、[sprint43 photo baseline diagnosis](docs/sprint43_photo_baseline_diagnosis.md)、[sprint44 image baseline fix](docs/sprint44_image_baseline_fix.md)、[sprint45 trHeight val-as-min fix](docs/sprint45_trheight_valasmin_fix.md)、[sprint46 meeting record diagnosis](docs/sprint46_meeting_record_diagnosis.md)、[sprint47 val-as-min unsnapped basis](docs/sprint47_valasmin_unsnapped_basis.md)、[sprint48 image row val-as-min](docs/sprint48_image_row_valasmin.md)、[sprint49 title docGrid snap diagnosis](docs/sprint49_title_docgrid_snap_diagnosis.md)。

**Phase 7 效能 + Phase 2 字型（Sprint 50-65）**：
Sprint 50 perf baseline、Sprint 51-58 cache 五連發 + LayoutCache、Sprint 59 path coalescing、Sprint 60 OffscreenCanvas probe、Sprint 61 BrowserTextMetrics negative、Sprint 62-65 FontMetricsAdapter promote default-on。代表 audit:[sprint65 promote font-metrics default commit](docs/sprint65_promote_font_metrics_default_commit.md)、[sprint68 font_serve security boundary](docs/sprint68_font_serve_security_boundary.md)、[sprint67 CONTRIBUTING.md](docs/sprint67_contributing_md.md)。

**font_serve + autonomous batch（Sprint 64b-89）**：
Sprint 64b portal font infra、Sprint 66 font endpoint tests、Sprint 67 CONTRIBUTING.md、Sprint 68 security boundary、Sprint 69 HttpCase runtime + dead code 修正、Sprint 70-89 autonomous batch(廣域應用紀律 / backend test 0→21 / docs glossary)。代表 audit:[sprint82 manifest data ordering audit](docs/sprint82_manifest_data_ordering_audit.md)、[sprint83 disabled plugins audit](docs/sprint83_disabled_plugins_audit.md)、[sprint84-87 batch](docs/sprint84_to_sprint87_batch.md)、[sprint88-89 autonomous exhaustion](docs/sprint88_89_autonomous_exhaustion.md)。

**Sprint 90-110 revert 事件**：
[sprint90_to_109_revert.md](docs/sprint90_to_109_revert.md)(紀律 #18 教訓案例 — esign UI 誤判全 revert、byte-identical)、[sprint111_discipline_sync_after_revert.md](docs/sprint111_discipline_sync_after_revert.md)(紀律列表同步)。

完整列表（含 60+ audit doc）見 `docs/` 目錄。

---

## 附錄 A:Phase 0 任務清單

**已完成**(2026-04-20 → Sprint 20 期間 + Sprint 67 補完 CONTRIBUTING.md)。實際產出：

- 模組目錄 `addons/dobtor_doc_editor/`、`docs/` 目錄含 sprint*.md × 60+
- 42 份測試 docx + 251 PNG goldens
- TypeScript / Vitest / pixelmatch / Playwright 技術棧
- [CONTRIBUTING.md](CONTRIBUTING.md) 10 章節（Sprint 67 補完）
- [docs/scope_decision.md](docs/scope_decision.md)（QWeb vs dobtor 邊界）
- canvas-editor fork 改用 npm + patch-package（patches/ 目前為空）

## 附錄 A.1:產品化補強清單

**已完成**(Sprint 20-24 期間)。實際產出：

- W1 CI/CD + Zip Bomb 防護：`.github/workflows/ci.yml`（flake8 + vitest + pixelmatch + Playwright）+ `models/doc_zip_guard.py`
- W2-3 Portal 整合：`/my/documents/*` 路由 + cy_pc_layout topbar + 兩層 ACL（portal user white-list / internal 全局）
- W4 OWL 升級：`doc_editor.js` 從 odoo.define legacy 升 OWL Component + `onWillUnmount()` 清理
- W5-6 QWeb 共存 + ChienYi mixin：[docs/scope_decision.md](docs/scope_decision.md) + `doc.linked.mixin` + 4-6 份預設樣板（監造會議記錄、施工計畫書、變更說明書）
- W7-8 版本管理 UI + AutoSave：4 條版本路由（list / diff / restore / annotate）+ `doc_version_panel.js` AST diff + `auto_save_manager.js` debounce + IndexedDB local cache
- W9-10 Python 端測試 + PDF 引擎:TransactionCase 12 條 controller + ACL 驗證 + LibreOffice headless(拒 Chromium:CJK 字型差 + 啟動慢 3x) + PSNR / pHash 黃金檔比對

---

## 附錄 B:關鍵術語對照表

| OOXML | 意義 | 對映到 canvas-editor |
|---|---|---|
| `<w:p>` | 段落 | paragraph element |
| `<w:r>` | run（字元格式相同的連續文字） | text / character element |
| `<w:pPr>` | 段落屬性 | paragraph properties |
| `<w:rPr>` | run 屬性 | character properties |
| `<w:tbl>` | 表格 | table |
| `<w:tr>` | 表格列 | table row |
| `<w:tc>` | 儲存格 | td |
| `<w:gridSpan>` | 橫向合併 | colspan |
| `<w:vMerge>` | 縱向合併錨點 / 續接 | rowspan（需演算法轉換） |
| `<w:tblGrid>` | 欄寬定義 | colgroup |
| `<w:sectPr>` | 節屬性（頁面設定） | page setup |
| `<w:drawing>` | 繪圖物件 | image / shape |
| EMU | English Metric Unit (914400/inch) | × 96 / 914400 = px |
| Twips / dxa | 1/1440 inch | × 96 / 1440 = px |
| Half-points | 1/2 point | × (96/72)/2 = px |

---

**Document End** — 版本 2.0 / 2026-05-16 精煉重整
