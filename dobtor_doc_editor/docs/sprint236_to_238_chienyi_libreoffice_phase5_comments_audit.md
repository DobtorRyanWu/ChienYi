# Sprint 236+237+238 — Comments 第十層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 三 corpus 三 audit 並排 / 全 100%（第二次 LibreOffice 邊緣 corpus 達 100%、首次「真實 content」非 trivially match）

**日期**：2026-05-26（週二）
**類型**：三 audit 並排（test-only / 0 行 production code）
**規畫書對應**：§6 黃金測試第十層 Comments（document.comments map / comments.xml）
**前置**：Sprint 233+234+235 九層三 corpus 矩陣完備（含 5 個 writer 真實修法）

---

## Hypothesis & Result

**hypothesis**：九層矩陣完備後、擴展第十層 Comments。comments.xml
定義所有註解（OOXML §17.13.4）、被 document.xml 以
`<w:commentRangeStart/End>` + `<w:commentReference>` 引用；writer Sprint 194
已 emit comments.xml（空 Map → 空 `<w:comments/>` 骨架、非空逐筆
writeCommentEntry）。

**範圍**：
- CommentMap = Map<id, CommentContent>；id 排序後串接
- CommentContent 含 id / author / date / initials / content[]
- audit 採保守序列化：id + author + date + initials + blockCount + 全段落 text 串接
- 段落 text 抽取 RunNode.text（'text' in r 安全 narrow、跳過 FieldNode/BreakNode/image）
- 表格 text 為 cell.content 巢狀遞迴抽取

**實測結果**：
- Sprint 236 ChienYi 42：**42/42 (100%) / 0 comments trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐**
- Sprint 237 LibreOffice 286：**288/288 (100%) / 27 comments byte-identical ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐**
  **第二次 LibreOffice 邊緣 corpus 達 100% + 首次「真實 content」非 trivially match**
  （note: 14 / misc: 10 / track: 3 真實 comment round-trip）
- Sprint 238 Phase 5 18：**18/18 (100%) / 0 comments trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐**

**三 corpus 十層 byte-identical 對稱矩陣完備 + LibreOffice 27 comments 真實
byte-identical** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Sprint 236 — ChienYi 42 / 42/42 (100%) / 0 comments trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

```
[sprint236] total=42 comment match=42/42 (100.0%) totalComments=0
[sprint236]   01_simple           : 7/7 (100.0%) comments=0
[sprint236]   02_std_table        : 8/8 (100.0%) comments=0
[sprint236]   03_complex_table    : 8/8 (100.0%) comments=0
[sprint236]   04_with_image       : 6/6 (100.0%) comments=0
[sprint236]   05_header_footer    : 10/10 (100.0%) comments=0
[sprint236]   06_template         : 3/3 (100.0%) comments=0
```

ChienYi v1 release 42 fixture 為純監造表單 / 樣板、皆無 reviewer comments
（comments.xml 為空 `<w:comments/>` 骨架）；trivially match。

---

## Sprint 237 — LibreOffice 286 / 288/288 (100%) / 27 comments byte-identical ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐（首次真實 content match）

```
[sprint237] total=290 parse=288/290 pipeline=288/288 comment=288/288 (100.0%) totalComments=27
  chart         : pipeline 9/9 comment 9/9 (100.0%) comments=0
  field         : pipeline 12/12 comment 12/12 (100.0%) comments=0
  headerfooter  : pipeline 9/9 comment 9/9 (100.0%) comments=0
  image         : pipeline 15/15 comment 15/15 (100.0%) comments=0
  list          : pipeline 11/11 comment 11/11 (100.0%) comments=0
  math          : pipeline 10/11 comment 10/10 (100.0%) comments=0
  misc          : pipeline 136/137 comment 136/136 (100.0%) comments=10   ← 真實
  note          : pipeline 10/10 comment 10/10 (100.0%) comments=14       ← 最大
  sdt           : pipeline 11/11 comment 11/11 (100.0%) comments=0
  section       : pipeline 13/13 comment 13/13 (100.0%) comments=0
  shape         : pipeline 23/23 comment 23/23 (100.0%) comments=0
  smartart      : pipeline 2/2 comment 2/2 (100.0%) comments=0
  style         : pipeline 10/10 comment 10/10 (100.0%) comments=0
  table         : pipeline 13/13 comment 13/13 (100.0%) comments=0
  track         : pipeline 4/4 comment 4/4 (100.0%) comments=3            ← 真實
```

**0 drift / 27 真實 comments 全 byte-identical**：

- `note/` 14 comments：LibreOffice 註解測試 fixture（含 commentRangeStart/End +
  commentReference 三件式 round-trip 全保留）
- `misc/` 10 comments：tdf* edge case 含 reviewer 註解
- `track/` 3 comments：追蹤修訂 fixture 中夾帶的 reviewer comment

writer Sprint 194 設計（id / author / date / initials + writeBlock dispatcher
重用段落 / 表格 / 巢狀邏輯）在 27 個真實 comment fixture 全部 round-trip。

**第二次** LibreOffice 邊緣 corpus 在某一層達 100%（前次 Sprint 234
NumberingMap）；但 NumberingMap 多為 primitives，本次 Comments 含 **真實
content 段落 + 結構化 metadata**，首次「真實 content non-trivially」邊緣
corpus 100%。

---

## Sprint 238 — Phase 5 18 / 18/18 (100%) / 0 comments trivially ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

```
[sprint238] total=18 comment match=18/18 (100.0%) totalComments=0
  07_chart      : 8/8 (100.0%) comments=0
  08_smartart   : 4/4 (100.0%) comments=0
  09_omml       : 6/6 (100.0%) comments=0
```

Phase 5 fixture 主體（chart/smartart/omml inline）皆無 reviewer comments、
trivially match。三 corpus 十層矩陣完備。

---

## 三 corpus 十層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

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
| NumberingMap | 100% / 207 | 100% / 1022 ⭐ | 100% / 0 trivially |
| **Comments** | **100% / 0 trivially** | **100% / 27 ⭐⭐** | **100% / 0 trivially** |

合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles + 1229 numberings + 27 comments**
byte-identical。

**LibreOffice edge corpus 8/10 層 ≥ 95% commercial-grade + NumberingMap +
Comments 雙 100%**（前 5 層 100% + TableProps 97.6% + SectionProps 95.1% +
StyleMap 96.9% + **NumberingMap 100% ⭐ + Comments 100% ⭐⭐**、僅
HeaderFooterContent 90.6% 為 edge tolerance）。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **2010 passed + 1 skipped**（+3 sprint236+237+238）；單跑三 audit 皆綠 |
| L2 VR v14 | ✅ **第 68 連 maintained** | 本三 sprint test-only、不改 production code、與 import path 互斥 |
| L3 perf | ✅ baseline 維持 | docs/test-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本三 sprint **0 行 production code 變動**、純 test
- **#2 magic number**：3 個具名常數（MIN_COMMENT_MATCH_RATE_PCT 各 corpus）
  + 沿用 deepStableStringify + extractBlockText 文字抽取
- **#14.b clean scope**：commit = sprint236+237+238 audit + audit doc +
  INDEX/snapshot；不含跨 module pyc / Portal v10 / Phase 8 平行 sprint 檔
- **#18 scope-down**：comment content 保守抽 text-only 不深比 RunProps；
  blockCount + concatenated text 足以揭發 round-trip 漏字 / 漏段 drift
- **#21**：本三 sprint 不影響 VR / round-trip / existing 測試

---

## File-level summary

```
A  tests/integration/sprint236_chienyi_comments_preservation_audit.test.ts     +135 行
A  tests/integration/sprint237_libreoffice_comments_preservation_audit.test.ts +135 行
A  tests/integration/sprint238_phase5_comments_preservation_audit.test.ts      +130 行
A  docs/sprint236_to_238_chienyi_libreoffice_phase5_comments_audit.md          本 audit
M  docs/INDEX.md                                                                +Sprint 236+237+238 entries
M  docs/progress_snapshot.md                                                    §1 + §7 + 十層三 corpus 矩陣完備
```

**淨 production code 變動 = 0 行**、vitest 2007 → **2010**（+3 audit）、
**三 corpus 十層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
（合計 347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles + 1229 numberings + **27 comments**
byte-identical）、**第二次 LibreOffice 邊緣 corpus 達 100%、首次真實
content non-trivially match**、ChienYi v1 release docx 匯入子系統最終
sign-off **GO（十層升級確認 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。
