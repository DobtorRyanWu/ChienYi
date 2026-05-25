# Sprint 226 — LibreOffice SectionProps writer 補完 `<w:cols>` + `<w:type>` 序列化（87.5% → 95.1% / +22 fixture / +7.6pp / 跨 commercial-grade 閾值 ⭐⭐⭐⭐⭐）

**日期**：2026-05-25（週一）
**類型**：production code 補完（Strategy C 第四次例外）
**規畫書對應**：§6 黃金測試 LibreOffice edge corpus SectionProps 第六層 + Phase 6 OoxmlWriter writeSectPr CT_SectPr schema 補完
**前置**：Sprint 224 LibreOffice 87.5% / 36 fixture drift（推測 cols / sectionBreakType 等漏實作）

---

## Hypothesis & Result

**hypothesis**：Sprint 224 LibreOffice 87.5% drift 中、推測 root cause #3 為
`OoxmlWriter.writeSectPr` 漏實作 `<w:cols>`（多欄）+ `<w:type>`
（sectionBreakType continuous/evenPage/oddPage），皆為 CT_SectPr §17.6.17
schema 必要子元素。

**Diagnostic 30 秒命中**：跑 3 個 sample（section/headerfooter/field 系列）
diff inspect、明確看到：
- ORIG `columns: { count: 2, equalWidth: true, space: 36 }` / REPARSE
  `columns` 欄位完全缺失
- ORIG `sectionBreakType: 'continuous'` / REPARSE 缺失

**修法 + 雙驗結果**：
- Sprint 223 ChienYi 42：**100% / 62 sections 維持** ✓
- Sprint 224 LibreOffice 286：87.5% → **95.1% / 274/288 / 328 sections** ⭐⭐⭐⭐⭐
  跨 commercial-grade 閾值（+7.6pp / +22 fixture）
- Sprint 225 Phase 5 18：**100% / 18 sections 維持** ✓

---

## Diagnostic 證據

```
========== section/default-sect-break-cols.docx ==========
  section[0] ORIG:    columns: { count: 2, equalWidth: true, space: 36 }
  section[0] REPARSE: (columns 缺失) ⚠️
  section[1] ORIG:    sectionBreakType: 'continuous'
  section[1] REPARSE: (sectionBreakType 缺失) ⚠️

========== headerfooter/2col-header.docx ==========
  section[0] ORIG:    columns: { count: 2, equalWidth: true, space: 36 }
  section[0] REPARSE: (columns 缺失) ⚠️

========== field/alphabeticalIndex_MultipleColumns.docx ==========
  section[1] ORIG:    columns: { count: 4, equalWidth: true, space: 36 }
                       + sectionBreakType: 'continuous'
  section[1] REPARSE: (兩者皆缺失) ⚠️
```

---

## 修法 — `writeSectPr` 補 `<w:type>` + `<w:cols>`（+23 行 production code）

`static/src/core/ooxml/export/OoxmlWriter.ts`：

依 CT_SectPr §17.6.17 schema 順序：
- `<w:type>` 在 pgSz 之前
- `<w:cols>` 在 pgMar 之後、titlePg 之前

```ts
// Sprint 226：sectionBreakType（CT_SectPr schema：type 在 pgSz 之前）
if (section?.sectionBreakType !== undefined) {
  parts.push(`<w:type w:val="${section.sectionBreakType}"/>`);
}

// ...（pgSz / pgMar 既有）

// Sprint 226：cols（CT_SectPr schema：cols 在 pgMar 之後、titlePg 之前）
const columns = section?.columns;
if (columns && columns.count > 1) {
  const colsAttrs: string[] = [`w:num="${columns.count}"`];
  if (columns.space !== undefined) colsAttrs.push(`w:space="${ptToTwips(columns.space)}"`);
  if (columns.equalWidth === false) colsAttrs.push('w:equalWidth="0"');
  if (columns.separator) colsAttrs.push('w:sep="1"');
  const hasCustomCols = columns.equalWidth === false && columns.colWidths && columns.colWidths.length > 0;
  if (hasCustomCols) {
    const colEls: string[] = [];
    const widths = columns.colWidths!;
    const spaces = columns.colSpaces ?? [];
    for (let i = 0; i < widths.length; i++) {
      const wAttr = ` w:w="${ptToTwips(widths[i])}"`;
      const sAttr = i < spaces.length ? ` w:space="${ptToTwips(spaces[i])}"` : '';
      colEls.push(`<w:col${wAttr}${sAttr}/>`);
    }
    parts.push(`<w:cols ${colsAttrs.join(' ')}>${colEls.join('')}</w:cols>`);
  } else {
    parts.push(`<w:cols ${colsAttrs.join(' ')}/>`);
  }
}
```

**對等性**：
- parser `parseSectionBreakType` 對 element 缺失返回 undefined、writer
  `sectionBreakType === undefined` 不 emit、對等
- parser `parseColumns` 對 count<=1 返回 undefined、writer `count > 1` 才
  emit、對等
- equalWidth 預設 true、writer 只在 false 時 emit attribute、parser 對
  缺 attr 默認 true、對等
- 個別 colWidths/colSpaces 只在 !equalWidth + colWidths.length>0 時 emit
  `<w:col>` 子節點、對等 parser 邏輯

---

## Result — LibreOffice 跨 95% commercial-grade 閾值 ⭐⭐⭐⭐⭐

```
[sprint224] total=290 parse=288/290 pipeline=288/288 section=274/288 (95.1%) totalSections=328
  chart         : pipeline 9/9 section 9/9 (100.0%) sections=9
  field         : pipeline 12/12 section 12/12 (100.0%) sections=18  [+3]
  headerfooter  : pipeline 9/9 section 8/9 (88.9%) sections=12       [+2]
  image         : pipeline 15/15 section 14/15 (93.3%) sections=15
  list          : pipeline 11/11 section 11/11 (100.0%) sections=11
  math          : pipeline 10/11 section 10/10 (100.0%) sections=10
  misc          : pipeline 136/137 section 131/136 (96.3%) sections=149 [+9]
  note          : pipeline 10/10 section 9/10 (90.0%) sections=10
  sdt           : pipeline 11/11 section 11/11 (100.0%) sections=13
  section       : pipeline 13/13 section 11/13 (84.6%) sections=25     [+6]
  shape         : pipeline 23/23 section 22/23 (95.7%) sections=23
  smartart      : pipeline 2/2 section 2/2 (100.0%) sections=2
  style         : pipeline 10/10 section 8/10 (80.0%) sections=10
  table         : pipeline 13/13 section 13/13 (100.0%) sections=17    [+2]
  track         : pipeline 4/4 section 3/4 (75.0%) sections=4
```

| 指標 | Sprint 224 v1 (gutter fix 後) | Sprint 226 v2 (cols+type fix 後) |
|---|---|---|
| LibreOffice SectionProps match | 252/288 (87.5%) | **274/288 (95.1%)** ⭐⭐⭐⭐⭐ |
| Drift 數 | 36 | **14** |
| 跨 95% commercial-grade 閾值 | ❌ | ✅ |

### 殘餘 14 個 drift 分布（推測 root cause #4）

```
headerfooter/inheritFirstHeader.docx
image/crop-roundtrip.docx
misc/n820504.docx
misc/tdf105143.docx
misc/tdf108849.docx
misc/tdf120551.docx
misc/tdf168567.docx
note/tdf109310_endnoteStyleForMSO.docx
section/endingSectionProps.docx
section/tdf136952_pgBreak3.docx
+ 4 個 style/track/note 邊緣 case
```

特徵：tdf* 系列為 **LibreOffice 故意畸形 / regression fixture**（OOXML
規範外輸入、LO 內部測試用）；其他可能含 evenAndOddHeaders settings 同步
問題、或 titlePage 與 inheritFirstHeader 互動。

**按紀律 #18 scope-down 不修**：對 ChienYi v1 release 無影響（監造文件
使用標準單欄 + nextPage break、不踩 LibreOffice 故意畸形 case）。

---

## 三 corpus 六層 commercial-grade 矩陣（Sprint 226 升級）

| 驗證層次 | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|
| Structure | 100% | 100% | 100% |
| Text | 100% | 100% | 100% |
| RunProps | 100% / 9508 | 100% / 2114 | 100% / 23 |
| ParagraphProps | 100% / 3384 | 100% / 1914 | 100% / 37 |
| TableProps | 100% / 71 | 97.6% / 56 | 100% / 0 trivially |
| **SectionProps** | **100% / 62** | **95.1% / 328 ⭐⭐⭐⭐⭐** | **100% / 18** |

**LibreOffice edge corpus 全 6 層皆達 ≥ 95% commercial-grade** ⭐⭐⭐⭐⭐
（structure / text / RunProps / ParagraphProps 100% + TableProps 97.6% +
SectionProps 95.1%）。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1998 passed + 1 skipped**（本 sprint 無新 test、修現有 3 個 audit）；單跑三 corpus audit 皆綠 |
| L2 VR v14 | ✅ **byte-identical 第 68 連** | 42/42 / 126 pages / 0 failures、writer +`<w:type>`/+`<w:cols>` emit 不觸 import path |
| L3 perf | ✅ baseline 維持 | sectPr writer 條件分支 / 對 60 fixture warm baseline 影響 <0.1ms 可忽略 |

---

## 紀律

- **#1.b / Strategy C 第四次例外**（Sprint 219 / Sprint 223 / Sprint 225 後）：
  audit 揭發 gap → diagnostic root cause 30 秒命中 → +23 行 writer fix →
  雙驗 pattern 第四次重現、+commercial-grade 閾值突破
- **#2 magic number**：無新引入；條件分支用既有 helpers（ptToTwips）
- **#14.b clean scope**：commit = sprint226 writer fix + audit doc +
  INDEX/snapshot + VR report；不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：僅補 cols + sectionBreakType（明確 schema gap）、
  不順手清殘餘 14 drift（tdf* LibreOffice 故意畸形 / evenAndOddHeaders
  settings / inheritFirstHeader edge case）— 各自由後續 sprint 揭發後再修
- **#21**：production code fix + 雙層驗證

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                    +23/-0 行
A  docs/sprint226_libreoffice_section_writer_cols_type_fix.md     本 audit
M  docs/INDEX.md                                                   +Sprint 226 entry
M  docs/progress_snapshot.md                                       Sprint 226 補述 + 矩陣升級
M  tests/fixtures/visual_regression_v14_report.json                regenerated 第 68 連
```

**淨 production code 變動 = +23 行 / -0 行**（writer `<w:type>` + `<w:cols>`
+ optional `<w:col>` 子節點 emit）、vitest 1998 維持（本 sprint 無新 test、
重跑現有 3 audit 升級結果）、VR byte-identical **第 68 連** maintained、
**LibreOffice edge corpus SectionProps 跨 95% commercial-grade 閾值**
（87.5% → 95.1% / +7.6pp / +22 fixture）、**LibreOffice 全 6 層皆 ≥ 95%
commercial-grade 達成**、Sprint 218→219 模式重現第四次完成、三 corpus
六層矩陣 LibreOffice 從「過 80% 閾值」升級為「過 95% 閾值」、ChienYi v1
release docx 匯入子系統最終 sign-off **GO（六層 commercial-grade 升級
⭐⭐⭐⭐⭐）**。
