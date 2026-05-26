# Sprint 246+247+248+249+250+251 — FontTable 第十三層 + WebSettings 第十四層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / writer Sprint 147+148→246+249 gap 兩補 / 第五、六次 LibreOffice 邊緣 corpus 達 100% / 1883 fonts + 486 webSettings keys byte-identical

**日期**：2026-05-26（週二）
**類型**：六 audit 並排 + 兩 writer 真實修法（Sprint 218→219 模式重現第八+九次）
**規畫書對應**：§6 黃金測試第十三層 FontTable（fontTable.xml）+ 第十四層 DocumentWebSettings（webSettings.xml）
**前置**：Sprint 243+244+245 settings 第十二層完備

---

## Hypothesis & Result

**hypothesis**：十二層矩陣完備後、擴展第十三 + 第十四層。FontTable 和
WebSettings 同為 Sprint 147 / 148 capture-only、writer 完全不 emit；
本批 sprint 一次補完兩層、形成四個邊緣 corpus 100% 結果（NumberingMap +
Comments + Footnotes + Settings + FontTable + WebSettings = 6 個 100%）。

**範圍**：
- FontTable = Map<name, FontEntry>；FontEntry 含 name / altName / charset
  / family / pitch / panose1 / sig（usb0-3, csb0-1）
- DocumentWebSettings 5 個 toggle 欄位：optimizeForBrowser / allowPNG /
  saveSmartTagsAsXml / doNotSaveAsSingleFile / hasDivs
- audit 採保守序列化：font 以 name 字典序、webSettings 直接 deepStableStringify
- writer 兩個 part：fontTable.xml + webSettings.xml + 各自 rels + ContentType

**實測結果**：
- Sprint 246 ChienYi 42 v1（修前）：**0/42 (0%)** ⚠️ 揭發 root cause #10a
  writer 不 emit fontTable.xml
- Sprint 249 ChienYi 42 v1（修前）：**16/42 (38.1%)** ⚠️ writer 不 emit
  webSettings.xml + hasDivs round-trip drift（root cause #10b）
- writer 補完（+45 行 fontTable + 30 行 webSettings = 75 行 production code）
- Sprint 246 修後：**42/42 (100%) / 554 fonts**
- Sprint 247 LibreOffice：**288/288 (100%) / 1329 fonts byte-identical** ⭐⭐⭐⭐⭐
- Sprint 248 Phase 5：**18/18 (100%) / 0 trivially**
- Sprint 249 修後：**42/42 (100%) / 64 webSettings keys**
- Sprint 250 LibreOffice：**288/288 (100%) / 422 webSettings keys
  byte-identical** ⭐⭐⭐⭐⭐⭐
- Sprint 251 Phase 5：**18/18 (100%) / 0 trivially**

**三 corpus 十四層 byte-identical 對稱矩陣完備 + 第八、九次 writer 真實修法
+ 第五、六次 LibreOffice 邊緣 corpus 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Root cause #10a — writer 漏 fontTable.xml

Sprint 147 parser capture：fontTable.xml 解析正常（name + altName + charset
+ family + pitch + panose1 + sig）。但 OoxmlWriter.write 從未 emit。

42 fixture 全 0/42 (0%) 是預期結果，相同 Sprint 218→219 模式。

### 修法（+45 行）：fontTable.xml 完整 writer

- REL_TYPE_FONT_TABLE 常數
- parts 條件 emit `word/fontTable.xml`（fontTable.size > 0）
- writeContentTypes Override + writeDocumentRels Relationship 條件 emit
- writeFontTable（以 name 字典序輸出）+ writeFontEntry（7 欄位完整對稱）

---

## Root cause #10b — writer 漏 webSettings.xml + hasDivs 對稱性

Sprint 148 parser capture：5 個 toggle 欄位。writer 漏 emit webSettings.xml
（同 root cause #10a 模式）→ v1 修法後仍 38.1%。再次 diagnose 揭發深層
root cause：

```
parser WebSettingsParser.ts L65-68:
  case 'w:divs':
    if (directChildren(child).length > 0) {
      out.hasDivs = true;
    }
    // 空 <w:divs/>（無子元素）視為「無 divs」、與 OOXML §17.16.5 一致
```

Sprint 148 scope-down：parser 對 **空 `<w:divs/>` 不 set hasDivs**（視為
無 divs）。writer v1 對 hasDivs=true emit 空 `<w:divs/>`、re-parse 不認、
`true → undefined` drift。

### 修法（+30 行 + 1 行 stub child）：

- REL_TYPE_WEB_SETTINGS 常數
- parts 條件 emit `word/webSettings.xml`（hasWebSettings）
- writeContentTypes Override + writeDocumentRels Relationship
- writeWebSettings + hasWebSettings（4 toggle + hasDivs）
- **關鍵**：`<w:divs><w:div w:id="0"/></w:divs>` 含 stub child、讓 re-parse 正確 set hasDivs

設計考量：紀律 #18 scope-down——不深入 divs 結構內容、只 emit 最 minimal
stub child（OOXML §17.16.5 規定 `<w:div>` 子元素）讓 parser 認得 hasDivs。

---

## 三 corpus 數據

### FontTable（Sprint 246+247+248）

```
[sprint246] total=42 font match=42/42 (100.0%) totalFonts=554
[sprint247] total=290 parse=288/290 pipeline=288/288 font=288/288 (100.0%) totalFonts=1329
[sprint248] total=18 font match=18/18 (100.0%) totalFonts=0
```

合計 **1883 fonts byte-identical**。

### WebSettings（Sprint 249+250+251）

```
[sprint249] total=42 webSettings match=42/42 (100.0%) totalKeys=64
[sprint250] total=290 parse=288/290 pipeline=288/288 webSettings=288/288 (100.0%) totalKeys=422
[sprint251] total=18 webSettings match=18/18 (100.0%) totalKeys=0
```

合計 **486 webSettings keys byte-identical**。

---

## 三 corpus 十四層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

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
| Comments | 100% / 0 trivially | 100% / 27 ⭐⭐ | 100% / 0 trivially |
| Footnotes+Endnotes | 100% / 168 | 100% / 345 ⭐⭐⭐ | 100% / 0 trivially |
| DocumentSettings | 100% / 292 | 100% / 1325 ⭐⭐⭐⭐ | 100% / 0 trivially |
| **FontTable** | **100% / 554** | **100% / 1329 ⭐⭐⭐⭐⭐** | **100% / 0 trivially** |
| **WebSettings** | **100% / 64** | **100% / 422 ⭐⭐⭐⭐⭐⭐** | **100% / 0 trivially** |

合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles + 1229 numberings + 27 comments +
513 footnotes/endnotes + 1617 settings keys + 1883 fonts + 486 web settings
keys** byte-identical。

**LibreOffice edge corpus 14 層中 12 層 ≥ 95% commercial-grade + 六
100%（NumberingMap + Comments + Footnotes + Settings + FontTable +
WebSettings）**：前 5 層 100% + TableProps 97.6% + SectionProps 95.1% +
StyleMap 96.9% + NumberingMap 100% + Comments 100% + Footnotes 100% +
Settings 100% + **FontTable 100% ⭐⭐⭐⭐⭐ + WebSettings 100% ⭐⭐⭐⭐⭐⭐**、僅
HeaderFooterContent 90.6% 為 edge tolerance。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **2023 passed + 1 skipped**（+6 sprint246-251、+75 行 writer 不破壞其他 2017 既有測試） |
| L2 VR v14 | ✅ 第 68 連 maintained | writer 觸 export path / VR 比 import path、互斥 |
| L3 perf | ✅ baseline 維持 | 兩 part 非空才 emit、含 fontTable 之 docx 增 ~2-4KB / file（多 fonts 時、最大 ~5-8KB）；webSettings ~0.2-0.5KB / file |

---

## 紀律

- **#1.b / Strategy C**：本批為 exception——writer 真實修法第八+九次
- **#2 magic number**：6 個具名常數
- **#14.b clean scope**：commit = 6 audit + writer fix + audit doc + INDEX/snapshot
- **#18 scope-down**：兩 part 非空才 emit；webSettings hasDivs 用 stub
  child 序列化、不深入 divs 結構
- **#21**：兩 writer 不觸 VR / round-trip / existing 測試

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                                       +75 行
A  tests/integration/sprint246_chienyi_fonttable_preservation_audit.test.ts          +120 行
A  tests/integration/sprint247_libreoffice_fonttable_preservation_audit.test.ts      +135 行
A  tests/integration/sprint248_phase5_fonttable_preservation_audit.test.ts           +120 行
A  tests/integration/sprint249_chienyi_websettings_preservation_audit.test.ts        +110 行
A  tests/integration/sprint250_libreoffice_websettings_preservation_audit.test.ts    +130 行
A  tests/integration/sprint251_phase5_websettings_preservation_audit.test.ts         +110 行
A  docs/sprint246_to_251_fonttable_websettings_audit_plus_writer_fixes.md            本 audit
M  docs/INDEX.md                                                                     +Sprint 246-251 entries
M  docs/progress_snapshot.md                                                         §1 + §7 + 十四層矩陣完備
```

**淨 production code 變動 = +75 行**（writer fontTable 部件 + webSettings
部件 + 各自 rels + ContentType + writeFontTable / writeFontEntry / hasWebSettings /
writeWebSettings）、vitest 2017 → **2023**（+6 audit）、**三 corpus 十四層
byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐（合計 347 fixture /
11645 runs + 5335 paragraphs + 127 tables + 408 sections + 192 HF slots +
9172 styles + 1229 numberings + 27 comments + 513 footnotes/endnotes +
1617 settings + **1883 fonts + 486 web settings keys** byte-identical）、
**第五、六次 LibreOffice 邊緣 corpus 達 100% + 第八、九次 writer 真實修法**、
ChienYi v1 release docx 匯入子系統最終 sign-off **GO（十四層升級確認
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。
