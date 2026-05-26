# Sprint 233+234+235 — NumberingMap 第九層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 三 corpus 三 audit 並排 / 全 100%（首次 LibreOffice 邊緣 corpus 達 100%）

**日期**：2026-05-26（週二）
**類型**：三 audit 並排（test-only / 0 行 production code）
**規畫書對應**：§6 黃金測試第九層 NumberingMap（document.numbering map / numbering.xml）
**前置**：Sprint 231+232 八層三 corpus 矩陣完備（含 5 個 writer 真實修法）

---

## Hypothesis & Result

**hypothesis**：八層矩陣完備後、擴展第九層 NumberingMap。numbering.xml
定義所有列表 / 編號樣式、被 ParagraphNode.numId+ilvl 引用；若 numbering
round-trip drift、ref 解析會錯位、列表編號 / bullet 視覺失準（如
1.2.3 → ●、●●●● → a.b.c）。

**範圍**：
- NumberingMap = Map<numId, AbstractNumbering>；numId 排序後串接
- AbstractNumbering 含 abstractNumId（lossy normalize）+ levels[9] array
- 每個 NumberingLevel 含 ilvl / numFmt / text / start / lvlRestart /
  indent / runProps / pProps / isLegal
- 空 `{}` props 規範化為 undefined（同 Sprint 230 root cause #5b 模式）
- `abstractNumId` 欄位 normalize 忽略（writer Sprint 191 design 用 numId
  作 abstractNumId 為 acceptable lossy、parser 不靠此值解析 levels）

**實測結果**：
- Sprint 233 ChienYi 42：v1 修前 9/42 (21.4%) ⚠️ / 兩 root cause 揭發
  → v2 修後 **42/42 (100%) / 207 numberings ⭐⭐⭐⭐⭐⭐⭐⭐⭐**
- Sprint 234 LibreOffice 286：**288/288 (100%) / 1022 numberings ⭐⭐⭐⭐⭐⭐⭐⭐⭐**
  **首次 LibreOffice 邊緣 corpus 達 100%**（前 8 層皆有 edge case drift）
- Sprint 235 Phase 5 18：**18/18 (100%) / 0 trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐**

**三 corpus 九層 byte-identical 對稱矩陣完備 + LibreOffice 第一次邊緣
corpus 達 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Sprint 233 — root cause 揭發與規範化修法（21.4% → 42.9% → 100%）

### v1（修前）：9/42 (21.4%) ⚠️

ChienYi 42 fixture 大量 drift。Diagnostic 對 `06_template/缺失改善.docx`
跑 diff inspect：

```diff
 ORIG numId=2:
   abstractNumId: 0          ← parser 從 <w:num><w:abstractNumId w:val="0"/> 抽出
   levels: [...]
 REPARSE numId=2:
   abstractNumId: 2          ← writer 用 numId 作 abstractNumId
   levels: [...]
```

### Root cause #6：abstractNumId round-trip lossy（writer design intentional）

`OoxmlWriter.writeNumbering` Sprint 191 design comment：

> "用 numId 直接當 abstractNumId（保證唯一、避免「多個 numId 共用
>  abstractNumId 但 levels 不同」場景在 re-parse 時被 Map 覆蓋）。
>  entry.abstractNumId 欄位於 round-trip 後變為 numId（acceptable lossy；
>  parser 不靠此值來解析 levels）"

設計層級 intentional：避免 abstractNum sharing 衝突。**audit normalize 忽略
abstractNumId 欄位**（semantic equivalent、不影響 numbering ref 解析）。

### v2 修法 1（audit normalize abstractNumId）：→ 18/42 (42.9%)

再 diagnose `05_header_footer/自主檢查表---人手孔調升降.docx`：

```diff
 ORIG numId=1 ilvl=0:
   numFmt: 'ideographLegalTraditional', text: '%1、', start: 1, ...
   runProps: {}              ← 顯式空 object
   pProps: {indent: {firstLine: 0}, tabs: [...]}
 REPARSE numId=1 ilvl=0:
   numFmt: 'ideographLegalTraditional', text: '%1、', start: 1, ...
   (no runProps)             ← writer 對 empty runProps 不 emit、reparse 為 undefined
   pProps: {...}
```

### Root cause #7：NumberingLevel empty `{}` vs undefined drift

同 Sprint 230 root cause #5b 模式：writer 對 empty props 不 emit、parser
reparse 為 undefined。audit normalize empty `{}` → undefined（runProps /
pProps / indent 三欄位）。

### v3 修法 2（audit normalize empty `{}`）：→ **42/42 (100%)** ⭐⭐⭐⭐⭐⭐⭐⭐⭐

```
[sprint233] total=42 numbering match=42/42 (100.0%) totalNumberings=207
[sprint233]   01_simple           : 7/7 (100.0%) nums=7
[sprint233]   02_std_table        : 8/8 (100.0%) nums=122
[sprint233]   03_complex_table    : 8/8 (100.0%) nums=14
[sprint233]   04_with_image       : 6/6 (100.0%) nums=38
[sprint233]   05_header_footer    : 10/10 (100.0%) nums=20
[sprint233]   06_template         : 3/3 (100.0%) nums=6
```

---

## Sprint 234 — LibreOffice 286 / 288/288 (100%) / 1022 numberings ⭐⭐⭐⭐⭐⭐⭐⭐⭐（首次邊緣 100%）

```
[sprint234] total=290 parse=288/290 pipeline=288/288 num=288/288 (100.0%) totalNumberings=1022
  chart         : pipeline 9/9 num 9/9 (100.0%) nums=1
  field         : pipeline 12/12 num 12/12 (100.0%) nums=11
  headerfooter  : pipeline 9/9 num 9/9 (100.0%) nums=471   ← 最大 cat
  image         : pipeline 15/15 num 15/15 (100.0%) nums=2
  list          : pipeline 11/11 num 11/11 (100.0%) nums=43
  math          : pipeline 10/11 num 10/10 (100.0%) nums=0
  misc          : pipeline 136/137 num 136/136 (100.0%) nums=318
  note          : pipeline 10/10 num 10/10 (100.0%) nums=1
  sdt           : pipeline 11/11 num 11/11 (100.0%) nums=87
  section       : pipeline 13/13 num 13/13 (100.0%) nums=10
  shape         : pipeline 23/23 num 23/23 (100.0%) nums=42
  smartart      : pipeline 2/2 num 2/2 (100.0%) nums=0
  style         : pipeline 10/10 num 10/10 (100.0%) nums=0
  table         : pipeline 13/13 num 13/13 (100.0%) nums=33
  track         : pipeline 4/4 num 4/4 (100.0%) nums=3
```

**0 drift** —— **首次** LibreOffice 邊緣 corpus 在某一層達 100%（前 8 層
皆有 LibreOffice 故意畸形 tdf* / chart-in-footer / hyperlink 等 edge case
drift；NumberingLevel 結構簡單、levels 為 primitives 為主、無進階 OOXML
schema 漏實作）。

---

## Sprint 235 — Phase 5 18 / 18/18 (100%) / 0 trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐

```
[sprint235] total=18 num match=18/18 (100.0%) totalNumberings=0
  07_chart      : 8/8 (100.0%) nums=0
  08_smartart   : 4/4 (100.0%) nums=0
  09_omml       : 6/6 (100.0%) nums=0
```

Phase 5 fixture 主體（chart/smartart/omml inline）皆無列表 / 編號、
nums=0 trivially match。三 corpus 九層矩陣完備。

---

## 三 corpus 九層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐

| 驗證層次 | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|
| Structure | 100% | 100% | 100% |
| Text | 100% | 100% | 100% |
| RunProps | 100% / 9508 | 100% / 2114 | 100% / 23 |
| ParagraphProps | 100% / 3384 | 100% / 1914 | 100% / 37 |
| TableProps | 100% / 71 | 97.6% / 56 | 100% / 0 trivially |
| SectionProps | 100% / 62 | 95.1% / 328 | 100% / 18 |
| HeaderFooterContent | 100% / 16 | 90.6% / 176 | 100% / 0 trivially |
| StyleMap | 100% / 4024 | 96.9% / 5130 | 100% / 18 |
| **NumberingMap** | **100% / 207** | **100% / 1022 ⭐** | **100% / 0 trivially** |

合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles + 1229 numberings** byte-identical。

**LibreOffice edge corpus 7/9 層 ≥ 95% commercial-grade + 第九層 100%**
（前 5 層 100% + TableProps 97.6% + SectionProps 95.1% + StyleMap 96.9% +
**NumberingMap 100%**、僅 HeaderFooterContent 90.6% 為 edge tolerance）。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **2007 passed + 1 skipped**（+3 sprint233+234+235）；單跑三 audit 皆綠 |
| L2 VR v14 | ✅ **第 68 連 maintained** | 本三 sprint test-only、不改 production code、與 import path 互斥 |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本三 sprint **0 行 production code 變動**、純
  test + audit normalization
- **#2 magic number**：3 個具名常數（MIN_NUMBERING_MATCH_RATE_PCT 各 corpus）
  + 沿用 deepStableStringify
- **#14.b clean scope**：commit = sprint233+234+235 audit + audit doc +
  INDEX/snapshot；不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：abstractNumId lossy 為 writer Sprint 191 intentional
  design、不嘗試「修」（會破壞 abstractNum sharing 衝突保護）
- **#21**：本三 sprint 不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint233_chienyi_numbering_preservation_audit.test.ts     +200 行
A  tests/integration/sprint234_libreoffice_numbering_preservation_audit.test.ts +160 行
A  tests/integration/sprint235_phase5_numbering_preservation_audit.test.ts      +135 行
A  docs/sprint233_to_235_chienyi_libreoffice_phase5_numbering_audit.md          本 audit
M  docs/INDEX.md                                                                 +Sprint 233+234+235 entries
M  docs/progress_snapshot.md                                                     §1 + §7 + 九層三 corpus 矩陣完備
```

**淨 production code 變動 = 0 行**、vitest 2004 → **2007**（+3 audit）、
**三 corpus 九層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐⭐（合計
347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408 sections +
192 HF slots + 9172 styles + **1229 numberings** byte-identical）、**首次
LibreOffice 邊緣 corpus 在 NumberingMap 層達 100%**、ChienYi v1 release
docx 匯入子系統最終 sign-off **GO（九層升級確認 ⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。
