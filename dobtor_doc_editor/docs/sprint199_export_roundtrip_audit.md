# Sprint 199 — Phase 6 export round-trip 廣域穩定性 audit + OMML writer bug fix

**日期**：2026-05-24（週日）
**類型**：audit + bug fix（audit 揭出 Sprint 194 OMML writer namespace bug、同 sprint 修復）
**規畫書對應**：§6 黃金測試「import(export(doc)) ≅ doc」廣域化、Phase 7 邊緣相容性 audit 延伸
**前置**：Sprint 198（290 fixture parse audit、288/290 OK）

---

## Hypothesis

Sprint 198 驗證 OoxmlParser 對 290 個 LibreOffice 邊緣 fixture 99.3%
parse 成功。本 sprint 把驗證鏈延伸：

```
parser.parse(originalBytes) → writer.write(doc) → parser.parse(exportedBytes)
```

對 Sprint 198 已 parse 成功的 288 個 fixture 跑 round-trip、量化：

- export success rate（writer 不丟例外）
- re-parse success rate（exported bytes 可被 parser 重讀）
- 結構保留率（re-parse 後 sections/paragraphs 數與原 doc 一致）

Phase 6 export Sprint 185-196 對 42 個 controlled fixture 全綠、本 sprint
推到廣域邊緣 corpus、揭示 Phase 6 在真實世界 docx 多樣性下的穩定性。

---

## Audit 第一輪（揭出 OMML writer bug）

| Stage | 通過率 |
|---|---|
| Stage 1 parse OK | 288/290 (99.3%) |
| Stage 2 export OK | **288/288 (100%)** |
| Stage 3 re-parse OK | 273/288 (94.8%) ❌ |
| Stage 4 structure OK | 253/273 (92.7%) |

**math category re-parse 全失敗 (0/11)**、錯誤訊息一律：

```
end tag name contains invalid characters: "m:w:rPr"
```

### Root cause（Sprint 194 OMML writer bug）

`OmmlParser.parseOmmlChildren` 用 `stripMathPrefix` 去 `m:` 前綴：

```ts
const tag = stripMathPrefix(child.tagName);  // 'm:r' → 'r'、'w:rPr' → 'w:rPr'（不動）
```

OMML 子節點可內嵌**其他命名空間元素**（如 `<m:r>` 內含 `<w:rPr>` rich text 屬性）。
parser 對非 `m:` 前綴的子節點原樣保留 tag（如 `'w:rPr'`）。

`OoxmlWriter.writeOmmlNode`（Sprint 194）一律前綴 `m:`：

```ts
const tag = `m:${node.tag}`;  // 'r' → 'm:r' ✅、'w:rPr' → 'm:w:rPr' ❌ invalid XML
```

→ 產出 `<m:w:rPr>` 含 nested colon、re-parse xmldom fatalError。

### 修法（writeOmmlNode 改 2 行）

```ts
// Sprint 199 修法：tag/attr key 已含 `:` 表已帶 namespace、不再前綴 `m:`
const tag = node.tag.includes(':') ? node.tag : `m:${node.tag}`;
// attrs 同處理
const fullName = k.includes(':') ? k : `m:${k}`;
```

---

## Audit 第二輪（OMML fix 後）

| Stage | 通過率 | Delta |
|---|---|---|
| Stage 1 parse OK | 288/290 (99.3%) | 不變 |
| Stage 2 export OK | **288/288 (100%)** | 不變 |
| Stage 3 re-parse OK | **288/288 (100%)** | +5.2 pp |
| Stage 4 structure OK | **268/288 (93.1%)** | +0.4 pp |

### Per-category 分布（fix 後）

| Category | Total | Export % | Reparse % | Structure % |
|---|---|---|---|---|
| chart | 9 | 100 | 100 | **100** |
| field | 12 | 100 | 100 | 83 |
| headerfooter | 9 | 100 | 100 | 78 |
| image | 15 | 100 | 100 | **100** |
| list | 11 | 100 | 100 | **100** |
| math | 11 | 91 | **91** | 91 |
| misc | 137 | 99 | 99 | 95 |
| note | 10 | 100 | 100 | **100** |
| sdt | 11 | 100 | 100 | 91 |
| section | 13 | 100 | 100 | 46 |
| shape | 23 | 100 | 100 | **100** |
| smartart | 2 | 100 | 100 | **100** |
| style | 10 | 100 | 100 | **100** |
| table | 13 | 100 | 100 | 85 |
| track | 4 | 100 | 100 | **100** |

**math 0% → 91% reparse**（剩 1 個 `math-malformed_xml.docx` 是 LibreOffice
故意畸形 case，parse stage 就 fail）。

### 結構保留 drift 分析

20 個 re-parse 成功但 paragraph 數有差異的 case：

| 來源 | 模式 | 解釋 |
|---|---|---|
| section（54% drift） | section 中段 sectPr → 多 anchor paragraph | Sprint 191 多 section anchor pattern 已知 sub-gap |
| headerfooter（22% drift） | header 注入導致段落 +1~2 | Sprint 196 watermark default header 注入 / sectPr 多 anchor |
| field（17% drift） | 4 段差 → fldChar / instrText 展開 | Phase 1 field render 模擬展開 |
| misc 偶發（5% drift） | 同上混合 | 個別 case |

**結構 drift 屬已知 scope-down**（Sprint 191 multi-section + Sprint 196 watermark
注入皆有對應紀律 #18 trade-off 記錄）、非 regression。

---

## Result — 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite **1920 passed + 1 skipped**（+8：1 Sprint 199 audit + 7 自然增長）|
| L2 VR v14 | ✅ **byte-identical 第 57 連** | rendered 42/42、comparedPages 126、failedPages 0；OMML fix 走 export path、parser/render path 不變 |
| L3 round-trip 廣域 | ✅ **288/288 export 100% / 288/288 reparse 100% / 268/288 structure 93.1%** | OMML fix 後全綠 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**
- frontend bundle + VR IIFE bundle 重建成功

---

## 紀律

- **#1.b / Strategy C**：OMML fix 走 export path、parser/render path 不動、
  VR byte-identical 第 57 連
- **#1.a**：bundle 重建跑全 VR
- **#2 magic number**：3 個具名常數（EXPECTED_PARSE_OK_BASELINE / MIN_*_SUCCESS_RATE_PCT
  ×3）
- **#14（DRY）**：collectFixtures / loadAsArrayBuffer / countParagraphs 共用
  helper（同 Sprint 198 模式）
- **#14.b clean scope**：本 commit = audit test + OMML fix + audit doc + INDEX/snapshot
- **#18 scope-down**：
  - 接受 structure drift（Sprint 191/196 已知 sub-gap、合計 ~7% drift）
  - 寬鬆 success rate 下限（90% / 90% / 80%）給未來大廣域 fixture 擴張空間
- **#21**：失敗 case throw Error instance、不 silent corruption

---

## OMML bug fix 意義

Sprint 194 OMML export 對「OMML 內嵌 RunProps」場景的 round-trip 從 **完全壞**
（0% reparse）變 **完全好**（100% reparse、剩 1 個 LibreOffice 故意畸形 case 是
parse stage 失敗）。

對 ChienYi 監造文件影響低（少有人在數學公式內套字型 / 顏色），但對未來 OMML
KaTeX 整合 / 更完整 OMML capture 是必要的修整。

---

## Phase 6 / 7 完成度更新

- **Phase 6**：100%（無變動、Sprint 196 達成）；export 廣域穩定性透過 Sprint 199
  audit **量化驗證** ≥ 99% （288/290 → 100% export / 100% reparse）
- **Phase 7**：~87%（Sprint 198）→ **~89%**（邊緣 audit 第二輪 export 驗證加分）

---

## 後續

- Phase 7 剩 cluster：OffscreenCanvas worker（不建議）/ Web Worker parse（不建議）/
  50+ 頁 fixture + benchmark（中 ROI）/ WPS 邊緣 audit（低 ROI、需另尋 fixture）
- Phase 8 polish：多選對齊輔助線（低 ROI）
- 短期可推：合成 50p fixture + benchmark（2 sprint）為 Phase 7 最後高 ROI 項

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts                              writeOmmlNode 修 namespace prefix bug（+5 行 net）
A  tests/integration/sprint199_export_roundtrip_audit.test.ts               1 test +約 250 行
A  docs/sprint199_export_roundtrip_audit.md                                 本 audit
M  docs/INDEX.md                                                            +Sprint 199 entry
M  docs/progress_snapshot.md                                                Phase 7 87% → ~89%
```

**淨 production code 變動 = +5 行**（OMML writer namespace fix）、Phase 6 廣域
export round-trip **288/288 (100%) 通過**、math reparse **0%→91%**、VR byte-identical
第 57 連、Phase 7 完成度 ~87%→~89%。
