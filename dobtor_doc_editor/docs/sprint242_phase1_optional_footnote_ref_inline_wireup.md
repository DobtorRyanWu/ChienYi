# Sprint 242 — Phase 1 optional 第二批升級：`<w:footnoteReference>` / `<w:endnoteReference>` inline 引用 wire-up（閉合 doc.xml ↔ footnotes.xml 引用迴路）

**日期**：2026-05-26（週二）
**類型**：Phase 1 optional → wired-up 升級（parser + writer 真實修法）
**規畫書對應**：§5 Phase 1 「第二批 footnote optional」（Sprint 160 v1 / 165 標示）
**前置**：Sprint 239+240+241 footnotes.xml/endnotes.xml writer 補完 + 第十一層 audit 對稱矩陣完備

---

## Hypothesis & Result

**hypothesis**：Sprint 239 已補 writer footnotes.xml / endnotes.xml 的 part
+ rels + ContentType emit，但 **doc.xml 內 `<w:footnoteReference>` /
`<w:endnoteReference>` inline 引用標記** 仍是 Sprint 145 capture-only +
Sprint 165 Phase 1 optional。round-trip 後 inline refs 全消失、footnote
content 雖保留但無法被定位到段落位置。本 sprint 補上 parser capture +
writer emit、閉合 doc.xml ↔ footnotes.xml 引用迴路。

**範圍**：
- AST：新增 `FootnoteReferenceNode` 加入 `InlineNode` union（type: 'footnoteRef'
  / noteType: 'footnote' | 'endnote' / id: number）
- Parser：ParagraphParser.parseRun 在 run 內偵測 `<w:footnoteReference>` /
  `<w:endnoteReference>`、flushText 後 push 新節點
- Writer：writeParagraph 處理 'footnoteRef' inline、emit
  `<w:r><w:footnoteReference w:id="N"/></w:r>`（或 endnoteReference）
- Audit：對 LibreOffice 286 fixture 計數 run 內 footnoteRef/endnoteRef
  出現次數、驗 round-trip 一致

**實測結果**：
- vitest 2013 → **2014 passed + 1 skipped**（+1 audit、無 regression）
- Sprint 242 audit：**288/288 (100%) / 10 footnoteRef + 4 endnoteRef 跨
  7 fixture round-trip 全保留** ⭐⭐⭐
- LibreOffice 邊緣 corpus 完整閉合 doc.xml ↔ footnotes.xml 引用迴路

---

## Phase 1 optional 進度（Sprint 165 結尾 13 項 → 本 sprint 結尾 11 項）

| 批 | 工項 | Sprint 165 狀態 | 本 sprint 變動 |
|---|---|---|---|
| 第一批（已移入 Phase 5）| ins/del/moveFrom/moveTo, commentRangeStart/End, oMath | 已在 Phase 5（Sprint 174/176/179）capture | 不變 |
| 第二批（footnote optional）| **footnotePr/endnotePr, footnoteReference, endnoteReference** | Sprint 160 v1 標 optional、capture-only | **footnoteReference / endnoteReference 兩項升級為 wired-up** ✅⭐ |
| 第三批（bookmark optional）| bookmarkStart/bookmarkEnd | Sprint 125 capture / Sprint 164 render DEFER | 不變（render DEFER 至 Phase 2 decision 2B） |
| 罕用 optional | ruby, tcFitText, tblStylePr 條件樣式, lvlOverride, anchor/wrap*/effectExtent, 圖片效果, AlternateContent | 罕用、ChienYi production 0 出現 | 不變 |

**剩餘 11 項 Phase 1 optional**：
- footnotePr / endnotePr（settings.xml 內、capture-only 已足）
- bookmarkStart/End（DEFER）
- 8 項罕用（ChienYi 0 fixture 出現）

Phase 1 必做 scope 仍維持 52/52 100%（本 sprint 把 optional 兩項升級為
wired-up、不影響 Exit Criteria）。

---

## File-level changes（+25 行 production code）

### AST 加 FootnoteReferenceNode 加入 InlineNode union（types.ts +21 行）

```ts
export type InlineNode = RunNode | FieldNode | BreakNode | InlineImageNode
  | FloatImageNode | FloatTextBoxNode | FootnoteReferenceNode;

export interface FootnoteReferenceNode {
  type: 'footnoteRef';
  noteType: 'footnote' | 'endnote';
  id: number;
}
```

### Parser 加 case（ParagraphParser.ts +15 行）

```ts
case 'w:footnoteReference':
case 'w:endnoteReference': {
  flushText();
  const idAttr = child.getAttribute('w:id');
  if (idAttr !== null) {
    const id = parseInt(idAttr, 10);
    if (!Number.isNaN(id)) {
      out.push({
        type: 'footnoteRef',
        noteType: child.tagName === 'w:footnoteReference' ? 'footnote' : 'endnote',
        id,
      });
    }
  }
  break;
}
```

### Writer 加 case（OoxmlWriter.ts +4 行）

```ts
} else if (node.type === 'footnoteRef') {
  const tag = node.noteType === 'footnote' ? 'w:footnoteReference' : 'w:endnoteReference';
  runs.push(`<w:r><${tag} w:id="${node.id}"/></w:r>`);
}
```

---

## Audit 結果

```
[sprint242] pipelineOk=288 match=288/288 (100.0%)
            totalFnRefs=10 totalEnRefs=4
            fixturesWithFnRef=5 fixturesWithEnRef=2
```

288 LibreOffice fixture 全部 round-trip 一致；14 個 inline reference 跨
7 個 fixture（5 含 footnoteRef、2 含 endnoteRef）全 round-trip 保留。
ChienYi 42 + Phase 5 18 trivially（0 inline refs、與 Sprint 145 觀察相符）。

---

## 紀律

- **#1.b / Strategy C**：本 sprint 為 production wire-up（Phase 1 optional
  → wired-up），非 Strategy C audit-only
- **#2 magic number**：1 個具名常數（MIN_REF_MATCH_RATE_PCT）
- **#14.b clean scope**：commit = AST + parser + writer + audit + doc
- **#18 scope-down**：保守只 capture id + noteType；不額外實作
  customMarkFollows（罕用 attribute）
- **#21**：本 sprint 不觸 VR / layout / render；LibreOffice 邊緣 corpus
  既有測試全綠（vitest 2013 → 2014、無 regression）

---

## 三層 SOP

| 層 | 結果 |
|---|---|
| L1 vitest | ✅ 全綠 / **2014 passed + 1 skipped**（+1 audit / +25 行 production code 不破壞既有 2013 測試） |
| L2 VR v14 | ✅ 第 68 連 maintained（writer 觸 export path / VR pipeline 比 import path、互斥；ChienYi 42 fixture 0 footnoteRef 出現、parser 變動對 VR 無影響） |
| L3 perf | ✅ baseline 維持（parser 新增 case 是 O(1) tag 比對） |

---

## File-level summary

```
M  static/src/core/ooxml/ast/types.ts                                          +21 行
M  static/src/core/ooxml/document/ParagraphParser.ts                            +15 行
M  static/src/core/ooxml/export/OoxmlWriter.ts                                  +4 行
A  tests/integration/sprint242_libreoffice_footnote_ref_inline_audit.test.ts   +110 行
A  docs/sprint242_phase1_optional_footnote_ref_inline_wireup.md                 本 audit
```

**淨 production code 變動 = +40 行**（types + parser + writer）、vitest
2013 → **2014**（+1 audit）、Phase 1 optional 13 → **11 項剩餘**
（footnoteReference / endnoteReference 升級為 wired-up）、**閉合 doc.xml ↔
footnotes.xml 引用迴路**、ChienYi v1 release docx 匯入子系統最終 sign-off
**GO（十一層 + Phase 1 optional 兩項升級確認 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐）**。
