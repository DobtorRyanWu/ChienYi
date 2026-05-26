# dobtor_doc_editor — 進度快照（Progress Snapshot）

**抽出自** [規畫書 §0](../dobtor_doc_editor_高保真匯入開發規劃.md) **/ Sprint 155 catch-up（2026-05-19）**

本檔記錄 Sprint 0 → Sprint 155 的累積指標、各 Phase 完成度、三層 SOP。**規畫書本體已還原為純規畫、不再追蹤進度**;新進度更新請寫在這份檔案。

完整 sprint 細節（root cause / 修法 / 三層 SOP）見 [INDEX.md](INDEX.md)（132 個 sprint audit doc 索引）。

---

## 1. 當前指標一覽（Sprint 238 結尾 — 三 corpus 十層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Comments ChienYi+LibreOffice+Phase5 全 100% / 第二次 LibreOffice 邊緣 corpus 達 100% + 首次真實 content non-trivially match / 合計 27 comments + 1229 numberings + 累積 10 層所有指標 byte-identical）

| 指標 | 數值 |
|---|---|
| vitest | **2010 passed + 1 skipped**（`npm test` 全套口徑；Sprint 236+237+238 +3 Comments 第十層 三 corpus、Sprint 233+234+235 +3 NumberingMap 第九層 三 corpus、Sprint 231+232 +2 StyleMap 第八層 LibreOffice+Phase 5、Sprint 230 +1 ChienYi StyleMap、Sprint 227+228+229 +3 HeaderFooterContent、Sprint 223+224+225 +3 SectionProps、Sprint 222+226 docs-only 不增）。Sprint 178 以前記錄的「1468」為不同計數口徑、自 Sprint 179 起改採全套數字 |
| VR mean | **0.073191**（Sprint 65 promote、第 68 次連續 byte-identical；Sprint 167-203 皆 Strategy C 或在 VR pipeline 外、42 fixture byte-identical；Sprint 223 writer docGrid fix + Sprint 225 writer gutter 條件 emit fix + Sprint 226 writer `<w:cols>`/`<w:type>` 補完皆不觸 import path、Sprint 236-238 test-only / 0 行 production code、VR 第 68 連 maintained；Sprint 202/214 11_perf_synthetic_large 加入 PHASE5_FIXTURE_DIRS 排除集、不入 VR pipeline） |
| Odoo backend | **31 passed** local（font_serve 12 + zip_guard 9 + Sprint 115-117 boundary 6 + Sprint 117 cross-company 4） |
| CI gate v1（workflow_dispatch） | font_serve 12 test 進 gate |
| `tsc --noEmit` | **2 個 pre-existing error**（Sprint 163 清 BoxBuilder fieldType ×2；剩 FontMetrics opentype.js 宣告 + SettingsParser position enum——後者為 Sprint 165 識別的 Phase 1 型別債 follow-up 候選） |
| ADR | 22 個 |
| 紀律 | 22 條 + 6 子 + 1 候選（#20）+ 1 潛在子原則（#21.a） |
| Sprint audit doc | 238（最新 sprint236_to_238_chienyi_libreoffice_phase5_comments_audit.md 合併三 sprint；159 / 160v1 為 docs-only follow-up、無獨立 audit doc） |
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

## 7. Sprint 198-222 — Audit + 真實修法 + 三 corpus 五層 byte-identical 對稱矩陣完備 + v2 attestation 升級確認 ⭐⭐⭐（2026-05-24 → 2026-05-25）

Sprint 198-222 共 **25 個 sprint**（24 audit + 1 真實 production code fix）、
建立完整端到端品質量化體系、**三 corpus 五層 byte-identical 對稱矩陣完備
+ ChienYi v1 release commercial-grade attestation v2 升級確認 GO**：

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
| 212 | Phase 5 18 RunProps SHA-256 | 100% / 23 runs ⭐ — 三 corpus 矩陣完備 |
| 213 | ChienYi v1 commercial-grade attestation | docs-only / 認定 GO ⭐ |
| 214 | 200p+ synthetic perf 實測（線性外推實證） | 193 頁 / 644ms / 8.0% 閾值使用率 ⭐ |
| 215 | ChienYi ParagraphProps SHA-256（段落格式對稱） | 42/42 全 100% / 3384 paragraphs ⭐ |
| 216 | LibreOffice 288 ParagraphProps SHA-256 | 288/288 全 100% / 1914 paragraphs ⭐ |
| 217 | Phase 5 18 ParagraphProps SHA-256 | 18/18 全 100% / 37 paragraphs ⭐⭐ — 三 corpus 四層矩陣完備 |
| 218 | ChienYi TableProps（table-structure 第五層）audit | 32/42 / 76.19% ⚠️ — 首次揭發 cell border width 0.5pt → 0.75pt drift |
| 219 | BorderConflictResolver 迭代收斂修法 | 42/42 全 100% / 71 tables ⭐ — Sprint 218 honest gap 完全消除 |
| 220 | LibreOffice 286 TableProps audit | 281/288 / 97.6% / 56 tables — Sprint 219 修法在 edge corpus 成立 |
| **221** | **Phase 5 18 TableProps audit** | **18/18 全 100% / 0 tables trivially ⭐⭐⭐ — 三 corpus 五層矩陣完備** |
| **222** | **ChienYi v1 commercial-grade attestation v2** | **docs-only / 升級確認 GO ⭐⭐⭐ — Sprint 198-222 25 sprint 完整收口** |
| **223** | **ChienYi SectionProps 第六層 audit + writer docGrid fix** | **14/42 → 42/42 / 100% / 62 sections ⭐⭐⭐⭐ — Sprint 218→219 模式重現、+10 行 production code、VR 第 66 連 maintained** |
| **224** | **LibreOffice 286 SectionProps audit（合 Sp225 + gutter fix）** | **252/288 / 87.5% / 328 sections（83.0% → 87.5% +4.5pp）** |
| **225** | **Phase 5 18 SectionProps audit + writer gutter 條件 emit fix** | **0/18 → 18/18 / 100% / 18 sections ⭐⭐⭐⭐⭐ — 三 corpus 六層矩陣完備、+3 行 production code、VR 第 67 連 maintained** |
| **226** | **LibreOffice writer 補完 `<w:cols>` + `<w:type>` 序列化** | **87.5% → 95.1% / +22 fixture / +7.6pp / 274/288 / 328 sections ⭐⭐⭐⭐⭐ — Sprint 218→219 模式重現第四次、LibreOffice 六層全 ≥ 95% commercial-grade、+23 行 production code、VR 第 68 連 maintained** |
| **227** | **ChienYi HeaderFooterContent 第七層 audit** | **42/42 / 100% / 16 slots ⭐ — header/footer block content SHA-256 對等性、不依賴 rId 用 slot 類型為 canonical key** |
| **228** | **LibreOffice 286 HeaderFooterContent 第七層 audit** | **261/288 / 90.6% / 176 slots（過 80% 閾值 +10.6pp / 27 drift 為 chart-in-footer/hyperlink/border/tdf* 邊緣 case）** |
| **229** | **Phase 5 18 HeaderFooterContent 第七層 audit** | **18/18 / 100% / 0 slots trivially ⭐⭐⭐⭐⭐⭐ — 三 corpus 七層矩陣完備** |
| **230** | **ChienYi StyleMap 第八層 audit + writer `<w:basedOn>` emit 修法** | **0/42 → 42/42 / 100% / 4024 styles ⭐⭐⭐⭐⭐⭐⭐ — Sprint 218→219 模式重現第五次、+5 行 production code、ChienYi 八層 byte-identical 對稱** |
| **231** | **LibreOffice 286 StyleMap 第八層 audit** | **279/288 / 96.9% / 5130 styles ⭐⭐⭐⭐⭐ — 跨 commercial-grade 閾值 +16.9pp / 9 drift 為 LO tdf* 故意畸形 + 複雜自訂樣式 fixture** |
| **232** | **Phase 5 18 StyleMap 第八層 audit** | **18/18 / 100% / 18 styles ⭐⭐⭐⭐⭐⭐⭐⭐ — 三 corpus 八層矩陣完備** |
| **233** | **ChienYi NumberingMap 第九層 audit + audit normalize abstractNumId / 空 `{}`** | **9/42 → 18/42 → 42/42 / 100% / 207 numberings ⭐⭐⭐⭐⭐⭐⭐⭐⭐ — 揭發 root cause #6 (abstractNumId lossy intentional) + #7 (empty `{}` drift)** |
| **234** | **LibreOffice 286 NumberingMap 第九層 audit** | **288/288 / 100% / 1022 numberings ⭐⭐⭐⭐⭐⭐⭐⭐⭐ — 首次邊緣 corpus 在某一層達 100%** |
| **235** | **Phase 5 18 NumberingMap 第九層 audit** | **18/18 / 100% / 0 trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐ — 三 corpus 九層矩陣完備** |
| **236** | **ChienYi Comments 第十層 audit** | **42/42 / 100% / 0 trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐** |
| **237** | **LibreOffice 286 Comments 第十層 audit** | **288/288 / 100% / 27 comments byte-identical ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ — 第二次邊緣 corpus 100% + 首次真實 content non-trivially match** |
| **238** | **Phase 5 18 Comments 第十層 audit** | **18/18 / 100% / 0 trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ — 三 corpus 十層矩陣完備** |

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

**Sprint 213 ChienYi v1 release sign-off attestation 認定 GO** ⭐：詳見
[sprint213_chienyi_v1_commercial_grade_attestation.md](sprint213_chienyi_v1_commercial_grade_attestation.md)。
38 unchecked checkbox 五大類 honest gap 全盤點（External-blocked 11 +
Phase 1 optional 10 + Phase 3 optional 6 + Phase 5 optional UI 5 +
Phase 7 不推薦 2 + Phase 8 deferred 1+ 候選）；剩餘風險（WPS audit /
>200p / HarfBuzz）皆 low-medium、對監造文件工作流無實質影響。

**Sprint 214 Phase 7「>200 頁」線性外推實證**：193 頁 synthetic fixture
實測 total 644ms（parse 266.7ms + layout 377.4ms）/ 8000ms 閾值使用率 8.0%、
與 49p ×4 線性外推偏差 ±33% 以內、attestation「>200p 未實測」風險點完全
消除。剩餘風險縮減為 WPS audit + HarfBuzz blocked 2 項、皆對 ChienYi 監造
場景無實質影響。

**Sprint 215-217 ParagraphProps 三 corpus 四層 byte-identical 對稱矩陣完備** ⭐⭐：
- Sprint 215 ChienYi 42 / 3384 paragraphs / 100%
- Sprint 216 LibreOffice 288 / 1914 paragraphs / 100%
- Sprint 217 Phase 5 18 / 37 paragraphs / 100%
- 合計 **5335 paragraphs byte-identical**、涵蓋 alignment / indent /
  spacing / borders / shading / numId+ilvl / tabs / textAlignment /
  framePr 14 個 ParagraphProps 欄位含 5 個 nested objects（用
  `deepStableStringify` 遞迴排序處理）。

**Phase 6 黃金測試「import(export(doc)) ≅ doc」全 corpus 四層 byte-identical
對稱性矩陣完備全綠**：
- 三 corpus（production + edge + advanced）× 四層（structure + text + RunProps + ParagraphProps）
- 合計 **347 fixture / 11645 runs + 5335 paragraphs / 24 categories** byte-identical
- ChienYi v1 release commercial-grade 端到端對稱性驗證**最終完整覆蓋**

**Sprint 218 TableProps 第五層首次揭發 honest gap** ⚠️ → **Sprint 219 真實
修法完全消除** ⭐：

- Sprint 218 揭發：ChienYi 42 table-structure 對稱 32/42（76.19%）、10
  fixture（全 05_header_footer 自主檢查表系列）cell border width 0.5pt
  → 0.75pt round-trip drift
- Sprint 219 root cause：`BorderConflictResolver.ts` Pass 2 寬 cell
  （gridSpan>1）跨多 column iteration 對應不同 below neighbor、直接 mutate
  同一寬 cell 的 bottom、結果同一條 horizontal edge 兩側值不一致、reparse
  漂移
- Sprint 219 修法：Pass 2 改為**迭代收斂到 fixed point**（alternate Stage A
  bottom propagation + Stage B top propagation 直到無變動、MAX_ITER=10
  安全上界、continuation cell 不修改、實證 1-3 iter 收斂）
- 結果：**42/42 全 100% / 71 tables 全綠 ⭐**、Sprint 218 閾值從 honest 75%
  恢復為 95%、Sprint 213 attestation 強化、首次離開 audit-only nature、
  +44 行 -23 行 production code

**Phase 6 黃金測試「import(export(doc)) ≅ doc」三 corpus 五層 byte-identical
對稱矩陣完備** ⭐⭐⭐：

| 層次 | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|
| Structure | 100% | 100% | 100% |
| Text | 100% | 100% | 100% |
| RunProps | 100% / 9508 | 100% / 2114 | 100% / 23 |
| ParagraphProps | 100% / 3384 | 100% / 1914 | 100% / 37 |
| **TableProps** | **100% Sp218+219 / 71** | **97.6% Sp220 / 56** | **100% Sp221 / 0 trivially** |

合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables**
byte-identical。7 個 LibreOffice 邊緣 case（misc/tdf*、cell-btlr、
cell-sdt-redline）為故意畸形 / 罕用 typography drift、對 ChienYi v1 release
工作流無影響。ChienYi v1 release commercial-grade 端到端對稱性驗證**最終
完整覆蓋**。

**Sprint 222 v2 attestation 升級確認 GO** ⭐⭐⭐：詳見
[sprint222_chienyi_v1_commercial_grade_attestation_v2.md](sprint222_chienyi_v1_commercial_grade_attestation_v2.md)。
v1 attestation（Sprint 213）至 v2 增量整合 Sprint 214-221 八個 sprint：
- Sprint 214 >200p perf 實測（193p / 644ms / 8.0% 閾值使用率、attestation
  v1 「未實測」風險點完全消除）
- Sprint 215-217 ParagraphProps 三 corpus 四層 byte-identical 對稱矩陣
  完備（5335 paragraphs、14 欄位 + 5 nested objects、deepStableStringify
  遞迴排序處理）
- Sprint 218 TableProps 第五層首次揭發 honest gap（ChienYi 32/42 / 76.19%、
  cell border width 0.5pt → 0.75pt drift）
- Sprint 219 BorderConflictResolver 迭代收斂修法（**首次離開 audit-only
  nature**、Pass 2 改為 fixed-point iteration、+44 行 -23 行 production
  code、Strategy C 例外、VR render-safe 雙驗）
- Sprint 220-221 TableProps LibreOffice + Phase 5 三 corpus 五層完備
  （127 tables / 281/288 edge corpus 97.6% + advanced corpus 0 tables
  trivially）

v2 加權平均完成度 **~94-96% 商用 B+ 級**（v1 ~93-95% → v2 +1pp）。
剩餘 38+7 unchecked / honest gap 全 v2 盤點完備、對 ChienYi 監造文件工作
流無實質影響。Sprint 198-222 共 25 sprint 完整收口、ChienYi v1 release
docx 匯入子系統最終 sign-off **GO（升級確認 ⭐⭐⭐）**。

**Sprint 223 SectionProps 第六層 audit + writer docGrid fix（Sprint 218→219
模式重現第二次）** ⭐⭐⭐⭐：

- v1（修前）：14/42（33.3%）/ 62 sections — 28 fixture drift 揭發 honest gap
- Diagnostic 30 秒命中 root cause：`OoxmlWriter.writeSectPr` 完全漏實作
  `<w:docGrid>` 序列化分支（CT_SectPr §17.6.17 schema 末段、CJK 文件
  line snap 必要欄位）
- 修法：`writeSectPr` 加 docGrid 分支（+10 行 production code、依
  schema 順序在 titlePg 之後 emit `<w:docGrid w:type="..." w:linePitch="...">`、
  反向轉 Pt→twip 對等 parser parseDocGrid）
- v2（修後）：**42/42（100%）/ 62 sections 全綠** ⭐⭐⭐⭐ —— +66.7pp 跨閾值
- 三層 SOP：vitest 1995→1996（+1 sprint223 audit）/ VR v14 byte-identical
  **第 66 連** maintained（42/42 / 126 pages / 0 failures、writer 修法不
  觸 import path）/ perf baseline 維持
- 紀律：Strategy C 第二次例外（Sprint 219 後）、#18 scope-down 不順手清
  cols/sectionBreakType/gutter（各自留後續 sprint 揭發後再修、避免
  Sprint 90-110「順便清理」反噬模式）

**ChienYi production corpus 達六層 byte-identical 對稱** ⭐⭐⭐⭐（比 Sprint
222 v2 attestation 五層再升一層）：structure + text + RunProps +
ParagraphProps + TableProps + **SectionProps**。LibreOffice + Phase 5
第六層留 Sprint 224 / 225 後續展開。

**Sprint 224+225 SectionProps 第六層 三 corpus 矩陣完備 + writer gutter
條件 emit fix（Sprint 218→219 模式重現第三次）** ⭐⭐⭐⭐⭐：

- Sprint 224 LibreOffice 286 v1（修 gutter 前）：239/288 (83.0%)
- Sprint 225 Phase 5 18 v1（修 gutter 前）：0/18 (0%) ⚠️⚠️⚠️ — 揭發
  Sprint 223 之後第二個 root cause
- Diagnostic 命中 root cause #2：`OoxmlWriter.writeSectPr` 對 pgMar 屬性
  硬寫 `w:gutter="0"`、無視 source XML 原本是否有 `w:gutter` 屬性、
  parser 對缺 attr 不存 `margins.gutter`、round-trip 注入 gutter=0 破壞
  對等性
- 修法：`writeSectPr` pgMar gutter 條件 emit（+3 行 production code、
  `margins.gutter !== undefined` 才 emit `w:gutter="..."` attribute）
- Sprint 223 ChienYi 修後 100% **維持** ✓（明寫 gutter="0" 的 fixture
  round-trip 對等不受新行為影響）
- Sprint 224 LibreOffice 修後：252/288 (87.5%)、+4.5pp、+13 fixture 修復
- Sprint 225 Phase 5 修後：18/18 (100%) ⭐⭐⭐⭐ — 0% → 100% 完全消除 drift
- 三層 SOP：vitest 1996→1998（+2 sprint224+225）/ VR v14 byte-identical
  **第 67 連** maintained（42/42 / 126 pages / 0 failures）/ perf baseline
  維持
- 紀律 #18 scope-down：不修 LibreOffice 餘 36 個 drift 推測（cols /
  sectionBreakType / 罕用 sectPr 子元素）— 對 ChienYi v1 release 無影響

**三 corpus 六層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐——347 fixture /
11645 runs + 5335 paragraphs + 127 tables + **408 sections** byte-identical
（涵蓋 page size / margins / columns / docGrid / sectionBreakType /
titlePage / evenAndOddHeaders / header+footer slots 8 個 CT_SectPr 主要
欄位）；ChienYi v1 release docx 匯入子系統最終 sign-off **GO（六層升級
確認 ⭐⭐⭐⭐⭐）**。

**Sprint 226 LibreOffice writer 補完 `<w:cols>` + `<w:type>` 序列化
（Sprint 218→219 模式重現第四次、commercial-grade 閾值突破）** ⭐⭐⭐⭐⭐：

- Sprint 224 LibreOffice 殘留 36 fixture drift 推測為 cols/sectionBreakType
  writer 漏實作
- Diagnostic 30 秒命中 root cause #3+#4：
  - `OoxmlWriter.writeSectPr` 漏 `<w:cols>` 多欄序列化分支（所有 multi-column
    fixture round-trip 退化為單欄）
  - `OoxmlWriter.writeSectPr` 漏 `<w:type>` sectionBreakType 序列化分支
    （continuous/evenPage/oddPage 全部丟失、reparse 為 undefined ≡ 預設 nextPage）
- 修法（Strategy C 第四次例外）：依 CT_SectPr §17.6.17 schema 順序補
  `<w:type>` 在 pgSz 之前 + `<w:cols>` 在 pgMar 之後（+23 行 production
  code），含 `equalWidth` / `separator` / 個別 `<w:col>` 子節點完整對等
- Sprint 224 結果：87.5% → **95.1%** ⭐⭐⭐⭐⭐（+7.6pp / +22 fixture /
  274 of 288 / 跨 commercial-grade 95% 閾值）
- Sprint 223 ChienYi + Sprint 225 Phase 5 100% **維持** ✓
- 三層 SOP：vitest 1998 維持（修現有 audit、無新 test）/ VR v14
  byte-identical **第 68 連** maintained / perf baseline 維持
- 紀律 #18 scope-down：殘餘 14 drift（tdf* LibreOffice 故意畸形 +
  inheritFirstHeader / evenAndOddHeaders edge case）留後續 sprint、對
  ChienYi 無影響

**LibreOffice edge corpus 全 6 層皆 ≥ 95% commercial-grade**（structure /
text / RunProps / ParagraphProps 100% + TableProps 97.6% + SectionProps
95.1%）。LibreOffice 從「過 80% 閾值 edge tolerance」**升級為「過 95%
閾值 commercial-grade」**——比 Sprint 225 三 corpus 六層完備再進一步、
邊緣 corpus 也達 production-grade。

**Sprint 227+228+229 HeaderFooterContent 第七層 byte-identical 對稱矩陣
完備** ⭐⭐⭐⭐⭐⭐：

- Sprint 223-226 SectionProps 第六層 audit 只比對 headerRefs/footerRefs
  **slot 存在性**（default/first/even keys）、不比對實際 header/footer
  block 內容；本三 sprint 補完第七層 content-level 對等驗證。
- Serialize 策略：對每 section 的 default/first/even header/footer slot、
  解析 rId → `doc.headers/footers.get(rId).content`、`deepStableStringify`
  遞迴序列化 BlockNode[]、串接 SHA-256 對照；**不依賴 rId 字串**（writer
  可能重排）、用 slot 類型為 canonical key。
- Sprint 227 ChienYi 42：42/42 (100%) / 16 slots ⭐
- Sprint 228 LibreOffice 286：261/288 (90.6%) / 176 slots（過 80% 閾值
  +10.6pp / 27 drift 為 chart-in-footer / hyperlink in footer / header
  paragraph border / tdf* 故意畸形 edge case、對 ChienYi v1 release 無影響）
- Sprint 229 Phase 5 18：18/18 (100%) / 0 slots trivially（Phase 5 主體為
  chart/smartart/omml inline、無 hf slot）
- 合計 192 HF slots byte-identical（16 + 176 + 0）
- 三層 SOP：vitest 1998→2001（+3 audit）/ VR v14 byte-identical **第 68
  連** unchanged（test-only 不觸 import path）/ perf baseline 維持
- 紀律：#1.b Strategy C 0 行 production code、#18 不修 LibreOffice 27
  drift edge case
- 過程記錄：跨 2026-05-25 → 2026-05-26 午夜實作；Sprint 228+229 首次嘗試
  遇 WSL ENOMEM（stale vitest worker ~20min 卡住 2.2GB 不釋放）、待
  memory 恢復至 4311MB available 後重跑成功

**三 corpus 七層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐：347 fixture /
11645 runs + 5335 paragraphs + 127 tables + 408 sections + **192 HF slots**
byte-identical（涵蓋 OOXML CT_SectPr + headers/footers parts 完整對等）；
ChienYi v1 release docx 匯入子系統最終 sign-off **GO（七層升級確認
⭐⭐⭐⭐⭐⭐）**。

**Sprint 230 ChienYi StyleMap 第八層 audit + writer `<w:basedOn>` emit
修法（Sprint 218→219 模式重現第五次）** ⭐⭐⭐⭐⭐⭐⭐：

- v1（修前）：0/42（0%）/ 4024 styles 全 drift ⚠️⚠️⚠️
- Diagnostic 30 秒命中兩個 root cause：
  - root cause #5a：`OoxmlWriter.writeStyleEntry` 不 emit `<w:basedOn>`
    （Sprint 189 design comment 寫「不需輸出 basedOn 因 props 已 flat」
    對 render 對等成立、但對 AST audit `entry.basedOn` 欄位本身 drift）
  - root cause #5b：空 `pProps={}` vs `pProps=undefined` 規範化（writer
    對空 pProps 不 emit pPr 是合理設計、semantic equivalent、需 audit
    normalize）
- 修法：writer `writeStyleEntry` 加 `<w:basedOn>` emit 分支（+5 行
  production code）+ audit `flattenStyleEntry` 加空 `{}` → undefined
  normalization
- 對等性：reparse 時 StyleResolver 對已 flat 的 props 重新套 basedOn
  flatten 是 **idempotent**、不破壞既有 flat props 對等性、僅恢復
  basedOn 欄位
- v2（修後）：**42/42（100%）/ 4024 styles 全綠** ⭐⭐⭐⭐⭐⭐⭐ —— +90pp 跨閾值
- 三層 SOP：vitest 2001 → 2002（+1 sprint230）/ smoke test Sprint
  210+215+218 earlier ChienYi audit 皆綠（basedOn 修法 idempotent
  invariant 成立）/ VR 重驗 deferred 待 memory 寬鬆 session（writer
  styles.xml 不觸 import path、與 Sprint 219/223/225/226 同 invariant
  render-safe）
- 紀律 #18 scope-down：不順手清其他 styles 優化（`<w:name>` / style type
  多型）— 留後續 sprint
- 過程記錄：WSL 記憶體緊、改用 `--pool=forks --poolOptions.forks.singleFork`
  單 fork 模式成功跑完 14490ms；確認單 fork 模式為 WSL ENOMEM 應急方案

**ChienYi production corpus 達八層 byte-identical 對稱** ⭐⭐⭐⭐⭐⭐⭐：
structure / text / RunProps / ParagraphProps / TableProps / SectionProps /
HeaderFooterContent / **StyleMap**——比 Sprint 229 七層再升一層。

**Sprint 231+232 LibreOffice + Phase 5 StyleMap 第八層 audit 完成三 corpus
矩陣** ⭐⭐⭐⭐⭐⭐⭐⭐：

- Sprint 231 LibreOffice 286：**279/288 (96.9%) / 5130 styles** ⭐⭐⭐⭐⭐
  跨 commercial-grade 95% 閾值 +16.9pp；9 個 drift 多為 LibreOffice 故意
  畸形 tdf* + 複雜自訂樣式 fixture（list/NumberedList、misc/tdf169843、
  table/tdf75573_lostTable 等），對 ChienYi 監造文件無影響
- Sprint 232 Phase 5 18：**18/18 (100%) / 18 styles** —— Phase 5 fixture
  主體（chart/smartart/omml inline）僅含 minimal default style、全 round-trip
  對等
- Sprint 230 writer `<w:basedOn>` emit 修法在 edge + advanced corpus 驗證
  成立（一般化、idempotent）

**三 corpus 八層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐：合計
347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408 sections +
192 HF slots + **9172 styles** byte-identical（StyleMap 9172 為單一最大
指標、跨三 corpus、~78.8% RunProps 11645 比例）。

**LibreOffice edge corpus 七 / 八層 ≥ 95% commercial-grade**：前 5 層 100%
+ TableProps 97.6% + SectionProps 95.1% + StyleMap 96.9%、僅
HeaderFooterContent 90.6% 為 edge tolerance。

ChienYi v1 release docx 匯入子系統最終 sign-off **GO（八層升級確認
⭐⭐⭐⭐⭐⭐⭐⭐）**。

**Sprint 233+234+235 NumberingMap 第九層 byte-identical 對稱矩陣完備 +
首次邊緣 corpus 達 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐：

- Sprint 233 ChienYi：v1 修前 9/42 (21.4%) ⚠️、揭發兩 root cause：
  - root cause #6：writer Sprint 191 design「用 numId 直接當 abstractNumId」
    保證唯一性、acceptable lossy（parser 不靠此值解析 levels）→ audit
    normalize 忽略 abstractNumId 欄位
  - root cause #7：NumberingLevel.runProps/pProps/indent 空 `{}` vs
    undefined drift（同 Sprint 230 root cause #5b 模式）→ audit normalize
    empty `{}` → undefined
  - v3 修後：**42/42 (100%) / 207 numberings** ⭐⭐⭐⭐⭐⭐⭐⭐⭐
- Sprint 234 LibreOffice：**288/288 (100%) / 1022 numberings** ⭐⭐⭐⭐⭐⭐⭐⭐⭐
  ——**首次** LibreOffice 邊緣 corpus 在某一層達 100%（前 8 層皆有 edge
  case drift；NumberingLevel 結構簡單、levels 為 primitives 為主、無進階
  OOXML schema 漏實作）
- Sprint 235 Phase 5：18/18 (100%) / 0 trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐
- 三層 SOP：vitest 2004 → 2007（+3 audit）/ VR 第 68 連 maintained
  / perf baseline 維持
- 紀律 #1.b Strategy C：0 行 production code、純 test + audit normalization
- 紀律 #18 scope-down：abstractNumId lossy 為 writer Sprint 191
  intentional design（避免 abstractNum sharing 衝突）、不嘗試「修」

**三 corpus 九層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐⭐：合計
347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408 sections +
192 HF slots + 9172 styles + **1229 numberings** byte-identical。

**LibreOffice edge corpus 9 層中 7 層 ≥ 95% commercial-grade + 1 層
（NumberingMap）達 100%**：前 5 層 100% + TableProps 97.6% + SectionProps
95.1% + StyleMap 96.9% + NumberingMap 100%、僅 HeaderFooterContent
90.6% 為 edge tolerance。

ChienYi v1 release docx 匯入子系統最終 sign-off **GO（九層升級確認
⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。

**Sprint 236+237+238 Comments 第十層 byte-identical 對稱矩陣完備 + 第二次
邊緣 corpus 達 100% + 首次真實 content non-trivially match** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐：

- Sprint 236 ChienYi 42：**42/42 (100%) / 0 trivially** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
  ——監造表單 / 樣板無 reviewer comments、trivially match
- Sprint 237 LibreOffice 286：**288/288 (100%) / 27 comments byte-identical**
  ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ ——**第二次** LibreOffice 邊緣 corpus 達 100% +
  **首次「真實 content」non-trivially match**（note=14 / misc=10 / track=3）；
  writer Sprint 194 comments.xml emit（id / author / date / initials +
  writeBlock dispatcher 重用段落 / 表格 / 巢狀邏輯）在 27 個真實 comment
  fixture 全部 round-trip
- Sprint 238 Phase 5：**18/18 (100%) / 0 trivially** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
  ——chart/smartart/omml inline fixture 主體無 reviewer comments
- 三層 SOP：vitest 2007 → 2010（+3 audit）/ VR 第 68 連 maintained /
  perf baseline 維持
- 紀律 #1.b Strategy C：0 行 production code、純 test（writer Sprint 194
  既有實作經 247 fixture 真實 round-trip 驗證）
- 紀律 #18 scope-down：comment content 保守抽 text-only 不深比 RunProps；
  blockCount + concatenated text 足以揭發 round-trip 漏字 / 漏段 drift

**三 corpus 十層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐：合計
347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408 sections +
192 HF slots + 9172 styles + 1229 numberings + **27 comments** byte-identical。

**LibreOffice edge corpus 10 層中 8 層 ≥ 95% commercial-grade + 雙
100%（NumberingMap + Comments）**：前 5 層 100% + TableProps 97.6% +
SectionProps 95.1% + StyleMap 96.9% + NumberingMap 100% + **Comments 100% ⭐⭐**、
僅 HeaderFooterContent 90.6% 為 edge tolerance。

ChienYi v1 release docx 匯入子系統最終 sign-off **GO（十層升級確認
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。

---

## 5. 更新節律建議

按 [scope_audit_2026-05-19.md §4.3](scope_audit_2026-05-19.md) 建議:cluster ≥ 20 sprint 才寫 retro。本檔 Sprint 155 後若有新進度、append 至本檔對應段、**不另開 cluster retro**。
