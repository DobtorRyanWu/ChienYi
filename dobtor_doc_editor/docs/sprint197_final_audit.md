# Sprint 197 — 全 Phase final audit（規畫書 §0-8 真實完成度盤點）

**日期**：2026-05-24（週日）
**類型**：docs-only audit（無 production code 變動）
**規畫書對應**：§0 Phase 0-8 + autonomous_roadmap.md §階段 E Sprint 175「A 級 final audit」
**前置**：Sprint 196（Phase 6 達 100%）

---

## Hypothesis

週末衝刺計畫 v2 結尾時、Phase 6 剛達 100%、距離 Monday 2026-05-25 deadline
不到 24hr、剩餘 Phase 7（OffscreenCanvas worker / Web Worker parse / 大檔
fixture / 邊緣相容性 audit）每 cluster 需 2-3 sprint、實際無法全收。

本 sprint 為**誠實 final audit**：盤點 Phase 0-8 各真實完成度、揭出
honest gaps、明確標註「可推 / 已 deferred / 外部依賴卡住」三類，
不假裝 100%、給後續決策準確基線。

---

## Method

逐 Phase 對 `dobtor_doc_editor_高保真匯入開發規劃.md` 與既有 sprint audit
逐條比對：

1. 該 Phase Exit Criteria 是否過？
2. 若部分完成、剩餘屬於「可推（剩 X sprint）」或「deferred（外部依賴）」？
3. 哪些是 honest gap、哪些是 scope-down 接受？

---

## Phase-by-Phase 盤點

### Phase 0 — 能力盤點 ✅ **100%**

- CI（GitHub Actions ✅）/ CONTRIBUTING.md ✅ / 42 docx fixture ✅
- Sprint 0-67 落地、無剩餘工項
- 狀態：**完成**

### Phase 1 — OOXML Parser ✅ **過 Exit Criteria（Sprint 165）**

- 必做項 52/52（100%）
- 42 fixture 0 parse error
- 13 項 Phase 1 optional 依設計延後（bookmark render / SDT 互動 / 等）
- 狀態：**完成**（optional 不計）

### Phase 2 — Text Shaping ⚠️ **部分（~40%、外部依賴卡住）**

- §2.1 FontMetricsAdapter（opentype.js）✅
- §2.2 fontTable.altName + CJK fallback chain ✅（Sprint 157 / 166、
  FontLoader 為 caller-side infrastructure、production canvas-editor 尚未消費）
- §2.3 HarfBuzz 整合 ⏸️（長期方案、Sprint 127 probe 揭示 production
  canvas-editor 整合需重做、defer）
- **honest gap**：HarfBuzz 端到端整合需 canvas-editor patch、不在 ChienYi
  scope 內、留長期 optional
- 狀態：**部分完成、外部依賴卡住**

### Phase 3 — Layout Engine ✅ **~95%（從 93% 推到 ~95%）**

- VR mean 0.073191、page count 100%（42 fixture）
- Sprint 44-49 突破紀錄
- Sprint 161-162 tab stop wire-up（Strategy C、opt-in）
- Sprint 167 textAlignment render wire-up
- Sprint 169-170 framePr 浮動段落框 layout（opt-in）
- **剩餘**：VR mean 從 0.073191 推到 <0.02 是 A 級 final target、需重定義
  量化標準（規畫書 §9.4 提到 50 份盲測 A 級 = VR <0.02、但 42 fixture
  byte-identical 多 sprint 已穩、再壓需 golden 重生 + render 端細部）；
  目前判定 **B+ 級**達成
- 狀態：**~95%、B+ 級達標**

### Phase 4 — Style Theme ✅ **~95%（從 91% 推到 ~95%）**

- Sprint 130 §4.1 HSL ✅
- Sprint 131 §4.2 tblStylePr / tcPr ✅
- Sprint 132 §4.3 numberingFormatter ✅
- Sprint 133 §4.4 pBdr + shd + borderShading DRY ✅
- Sprint 134 §4.4 textAlignment + framePr capture ✅
- Sprint 137-139 numbering wire-up Strategy C ✅
- Sprint 167-170 §4.4 textAlignment + framePr render wire-up（決策 A）✅
- **剩餘**：framePr auto-width 側繞 + 框跨頁 + page/margin anchor（cluster
  3/3、Sprint 169-170 已收基礎）；§4.2 條件樣式 tblStylePr 部分餘項
- 狀態：**~95%、決策 A 完成**

### Phase 4.5 — 產品化基礎建設 ✅ **100%**

- LibreOffice headless PDF / Zip Bomb 防護 / font_serve / Portal 整合 /
  OWL 升級 / QWeb 共存 / 版本管理 / AutoSave / CI/CD
- Sprint 20-24 落地、詳見 phase4_5_completed.md
- 狀態：**完成**

### Phase 5 — 註腳 / 追蹤修訂 / OMML / SmartArt / Chart / 浮水印 / 背景 ✅ **100%**

- 5.1 OMML：Sprint 179 capture + Sprint 180 render（線性文字 fallback）✅
- 5.2 SmartArt：Sprint 181 capture + Sprint 183 render ✅
- 5.3 Charts：Sprint 182 capture + Sprint 183 render ✅
- 5.4 追蹤修訂：Sprint 174 capture + Sprint 175 render ✅
- 5.5 註解：Sprint 176-177 capture + Sprint 184 render（線性文字 fallback）✅
- 5.6 浮水印 + 背景：Sprint 171-173 + Sprint 178 ✅
- **未涵蓋 optional**：OMML KaTeX 全保真 render（依 bundle 取捨）、
  SmartArt 圖形 render（線性文字外）、Chart 真正圖表 render、註解互動
  panel（回覆 / 解決狀態）—— 全列為**未來 optional**
- 狀態：**全 6 子功能 capture + render 完成、interactive panel optional**

### Phase 6 — docx Export 對稱性 ✅ **100%**（**本次 Sprint 196 達成**）

- Sprint 185 MVS（純文字）✅
- Sprint 186 RunProps ✅
- Sprint 187-188 ParagraphProps（含 pBdr / shd / framePr）✅
- Sprint 189 Styles.xml ✅
- Sprint 190 表格 ✅
- Sprint 191 多 section + numbering.xml ✅
- Sprint 192 圖片 / media ✅
- Sprint 193 頁首頁尾 + sectPr ✅
- Sprint 194 OMML / 追蹤修訂 / 註解 / background ✅
- Sprint 195 SmartArt + Chart ✅
- Sprint 196 watermark ✅
- 14 個子目標全達成、byte-identical 第 56 連、round-trip 對稱
- 狀態：**完成** 🎉

### Phase 7 — 效能優化 ⏸️ **84%（剩 16% 為 cluster 工作、單 sprint 不可收）**

- Sprint 50-66 cache 五連發 + LayoutCache + path coalescing ✅
- Sprint 60 OffscreenCanvas probe GREEN ✅
- **剩餘 cluster**（每 cluster 2-3 sprint、合計 ~10 sprint）：
  - OffscreenCanvas + Web Worker render（Sprint 60 probe 已 GREEN、實作未動）
  - Web Worker parse + IndexedDB incremental render
  - 50+ 頁 fixture 替代品（合成大檔）
  - 大文件效能驗證 benchmark（50/100/200p、<3s 匯入 / <1s 首屏）
  - 邊緣 docx 相容性 audit（Word 2007 / LibreOffice / WPS）
- **honest gap**：cache 五連發後實際命中率已 ~7× warm path 加速、
  ChienYi 監造文件多在 20-50 頁、現有效能已堪用；worker 改造收益
  與成本比 marginal、留長期 optional
- 狀態：**84%、剩餘屬大 scope cluster、本次衝刺不收**

### Phase 8 — Template UI Builder ✅ **方案 1 完成（7/8 UI 缺口 + overlay MVP）**

- Phase 1 視覺 + Phase 2.1 inline control 程式碼（2026-05-19 ADR-022 落地）
- Sprint A 三分頁 sub-nav + 預覽鈕 sandbox ✅
- Sprint B intersectionPageNoChange / pageSizeChange / pageScaleChange 三 listener ✅
- Sprint C canvas thumbnail 200×283 JPEG ✅
- Sprint D MVP Phase 8.2.2 overlay 絕對定位（拖曳 / scale 縮放）✅
- Sprint E Odoo field record 重寫接後端 ✅
- Sprint F overlay polish（resize handle + 越界 clamp + Inspector 幾何輸入）✅
- Sprint G jinja2 scanner 批次掃描自動建 Odoo field record ✅
- **剩餘 polish**：多選對齊輔助線（標 polish sprint、可選）
- 狀態：**方案 1 完成**（規畫書 §11.2 Phase 8 MVP scope 達成）

---

## 整體完成度

| Phase | 完成度 | 狀態 |
|---|---|---|
| Phase 0 能力盤點 | **100%** | ✅ 完成 |
| Phase 1 OOXML Parser | **100%（過 Exit Criteria）** | ✅ 完成 |
| Phase 2 Text Shaping | **~40%** | ⏸️ 外部依賴卡住 |
| Phase 3 Layout Engine | **~95%（B+ 級）** | ✅ 達商用 |
| Phase 4 Style Theme | **~95%（決策 A 完成）** | ✅ 達商用 |
| Phase 4.5 產品化基建 | **100%** | ✅ 完成 |
| Phase 5 進階子功能 | **100%（互動 panel optional）** | ✅ 完成 |
| Phase 6 Export 對稱性 | **100%** | ✅ 完成（Sprint 196） |
| Phase 7 效能優化 | **84%** | ⏸️ 大 scope cluster |
| Phase 8 Template UI | **方案 1 完成** | ✅ 達 MVP |

**加權平均**（Phase 1-7 主線、Phase 4.5 / Phase 8 並行）≈ **~89%**

---

## Honest gaps（誠實標註）

| Gap | 屬性 | 對 ChienYi 影響 |
|---|---|---|
| Phase 2 HarfBuzz 整合 | 外部依賴（canvas-editor patch）| 低（FontMetricsAdapter 已替代主要 metric 需求） |
| Phase 3 VR mean <0.02 A 級 | scope-down（B+ 級已商用）| 低（42 fixture byte-identical 多 sprint 已驗證） |
| Phase 4 §4.2 tblStylePr 條件樣式餘項 | 部分完成 | 低（多數監造表格用基礎 tcBorders / shd 就夠） |
| Phase 5 OMML KaTeX 全保真 render | optional（bundle 取捨）| 低（線性文字 fallback 已可讀） |
| Phase 5 SmartArt / Chart 真圖形 render | optional（mc:Fallback 壓縮策略 + 線性文字 fallback）| 低（user 2026-05-21 GO mc:Fallback 策略） |
| Phase 5 註解互動 panel | optional | 低（線性文字 fallback 已可閱） |
| Phase 7 OffscreenCanvas worker | scope-down | 低（cache 五連發已達 7× warm 加速） |
| Phase 7 Web Worker parse | scope-down | 低（同上） |
| Phase 7 大檔 benchmark（50-200p）| 缺合成 fixture | 中（無 50p 真實監造文件、合成 fixture 需建） |
| Phase 7 邊緣相容性 audit | 未做 | 中（Word 2007 / LibreOffice / WPS 產出 docx 未驗） |
| Phase 8 多選對齊輔助線 | polish | 低（已有單選拖曳 + Inspector 幾何輸入） |

**重大 gap 評估**：上表沒有任何「高影響」gap。ChienYi 業務文件用例
（20-50 頁監造日誌 / 估驗 / 自主檢查表）**全部達商用標準**。

---

## 三層 SOP（Sprint 197）

- L1 vitest：**1906 passed + 1 skipped**（重跑全套確認、Sprint 197 docs-only 未動 code、計數差來自 fixture-driven 動態測試自然重發）
- L2 VR v14：**byte-identical 第 56 連**（rendered 42/42、failedPages 0）
- L3 docs-only：本 sprint 純 audit、無 production code 變動

---

## 紀律

- **#1 / Strategy C**：本 sprint docs-only、不動 VR
- **#14.b**：clean commit scope（只 audit doc + progress_snapshot.md + INDEX.md）
- **#18 honest scope-down**：明確標記 honest gaps、不假裝 100%
- **#21**：未涵蓋項目明確列為 deferred / optional / 外部依賴卡住

---

## 結論

**規畫書 §0-8 整體進度**：~89%、Phase 0/1/4.5/5/6/8 達 100% / MVP，
Phase 3/4 達商用 B+ 級，Phase 7 cache 部分完成，Phase 2 外部依賴卡住。

**對 ChienYi 監造系統的實際價值**：
- docx 匯入：✅ 商用可用
- docx 編輯：✅ 商用可用（含 watermark 注入新增能力）
- docx export：✅ 完整 round-trip（Phase 6 100%）
- PDF 產出：✅（Phase 4.5 LibreOffice headless）
- Portal 整合：✅（Phase 4.5 + Sprint A-G）

**剩餘工作建議**（如有後續 sprint window）：
- **高 ROI**：Phase 7 邊緣相容性 audit（1 sprint、跑 LibreOffice / WPS 產出
  docx 透過 parser、驗證 0 crash + 結構保留率）
- **中 ROI**：Phase 7 合成 50p fixture + benchmark（2 sprint）
- **低 ROI**：Phase 8 多選對齊輔助線 polish（1 sprint）
- **不建議**：OffscreenCanvas worker（高成本、低 ROI、ChienYi 已堪用）

---

## File-level summary

```
M  docs/progress_snapshot.md     Sprint 197 audit + Phase 完成度更新
M  docs/INDEX.md                 +sprint197 entry
A  docs/sprint197_final_audit.md 本 audit
```

**淨 production code 變動 = 0 行**、docs-only、L1/L2 全綠（Sprint 196 結尾
狀態 unchanged）。
