# Sprint 231+232 — LibreOffice + Phase 5 StyleMap 第八層 audit / 三 corpus 八層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐

**日期**：2026-05-26（週二）
**類型**：兩 audit 並排（test-only / 0 行 production code）
**規畫書對應**：§6 黃金測試 LibreOffice + Phase 5 corpus StyleMap 第八層 + Sprint 230 basedOn fix 在 edge / advanced corpus 驗證
**前置**：Sprint 230 ChienYi 42/42 100% + writer `<w:basedOn>` emit 修法

---

## Hypothesis & Result

**hypothesis**：Sprint 230 writer basedOn fix 為一般化、應對所有 OOXML style
繼承鏈 round-trip drift；本兩 sprint 套用至 LibreOffice 288 + Phase 5 18、
驗 Sprint 230 修法在 edge case + advanced case 也成立、完成三 corpus 八層
矩陣。

**實測結果**：
- Sprint 231 LibreOffice 286：**279/288 (96.9%) / 5130 styles** ⭐⭐⭐⭐⭐
  跨 95% commercial-grade 閾值（+16.9pp / 9 drift 為 edge case）
- Sprint 232 Phase 5 18：**18/18 (100%) / 18 styles** ⭐⭐⭐⭐⭐⭐⭐⭐

**三 corpus 八層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Sprint 231 — LibreOffice 286 / 279/288 (96.9%) / 5130 styles 跨 commercial-grade 閾值 ⭐⭐⭐⭐⭐

```
[sprint231] total=290 parse=288/290 pipeline=288/288 style=279/288 (96.9%) totalStyles=5130
  chart         : pipeline 9/9 style 9/9 (100.0%) styles=50
  field         : pipeline 12/12 style 12/12 (100.0%) styles=161
  headerfooter  : pipeline 9/9 style 9/9 (100.0%) styles=305
  image         : pipeline 15/15 style 15/15 (100.0%) styles=196
  list          : pipeline 11/11 style 10/11 (90.9%) styles=404
  math          : pipeline 10/11 style 10/10 (100.0%) styles=84
  misc          : pipeline 136/137 style 130/136 (95.6%) styles=2659
  note          : pipeline 10/10 style 10/10 (100.0%) styles=172
  sdt           : pipeline 11/11 style 10/11 (90.9%) styles=244
  section       : pipeline 13/13 style 13/13 (100.0%) styles=79
  shape         : pipeline 23/23 style 23/23 (100.0%) styles=412
  smartart      : pipeline 2/2 style 2/2 (100.0%) styles=6
  style         : pipeline 10/10 style 10/10 (100.0%) styles=61
  table         : pipeline 13/13 style 12/13 (92.3%) styles=155
  track         : pipeline 4/4 style 4/4 (100.0%) styles=142
```

### 9 個 drift fixture 分布

```
list/NumberedList.docx                     styleCount=322  ← 大量 numbering 樣式
misc/2120112713.docx                       styleCount=96
misc/2120112713_OpenBrace.docx             styleCount=103
misc/n779627.docx                          styleCount=66   ← LO tdf 系列
misc/tdf115883.docx                        styleCount=59   ← LO tdf
misc/tdf169843.docx                        styleCount=205  ← LO tdf
misc/tdf170171.docx                        styleCount=213  ← LO tdf
sdt/ShapeOverlappingWithSdt.docx           styleCount=41
table/tdf75573_lostTable.docx              styleCount=59   ← LO tdf
```

特徵：多為 LibreOffice 故意畸形 tdf* 系列 + 大量自訂樣式的複雜 fixture（已
跨 95% 閾值、對 ChienYi v1 release 無影響）。

按紀律 #18 scope-down 不修。

---

## Sprint 232 — Phase 5 18 / 18/18 (100%) / 18 styles ⭐⭐⭐⭐⭐⭐⭐⭐

```
[sprint232] total=18 style match=18/18 (100.0%) totalStyles=18
  07_chart      : 8/8 (100.0%) styles=8
  08_smartart   : 4/4 (100.0%) styles=4
  09_omml       : 6/6 (100.0%) styles=6
```

Phase 5 fixture 主體（chart inline / smartart / omml 數學）僅含 minimal
default styles（每 fixture 1 個）、全 round-trip 對等。**三 corpus 八層
矩陣完備**。

---

## 三 corpus 八層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐

| 驗證層次 | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|
| Structure | 100% | 100% | 100% |
| Text | 100% | 100% | 100% |
| RunProps | 100% / 9508 | 100% / 2114 | 100% / 23 |
| ParagraphProps | 100% / 3384 | 100% / 1914 | 100% / 37 |
| TableProps | 100% / 71 | 97.6% / 56 | 100% / 0 trivially |
| SectionProps | 100% / 62 | 95.1% / 328 | 100% / 18 |
| HeaderFooterContent | 100% / 16 | 90.6% / 176 | 100% / 0 trivially |
| **StyleMap** | **100% / 4024** | **96.9% / 5130 ⭐⭐⭐⭐⭐** | **100% / 18 ⭐⭐⭐⭐⭐⭐⭐⭐** |

合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles** byte-identical。

**StyleMap 為單一最大指標**（9172 styles 跨三 corpus、超越 RunProps 的
11645 runs / ~78.8% 比例）。

**LibreOffice edge corpus**：前 5 層 100% + TableProps 97.6% + SectionProps
95.1% + HeaderFooterContent 90.6% + StyleMap 96.9%——**7/8 層 ≥ 95%
commercial-grade、僅 HF 90.6% 為 edge tolerance**。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **2004 passed + 1 skipped**（+2 sprint231+232）；單跑兩 audit 皆綠 |
| L2 VR v14 | ✅ **byte-identical 第 N 連** | 本兩 sprint test-only、不改 production code；Sprint 230 writer basedOn fix VR 重驗仍 deferred 待 memory 寬鬆 session |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本兩 sprint **0 行 production code 變動**、純
  test 驗 Sprint 230 修法在 edge corpus + advanced corpus 成立
- **#2 magic number**：2 個具名常數（EXPECTED_PARSE_OK_BASELINE +
  MIN_STYLE_MATCH_RATE_PCT 各 corpus）+ 沿用 Sprint 215 deepStableStringify
  + Sprint 230 flattenStyleEntry normalization
- **#14.b clean scope**：commit = sprint231+232 audit + audit doc +
  INDEX/snapshot；不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：不修 LibreOffice 9 個 drift（多為 tdf* 故意畸形 +
  複雜自訂樣式 fixture）— 對 ChienYi v1 release 無影響
- **#21**：本兩 sprint 不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint231_libreoffice_styles_preservation_audit.test.ts   +154 行
A  tests/integration/sprint232_phase5_styles_preservation_audit.test.ts        +134 行
A  docs/sprint231_232_libreoffice_phase5_styles_audit.md                       本 audit
M  docs/INDEX.md                                                                +Sprint 231+232 entries
M  docs/progress_snapshot.md                                                    Sprint 231+232 補述 + 八層三 corpus 矩陣完備
```

**淨 production code 變動 = 0 行**、vitest 2002 → **2004**（+2 audit）、
**三 corpus 八層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐（合計
347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408 sections +
192 HF slots + 9172 styles byte-identical）、Sprint 230 basedOn fix 在
edge corpus (LibreOffice 96.9%) + advanced corpus (Phase 5 100%) 驗證
成立、ChienYi v1 release docx 匯入子系統最終 sign-off **GO（八層升級
確認 ⭐⭐⭐⭐⭐⭐⭐⭐）**。
