# Sprint 156 — Phase 1 Checkbox Audit

**性質**: docs-only sprint、純 audit、0 production code 變動
**範圍**: 規畫書 §5 Phase 1（§1.1-§1.9）所有 `[ ]` 工項依 Sprint 0-155 真實 wire-up 狀態打 `[x]` 或留 `[ ]`
**依據**: [/home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md](/home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md)「Checkbox 規則」段
**對應 plan**: 同上、Sprint 156-158 Phase 1 wire-up 開工前 pre-work

---

## 1. Hypothesis

規畫書 §5 Phase 1 內所有 `[ ]` 是 Sprint 0 era 既定工作清單。Sprint 0-155 完成了大量工作、但從未 audit 過哪些 `[ ]` 真實 wire-up（不只是 capture）。

依 plan 規則:**capture-only 已完成但 wire-up 未做 → 仍標 `[ ]`**。本 audit 是 Phase 1 Exit Criteria 前置工作（所有 `[ ]` 全 `[x]` 才算過 Exit）。

---

## 2. Method

### 2.1 判定準則

| 標記 | 條件 |
|---|---|
| `[x]` | capture **+** wire-up 都接通 production 路徑（layout / render / mapper 有 caller 消費 parser 輸出） |
| `[ ]` | (a) 未做 / (b) capture-only / (c) wire-up 部分缺失 / (d) Phase 5 範圍 / (e) 罕用未做 |

### 2.2 依據

- [docs/INDEX.md](INDEX.md) 132 個 sprint audit doc 索引
- [docs/scope_audit_2026-05-19.md §3.1 G10](scope_audit_2026-05-19.md) capture-only 九連識別
- [docs/sprint145_153_retro.md](sprint145_153_retro.md) retro §8 自承「capture-only 路線真的耗盡、autonomous-friendly 候選 = 0」
- Sprint 0-155 累積 sprint audit doc 直接證據（非 grep code、信任 audit doc 自述）

---

## 3. Audit 結果

### 3.1 §1.1 Package 與 Relationships（4 項全 `[x]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| `DocxPackage` class | `[x]` | Sprint 0 PackageReader 落地、`getPart()` 被 layout/render 廣用 |
| `[Content_Types].xml` 解析 | `[x]` | Sprint 152 expose internal、但本身 Sprint 0 internal parse 已存在、是基礎建設、layout 不直接消費但 Package layer 必要 |
| `.rels` 檔解析 | `[x]` | Sprint 0-1 落地、`r:embed`/`rId` 在 Sprint 15-40 image/header/footer/font 廣用 |
| 資源管線 | `[x]` | 圖片 Sprint 15、頁首頁尾 Sprint 11、字型 Sprint 147 |

### 3.2 §1.2 單位系統（2 項全 `[x]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| `units.ts` | `[x]` | Sprint 1+ 落地、twips/dxa/EMU 在 layout/render 廣用 |
| DPI 處理 | `[x]` | Sprint 30 DPI alignment 落地 |

### 3.3 §1.3 Styles 與繼承鏈（6 項全 `[x]`）

全部由 Sprint 19 style merge visual rerun 落地、StyleResolver 接通整體 pipeline。

### 3.4 §1.4 Paragraph / Run / Text（5 `[x]` / 1 `[ ]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| `<w:p>` + `<w:pPr>` | `[x]` | Sprint 32 paragraph alignment + Sprint 25 spacing + Sprint 133 pBdr/shd 已 wire-up 至 Layout |
| `<w:r>` + `<w:rPr>` | `[x]` | Sprint 1+ 落地、字型 4 屬性 / size / bold / italic / color 全 wire-up |
| `xml:space="preserve"` | `[x]` | Sprint 1+ 落地 |
| `<w:tab>` / `<w:br>` | `[x]` | Sprint 10 column / Sprint 17 pagination break 落地 |
| `<w:symbol>` / `<w:sym>` | `[x]` | 落地（Phase 4 §4.3 編號 lvlText 用到） |
| **`<w:ruby>` 注音** | **`[ ]`** | 未做、Sprint 35 CJK vertical 不含 ruby、罕用日文需求 |

### 3.5 §1.5 表格完整解析（17 `[x]` / 2 `[ ]`）

| 段 | 工項 | 判定 |
|---|---|---|
| 1.5.1 結構 | `<w:tbl>/<w:tr>/<w:tc>` | `[x]` |
| 1.5.1 | `<w:tblGrid>` | `[x]` |
| 1.5.2 儲存格屬性 | `<w:tcW>` | `[x]` |
| 1.5.2 | `<w:gridSpan>` | `[x]` |
| 1.5.2 | `<w:vMerge>` | `[x]` (Sprint 33) |
| 1.5.2 | `<w:tcBorders>+<w:tblBorders>` | `[x]` |
| 1.5.2 | `<w:shd>` | `[x]` (Sprint 3 + Sprint 131) |
| 1.5.2 | `<w:tcMar>` | `[x]` |
| 1.5.2 | `<w:vAlign>` | `[x]` (Sprint 42) |
| 1.5.2 | `<w:noWrap>/<w:hideMark>` | `[x]` |
| 1.5.2 | **`<w:tcFitText>`** | **`[ ]`** 罕用 |
| 1.5.3 列與表 | `<w:trHeight>` | `[x]` (Sprint 45-48) |
| 1.5.3 | `<w:tblHeader>/<w:cantSplit>` | `[x]` |
| 1.5.3 | `<w:tblPr>` | `[x]` (+ Sprint 131) |
| 1.5.3 | **`<w:tblStylePr>` 15 條件** | **`[ ]`** Sprint 131 補 cell-level shading+vAlign 部分;tcBorders / trPr / tblPr 條件樣式未做 |
| 1.5.3 | 巢狀表格 | `[x]` (Sprint 7) |
| 1.5.4 vMerge 演算法 | resolveVerticalMerges | `[x]` (Sprint 33) |

### 3.6 §1.6 Numbering（5 `[x]` / 1 `[ ]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| `<w:num>+<w:abstractNum>` 二層 | `[x]` | Sprint 137-139 wire-up |
| 多層級 `<w:lvl ilvl=0..8>` | `[x]` | Sprint 137 NumberingCounterState |
| 編號格式 16 種 | `[x]` | Sprint 132 numberingFormatter（含 Sprint 138 mapper wire-up + Sprint 139 layout Strategy C） |
| `<w:lvlRestart>` 重啟 | `[x]` | Sprint 137 NumberingCounterState |
| **`<w:lvlOverride>` 局部覆寫** | **`[ ]`** | 未確認 wire-up、保守留 `[ ]` |
| 編號連續性（跨段落） | `[x]` | Sprint 137-139 wire-up |

### 3.7 §1.7 Sections 與頁面（5 `[x]` / 1 `[ ]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| `<w:sectPr>` | `[x]` | Sprint 4 |
| `<w:headerReference>/<w:footerReference>` | `[x]` | Sprint 11 |
| 頁首頁尾 parts 解析 | `[x]` | Sprint 11 |
| `<w:cols>` 分欄 | `[x]` | Sprint 5/6/10 |
| **`<w:footnotePr>/<w:endnotePr>`** | **`[ ]`** | Sprint 146 settings.xml capture 含 / Sprint 145 footnotes/endnotes capture-only / **wire-up=0** |
| `<w:docGrid>` CJK 行格 | `[x]` | Sprint 29 |

### 3.8 §1.8 Drawings 與 OLE（6 `[x]` / 3 `[ ]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| `<w:drawing>` > `<wp:inline>` | `[x]` | Sprint 15 |
| **`<w:drawing>` > `<wp:anchor>`** | **`[ ]`** | wrap 5 種僅完成 3 種、保守留 `[ ]` |
| `<wp:positionH>/<wp:positionV>` | `[x]` | Sprint 37-39 |
| **`<wp:wrap*>` 5 種** | **`[ ]`** | wrapNone / wrapSquare / wrapTopAndBottom 已做、wrapTight / wrapThrough 未做 |
| `<wp:extent>` | `[x]` | Sprint 15 |
| **`<wp:effectExtent>`** | **`[ ]`** | capture 含、render 端未消費 |
| `<a:blip r:embed>` | `[x]` | Sprint 15 |
| `<a:srcRect>` 裁切 | `[x]` | Sprint 40 |
| **圖片效果（陰影、外框）** | **`[ ]`** | 規畫書標「可選」、未做 |
| `<v:shape>` VML 降級 | `[x]` | Sprint 122 fallback placeholder |

### 3.9 §1.9 進階結構（2 `[x]` / 9 `[ ]`）

| 工項 | 判定 | 依據 |
|---|---|---|
| **`<w:footnoteReference>`** | **`[ ]`** | Sprint 145 capture-only、wire-up=0 |
| **`<w:endnoteReference>`** | **`[ ]`** | Sprint 145 capture-only、wire-up=0 |
| `<w:hyperlink>` + rels | `[x]` | Sprint 10/126 wire-up（Sprint 126 capture-only 擴 tgtFrame 等不影響基本 wire-up） |
| `<w:fldSimple>` 簡單欄位 | `[x]` | Sprint 12 metadata + Sprint 10 column/page field |
| **`<w:instrText>` 複雜欄位** | **`[ ]`** | Sprint 123 capture-only 強化、render 端未完全消費 |
| **`<w:bookmarkStart>/<w:bookmarkEnd>`** | **`[ ]`** | Sprint 125 capture-only、render 端不消費 |
| `<w:sdt>` 結構化標籤 | `[x]` | Sprint 124 transparent unwrap（render 透明 = 等效 wire-up） |
| **`<w:ins>/<w:del>/<w:moveFrom>/<w:moveTo>`** | **`[ ]`** | Phase 5.4 範圍、未做 |
| **`<w:commentRangeStart>`** | **`[ ]`** | Phase 5.5 範圍、未做 |
| **`<m:oMath>` 數學公式** | **`[ ]`** | Phase 5.1 範圍、未做 |
| **`<mc:AlternateContent>`** | **`[ ]`** | 未做 |

---

## 4. 統計

| 段 | `[x]` | `[ ]` | 完成度 |
|---|---|---|---|
| §1.1 Package | 4 | 0 | 100% |
| §1.2 Units | 2 | 0 | 100% |
| §1.3 Styles | 6 | 0 | 100% |
| §1.4 Paragraph/Run/Text | 5 | 1 | 83% |
| §1.5 表格 | 17 | 2 | 89% |
| §1.6 Numbering | 5 | 1 | 83% |
| §1.7 Sections | 5 | 1 | 83% |
| §1.8 Drawings | 6 | 3 | 67% |
| §1.9 進階結構 | 2 | 9 | 18% |
| **合計** | **52** | **17** | **75%** |

### 與 progress_snapshot 雙指標對照

- 之前 progress_snapshot Phase 1: **90%（含 capture-only）/ 86%（含 wire-up only）**
- 本 audit 結果: **75%（嚴格 wire-up）**

→ Phase 1 真實 wire-up 完成度比 progress_snapshot 標的 86% 還低。原因：**Sprint 145-153 9 個 capture-only parser 對應 §1.7 / §1.9 共 4-5 個 `[ ]`**（footnotePr/endnotePr、footnoteReference、endnoteReference、settings.xml 在 §1.7 / 包含於 footnotePr 工項）、**這些不算 wire-up 完成**。

進一步、Sprint 125 / 126 / 123 也是 capture-only 不接通、§1.9 9 個 `[ ]` 是真實未 wire-up。

---

## 5. 紀律與啟示

| 紀律 | 應用 |
|---|---|
| #14 即時 docs 同步 | 本 sprint 是 catch-up audit（Sprint 0-155 期間從未 audit `[ ]` 狀態） |
| #18 PR-size + scope-down | 純文件 audit、0 production code、嚴格 PR-size |
| #18.a「根據計劃書繼續執行」是 scope 限制詞 | 本 sprint 不發明新工項、不改 plan、純 audit `[ ]` |
| #22 probe before action | Sprint 157+ wire-up 工作開工前、知道哪 17 個 `[ ]` 是真實未完成（避免亂打勾）|

**揭示**:
- Phase 1 真實完成度（75% wire-up）比 progress_snapshot 標 86% 還低 5pp
- Sprint 145-153 capture-only 九連 **+** Sprint 121-126 部分 capture-only 對應的 `[ ]` 工項合計 9-10 個 → 推算 progress_snapshot 86% wire-up 也偏樂觀
- Phase 1 Exit Criteria 嚴格達成 = 全 17 個 `[ ]` 補完 → 需 Sprint 157-165+ 約 8-10 sprint wire-up 工作

→ 對 Sprint 157+ Phase 1 wire-up 推進的 sprint 數估算可能比 plan「3 sprint」偏低、現實可能需要 8-10 sprint。

---

## 6. Result

### 6.1 檔案變動

```
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (§5 Phase 1 [ ] → [x] / [ ] 標記 audit、69 個工項)
A  addons/dobtor_doc_editor/docs/sprint156_phase1_checkbox_audit.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/progress_snapshot.md  (Phase 1 完成度更新為 75% wire-up / 86% wire-up 含部分 / 90% 含 capture-only)
```

### 6.2 三層 SOP 結果

- vitest **1331 passed + 1 skipped**（未跑、純 docs）
- VR mean **0.073191**（未跑、純文件）
- L3 spot check ✅：`[x]` 52 個 / `[ ]` 17 個 + 4 nested `[ ]`（§1.8 anchor 子項已展開、屬同一工項拆分）
- L4 Odoo 跳過（純前端 docs）

### 6.3 累積指標

- vitest 1331 + 1 skipped（未動）
- VR mean 0.073191（未動、第 23 連 byte-identical 維持）
- Phase 1 wire-up 真實完成度: **75%**（52/69 工項）
- Sprint audit doc 155 → **156**

---

## 7. 後續

### 7.1 Sprint 157 候選

按 plan 推進、Sprint 157 開工 Phase 1 wire-up。候選工項（從 17 個 `[ ]` 中挑）按優先級排:

| 優先級 | 工項 | scope | 估算 sprint |
|---|---|---|---|
| P1 | settings.defaultTabStop → Layout.LineBreaker | 中、可能破 baseline（Strategy C）| 1-2 sprint |
| P1 | fontTable.altName → FontLoader fallback chain | 低、不破 baseline | 1 sprint |
| P2 | bookmark → render 錨點 | 中 | 1 sprint |
| P2 | instrText 複雜欄位 → render 端消費 | 中 | 1-2 sprint |
| P3 | wrapTight / wrapThrough（§1.8 anchor 5 種補完）| 高、Phase 3.4 待 | Phase 3 範圍 |
| Phase 5 | 追蹤修訂 / 註解 / OMML | - | 留 Phase 5 |
| 罕用 defer | ruby / tcFitText / lvlOverride / effectExtent / 圖片效果 / mc:AlternateContent | - | 必要時再做 |

**Sprint 157 建議 scope**:`fontTable.altName → FontLoader fallback chain` wire-up。
- 理由:低風險、不破 baseline、明確 caller（FontLoader）、Sprint 147 capture 已 ready、PR-size 適合單 sprint。
- 過後立即在規畫書 `<w:fontTable>` 相關 `[ ]` 打 `[x]`（雖然規畫書 §5 沒明確 fontTable 工項、可能對應 §1.7 之外、留 audit doc 紀錄）。

### 7.2 雙指標降為「75% 嚴格 wire-up」

更新 progress_snapshot Phase 1 描述為:
- 90%（含 capture-only、最寬鬆）
- 86%（含部分 wire-up、原描述）
- **75%（嚴格 wire-up、本 audit 確認）**

---

## File-level summary

```
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md
M  addons/dobtor_doc_editor/docs/progress_snapshot.md
A  addons/dobtor_doc_editor/docs/sprint156_phase1_checkbox_audit.md
```

**淨 production code 變動 = 0**、純 docs audit、為 Sprint 157+ Phase 1 wire-up 開工提供 17 個 `[ ]` 真實缺口清單。
