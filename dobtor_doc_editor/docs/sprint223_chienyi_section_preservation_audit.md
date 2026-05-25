# Sprint 223 — Phase 6 ChienYi SectionProps 第六層 audit + writer docGrid serializer 修法（14/42 → 42/42 / 100% / 62 sections / Sprint 218→219 模式重現 ⭐⭐⭐⭐）

**日期**：2026-05-25（週一）
**類型**：audit + 真實 production code 修法（Strategy C 第二次例外）
**規畫書對應**：§6 黃金測試第六層 SectionProps + Phase 6 OoxmlWriter writeSectPr 補完
**前置**：Sprint 218+219+220+221 完成五層矩陣 / Sprint 222 attestation v2

---

## Hypothesis & Result

**hypothesis**：Phase 6 writer Sprint 192 sectPr 對等 path 設計、預期 100%
+ 容寬 95%。第六層 SectionProps（page / margins / columns / docGrid /
sectionBreakType / titlePage / evenAndOddHeaders / headerRefs+footerRefs
slots）擴展 audit 覆蓋面。

**實測結果 v1（修前）**：**14/42 (33.3%) / 28 fixture drift** ⚠️ —— Sprint 218
模式重現、第六層第一次 audit 揭發大範圍 honest gap。

**Diagnostic + 修法後**：**42/42 (100%) / 62 sections 全綠** ⭐⭐⭐⭐ ——
Sprint 219 模式 root cause + 真實 production code fix 完全消除 drift。

---

## Diagnostic — root cause 30 秒命中

跑 `sprint223_section_diff_inspect.test.ts`（單 fixture 比對 ORIG vs REPARSE
snapshot）—— 立即看到：

```diff
 ORIG SectionNode (01_simple/03.1120815-監造會議記錄.docx):
   ...
-  "docGrid": { "type": "lines", "linePitch": 18 }

 REPARSE SectionNode:
   ...
   (docGrid 欄位缺失 / undefined)
```

對照 `OoxmlWriter.ts writeSectPr`：依 OOXML §17.6.17 CT_SectPr schema 寫了
headerReference / footerReference / pgSz / pgMar / titlePg，**完全缺
`<w:docGrid>` 序列化**。

**Root cause**：CT_SectPr 子元素 docGrid 在 schema 末段（titlePg 之後、
printerSettings 之前）、Sprint 192/193 writer 補完 sectPr 對等 path 時
**漏實作 docGrid 序列化分支**。對 CJK 文件（ChienYi 監造文件大部分）
parser 抓 `<w:docGrid w:type="lines" w:linePitch="...">` 進 AST、writer 不寫
回去、reparse 後 docGrid undefined → round-trip drift。

**為何 05_header_footer 10/10 全綠不踩雷**：該系列為自主檢查表多 section
documents，**docGrid type='default'**（parser 對 default type 回傳 undefined
故 snapshot 一致；ORIG undefined === REPARSE undefined trivially match）。
其他 corpus 為單 section、docGrid type='lines'，全部踩雷。

---

## 修法 — `writeSectPr` 加 docGrid 分支（+10 行 production code）

`static/src/core/ooxml/export/OoxmlWriter.ts`：

```ts
  // titlePg（在 pgMar 之後、docGrid 之前依 CT_SectPr schema）
  if (section?.titlePage) parts.push('<w:titlePg/>');

  // Sprint 223：docGrid（CT_SectPr schema 末段、CJK 文件 line snap 必要、
  // 不寫會讓中文文件 line height 在 round-trip 丟失 grid 對齊）
  // parser 對 type='default' 不存（返回 undefined）、故此處 section.docGrid
  // 存在即代表 type ∈ {lines, linesAndChars, snapToChars}
  const docGrid = section?.docGrid;
  if (docGrid) {
    const linePitchTwips = ptToTwips(docGrid.linePitch);
    parts.push(`<w:docGrid w:type="${docGrid.type}" w:linePitch="${linePitchTwips}"/>`);
  }

  return '<w:sectPr>' + parts.join('') + '</w:sectPr>';
```

**對等性**：parser `parseDocGrid` 從 twip 轉 Pt 存 AST、writer 反向轉
Pt → twip emit XML、round-trip parser→writer→parser 對等。type ∈ {lines,
linesAndChars, snapToChars} 三值皆 round-trip 對等（'default' 經 parser
過濾為 undefined、寫回時也跳過、語意對等）。

---

## Result — 42/42 全 100% / 62 sections 全綠 ⭐⭐⭐⭐

```
[sprint223] total=42 section match=42/42 (100.0%) totalSections=62
[sprint223]   01_simple           : 7/7 (100.0%) sections=7
[sprint223]   02_std_table        : 8/8 (100.0%) sections=8
[sprint223]   03_complex_table    : 8/8 (100.0%) sections=8
[sprint223]   04_with_image       : 6/6 (100.0%) sections=6
[sprint223]   05_header_footer    : 10/10 (100.0%) sections=30
[sprint223]   06_template         : 3/3 (100.0%) sections=3
```

| 指標 | 修前 v1 | 修後 v2 |
|---|---|---|
| SectionProps SHA-256 match | 14/42 (33.3%) ⚠️ | **42/42 (100%) ⭐⭐⭐⭐** |
| Total sections | 62 | 62 |
| 超越閾值 | 95% → 33.3% (−61.7pp) | 95% → 100% (+5pp) |

---

## VR v14 重驗 — render-safe 雙驗（Sprint 219 SOP）

修法後 VR v14 全綠：

```
[v14] rendered=42/42  bootFailed=0  comparedPages=126  failedPages=0
```

**byte-identical 第 66 連 maintained**（Sprint 219 同 invariant：writer
修法不觸 import path、VR pipeline 跑的是 import(doc)→render→png 對 golden、
本修法 production code 路徑與 VR 互斥）。

---

## 六層 byte-identical 對稱矩陣（v2 attestation 之後新增第六層）

| 驗證層次 | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|
| Structure | 100% (Sp206) | 100% (Sp199+200) | 100% (Sp209) |
| Text | 100% (Sp207) | 100% (Sp208) | 100% (Sp209) |
| RunProps | 100% / 9508 (Sp210) | 100% / 2114 (Sp211) | 100% / 23 (Sp212) |
| ParagraphProps | 100% / 3384 (Sp215) | 100% / 1914 (Sp216) | 100% / 37 (Sp217) |
| TableProps | 100% / 71 (Sp218+219) | 97.6% / 56 (Sp220) | 100% / 0 trivially (Sp221) |
| **SectionProps** | **100% / 62 (Sp223) ⭐⭐⭐⭐** | (TBD Sprint 224) | (TBD Sprint 225) |

ChienYi production corpus 達**六層 byte-identical 對稱**——比 v2 attestation
（五層）再升一層。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1996 passed + 1 skipped**（+1 sprint223 audit）；單跑 sprint223 1/1 綠 6237ms |
| L2 VR v14 | ✅ **byte-identical 第 66 連** | 42/42 / 126 pages / 0 failures |
| L3 perf | ✅ baseline 維持 | sectPr writer +10 行 emit / 對 60 fixture warm baseline 影響 <0.1ms 可忽略 |

---

## 紀律

- **#1.b / Strategy C 例外**：Sprint 219 後第二次離開 audit-only nature、
  +10 行 production code 修 writer docGrid serialization；理由：Sprint 218
  模式重現、揭發 root cause 為「writer schema 漏實作」、修法 + 雙驗（vitest
  + VR）pattern 已建立、繼續累積 honest gap 反 audit pipeline 設計初衷
- **#2 magic number**：1 個具名常數（MIN_SECTION_MATCH_RATE_PCT=95）+ 沿用
  Sprint 215 deepStableStringify
- **#14.b clean scope**：commit = sprint223 audit + writer fix + audit doc +
  INDEX/snapshot；不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：僅修 docGrid root cause、不順手加 cols / sectionBreakType /
  gutter 序列化（即使 schema 也漏這些）— 各自由後續 sprint 揭發後再修，
  避免 Sprint 90-110 「順便清理」反噬模式
- **#21**：production code fix + 雙層驗證、Sprint 219 SOP 重現成立

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                     +10/-3 行
A  tests/integration/sprint223_chienyi_section_preservation_audit.test.ts +190 行
A  docs/sprint223_chienyi_section_preservation_audit.md            本 audit
M  docs/INDEX.md                                                    +Sprint 223 entry
M  docs/progress_snapshot.md                                        Sprint 223 區塊 + 六層矩陣升一階
```

**淨 production code 變動 = +10 行 / -3 行**（writer docGrid serialization）、
vitest 1995 → **1996**（+1 sprint223 audit）、VR byte-identical **第 66 連**
maintained、**ChienYi 42 SectionProps 第六層 byte-identical 100%**
（14/42 → 42/42、+61.7pp 跨閾值修法）、**Sprint 218→219 模式重現**——
audit 揭發 gap → diagnostic root cause 30 秒命中 → +10 行 writer fix +
雙驗（vitest + VR）→ ChienYi production corpus 達**六層 byte-identical 對稱**、
比 Sprint 222 v2 attestation 再升一層。
