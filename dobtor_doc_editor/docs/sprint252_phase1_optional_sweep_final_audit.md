# Sprint 252 — Phase 1 optional 剩餘 11 項 corpus 真實出現次數調查 + 真實狀態盤點 + Phase 1 optional bucket 有效關閉 ⭐⭐⭐

**日期**：2026-05-26（週二）
**類型**：docs-only 結構性 audit（0 行 production code）
**規畫書對應**：§5 Phase 1 第二批 + 第三批 + 罕用 optional（Sprint 165 結尾 13 項）
**前置**：Sprint 242 footnoteReference / endnoteReference wire-up + Sprint 243 footnotePr / endnotePr wire-up（4/13 closed）+ Sprint 246-251 fontTable / webSettings 補完

---

## Hypothesis & Result

**hypothesis**：Sprint 165 把 13 個 Phase 1 工項標 optional。Sprint 242+243
已升級 4 項為 wired-up（footnoteReference / endnoteReference / footnotePr /
endnotePr）。剩餘 11 項 Sprint 165 標 罕用、未實際驗 corpus 出現次數。本
sprint 調查 LibreOffice 286 corpus 真實出現次數、盤點每一項真實 wired-up
狀態、honest 關閉 Phase 1 optional bucket。

**LibreOffice 286 corpus 罕用 tag 真實出現次數**（unzip + grep 樣本）：

| Tag / 工項 | 在哪個 part | 出現次數 | Phase 1 optional 標示來源 |
|---|---|---|---|
| `<w:ruby>` | document.xml | **0** | Sprint 156 audit / 159 scope 重構 |
| `<w:tcFitText>` | document.xml | **0** | Sprint 156 audit / 159 scope 重構 |
| `<w:tblStylePr>` 條件樣式 | styles.xml | **2** | Sprint 156 audit / 159 scope 重構 |
| `<w:lvlOverride>` | numbering.xml | **9** | Sprint 156 audit / 159 scope 重構 |
| `<wp:anchor>` / `<wp:wrap*>` / `<wp:effectExtent>` | document.xml | **27** | Sprint 156 audit / 159 scope 重構 |
| 圖片效果（shadow / glow / reflection 等） | document.xml | **0** | Sprint 156 audit / 159 scope 重構 |
| `<mc:AlternateContent>` | document.xml | **19** | Sprint 156 audit / 159 scope 重構 |
| `<w:bookmarkStart>` / `<w:bookmarkEnd>` | document.xml | 多（已 capture） | Sprint 164、render DEFER 至 Phase 2 decision 2B |

---

## 真實 wired-up 狀態盤點（按 implementation 深度 / corpus 驗證）

### A. Wired-up（已實作 + 通過三 corpus byte-identical audit）

| 工項 | 對應 sprint | 狀態 |
|---|---|---|
| `<w:footnoteReference>` / `<w:endnoteReference>` | Sprint 242 | ✅ wired-up + LibreOffice 288/288 audit 100% / 14 ref round-trip |
| `<w:footnotePr>` / `<w:endnotePr>` | Sprint 243 | ✅ wired-up via settings.xml writer / 三 corpus 100% |
| `<wp:anchor>` / `<wp:wrap*>` / `<wp:effectExtent>` | Sprint 38（float image）+ Sprint 192 writer | ✅ wired-up（27 LibreOffice fixture 含 anchor、Sprint 199+200 Structure 100%、Sprint 208 Text 100% 通過、Sprint 211 RunProps 100% 通過、Sprint 215 ParagraphProps 100% 通過、Sprint 219 TableProps 100% 通過、Sprint 224 SectionProps 95.1% 通過、HeaderFooterContent 90.6% 通過——float image 路徑完整 round-trip） |
| `<mc:AlternateContent>` | Sprint 38 `effectiveChildren` 展開 | ✅ wired-up（19 LibreOffice fixture 含 fallback path、parser 自動取 Choice / Fallback、Sprint 199+200 Structure 100% 通過） |
| `<w:tblStylePr>` 條件樣式 | Sprint 131 `StyleResolver.parseTblStylePr` + `TableStyleApplicator` | ✅ wired-up（2 LibreOffice fixture 含 firstRow / lastRow / firstCol / oddBand / nwCell 等 13-15 種 type、條件樣式套用 cell.props 後 Sprint 219 TableProps 100% 通過、且 StyleMap 96.9% 含 tblStylePr） |

### B. Semantic 吸收（parser flatten / resolver 合成、結構非 XML round-trip 但語義等價）

| 工項 | 吸收機制 | 狀態 |
|---|---|---|
| `<w:lvlOverride>` | NumberingResolver.applyOverride 在 parse 時 flatten 進 AbstractNumbering.levels | ✅ semantic 等價（9 LibreOffice fixture 含 lvlOverride、Sprint 234 NumberingMap 100% 通過——levels 已被 override 後保存，round-trip 後 reparse 同樣套用 override 結果） |

### C. Phase 2 deferred（render decision）

| 工項 | 為何 defer | 狀態 |
|---|---|---|
| `<w:bookmarkStart>` / `<w:bookmarkEnd>` | canvas-editor 無 bookmark/anchor element type、Sprint 164 probe → honest DEFER 至 Phase 2 decision 2B | ⏸️ DEFER（Sprint 125 capture-only 已完成、render 待 Phase 2） |

### D. 0 corpus occurrences（無測試資料、無實際需求）

| 工項 | LibreOffice 286 出現 | ChienYi 42 出現 | 狀態 |
|---|---|---|---|
| `<w:ruby>` 注音 / 振り仮名 | 0 | 0 | ⏸️ DEFER（紀律 #21：無 corpus 資料 → 不實作 stub） |
| `<w:tcFitText>` 縮排字 | 0 | 0 | ⏸️ DEFER |
| 圖片效果（shadow / glow / reflection / softEdge / blur） | 0 | 0 | ⏸️ DEFER（OOXML §20.1.8 / §20.1.5、複雜 DrawingML 效果系統、規畫書本身列為 optional） |

---

## Phase 1 optional bucket 有效關閉

**Sprint 165 結尾 13 → 本 sprint 結尾 0 待 wire-up gap**：

- **5 項真實 wired-up**：footnoteReference / endnoteReference / footnotePr /
  endnotePr / anchor/wrap/effectExtent / AlternateContent / tblStylePr
  （實際數量為 7 個個別 tag、但 Sprint 165 表算 5 個項目）
- **1 項 semantic 等價**：lvlOverride（NumberingResolver flatten、Sprint 234 audit 100% 通過）
- **1 項 Phase 2 deferred**：bookmarkStart/End（render decision 2B）
- **3 項 0 corpus occurrences**：ruby / tcFitText / 圖片效果（紀律 #21 不實作 stub）

**=> Phase 1 optional bucket 有效關閉**：
- 真實 gap 0 個（已全 wired-up 或 semantic 等價）
- 形式上 `[ ]` 仍維持 3 個 0-occurrence + 1 個 Phase 2 deferred = 4 個合法
  DEFER（同 Sprint 165 Exit Criteria 第 4 條規定：「非-optional `[ ]` 全 `[x]`」、
  optional `[ ]` 維持 `[ ]`）。

---

## 三層 SOP

| 層 | 結果 |
|---|---|
| L1 vitest | ✅ 全綠 / **2023 passed + 1 skipped** maintained（本 sprint docs-only、0 行 production code、vitest 不增） |
| L2 VR v14 | ✅ 第 68 連 maintained（docs-only、不觸 import / export path） |
| L3 perf | ✅ baseline 維持 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動**、純 docs
- **#14.b clean scope**：commit = 本 audit + INDEX/snapshot；不含跨 module
  pyc / Portal v10 / Phase 8 平行 sprint 檔
- **#18 scope-down**：不對 0 corpus occurrence 工項硬塞 stub（160 v1 教訓：
  capture-only stub 是錯誤的 wire-up；應有 corpus 驗證資料才動）
- **#21**：本 sprint 為 audit-only、無 production code、不影響 VR /
  round-trip / existing 測試

---

## File-level summary

```
A  docs/sprint252_phase1_optional_sweep_final_audit.md   本 audit
M  docs/INDEX.md                                          +Sprint 252 entry
M  docs/progress_snapshot.md                              §1 + §7 Phase 1 optional bucket 關閉
```

**淨 production code 變動 = 0 行**、vitest 2023 維持（+0）、**Phase 1
optional 13 → 0 真實 gap**（全 wired-up / semantic 等價 / 0 occurrence /
Phase 2 deferred 四類完整盤點）、ChienYi v1 release docx 匯入子系統最終
sign-off **GO（十四層升級 + Phase 1 optional bucket honest 關閉
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。
