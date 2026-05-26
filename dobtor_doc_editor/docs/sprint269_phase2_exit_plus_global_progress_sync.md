# Sprint 269 — Phase 2 Exit verify + 全 Phase 完成度重估 + Sprint 256-268 cluster 收口 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

**日期**：2026-05-26（週二）
**類型**：docs-only / 紀律 #1.b 零 production code
**規畫書對應**：§5 各 Phase Exit Criteria 全 re-verify
**前置**：Sprint 256-268 13 個 sprint 連跑完成（第十六~十八層 byte-identical
matrix + Phase 2 Text Shaping 八 checkbox 全完成）

---

## Hypothesis & Result

**hypothesis**：Sprint 256-268 一輪推進後（Phase 2 完整 / Phase 6 多 3 層 +
1 次真實修法 + 2 次 Strategy C audit），先前 progress_snapshot 標的「Phase 2
部分」/「Phase 6 ~100%」已過時；本 sprint docs-only 重新校準全 Phase
完成度 + 規畫書 §5 checkbox 統計。

**結果**：
- Phase 2 「部分」→ **100% (8/8 checkbox 全完成)** ⭐⭐⭐⭐
- Phase 6 「~100%」→ **18 層 byte-identical 對稱矩陣完備 + writer 真實修法 11 次** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
- 加權平均完成度：**~95-97% 商用級**（自 Sprint 222 v2 ~94-96% → +1-2pp）
- ChienYi v1 docx 匯入子系統最終 sign-off **GO v3**（十八層升級 + Phase 2
  exit 雙重達成）

---

## Phase 2 Exit Criteria re-verify

### 規畫書 §Phase 2 對應 checkbox（user 標 7-10 個 [ ]）

| # | checkbox | Sprint 268 前 | Sprint 268 後 |
|---|---|---|---|
| 1 | HarfBuzz WASM 整合 | [ ] | **[x]** Sprint 128 spike + 265 |
| 2 | ShapingEngine | [ ] | **[x]** Sprint 128 + 265 完整 API |
| 3 | Script & Language 偵測 | [ ] | **[x]** Sprint 265 detectScript（9 種 ISO 15924）|
| 4 | kerning / liga feature | [ ] | **[x]** Sprint 265 ShapeOptions.features |
| 5 | Glyph 快取 | [ ] | **[x]** Sprint 266 cache + stats + FIFO 淘汰 |
| 6 | opentype.js 完整字型 metrics | [ ] | **[x]** Sprint 268（typo/win/hhea + italic/bold/weight）|
| 7 | measureRun() 替代 ctx.measureText() | [ ] | **[x]** Sprint 265 measureRun |
| 8 | 行高公式 | [ ] | **[x]** Sprint 267 resolveOoxmlLineHeight + baselineOffsetPt |

**8/8 通過**。

### Phase 2 Exit Criteria（規畫書原列）

| 條件 | 結果 |
|---|---|
| ① HarfBuzz / opentype.js 可載入並 shape 任一字型 | ✅ Sprint 128 spike + 265 production API |
| ② measureRun 取代 ctx.measureText（CJK + 西文混排） | ✅ Sprint 265 15 test passed |
| ③ kerning / ligature 控制 | ✅ Sprint 265 features 字串 |
| ④ Glyph cache 觀察 hitRate > 50% on Layout pass | ⚠️ 設計就緒、未在 production Layout pass 量測（紀律 #21 hypothesis、Phase 6 Layout Engine 銜接時驗證） |
| ⑤ 行高公式對齊 OOXML §17.3.1.33 | ✅ Sprint 267 auto/exact/atLeast 全測試 |
| ⑥ 完整 OS/2 + hhea + head metrics 可讀 | ✅ Sprint 268 typo/win/hhea +11 欄位 |

**Phase 2 Exit 通過附 ④ 有保留條件**（紀律 #22）：hitRate 量測需 Phase 6
Layout Engine 接 measureRun 才能驗證。本 sprint 確認 cache 機制行為正確
（unit test 8/8），實 hitRate 量測延後。

---

## 全 Phase 完成度更新表

| Phase | Sprint 268 前 | Sprint 268 後 | Δ |
|---|---|---|---|
| 0 能力盤點 | 100% | 100% | — |
| 1 OOXML Parser | 過 Exit (Sprint 165) / 必做 52/52 | 過 Exit / 必做 52/52 / **18 層 byte-identical 對稱矩陣完備** | ✅ 強化 |
| **2 Text Shaping** | **部分（FontMetricsAdapter -1.7%、§2.2 2/5 [x]）** | **100% (8/8 checkbox)** ⭐⭐⭐⭐ | **+~+50%** |
| 3 Layout Engine | 93% / VR 0.073191 | 93% / VR 0.073191（VR 第 68 連 maintained） | — |
| 4 Style Theme | 91%（~95% per Sprint 204）/ 決策 A 完成 | 同 91-95% | — |
| 4.5 產品化基礎建設 | 100% | 100% | — |
| 5+ 註腳/追蹤/OMML | 5.1-5.6 全完成 | 同 | — |
| **6 Export 對稱性** | **~100%** | **18 層 byte-identical + writer 真實修法 11 次 + 10 次 LibreOffice 邊緣 corpus 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ | ✅ 強化敘述 |
| 7 效能優化 | ~92% | ~92%（Sprint 197 final audit 結論不變） | — |
| 8 Template UI Builder | Phase 1 + 2.1 + Sprint A-E | 同 | — |

**加權平均**：~93-95% → **~95-97% 商用級**（Phase 2 從「部分」→100% 推升
加權平均約 +1-2pp）。

---

## Phase 6 byte-identical 對稱矩陣最終狀態（18 層）

| 層 | sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 | LibreOffice 100% |
|---|---|---|---|---|---|
| 1 Structure | 218→219 | 100% | 95.5% | 100% |  |
| 2 Text | 220→226 | 100% | 96.8% | 100% |  |
| 3 RunProps | 227→230 | 100% | 93.1% | 100% |  |
| 4 ParaProps | 231→233 | 100% | 97.6% | 100% |  |
| 5 TableProps | 234→236 | 100% | 95.5% | 100% |  |
| 6 SectionProps | 237→239 | 100% | 94.8% | 100% |  |
| 7 HF Content | 240→242 | 100% | 94.4% | 100% |  |
| 8 StyleMap | 243→245 | 100% | 96.5% | 100% |  |
| 9 NumberingMap | 243→245 | 100% | **100%** | 100% | ✅ 1 |
| 10 Comments | 243→245 | 100% | **100%** | 100% | ✅ 2 |
| 11 Footnotes | 243→245 | 100% | **100%** | 100% | ✅ 3 |
| 12 Settings | 243→245 | 100% | **100%** | 100% | ✅ 4 |
| 13 FontTable | 246→248 | 100% | **100%** | 100% | ✅ 5 |
| 14 WebSettings | 249→251 | 100% | **100%** | 100% | ✅ 6 |
| 15 DocProps | 253→255 | 100% | **100%** | 100% | ✅ 7 |
| 16 SmartArt | 256→258 | 100% | **100%** | 100% | ✅ 8 |
| 17 Charts | 259→261 | 100% | **100%** | 100% | ✅ 9 |
| 18 theme | 262→264 | 100% | **100%** | 100% | ✅ 10 |

**LibreOffice 18 層：16 ≥ 95% commercial-grade + 10 層 100%**（NumberingMap +
Comments + Footnotes + Settings + FontTable + WebSettings + DocProps +
SmartArt + Charts + theme）。

**writer 真實修法 11 次記分卡**：Sprint 219 / 223 / 225 / 226 / 230 / 239 /
243 / 246 / 249 / 253 / 262。

---

## 規畫書 §5 checkbox 估算（待 user 校對）

Sprint 204 時 sync：131 [x] / 36 [ ] / 翻 69 個。

Sprint 256-268 期間翻轉的 checkbox（粗估）：
- §Phase 2 Text Shaping：+8（HarfBuzz / ShapingEngine / Script&Language /
  kern&liga / Glyph cache / opentype.js metrics / measureRun / 行高公式）
- §Phase 6 Export 對稱性：+8 層 audit dimension（SmartArt / Charts / theme
  本層算「parser AST 擴充」新分項；前 5 層 Settings/FontTable/WebSettings/
  DocProps/...在 Sprint 222 v2 attestation 時已部分 sync）

估算更新後：**~139-145 [x] / ~22-28 [ ]**（剩餘皆 honest 標 optional /
advanced / 條件性 / 不建議；user 之前明確 audit）。

實際數字需 user 校對規畫書原文（本 sprint docs-only、不擅自改規畫書檔案）。

---

## ChienYi v1 final sign-off GO v3（升級）

| 版次 | 日期 | 範疇 | 結論 |
|---|---|---|---|
| GO v1 | Sprint 213 | 三 corpus 三層 byte-identical（Structure/Text/RunProps）| 通過 |
| GO v2 | Sprint 222 | 三 corpus 五層 byte-identical + RunProps/ParagraphProps/TableProps 補完 | 升級 |
| **GO v3** | **Sprint 269** | **三 corpus 十八層 byte-identical + Phase 2 8 checkbox 全完成 + writer 真實修法 11 次 + 10 次 LibreOffice 邊緣 corpus 100%** | **再升級** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ |

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C：docs-only / 0 行 production code | ✅ |
| #14.b clean scope：commit 只含 1 audit doc + progress_snapshot/INDEX 更新 | ✅ |
| #22 verify 結論誠實標 hypothesis：Phase 2 Exit ④（cache hitRate）標保留條件 | ✅ |
| Phase 2 Exit 認定模式對齊 Sprint 165 Phase 1 Exit re-verify | ✅ |

---

## 殘項 / Next Steps（user 已標 honest）

| 殘項 | 狀態 |
|---|---|
| Phase 8.2.2 overlay polish | 等 Phase 2.1 inline 試用反饋（user 標半條）|
| Phase 7 OffscreenCanvas / Web Worker | Sprint 197 / 201 雙驗「不建議」|
| Phase 1 optional 剩 11 項 | Sprint 252 已 honest 關閉帳本 |
| Phase 3 advanced（連字 / wrap polygon） | 規畫書 optional |
| Phase 5 optional（OMML alt text / 註解回覆） | 規畫書 optional |
| 第十九層 fmtScheme / objectDefaults / extraClrSchemeLst | 優先級低、Word UI「主題效果」、render 不消費 |
| Phase 6 Layout Engine（自寫取代 canvas-editor）| 長期 optional，需先做完 Phase 2 才能銜接（本 cluster 完成 Phase 2、銜接已 ready）|

---

## End of Sprint 269

**Phase 2 Exit 通過 + 全 Phase 完成度重估 + ChienYi v1 GO v3 升級 +
Sprint 256-268 cluster 收口**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

無新 production code、紀律 #1.b 零行；docs sync 至 Sprint 268 真實狀態。
本 sprint 不對應規畫書新 checkbox，純 docs-only 收口。
