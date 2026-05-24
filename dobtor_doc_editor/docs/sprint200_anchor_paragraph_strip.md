# Sprint 200 — Sprint 191 multi-section anchor paragraph round-trip 對稱（structure 93.1% → 100%）

**日期**：2026-05-24（週日）
**類型**：parser bug fix（Sprint 199 audit 揭出、同 sprint 串行修復）
**規畫書對應**：§6 黃金測試「import(export(doc)) ≅ doc」結構對稱性
**前置**：Sprint 199（揭出 structure 93.1% 含 20 個 drift case、section 46% 最差）

---

## Hypothesis

Sprint 199 export round-trip 廣域 audit 揭出 20 個結構 drift case，集中於：

- **section 46%**（7/13 drift）— 最嚴重
- headerfooter 78%（2/9 drift）
- table 85%、field 83%、sdt 91%、misc 95%

Drift pattern 共通：**sections 數一致、paragraphs 數每非最後 section +1**。

例：
```
field/IndexFieldFlagF.docx: sections 5→5, paragraphs 20→24  (+4 = 4 個非最後 section)
```

Hypothesis：Sprint 191 writer 為多 section 文件 emit 「anchor paragraph」
`<w:p><w:pPr><w:sectPr>...</w:sectPr></w:pPr></w:p>` 嵌 sectPr，但 parser
`walkBodyAsSections` 把它當實段收入 blocks、導致 round-trip 後段落數 +1。

---

## Root cause

`OoxmlWriter.writeDocument`（Sprint 191）對非最後 section emit：

```ts
if (i < n - 1) {
  bodyParts.push(`<w:p><w:pPr>${writeSectPr(sec, watermarkItem)}</w:pPr></w:p>`);
}
```

`DocumentParser.walkBodyAsSections`（Sprint 1）對所有 `<w:p>` 一律加進 blocks：

```ts
case 'w:p': {
  currentBlocks.push(this.paragraphParser.parse(child));
  const pPr = directChild(child, 'w:pPr');
  const innerSectPr = directChild(pPr, 'w:sectPr');
  if (innerSectPr) {
    sections.push({ sectPrEl: innerSectPr, blocks: currentBlocks });
    currentBlocks = [];
  }
}
```

→ writer-emitted anchor 被 parser 當成實段收入、round-trip 後段落數膨脹。

---

## 修法

### 1. `isWriterAnchorParagraph` helper（DocumentParser.ts、+33 行）

嚴格簽名（避免誤殺 LibreOffice / Word 自然 emit 的「最後段帶 sectPr」case）：

- paragraph 元素**無任何 run-like 子節點**
  （`w:r` / `w:ins` / `w:del` / `w:hyperlink` / `w:fldSimple` / `w:smartTag`）
- `w:pPr` 存在
- `w:pPr` 直接子元素**剛好一個、且為 `w:sectPr`**

真實 docx 若用空段落結尾 section、通常 pPr 還會有 `w:rPr` 帶字型大小等屬性、
不會被誤判。

### 2. `walkBodyAsSections` 改 4 行（DocumentParser.ts）

```ts
case 'w:p': {
  const pPr = directChild(child, 'w:pPr');
  const innerSectPr = directChild(pPr, 'w:sectPr');
  const isAnchor = innerSectPr !== undefined && isWriterAnchorParagraph(child, pPr);
  if (!isAnchor) {
    currentBlocks.push(this.paragraphParser.parse(child));
  }
  if (innerSectPr) {
    sections.push({ sectPrEl: innerSectPr, blocks: currentBlocks });
    currentBlocks = [];
  }
}
```

### 3. 測試（+3）

- `tests/unit/SectionParser.test.ts` Sprint 200 區塊（+3）：
  - writer anchor paragraph 不計入 blocks（驗主修法）
  - 含 run 的最後段帶 sectPr **不視為 anchor**（驗保留真實段不誤殺）
  - pPr 含 rPr 等非 sectPr 屬性的空段**不視為 anchor**（驗 LibreOffice / Word 風格）

---

## Result — Sprint 199 audit 第三輪（Sprint 200 fix 後）

| Stage | Sprint 199 後 | **Sprint 200 後** | Delta |
|---|---|---|---|
| Stage 1 parse OK | 288/290 (99.3%) | 288/290 (99.3%) | 不變 |
| Stage 2 export OK | 288/288 (100%) | 288/288 (100%) | 不變 |
| Stage 3 reparse OK | 288/288 (100%) | 288/288 (100%) | 不變 |
| **Stage 4 structure OK** | 268/288 (93.1%) | **288/288 (100%)** | **+6.9pp** |

### Per-category structure（fix 後）

| Category | Sprint 199 後 | **Sprint 200 後** |
|---|---|---|
| section | 46% | **100%** ⭐ |
| headerfooter | 78% | **100%** ⭐ |
| field | 83% | **100%** ⭐ |
| table | 85% | **100%** ⭐ |
| sdt | 91% | **100%** ⭐ |
| math | 91% | 91%（剩 1 個 parse stage fail）|
| misc | 95% | 99%（剩 1 個 parse stage fail）|
| 其餘 8 category | 100% | 100% |

**13/15 category 100% 結構保留**！剩 math/misc 各 1 個故意畸形 case parse stage fail（與本修法無關、Sprint 198 揭出）。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | 1920 → **1923 passed + 1 skipped**（+3：SectionParser unit）|
| L2 VR v14 | ✅ **byte-identical 第 58 連** | rendered 42/42、comparedPages 126、failedPages 0；parser-side 修法不影響 export bytes、不影響 render output |
| L3 廣域 round-trip | ✅ **288/288 (100%) 4 階段全綠** | 結構保留 93.1% → **100%** |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**
- frontend bundle + VR IIFE bundle 重建成功

---

## 紀律

- **#1.b / Strategy C**：parser fix 不改變 export bytes、不改變 render output、
  VR byte-identical 第 58 連
- **#2 magic number**：anchor 簽名以 enum-like 檢查（run-like tagName 集合 +
  pPr 子節點數量 1 + tagName 'w:sectPr'）
- **#14 DRY**：reuse 既有 `directChildren` / `directChild` helper、無新 dom 抽象
- **#14.b clean scope**：本 commit = parser helper + walkBodyAsSections 4-line edit +
  3 unit test + audit doc + INDEX/snapshot 更新
- **#18 scope-down**：
  - 嚴格簽名避免誤殺真實 docx 的空段（pPr 帶 rPr 等其他屬性 → 保留）
  - 不改 writer（writer 維持 Sprint 191 anchor 寫法、parser 端優雅吃下）
- **#21**：fix 不破壞既有 Sprint 191 multi-section round-trip 測試（10 個既有
  round-trip test 全綠）

---

## 為什麼選擇 parser-side 修法

考量過兩條路徑：

**Path A：writer 改 embed sectPr 進最後段（避免額外 anchor）**
- 缺點：需修 writer + 改變 export bytes → 全 round-trip 測試 fixture VR 風險
- 缺點：若最後 block 不是 paragraph（如表格結尾），仍需 anchor fallback
- 優點：bytes 更乾淨

**Path B：parser 識別 writer-emitted anchor 並 skip（採用）** ✅
- 優點：**不改變 export bytes、零 VR 風險、第 58 連**
- 優點：parser 端優雅吃下 writer's anchor pattern、不影響真實 docx 解析
- 優點：1 個 helper + 4 行 edit、易讀易維護
- 缺點：理論上若有原始 docx 嚴格使用 `<w:p><w:pPr><w:sectPr/></w:pPr></w:p>`
  簽名會被誤判 stripped；但 LibreOffice / Word 自然 emit 不會出現該嚴格
  簽名（會帶 rPr 或其他 pPr 子元素）

LibreOffice 290 fixture 廣域 audit 驗證：**13/15 category 結構 100% 保留**、
0 個 LibreOffice fixture 出現「真實 anchor 簽名被誤判」情境 → Path B 安全。

---

## Phase 6 / 7 完成度更新

- **Phase 6**：100% unchanged；export 廣域穩定性現驗證為 **完整 round-trip
  4 階段全綠**（parse 99.3% / export 100% / reparse 100% / **structure 100%**）
- **Phase 7**：~89%（Sprint 199）→ **~90%**（結構對稱性完整驗證、邊緣 audit
  第三輪達 4 階段全綠）

---

## 後續

- 剩 ROI 項：合成 50p fixture + benchmark（Phase 7 中 ROI、2 sprint）/
  WPS audit（低 ROI、需另尋 fixture）/ Phase 8 多選對齊輔助線（低 ROI）/
  OffscreenCanvas worker（不建議）
- Sprint 199 + 200 完成 Phase 7 邊緣 + export 穩定性兩條 audit pipeline、
  ChienYi 監造 docx workflow 端到端對稱性已量化保證

---

## File-level summary

```
M  static/src/core/ooxml/document/DocumentParser.ts        +isWriterAnchorParagraph helper + walkBodyAsSections 改 4 行（+38 行 net）
M  tests/unit/SectionParser.test.ts                        +3 test
A  docs/sprint200_anchor_paragraph_strip.md                本 audit
M  docs/INDEX.md                                           +Sprint 200 entry
M  docs/progress_snapshot.md                               Phase 7 89% → ~90%、Sprint 200 audit 區塊
```

**淨 production code 變動 = +38 行**、**288/290 fixture 4 階段廣域 round-trip
100% 結構保留**、VR byte-identical 第 58 連、Phase 7 完成度 ~89%→~90%。
