# dobtor_doc_editor — 進度快照（Progress Snapshot）

**抽出自** [規畫書 §0](../dobtor_doc_editor_高保真匯入開發規劃.md) **/ Sprint 155 catch-up（2026-05-19）**

本檔記錄 Sprint 0 → Sprint 155 的累積指標、各 Phase 完成度、三層 SOP。**規畫書本體已還原為純規畫、不再追蹤進度**;新進度更新請寫在這份檔案。

完整 sprint 細節（root cause / 修法 / 三層 SOP）見 [INDEX.md](INDEX.md)（132 個 sprint audit doc 索引）。

---

## 1. 當前指標一覽（Sprint 212 結尾 — 三 corpus 三層 byte-identical 對稱矩陣完備 / 347 fixture / 11645 runs / 24 categories 全 100%）

| 指標 | 數值 |
|---|---|
| vitest | **1976 passed + 1 skipped**（`npm test` 全套口徑；Sprint 212 +1 sprint212 Phase 5 RunProps preservation audit）。註：Sprint 178 以前記錄的「1468」為不同計數口徑、自 Sprint 179 起改採全套數字 |
| VR mean | **0.073191**（Sprint 65 promote、第 60 次連續 byte-identical；Sprint 167-203 皆 Strategy C 或在 VR pipeline 外、42 fixture byte-identical；Sprint 202 11_perf_synthetic_large 加入 PHASE5_FIXTURE_DIRS 排除集、不入 VR pipeline） |
| Odoo backend | **31 passed** local（font_serve 12 + zip_guard 9 + Sprint 115-117 boundary 6 + Sprint 117 cross-company 4） |
| CI gate v1（workflow_dispatch） | font_serve 12 test 進 gate |
| `tsc --noEmit` | **2 個 pre-existing error**（Sprint 163 清 BoxBuilder fieldType ×2；剩 FontMetrics opentype.js 宣告 + SettingsParser position enum——後者為 Sprint 165 識別的 Phase 1 型別債 follow-up 候選） |
| ADR | 22 個 |
| 紀律 | 22 條 + 6 子 + 1 候選（#20）+ 1 潛在子原則（#21.a） |
| Sprint audit doc | 212（最新 sprint212_phase5_runprops_preservation_audit.md；159 / 160v1 為 docs-only follow-up、無獨立 audit doc） |
| 規畫書 §5 checkbox | **131 `[x]` / 36 `[ ]`**（Sprint 204 sync 後；翻 69 個；剩餘皆合法 blocked / deferred / optional） |
| 加權平均完成度 | **~93-95% 商用級**（Sprint 204 揭露 Phase 3 ~93%→~96% / Phase 4 ~91%→~95% 為記錄修正、非新增實作） |
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
| Phase 5+（註腳 / 追蹤修訂 / OMML） | 5.1-5.6 capture+render 全完成（互動 panel optional） | Sprint 142 probe → user 2026-05-21 GO 全 6 子功能;**Sprint 171 §Phase 5.6「背景」完成**（`<w:background>` parse + render wire-up）;**Sprint 172-173 §Phase 5.6「浮水印」完成**（Sprint 172 WatermarkParser capture header VML `<v:shape>` 文字/圖片浮水印;Sprint 173 CanvasRenderer renderWatermark 文字浮水印旋轉淺灰繪製、opt-in Strategy C、VR byte-identical;圖片浮水印 render 留後續）;**Phase 5.6「浮水印 + 背景」收尾**;**Sprint 174-175 §Phase 5.4「追蹤修訂」收尾**（capture + render、Strategy C）;**Sprint 176 §Phase 5.5「註解」capture**（`comments.xml` CommentsParser → `DocumentNode.comments`、比照 FootnotesParser、capture-only、VR byte-identical）;**決策 C 可控部分（5.4+5.5+5.6）全數完成**;**Sprint 177 §Phase 5.5 註解錨點 capture**（`<w:commentRangeStart>`/`<w:commentReference>` → `ParagraphNode.commentRefs`、capture-only）;**Sprint 178 §Phase 5.6 background themeColor→hex**（`BackgroundParser` 加 themeMap 參數、`resolveThemeColor` 解析、theme-based 背景可 render）;**Sprint 179 §Phase 5.1 OMML capture**（`omml/OmmlParser.ts` `parseOmmlChildren` 遞迴樹解析 → `ParagraphNode.math`、`<m:oMath>` 行內 / `<m:oMathPara>` display、capture-only、VR byte-identical;6 omml synthetic fixture 入庫）;**Sprint 180 §Phase 5.1 OMML render**（`OmmlNode` 補 attrs + `ommlToLinearText` 線性文字 fallback + ToCanvasEditor 接線;KaTeX 全保真留未來 optional、依 Sprint 128 bundle 取捨 + user mc:Fallback 決策）;**Phase 5.1 OMML 完成**（capture 179 + render 180）;**Sprint 181 §Phase 5.2 SmartArt capture**（新模組 `diagram/DiagramParser.ts` 解析 `diagrams/dataN.xml` `<dgm:dataModel>` → `DocumentNode.smartArts?`：內容點文字 + `loTypeId` 版面類型;勘查 4 個真實 fixture 確認**皆無 `<mc:Fallback>` 內嵌圖**、SmartArt 走 dgm 資料模型 + `drawingN.xml` 預渲染 shape → mc:Fallback 壓縮的實際對應 = 取資料模型語意文字;capture-only、VR byte-identical 第 41 連;17 DiagramParser unit + 4 真實 fixture integration test）;**Sprint 182 §Phase 5.3 Chart capture**（新模組 `chart/ChartParser.ts` 解析 `charts/chartN.xml` `<c:chartSpace>` → `DocumentNode.charts?`：圖表型別 + 標題 + 各數列的類別/數值快取;`<c:strCache>`/`<c:numCache>` 稀疏 `<c:pt idx>` 對位、cat↔val 同長;勘查 8 個真實 fixture 同確認皆無 `<mc:Fallback>` 圖;capture-only、VR byte-identical 第 42 連;18 ChartParser unit + 5 真實 fixture integration test）;**Sprint 183 §Phase 5.2/5.3 SmartArt+Chart render wire-up**（`InlineImageNode.graphic?` + DrawingParser `parseGraphicFrame` 偵測 `<a:graphicData uri=".../diagram｜chart">` → relId;`smartArtToText`/`chartToText` 線性文字函式;ToCanvasEditor `appendImage` graphic frame 分支查 `smartArtsByRId`/`chartsByRId` → 線性文字 fallback;Strategy C、0/42 fixture 含 graphic frame → byte-identical 第 43 連;+20 test）;**Phase 5 大三項（5.1 OMML / 5.2 SmartArt / 5.3 Charts）capture + render 全數完成**;**Sprint 184 §Phase 5.5 註解 render wire-up**（`commentToText` 攤平 `CommentContent` BlockNode[] → 純文字;ToCanvasEditor `appendParagraph` 加 `commentRefs` 分支、被註解段落後 append `[註解 作者: 內容]`;Strategy C、byte-identical 第 44 連;+10 test）;**Phase 5 全 6 子功能（5.1-5.6）capture + render 全數完成**;精確錨點 highlight + 互動 panel（回覆/解決狀態）列為未來 optional** |
| Phase 6 Export 對稱性 | **~100%（完成）** | Sprint 185-195 + **196 watermark export**（合成 watermark header 部件、`<w:hdr><w:p><w:r><w:pict><v:shape type="#_x0000_t136"><v:textpath string font-family>`、無 default header section 注入 WATERMARK_HEADER_RID 為 default headerReference、有 default 的保留原 default 為 honest sub-gap、Content_Types/rels 自動擴充、文字浮水印 text/font/rotation round-trip 對稱）；**Phase 6「docx export 對稱性」全 7 子目標達成**（MVS / RunProps / ParagraphProps / Styles / 表格 / 多 section + numbering / 圖片 / 頁首頁尾 + sectPr / OMML / 追蹤修訂 / 註解 / background / SmartArt / Chart / watermark） |
| Phase 7 效能優化 | **~92%**（邊緣 audit + 結構對稱性 + perf re-baseline + 大檔 perf 雙 anchor + vitest regression guard 五條 pipeline 完整）| cache 五連發 + LayoutCache + path coalescing + OffscreenCanvas probe（Sprint 60 GREEN）+ **Sprint 198 parse 邊緣 audit**（290 LibreOffice fixture、288/290 = 99.3% parse / 0 crash）+ **Sprint 199 export round-trip 廣域 audit + OMML namespace bug fix**（288 parse-OK fixture：export 100% / reparse 100% / structure 93.1%；math reparse 0%→91%）+ **Sprint 200 anchor paragraph strip**（揭出並修復 Sprint 191 writer anchor 被 parser 當實段、structure 93.1%→**100%**、13/15 category 完整保留）+ **Sprint 201 perf re-baseline**（33 sprint 後 warm-cache total **−25.3%**：1349.9ms→1008.0ms 原 42 fixture、cold→warm 加速 **9.98×**、cache 五連發架構維持健康無 regression、瓶頸落在 render 93.4% 不可消除部分→ OffscreenCanvas worker 「不建議」判定被驗證）+ **Sprint 202 大檔 perf baseline**（用 Phase 6 OoxmlWriter 程式化合成 49p 1375 段落 text-heavy fixture 入庫；cold 1577.5ms / warm 758.3ms / cold→warm 2.08× render-dominant 場景天然加速倍率較低；per-page warm 15.5ms 仍 < 60fps frame budget 16.7ms；揭示 render 不可消除上限；6p 真實 + 49p synthetic 雙 perf anchor 點建立）+ **Sprint 203 vitest perf regression guard**（parse cold 266ms / warm avg 95ms / layout cold 228ms / 49 頁、斷言 < 600/1500/2000ms 含 3× CI safety margin；npm test 自此抓 parse/layout regression alarm；render 不量留 puppeteer harness、雙 harness 互補）；**剩餘 cluster**（每個 2-3 sprint、合計 ~5 sprint）：OffscreenCanvas worker render（Sprint 197+201 雙驗不建議）/ Web Worker parse（同）/ 50+ 頁真實 ChienYi fixture audit / WPS 來源 fixture audit。Sprint 197 final audit 判定：ChienYi 監造文件實際 20-50p、cache 五連發已達 ~10× warm path 加速、worker 改造收益與成本比 marginal、留長期 optional |
| Phase 8 Template UI Builder | Phase 1 + 2.1 + Sprint A-E 收口 8/8 UI 缺口（方案 1 完成） | ADR-022 落地（2026-05-19）、非 docx 匯入、工時 / VR mean 與 Phase 0-7 分開計算；Phase 1 視覺 + Phase 2.1 inline control 程式碼於 ADR-022 當日落地、2026-05-20 端到端驗證通過，詳見 [phase8_verification_2026-05-20.md](phase8_verification_2026-05-20.md)；**Sprint A+B+C（2026-05-23）一口氣收口 7/8 UI 缺口（方案 1）**：Sprint A sub-nav 三分頁（儀表板/請求/設定）解封 + 預覽鈕接 `/dobtor_doc/template_preview` jinja2 sandbox；Sprint B `intersectionPageNoChange`/`pageSizeChange`/`pageScaleChange` 三 listener + `_scrollToPage` 用 `<canvas>` scrollIntoView 換頁 + fit-width/page DOM 量測；Sprint C canvas.toDataURL 縮圖 200×283 JPEG@0.5、debounce 800ms 重生、點縮圖跳頁；92 backend test + 1722 vitest 全綠（0 regression）、詳見 [phase8_sprint_a_2026-05-23.md](phase8_sprint_a_2026-05-23.md) / [phase8_sprint_b_2026-05-23.md](phase8_sprint_b_2026-05-23.md) / [phase8_sprint_c_2026-05-23.md](phase8_sprint_c_2026-05-23.md)；**Sprint D（2026-05-23 同日）MVP Phase 8.2.2 overlay 絕對定位**：model 加 `layout_mode` Selection、工具列 inline/overlay toggle、overlay layer 渲染 + mousedown/move/up 拖曳 + `transform:scale` 縮放聯動 + inline/overlay 共存；**Sprint E** Odoo 欄位按鈕重寫接後端 field 紀錄；92 backend tests + 1800 vitest + **13 Playwright E2E** 全綠（0 regression）、詳見 [phase8_sprint_d_2026-05-23.md](phase8_sprint_d_2026-05-23.md) / [phase8_sprint_e_2026-05-23.md](phase8_sprint_e_2026-05-23.md)；Sprint D resize 控制點 + 越界限制 + 多選對齊輔助線留 polish sprint |

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

## 6. Sprint 197 — Final audit 結論（2026-05-24）

詳見 [sprint197_final_audit.md](sprint197_final_audit.md)。

**整體進度**：~89% 加權平均（Phase 1-7 主線 + Phase 4.5 / Phase 8 並行）。

**達 100% / MVP 的 Phase**：0、1、4.5、5、6、8（方案 1）。

**達商用 B+ 級的 Phase**：3（VR mean 0.073191）、4（決策 A 完成）。

**外部依賴卡住的 Phase**：2（HarfBuzz 整合需 canvas-editor patch）。

**剩餘為大 scope cluster 的 Phase**：7（OffscreenCanvas worker / Web Worker parse / 大檔 fixture / benchmark / 邊緣相容性 audit）。

**對 ChienYi 監造系統實際價值**：docx 匯入 / 編輯 / export / PDF 產出 / Portal 整合**全部達商用標準**。無高影響 honest gap。

**後續建議 ROI 排序**：邊緣相容性 audit（高）> 合成 50p fixture + benchmark（中）> Phase 8 多選對齊輔助線（低）> OffscreenCanvas worker（不建議）。

---

## 7. Sprint 198-212 — Audit pipeline 完整覆蓋 + 三 corpus 三層矩陣完備全綠（2026-05-24 → 2026-05-25）

Sprint 198-212 共 15 個 audit sprint，建立完整覆蓋的端到端品質量化體系：

| Sprint | 範疇 | 結果 |
|---|---|---|
| 198 | LibreOffice 290 parse audit | 99.3% / 0 crash |
| 199 | LibreOffice 288 round-trip 4-stage | 100% / 100% / 93.1% (Sprint 200 後 100%) |
| 200 | Sprint 191 anchor strip fix | structure 93.1% → 100% |
| 201 | 60 fixture perf re-baseline | warm-cache −25.3% / cold→warm 9.98× |
| 202 | 49p text-heavy synthetic | cold 1577ms / warm 758ms |
| 203 | 49p vitest perf guard | parse 266ms / layout 228ms < 閾值 |
| 205 | top-3 ChienYi vitest perf guard | parse 45-149ms / layout 2-10ms < 閾值 |
| 206 | ChienYi 42 round-trip 4-stage | 100% / 100% / 100% / 100% |
| 207 | ChienYi 42 text SHA-256 | 100% byte-identical |
| 208 | LibreOffice 288 text SHA-256 | 100% byte-identical |
| 209 | Phase 5 18 round-trip + text | 100% / 100% ⭐ |
| 210 | ChienYi 42 **RunProps SHA-256** | **100% / 9508 runs** ⭐ |
| 211 | LibreOffice 288 **RunProps SHA-256** | **100% / 2114 runs** ⭐ |
| **212** | **Phase 5 18 RunProps SHA-256** | **100% / 23 runs ⭐ — 三 corpus 矩陣完備** |

**Phase 6 黃金測試「import(export(doc)) ≅ doc」雙 corpus（ChienYi production
+ LibreOffice edge）達 structure + text + RunProps 三層 byte-identical 對稱**：

| 層次 | ChienYi 42 (production) | LibreOffice 286 (edge) | Phase 5 18 (advanced) |
|---|---|---|---|
| Structure | 100% (Sprint 206) | 100% (Sprint 199+200) | 100% (Sprint 209) |
| Text SHA-256 | 100% (Sprint 207) | 100% (Sprint 208) | 100% (Sprint 209) |
| **RunProps SHA-256** | **100% (Sprint 210) / 9508 runs** ⭐ | **100% (Sprint 211) / 2114 runs** ⭐ | **100% (Sprint 212) / 23 runs** ⭐ |

**ChienYi v1 release commercial-grade 端到端「匯入→匯出→再匯入文字+格式皆
不失真」最嚴格量化保證**（production + edge + advanced 三 corpus 矩陣完備
全綠、347 fixture / 11645 runs / 24 categories byte-identical）。

---

## 5. 更新節律建議

按 [scope_audit_2026-05-19.md §4.3](scope_audit_2026-05-19.md) 建議:cluster ≥ 20 sprint 才寫 retro。本檔 Sprint 155 後若有新進度、append 至本檔對應段、**不另開 cluster retro**。
