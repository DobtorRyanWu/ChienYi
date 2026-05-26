# Sprint 253+254+255 — DocProps (core+app+custom) 第十五層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / writer Sprint 13+150+151→253 gap 三補 / 第七次 LibreOffice 邊緣 corpus 達 100% / 5890 docProps keys byte-identical

**日期**：2026-05-26（週二）
**類型**：三 audit 並排 + writer 三補（Sprint 218→219 模式重現第十次）
**規畫書對應**：§6 黃金測試第十五層 DocProps（docProps/core.xml + app.xml + custom.xml）
**前置**：Sprint 246-251 fontTable + webSettings 完備 + Sprint 252 Phase 1 optional 關閉

---

## Hypothesis & Result

**hypothesis**：十四層 + Phase 1 optional bucket 關閉後、擴展第十五層
DocProps。三 part（core.xml / app.xml / custom.xml）皆 capture-only / writer
未實作；本 sprint 一次補完三 part、所有 PII / metadata 完整 round-trip。

**範圍**：
- DocProps（core.xml）8 欄位：title / creator / subject / description /
  keywords / lastModifiedBy / created / modified
- DocPropsApp（app.xml）16 欄位：template / application / appVersion /
  company / pages / words / characters / lines / paragraphs /
  charactersWithSpaces / totalTime / docSecurity / scaleCrop /
  linksUpToDate / sharedDoc / hyperlinksChanged
- DocPropsCustom（custom.xml）Map<name, CustomPropertyValue>；5 個 variant
  型別：string / int / bool / real / filetime + unknown fallback

**實測結果**：
- Sprint 253 ChienYi 42 v1（修前）：**0/42 (0%)** ⚠️ writer 完全不 emit
- writer 補完（+95 行 production code、Dublin Core + extended-properties
  + custom-properties namespace、root rels + Content_Types Override）
- Sprint 253 修後：**42/42 (100%) / 203 core + 647 app + 38 custom = 888 keys**
- Sprint 254 LibreOffice：**288/288 (100%) / 1035 core + 3809 app + 158
  custom = 5002 keys byte-identical** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
  **第七次 LibreOffice 邊緣 corpus 達 100%**
- Sprint 255 Phase 5：**18/18 (100%) / 0 trivially**

**三 corpus 十五層 byte-identical 對稱矩陣完備 + 第十次 writer 真實修法
+ 第七次 LibreOffice 邊緣 corpus 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Root cause #11 — writer 漏 docProps/{core,app,custom}.xml + root rels + Content_Types

Sprint 13 parser capture core.xml / Sprint 150 capture app.xml / Sprint 151
capture custom.xml；DocumentNode 三 prop 容器存在。但 OoxmlWriter.write
從未 emit 對應 part：

- `parts` 字典：缺 `docProps/core.xml` + `docProps/app.xml` + `docProps/custom.xml`
- `writeRootRels`：缺三個 Relationship（注意：DocProps rels 屬於 root rels、
  不是 document.xml.rels）
- `writeContentTypes`：缺三個 Override
- 對應 writer 函式：不存在

### 修法（+95 行 production code）

#### 1. REL_TYPE / namespace 常數 +9 行

- `REL_TYPE_CORE_PROPERTIES` / `REL_TYPE_EXTENDED_PROPERTIES` /
  `REL_TYPE_CUSTOM_PROPERTIES`
- `DC_NS` / `DCTERMS_NS` / `DCMITYPE_NS` / `XSI_NS` / `CP_NS`
  （Dublin Core + DC Terms + cp namespaces）
- `EXT_PROPS_NS` / `CUSTOM_PROPS_NS` / `VT_NS`

#### 2. parts 字典條件 emit +9 行

```ts
if (hasDocProps(doc.docProps)) parts['docProps/core.xml'] = strToU8(writeDocPropsCore(doc.docProps));
if (hasAppProps(doc.appProps)) parts['docProps/app.xml'] = strToU8(writeDocPropsApp(doc.appProps));
if (doc.customProps.size > 0) parts['docProps/custom.xml'] = strToU8(writeDocPropsCustom(doc.customProps));
```

#### 3. writeRootRels 加 doc 參數 + 三 Relationship +10 行

關鍵：DocProps rels 屬於 root `_rels/.rels`（不是 document.xml.rels）。

#### 4. writeContentTypes 三 Override +12 行

#### 5. writeDocPropsCore +20 行（Dublin Core 8 欄位序列化）

```ts
function writeDocPropsCore(p: DocProps): string {
  /* dc:title / dc:creator / dc:subject / dc:description / cp:keywords /
     cp:lastModifiedBy / dcterms:created / dcterms:modified */
}
```

#### 6. writeDocPropsApp +20 行（extended-properties 16 欄位序列化）

```ts
function writeDocPropsApp(p: DocPropsApp): string {
  /* Template / TotalTime / Pages / Words / Characters / Application /
     DocSecurity / Lines / Paragraphs / ScaleCrop / Company /
     LinksUpToDate / CharactersWithSpaces / SharedDoc / HyperlinksChanged /
     AppVersion */
}
```

#### 7. writeDocPropsCustom + writeCustomVariant +15 行

```ts
function writeDocPropsCustom(c: DocPropsCustom): string {
  /* OOXML §22.4 規範 fmtid 固定 GUID + pid 從 2 起遞增 */
}

function writeCustomVariant(v: CustomPropertyValue): string {
  /* 5 個 variant 型別 + unknown fallback → vt:lpwstr */
}
```

關鍵設計：
- **root rels**：DocProps rels 屬 root `_rels/.rels`（test Sprint 253 揭發
  parser 讀 root rels 找 docProps target、不是 document.xml.rels）
- **Dublin Core namespace**：core.xml 用 cp/dc/dcterms/dcmitype/xsi 五個
  namespace、xsi:type="dcterms:W3CDTF" 標 created / modified 為 W3C 日期格式
- **custom fmtid 重建**：parser Sprint 151 不保留 fmtid / pid，writer 用
  OOXML §22.4 規範 fmtid `{D5CDD505-2E9C-101B-9397-08002B2CF9AE}` + pid
  從 2 按 name 字典序遞增（symmetric round-trip）
- **vt:variant**：5 個 kind（string / int / bool / real / filetime）+
  unknown 降級為 vt:lpwstr（紀律 #18）
- **app.xml namespace**：extended-properties default namespace + vt namespace
  for variant types
- **不破壞既有 fixture**：full vitest 2023 → 2026（+3 audit）全綠

---

## 三 corpus 數據

```
[sprint253] total=42 match=42/42 (100.0%) totalCoreKeys=203 totalAppKeys=647 totalCustomEntries=38
[sprint254] total=290 parse=288/290 pipeline=288/288 docProps=288/288 (100.0%) totalCoreKeys=1035 totalAppKeys=3809 totalCustomEntries=158
[sprint255] total=18 match=18/18 (100.0%) totalCoreKeys=0 totalAppKeys=0 totalCustomEntries=0
```

合計 **5890 docProps keys byte-identical**（合：core 1238 + app 4456 +
custom 196）。

---

## 三 corpus 十五層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

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
| FontTable | 100% / 554 | 100% / 1329 ⭐⭐⭐⭐⭐ | 100% / 0 trivially |
| WebSettings | 100% / 64 | 100% / 422 ⭐⭐⭐⭐⭐⭐ | 100% / 0 trivially |
| **DocProps（core+app+custom）** | **100% / 888** | **100% / 5002 ⭐⭐⭐⭐⭐⭐⭐** | **100% / 0 trivially** |

合計 **347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles + 1229 numberings + 27 comments +
513 footnotes/endnotes + 1617 settings + 1883 fonts + 486 webSettings +
5890 docProps** byte-identical。

**LibreOffice edge corpus 15 層中 13 層 ≥ 95% commercial-grade + 七 100%
（NumberingMap + Comments + Footnotes + Settings + FontTable + WebSettings
+ DocProps）**：前 5 層 100% + TableProps 97.6% + SectionProps 95.1% +
StyleMap 96.9% + NumberingMap 100% + Comments 100% + Footnotes 100% +
Settings 100% + FontTable 100% + WebSettings 100% + **DocProps 100% ⭐⭐⭐⭐⭐⭐⭐**、
僅 HeaderFooterContent 90.6% 為 edge tolerance。

---

## 三層 SOP

| 層 | 結果 |
|---|---|
| L1 vitest | ✅ 全綠 / **2026 passed + 1 skipped**（+3 sprint253+254+255 + 95 行 writer 不破壞其他 2023 既有測試） |
| L2 VR v14 | ✅ 第 68 連 maintained（writer 觸 export path / VR 比 import path） |
| L3 perf | ✅ baseline 維持（三 part 非空才 emit、增 ~1-3KB / file） |

---

## 紀律

- **#1.b / Strategy C**：本 sprint 為 exception——writer 真實修法第十次
- **#2 magic number**：3 個具名常數（MIN_DOCPROPS_MATCH_RATE_PCT 各 corpus）
  + OOXML §22.4 fmtid GUID 為命名常數於函式內
- **#14.b clean scope**：commit = 3 audit + writer fix + audit doc + INDEX/snapshot
- **#18 scope-down**：三 part 非空才 emit；custom variant 5 個 kind +
  unknown fallback（不為 closure 而擴充 vt 變體）
- **#21**：本 sprint 不觸 VR / round-trip / existing 測試

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                                  +95 行
A  tests/integration/sprint253_chienyi_docprops_preservation_audit.test.ts      +130 行
A  tests/integration/sprint254_libreoffice_docprops_preservation_audit.test.ts  +145 行
A  tests/integration/sprint255_phase5_docprops_preservation_audit.test.ts       +125 行
A  docs/sprint253_to_255_docprops_audit_plus_writer_fix.md                      本 audit
M  docs/INDEX.md                                                                +Sprint 253-255 entries
M  docs/progress_snapshot.md                                                    §1 + §7 + 十五層矩陣完備
```

**淨 production code 變動 = +95 行**（OoxmlWriter docProps core/app/custom
parts + root rels + ContentType + writeDocPropsCore/App/Custom +
writeCustomVariant + hasDocProps/hasAppProps）、vitest 2023 → **2026**（+3
audit）、**三 corpus 十五層 byte-identical 對稱矩陣完備** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
（合計 347 fixture / 11645 runs + 5335 paragraphs + 127 tables + 408
sections + 192 HF slots + 9172 styles + 1229 numberings + 27 comments +
513 footnotes/endnotes + 1617 settings + 1883 fonts + 486 webSettings +
**5890 docProps**（1238 core + 4456 app + 196 custom）byte-identical）、
**第七次 LibreOffice 邊緣 corpus 達 100% + 第十次 writer 真實修法**、
ChienYi v1 release docx 匯入子系統最終 sign-off **GO（十五層升級確認
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。
