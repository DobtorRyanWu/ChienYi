# Sprint 187 — ParagraphProps export（Phase 6 docx export 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 ParagraphProps + styleId 序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185 MVS、Sprint 186 RunProps

---

## Hypothesis

Sprint 186 完成 RunProps（run 層樣式）。本 sprint 補 ParagraphProps（段落層
樣式）+ styleId（段落樣式引用）、把 Phase 6 推到「段落 + run 完整樣式」。

按 Sprint 185 預估覆蓋類別表，本 sprint 完成 ParagraphProps 主流欄位、
Phase 6 進度 ~+10pp。

---

## 修法

### 1. `writePPr(props, styleId)`（OoxmlWriter.ts、+約 80 行）

把 ParagraphProps + styleId 序列化為 `<w:pPr>` 屬性容器。子元素依 OOXML
CT_PPr schema（§17.3.1）順序：

```
pStyle → keepNext → keepLines → pageBreakBefore → numPr → tabs →
spacing → ind → jc → textAlignment → snapToGrid
```

欄位對應：
- `styleId` → `<w:pStyle w:val="..."/>`（CT_PPr 第一個子元素）
- `keepNext` / `keepLines` / `pageBreakBefore` → toggle property
  （true = 空 element、false = `w:val="0"` 顯式覆蓋 style 繼承）
- `numId` + `ilvl` → `<w:numPr><w:ilvl w:val="N"/><w:numId w:val="N"/></w:numPr>`
- `tabs[]` → `<w:tabs><w:tab w:val="left|right|..." w:pos="twips" w:leader="..."/></w:tabs>`
- `spacing.before` / `after` → `<w:spacing w:before w:after>`（twips）
- `spacing.line` → `<w:spacing w:line w:lineRule>`：
  - rule = `'auto'` → 240 分母（1.5 行 → `w:line="360"`）
  - rule = `'exact'` / `'atLeast'` → twips（14pt → `w:line="280"`）
- `indent` → `<w:ind w:left w:right w:firstLine w:hanging>`（皆 twips）
- `alignment` → `<w:jc w:val="left|center|right|justify"/>`
- `textAlignment` → `<w:textAlignment w:val="auto|top|center|baseline|bottom"/>`
- `snapToGrid` → `<w:snapToGrid/>` toggle

紀律 #21：欄位皆 optional、無值不掛子元素；props 全空且無 styleId → 回空字串
（不輸出 `<w:pPr>`、與 parser 對稱）。

### 2. `writeParagraph` 整合（+2 行）

`writeParagraph(para)` 在 `<w:p>` 開頭呼叫 `writePPr(para.props, para.styleId)`、
插入 runs 之前。

### 3. 新具名常數（+1）

`LINE_SPACING_AUTO_BASE = 240`（auto 規則分母、紀律 #2）。

### 4. 留後續 sprint 的 ParagraphProps 欄位

本 sprint **未覆蓋**（schema 較複雜、留 Sprint 188+）：
- `borders`（pBdr）—— `<w:pBdr><w:top/><w:bottom/>...</w:pBdr>` 含多 BorderDef
- `shading`（shd）—— `<w:shd w:fill w:color w:val>`
- `framePr`—— 多屬性複雜浮動段落框

### 5. 測試（+23）

- `tests/unit/OoxmlWriter.test.ts` Sprint 187 區塊（+13）：無 pPr 紀律 #21 /
  styleId 為 pPr 第一子元素 / keepNext-keepLines-pageBreakBefore toggle /
  keepNext false 顯式關閉 / numPr (numId + ilvl 順序) / alignment 列舉 /
  indent 四欄位 twips / spacing auto rule 240 分母 / spacing exact rule
  twips / tabs 多 tab + leader / textAlignment / snapToGrid toggle /
  子元素 schema 順序驗證。
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 187 區塊（+10）：
  alignment / styleId / numId+ilvl / indent 四欄位 / spacing auto 1.5 行 /
  spacing exact / 三 toggle / tabs / textAlignment 五列舉 / 多 props 組合
  round-trip。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1699 → **1722 passed + 1 skipped**（+23） |
| L2 VR v14 | ✅ **byte-identical 第 47 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 10 個 ParagraphProps 案例全綠 | 對齊 / styleId / numbering / 縮排 / spacing / toggles / tabs / textAlignment / 多 props 組合對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（rollup tree-shake、export 仍未被 entry
  引用、輸出 byte-identical）。

---

## Phase 6 完成度進度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS 純文字骨架（5 part / paragraph+run+sectPr） | ✅ | 185 |
| RunProps（粗體 / 斜體 / 字級 / 顏色 / 字型 / 高亮 / 上下標 / 字距 / 語言） | ✅ | 186 |
| **ParagraphProps（對齊 / styleId / numbering / 縮排 / spacing / tabs / toggles / textAlignment / snapToGrid）** | ✅ | **187** |
| ParagraphProps 進階（borders / shading / framePr） | ⏳ | Sprint 188 候選 |
| Styles.xml 完整 + 繼承 | ⏳ | Sprint 189 |
| 多 section / numbering.xml 完整輸出 | ⏳ | Sprint 190 |
| 表格 | ⏳ | Sprint 191-192 |
| 圖片 / media | ⏳ | Sprint 193 |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 194-195 |
| Phase 5 子功能 | ⏳ | Sprint 196+ |

**Phase 6 完成度估算：~25% → ~35%**（MVS 15% + RunProps 10% + ParagraphProps 10%）

---

## 紀律

- **#1.b / Strategy C**：export 路徑仍在 VR pipeline 外、bundle tree-shake 排除、
  VR byte-identical 第 47 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR 確認無 side effect。
- **#14（DRY）**：`writePPr` 結構鏡像 `writeRPr`（schema-order、紀律 #21、
  toggle property false 處理）；`ptToTwips` 工具持續複用。
- **#18 scope-down**：僅 ParagraphProps 主流欄位、borders / shading / framePr
  等留 Sprint 188+；避免一個 sprint 吞下整個段落樣式深淵。
- **#21**：所有 ParagraphProps 欄位 optional、無值不掛；props 全空且無
  styleId → `<w:pPr>` 整段不輸出（與 parser 對稱）。
- **#2 magic number**：`LINE_SPACING_AUTO_BASE = 240`（新具名常數）。
- **schema-order**：依 OOXML CT_PPr schema 子元素順序輸出。

---

## 後續

- **Sprint 188**：ParagraphProps 進階（pBdr / shd）+ framePr export + 對應
  round-trip。或先衝 Styles.xml 完整輸出（樣式繼承的 export 等價）。
- 依 Phase 6 進度表逐步推進至 100%。

---

## Sprint 187 結尾累積指標

- vitest **1722 passed + 1 skipped**（`npm test` 全套；+23）
- VR mean **0.073191**（byte-identical 第 47 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 186 → **187**
- Phase 6 完成度 ~25% → ~35%（MVS + RunProps + ParagraphProps 主流欄位）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       writePPr + writeParagraph 整合 + LINE_SPACING_AUTO_BASE（+約 82）
M  tests/unit/OoxmlWriter.test.ts                    +13 test（ParagraphProps 區塊）
M  tests/integration/sprint185_export_roundtrip.test.ts  +10 test（ParagraphProps round-trip）
```

**淨 production code 變動 = +約 82 行**、ParagraphProps round-trip 對稱、
VR byte-identical 第 47 連、Phase 6 完成度 ~35%。
