# dobtor_doc_editor — 進度快照（Progress Snapshot）

**抽出自** [規畫書 §0](../dobtor_doc_editor_高保真匯入開發規劃.md) **/ Sprint 155 catch-up（2026-05-19）**

本檔記錄 Sprint 0 → Sprint 155 的累積指標、各 Phase 完成度、三層 SOP。**規畫書本體已還原為純規畫、不再追蹤進度**;新進度更新請寫在這份檔案。

完整 sprint 細節（root cause / 修法 / 三層 SOP）見 [INDEX.md](INDEX.md)（132 個 sprint audit doc 索引）。

---

## 1. 當前指標一覽（Sprint 181 結尾）

| 指標 | 數值 |
|---|---|
| vitest | **1598 passed + 1 skipped**（`npm test` 全套口徑＝tests/unit + tests/integration；Sprint 181 +21：17 DiagramParser + 4 SmartArt integration）。註：Sprint 178 以前記錄的「1468」為不同計數口徑、自 Sprint 179 起改採全套數字 |
| VR mean | **0.073191**（Sprint 65 promote、第 41 次連續 byte-identical；Sprint 167-181 textAlignment / framePr / background / watermark / 追蹤修訂 / 註解 / OMML / SmartArt 皆 Strategy C 或 capture-only、42 fixture byte-identical） |
| Odoo backend | **31 passed** local（font_serve 12 + zip_guard 9 + Sprint 115-117 boundary 6 + Sprint 117 cross-company 4） |
| CI gate v1（workflow_dispatch） | font_serve 12 test 進 gate |
| `tsc --noEmit` | **2 個 pre-existing error**（Sprint 163 清 BoxBuilder fieldType ×2；剩 FontMetrics opentype.js 宣告 + SettingsParser position enum——後者為 Sprint 165 識別的 Phase 1 型別債 follow-up 候選） |
| ADR | 22 個 |
| 紀律 | 22 條 + 6 子 + 1 候選（#20）+ 1 潛在子原則（#21.a） |
| Sprint audit doc | 181（最新 sprint181_smartart_capture.md；159 / 160v1 為 docs-only follow-up、無獨立 audit doc） |
| Working tree drift | **0**（Sprint 158 P0 prep 清零、紀律 #14.b enforce；每 sprint commit 收口 clean） |

---

## 2. 累積進度摘要（Sprint 0 → Sprint 155）

- **OOXML Parser**（14 子目錄、Section / HeaderFooter / Drawing / Numbering 全覆蓋 + Sprint 145-153 capture-only 九 parts）
- **Layout Engine**（Knuth-Plass / 分頁 / Table layout / wrapSquare / multi-column / cell-internal）
- **Renderer + BrowserCanvas**（含 char-level CJK 直書、image srcRect、cell vAlign）
- **Visual Regression v14**（42 fixture × 251 PNG golden、pixelmatch、page count 100% 對齊）
- **產品化基礎建設**（CI/CD、Zip Bomb 防護、Portal 整合、OWL 升級、QWeb 共存、版本管理、AutoSave、PDF 引擎 LibreOffice headless）— 詳見 [phase4_5_completed.md](phase4_5_completed.md)
- **FontMetricsAdapter**（Sprint 62-65 落地 default-on、LO 系統 fallback fonts、VR mean -2.3%）
- **Performance cache 五連發 + LayoutCache**（Sprint 51-58、AST L1+L2 / image L1+L2 / layout L1、warm path 7×）
- **font_serve.py**（Sprint 64b-69、12 backend test 含 path traversal / null byte / URL-encoded CJK）

### VR mean 進展

| Sprint | VR mean | 突破 |
|---|---|---|
| 28 baseline | 0.1728 | 起點 |
| 33 | 0.1156 | CJK 寬度經驗校準 |
| 44 首次突破 | 0.0955 | image-only line baseline=height |
| 45 | 0.0774 | trHeight val-as-min fix |
| 48 | 0.0749 | image row val-as-min |
| **65 → 153** | **0.073191** | font metrics default-on、第 23 次連續 byte-identical |

---

## 3. Phase 完成度

| Phase | 完成度 | 說明 |
|---|---|---|
| Phase 0 能力盤點 | 100% | CI ✅ / CONTRIBUTING.md ✅（Sprint 67 落地） |
| Phase 1 OOXML Parser | **過 Exit Criteria（Sprint 165）/ 必做項 52/52（100%）** | Sprint 121-126 trHeight / OLE / SDT / bookmark / hyperlink rels;Sprint 145-153 九連 capture-only(footnotes/settings/fontTable/webSettings/appProps/customProps/contentTypes/latentStyles);**Sprint 156 checkbox audit 揭示真實 wire-up 75%**;Sprint 159 / 160 v1 §5 Phase 1 scope 重構（總數 69→65）;**Sprint 160 v2** §1.9 `instrText` render wire-up（[ ]→[x]）;**Sprint 164** bookmark render probe → 改標 Phase 1 optional（render 消費依賴 Phase 2 canvas-editor patch、decision 2B）;**Sprint 165 Phase 1 Exit re-verify 通過**——4 條 Exit Criteria 全過（42 fixture 0 error / AST snapshot+audit 全綠 / 型別齊備附 1 項 follow-up 型別債 / 0 個非-optional `[ ]`）、13 項 Phase 1 optional 依設計延後至 Phase 2·5.4;雙指標 / 三指標見 [sprint165_phase1_exit_reverify.md](sprint165_phase1_exit_reverify.md) + [sprint156_phase1_checkbox_audit.md §4](sprint156_phase1_checkbox_audit.md) + [scope_audit_2026-05-19.md §3.1](scope_audit_2026-05-19.md) |
| Phase 2 Text Shaping | 部分（FontMetricsAdapter -1.7%、§2.2 2/5 [x]） | opentype.js 已用於字型 metric;HarfBuzz 為長期方案;Sprint 127 probe 揭示「production canvas-editor 未整合」;**Sprint 157 fontTable.altName fallback wire-up to FontLoader 完成**（§2.2 第 1 個 [ ] → [x]）;**Sprint 166 CJK fallback chain wire-up to FontLoader 完成**（§2.2 L406 [ ]→[x]：主+altName 失敗且 charset 判定 CJK 時試 思源黑體→微軟正黑體→新細明體 chain;FontLoader 為 caller-side infrastructure、production canvas-editor 尚未消費、同 Sprint 157 定位） |
| Phase 3 Layout Engine | 93% | page count 100% / VR mean 0.073191;Sprint 44-49 突破紀錄;Sprint 161-162 tab stop wire-up（LineBreaker 引擎 + layoutDocument/Paginator/TableLayout 接線 + VR opt-in 量測；Strategy C、aggregate delta 可忽略） |
| Phase 4 Style Theme | 91% | Sprint 19 style merge;Sprint 130 §Phase 4.1 HSL;Sprint 131 §Phase 4.2 tblStylePr/tcPr;Sprint 132 §Phase 4.3 numberingFormatter（wire-up defer）;Sprint 133 §Phase 4.4 pBdr + shd + borderShading DRY;Sprint 134 §Phase 4.4 textAlignment + framePr capture;Sprint 137-139 numbering wire-up Strategy C;**Sprint 167 §Phase 4.4 textAlignment render wire-up（decision A part 1）**;**Sprint 168 framePr probe → user 選 opt-in 路徑**;**Sprint 169-170 §Phase 4.4 framePr 浮動段落框 layout wire-up（decision A part 2、frameGroup.ts + Paginator layFramedParagraphs + framePr.wrap 模式分派 around 側繞排除區/notBeside 保留空間/none 純浮動、opt-in enableFramePr、Strategy C、VR byte-identical）**;**決策 A（textAlignment + framePr）完成**;framePr auto-width 側繞 + 框跨頁 + page/margin anchor 留 Sprint 171 optional |
| Phase 4.5 產品化基礎建設 | 100% | 詳見 [phase4_5_completed.md](phase4_5_completed.md) |
| Phase 5+（註腳 / 追蹤修訂 / OMML） | 進行中（5.6 背景 done） | Sprint 142 probe → user 2026-05-21 GO 全 6 子功能;**Sprint 171 §Phase 5.6「背景」完成**（`<w:background>` parse + render wire-up）;**Sprint 172-173 §Phase 5.6「浮水印」完成**（Sprint 172 WatermarkParser capture header VML `<v:shape>` 文字/圖片浮水印;Sprint 173 CanvasRenderer renderWatermark 文字浮水印旋轉淺灰繪製、opt-in Strategy C、VR byte-identical;圖片浮水印 render 留後續）;**Phase 5.6「浮水印 + 背景」收尾**;**Sprint 174-175 §Phase 5.4「追蹤修訂」收尾**（capture + render、Strategy C）;**Sprint 176 §Phase 5.5「註解」capture**（`comments.xml` CommentsParser → `DocumentNode.comments`、比照 FootnotesParser、capture-only、VR byte-identical）;**決策 C 可控部分（5.4+5.5+5.6）全數完成**;**Sprint 177 §Phase 5.5 註解錨點 capture**（`<w:commentRangeStart>`/`<w:commentReference>` → `ParagraphNode.commentRefs`、capture-only）;**Sprint 178 §Phase 5.6 background themeColor→hex**（`BackgroundParser` 加 themeMap 參數、`resolveThemeColor` 解析、theme-based 背景可 render）;**Sprint 179 §Phase 5.1 OMML capture**（`omml/OmmlParser.ts` `parseOmmlChildren` 遞迴樹解析 → `ParagraphNode.math`、`<m:oMath>` 行內 / `<m:oMathPara>` display、capture-only、VR byte-identical;6 omml synthetic fixture 入庫）;**Sprint 180 §Phase 5.1 OMML render**（`OmmlNode` 補 attrs + `ommlToLinearText` 線性文字 fallback + ToCanvasEditor 接線;KaTeX 全保真留未來 optional、依 Sprint 128 bundle 取捨 + user mc:Fallback 決策）;**Phase 5.1 OMML 完成**（capture 179 + render 180）;**Sprint 181 §Phase 5.2 SmartArt capture**（新模組 `diagram/DiagramParser.ts` 解析 `diagrams/dataN.xml` `<dgm:dataModel>` → `DocumentNode.smartArts?`：內容點文字 + `loTypeId` 版面類型;勘查 4 個真實 fixture 確認**皆無 `<mc:Fallback>` 內嵌圖**、SmartArt 走 dgm 資料模型 + `drawingN.xml` 預渲染 shape → mc:Fallback 壓縮的實際對應 = 取資料模型語意文字;capture-only、VR byte-identical 第 41 連;17 DiagramParser unit + 4 真實 fixture integration test）;5.2 SmartArt render / 5.3 Charts capture 待續（07_chart fixture 已就緒） |
| Phase 6 Export 對稱性 | 0% | 未開始 |
| Phase 7 效能優化 | 84% | cache 五連發 + LayoutCache + path coalescing + OffscreenCanvas probe（Sprint 60 GREEN） |
| Phase 8 Template UI Builder | Phase 1 + 2.1 已驗證 / 2.2 未啟動 | ADR-022 落地（2026-05-19）、非 docx 匯入、工時 / VR mean 與 Phase 0-7 分開計算；Phase 1 視覺 + Phase 2.1 inline control 程式碼於 ADR-022 當日落地、2026-05-20 端到端驗證通過（vitest 1358 / 後端 6 test / 瀏覽器實測 0 console error、欄位插入刪除全通），詳見 [phase8_verification_2026-05-20.md](phase8_verification_2026-05-20.md)；Phase 2.2 overlay 依 ADR-022 條件啟動、未動工 |

---

## 4. 三層 SOP（自 Sprint 23 起所有 sprint 適用）

1. **Vitest layer** — unit + integration 測試覆蓋 root cause;新增測試與既有測試 100% 兼容
2. **Visual Regression v14** — `scripts/visual_regression_v14.mjs` + 42 fixture × 126 pages × pixelmatch;fixture-level mean 收斂量化
3. **Visual spot check** — human-readable 比對 render PNG vs golden;確認結構性差異消除

延伸層（情境性、非所有 sprint 都跑）:

4. **Odoo backend HttpCase / TransactionCase**（backend code 變動時跑）
5. **CI gate v1 workflow_dispatch**（security test 進 gate、紀律 #15.a）

每個 sprint 的 audit doc（[INDEX.md](INDEX.md)）含三層 SOP 的具體數據。完整紀律集合見 [../CONTRIBUTING.md §5 + §6](../CONTRIBUTING.md)。

**自 Sprint 159 起紀律 #14.b 嚴格 enforce**:每個 sprint commit 前 `git status -s addons/dobtor_doc_editor/` 必須 0 modified 0 untracked、否則先補 commit 殘留(避免 working tree drift 累積、Sprint 158 P0 prep 揭發 Sprint 0-157 期間 353 件 backfill 是反例)。

---

## 5. 更新節律建議

按 [scope_audit_2026-05-19.md §4.3](scope_audit_2026-05-19.md) 建議:cluster ≥ 20 sprint 才寫 retro。本檔 Sprint 155 後若有新進度、append 至本檔對應段、**不另開 cluster retro**。
