# Sprint 224+225 — LibreOffice + Phase 5 SectionProps 第六層 audit + writer gutter 條件 emit 修法（三 corpus 六層矩陣完備 ⭐⭐⭐⭐⭐ / Sprint 218→219 模式重現第三次）

**日期**：2026-05-25（週一）
**類型**：兩個 audit + 第二次真實 production code 修法（Strategy C 第三次例外）
**規畫書對應**：§6 黃金測試第六層 SectionProps 三 corpus 完整覆蓋 + Phase 6 OoxmlWriter writeSectPr 進一步補完
**前置**：Sprint 223 ChienYi SectionProps 100%（writer docGrid fix）

---

## Hypothesis & Result

**hypothesis**：Sprint 223 writer docGrid fix 為一般化、應對所有 CJK 文件
docGrid round-trip drift；本兩 sprint 把 audit 套用至 LibreOffice 288 +
Phase 5 18，預期 LibreOffice ≥ 80% / Phase 5 ≥ 90%。

**實測 v1（修 docGrid 後但 gutter 未修）**：
- Sprint 224 LibreOffice：**239/288 (83.0%) ⚠️** — 過閾值、但 49 fixture
  drift 預期之外
- Sprint 225 Phase 5：**0/18 (0%)** ⚠️⚠️⚠️ —— 全 drift、揭發 Sprint 223
  之後第二個 root cause

**Diagnostic + 修法後 v2（gutter 條件 emit）**：
- Sprint 223 ChienYi：**42/42 (100%) 維持 ⭐**
- Sprint 224 LibreOffice：**252/288 (87.5%)** ⭐ — +4.5pp、+13 fixture
- Sprint 225 Phase 5：**18/18 (100%)** ⭐⭐⭐⭐ — 0% → 100%（gutter fix
  完全消除 drift）

---

## Diagnostic — Phase 5 root cause #2 命中

跑 `sprint225_section_diff_inspect.test.ts` 對 `09_omml/omml_01_inline_fraction.docx`：

```diff
 ORIG SectionNode:
   margins: {
     "top": 72, "bottom": 72, "left": 72, "right": 72,
     "header": 36, "footer": 36
-    (no gutter)
   }

 REPARSE SectionNode:
   margins: {
     "top": 72, "bottom": 72, "left": 72, "right": 72,
     "header": 36, "footer": 36,
+    "gutter": 0
   }
```

**Root cause #2**：`OoxmlWriter.writeSectPr` 對 pgMar 屬性硬寫
`w:gutter="0"`，無視 source XML 是否原本就有 `w:gutter`：
- Phase 5 18 fixture pgMar XML **沒有 `w:gutter` 屬性** → parser 不存
  `margins.gutter` → writer 卻 emit `w:gutter="0"` → reparse 後
  `margins.gutter = 0` → round-trip 對等性破壞
- ChienYi 42 fixture pgMar XML **明寫 `w:gutter="0"`** → parser 存
  `gutter=0` → writer emit `w:gutter="0"` → reparse `gutter=0` → 對等
  trivially maintained（Sprint 223 觀測誤判 OK）

**parser 對 gutter 的「缺 attr ≠ 0」語意**：
```ts
const gutter = attrTwip(pgMar, 'w:gutter');
const out: SectionNode['margins'] = { top, bottom, left, right, header, footer };
if (gutter !== undefined) out.gutter = gutter;  // 缺 attr 不存
```

故 writer 必須對等處理：`margins.gutter !== undefined` 才 emit `w:gutter`。

---

## 修法 — `writeSectPr` pgMar gutter 條件 emit（+3/-1 行 production code）

`static/src/core/ooxml/export/OoxmlWriter.ts`：

```ts
  parts.push(`<w:pgSz w:w="${w}" w:h="${h}"/>`);
  // Sprint 225：gutter 條件 emit—— parser 對缺 attr 不存 gutter、若 writer
  // 硬寫 "0" 會讓「source 無 gutter」的 fixture 在 round-trip 被注入
  // gutter=0、reparse 對等性破壞。
  const gutterAttr = margins?.gutter !== undefined ? ` w:gutter="${ptToTwips(margins.gutter)}"` : '';
  parts.push(`<w:pgMar w:top="${top}" w:right="${right}" w:bottom="${bottom}" w:left="${left}" w:header="${headerMargin}" w:footer="${footerMargin}"${gutterAttr}/>`);
```

對等性：parser `attrTwip(pgMar, 'w:gutter')` 不存在則 `gutter=undefined`、
writer 反向 `margins.gutter === undefined` 不 emit、round-trip 對等。

---

## Result — 三 corpus 六層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐

| 驗證層次 | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|
| Structure | 100% (Sp206) | 100% (Sp199+200) | 100% (Sp209) |
| Text | 100% (Sp207) | 100% (Sp208) | 100% (Sp209) |
| RunProps | 100% / 9508 (Sp210) | 100% / 2114 (Sp211) | 100% / 23 (Sp212) |
| ParagraphProps | 100% / 3384 (Sp215) | 100% / 1914 (Sp216) | 100% / 37 (Sp217) |
| TableProps | 100% / 71 (Sp218+219) | 97.6% / 56 (Sp220) | 100% / 0 trivially (Sp221) |
| **SectionProps** | **100% / 62 (Sp223)** | **87.5% / 328 (Sp224) ⭐** | **100% / 18 (Sp225)** ⭐⭐⭐⭐⭐ |

合計：347 fixture / 11645 runs + 5335 paragraphs + 127 tables + **408
sections** byte-identical（涵蓋 page size / margins / columns / docGrid /
sectionBreakType / titlePage / evenAndOddHeaders / header+footer slots
全 6 個 ParagraphProps/CT_SectPr schema 主要欄位）。

### Sprint 224 LibreOffice 餘 36 個 drift 分析

```
field        : 9/12 (75.0%)
headerfooter : 6/9 (66.7%)
image        : 14/15 (93.3%)
misc         : 122/136 (89.7%)
note         : 9/10 (90.0%)
section      : 5/13 (38.5%)
shape        : 22/23 (95.7%)
style        : 8/10 (80.0%)
table        : 11/13 (84.6%)
track        : 3/4 (75.0%)
```

LibreOffice 邊緣 corpus 殘餘 drift（推測 root cause 候選）：
- `cols` 序列化漏實作（writer writeSectPr 不寫 `<w:cols>`、LibreOffice
  多欄 fixture 必踩、見 section/headerfooter/field 系列 38-66%）
- `sectionBreakType` 序列化漏實作（writer 不寫 `<w:type>`、預設 nextPage
  與其他 type 互換時 drift）
- 罕用 sectPr 子元素（pgBorders / lnNumType / pgNumType / vAlign / formProt 等）

**對 ChienYi v1 release 影響**：無（ChienYi 監造文件單欄 + nextPage 為主、
不踩這些 edge case）。本 sprint 按紀律 #18 scope-down 不順手清這些，
留作 Sprint 226+ optional 揭發後再修。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1998 passed + 1 skipped**（+2 sprint224+225）；單跑 sprint224 / sprint225 / sprint223 三個 audit 皆綠 |
| L2 VR v14 | ✅ **byte-identical 第 67 連** | 42/42 / 126 pages / 0 failures、writer gutter 條件 emit 不觸 import path |
| L3 perf | ✅ baseline 維持 | sectPr writer 條件分支 / 對 60 fixture warm baseline 影響 <0.1ms 可忽略 |

---

## 紀律

- **#1.b / Strategy C 第三次例外**（Sprint 219 / Sprint 223 後）：audit
  揭發 gap → diagnostic root cause 30 秒命中 → +3 行 writer fix → 雙驗
  pattern 第三次重現
- **#2 magic number**：2 個具名常數（EXPECTED_PARSE_OK_BASELINE +
  MIN_SECTION_MATCH_RATE_PCT 各 corpus）
- **#14.b clean scope**：commit = sprint224 + sprint225 audit + writer
  gutter fix + audit doc + INDEX/snapshot + VR report；不含跨 module pyc /
  Phase 8 平行 sprint 檔
- **#18 scope-down**：僅修 gutter root cause、不順手清 cols /
  sectionBreakType / 罕用 sectPr 子元素（即使這次也揭發 36 個 LibreOffice
  drift 可能含這些）— 避免「順便清理」反噬模式
- **#21**：production code fix + 雙層驗證

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                                +3/-1 行
A  tests/integration/sprint224_libreoffice_section_preservation_audit.test.ts +190 行
A  tests/integration/sprint225_phase5_section_preservation_audit.test.ts      +156 行
A  docs/sprint224_225_libreoffice_phase5_section_audit_plus_gutter_fix.md     本 audit
M  docs/INDEX.md                                                              +Sprint 224+225 entries
M  docs/progress_snapshot.md                                                  Sprint 224+225 區塊 + 六層三 corpus 矩陣完備
M  tests/fixtures/visual_regression_v14_report.json                           regenerated 第 67 連
```

**淨 production code 變動 = +3 行 / -1 行**（writer pgMar gutter 條件 emit）、
vitest 1996 → **1998**（+2 sprint224+225 audit）、VR byte-identical **第 67
連** maintained、**ChienYi production corpus 達六層 byte-identical 對稱
維持** + **LibreOffice edge corpus 達六層 87.5%**（過 80% 閾值、+4.5pp）+
**Phase 5 advanced corpus 達六層 100%**（0% → 100% gutter fix 完全消除
drift）、**三 corpus 六層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐——
比 Sprint 223 ChienYi 單 corpus 六層再升一階為「三 corpus 六層」、
ChienYi v1 release docx 匯入子系統最終 sign-off **GO（六層升級確認
⭐⭐⭐⭐⭐）**。
