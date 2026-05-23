# Sprint 190 — 表格 export（Phase 6 docx export 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 表格 part 完整序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-189（MVS / RunProps / ParagraphProps / Styles.xml）

---

## Hypothesis

Sprint 189 完成 Styles.xml export。本 sprint 補 Phase 6 剩下單一最大塊——
表格（OOXML §17.4）。涵蓋表格層級屬性、grid 欄寬、列屬性、儲存格屬性、
gridSpan / vMerge 合併、巢狀表格。

完成後 Phase 6 進度從 ~55% 推到 ~75%（表格是 ChienYi 監造文件最常用結構）。

---

## 修法

### 1. `writeBlock(block)`（OoxmlWriter.ts、+5 行）

統一 dispatch：BlockNode 為 ParagraphNode | TableNode → `writeParagraph` /
`writeTable`。`writeDocument` 主流程改呼叫此 dispatcher、cell content 遞迴
也用此 dispatcher（巢狀表格自然支援）。

### 2. `writeTable(table)`（+10 行）

結構 `<w:tbl><w:tblPr>...</w:tblPr><w:tblGrid>...</w:tblGrid>0..N <w:tr>...</w:tr></w:tbl>`。

### 3. `writeTblPr(props, styleId)`（+約 18 行）

子元素依 OOXML CT_TblPrBase schema 順序：
- `<w:tblStyle w:val>`（styleId）
- `<w:tblW w:w w:type>`（透過 `writeTblW`：'dxa' 用 twips、'pct'/'auto'/'nil' 用 0）
- `<w:jc w:val>`（alignment）
- `<w:tblInd w:w w:type="dxa">`（indent twips）
- `<w:tblBorders>`（top/left/bottom/right/insideH/insideV、`writeBorderSet`）
- `<w:tblCellMar>`（四邊邊距 twips）
- `<w:tblLook w:val>`

### 4. `writeTblGrid(grid)`（+約 4 行）

每個 `<w:gridCol w:w="N"/>`（pt × 20 = twips）。

### 5. `writeRow` + `writeTrPr`（+約 15 行）

- `<w:trHeight w:val w:hRule>`（pt → twips；`heightRule` 預設 'auto'）
- `<w:tblHeader/>` toggle（isHeader）
- `<w:cantSplit/>` toggle

### 6. `writeCell` + `writeTcPr`（+約 45 行）

`<w:tc>` 結構：`<w:tcPr>...</w:tcPr><w:p>...</w:p>+|<w:tbl>...</w:tbl>` 遞迴。
**空 content 自動補 `<w:p/>`**（OOXML 規範：每個 tc 必含至少一個 block-level
child；isContinuation=true 的 vMerge 延續格也適用）。

`writeTcPr` 子元素：
- `<w:tcW w:w w:type="dxa">`（cell width）
- `<w:gridSpan w:val>`（**>1 才掛、紀律 #21**）
- `<w:vMerge w:val="restart"/>`（**rowSpan>1 起始格**）或 `<w:vMerge/>`（**isContinuation=true 延續格、無 val=預設 continue**）
- `<w:tcBorders>`（top/left/bottom/right + insideH/insideV、`writeBorderSet`）
- `<w:shd w:val w:fill w:color>`
- `<w:noWrap/>` toggle
- `<w:tcMar>` 四邊邊距
- `<w:textDirection w:val>`（含 lrTb/tbRl/tbRlV 等 6 種、Sprint 34 中文直書）
- `<w:vAlign w:val>`（top/center/bottom）
- `<w:tcFitText/>` toggle

### 7. `writeBorderSet(borders, wrapper)`（+約 15 行、共用）

CellBorders → `<w:tblBorders>` 或 `<w:tcBorders>`（依 wrapper 名）：
- 6 sides：top / left / bottom / right / **insideH / insideV**
- 每邊：`w:val` / `w:sz`（1/8 pt）/ `w:color` / `w:space`（紀律 #21 缺漏跳過）
- 紀律 #14：與 Sprint 188 `writePBdr` 同邏輯、但需支援 6 sides（vs 4）+ 動態
  wrapper 名 → 分開為新函式而非合併。

### 8. 測試（+28）

- `tests/unit/OoxmlWriter.test.ts` Sprint 190 區塊（+16）：基本結構（空表 /
  tblGrid / 單列單格 / 空 cell 補空段落）/ tblPr（styleId+tblW+jc+tblInd+
  tblLook / 非 dxa 型別 / tblBorders+tblCellMar）/ trPr（trHeight+heightRule+
  tblHeader+cantSplit）/ tcPr（tcW+vAlign+noWrap+textDirection / tcBorders+
  shading+margins）/ gridSpan（>1 / =1 紀律 #21）/ vMerge（restart / continue）/
  巢狀表格 / 2×2 表格。
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 190 區塊（+12）：
  空表 / grid 寬度 / 單列單格+文字 / tblPr 完整 / tblW dxa / tblBorders+
  tblCellMar / trPr 四欄位 / tcPr width+vAlign+textDirection / tcBorders+
  shading / gridSpan / 2×2 完整 / 巢狀表格 round-trip。

### 9. Sprint 185 MVS 測試升級（+0 / 修改 1）

原「表格 BlockNode → MVS 跳過」測試斷言 `not.toContain('<w:tbl')`，本 sprint
表格已實作 → 改為「與段落並存輸出」斷言 `toContain('<w:tbl>')`，並補上
TableNode 必填 `props` 欄位。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1752 → **1780 passed + 1 skipped**（+28） |
| L2 VR v14 | ✅ **byte-identical 第 50 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 12 個表格案例全綠 | 含 gridSpan / vMerge / 巢狀表格端到端對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（tree-shake 維持）。

---

## Phase 6 完成度進度

| 子目標 | 狀態 | Sprint |
|---|---|---|
| MVS 純文字骨架 | ✅ | 185 |
| RunProps | ✅ | 186 |
| ParagraphProps 主流欄位 | ✅ | 187 |
| ParagraphProps 進階（pBdr / shd / framePr） | ✅ | 188 |
| Styles.xml 完整輸出 | ✅ | 189 |
| **表格（tblPr / tblGrid / trPr / tcPr / gridSpan / vMerge / 巢狀）** | ✅ | **190** |
| 多 section / numbering.xml 完整輸出 | ⏳ | Sprint 191 |
| 圖片 / media | ⏳ | Sprint 192 |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 193-194 |
| Phase 5 子功能（OMML / SmartArt / Chart / 浮水印 / 追蹤修訂） | ⏳ | Sprint 195+ |

**Phase 6 完成度估算：~55% → ~75%**（表格是單一最大塊、佔規畫 ~20pp）

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 50 連
  （連續 byte-identical 半百里程碑）。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：`writeBlock` dispatcher 巢狀表格自然支援（cell content 用同
  dispatcher）；`writeTblW` / `writeTcW` 共用單位邏輯；`writeBorderSet`
  支援 6 sides + 動態 wrapper 名（拆出與 Sprint 188 `writePBdr` 並存、避免
  4-side vs 6-side 攪在一起）；`writeTcMar` / `writeTblCellMar` 結構相同
  但 wrapper 不同、分兩函式（schema 位置不同：tblPr 內 vs tcPr 內）。
- **#18 scope-down**：表格 part 一個 sprint 收完（原預估拆兩 sprint）；
  conditional table styles（`<w:tblStylePr>`）/ `<w:tblpPr>` 浮動表格 /
  `<w:tblLayout>` fixed 表格佈局 / cellSpacing 留後續。
- **#21**：gridSpan=1 不掛 / vMerge 預設不掛 / 空 borders 不掛 / 空 margins
  不掛；最內層元素全空 → 該元素不輸出。
- **schema-order**：tblPr 子元素依 CT_TblPrBase schema 順序、tcPr 同 CT_TcPr
  schema 順序。
- **正確性**：空 cell 自動補 `<w:p/>`（OOXML 規範：每 tc 必含至少一個
  block-level child；忽略此規則的 docx 會被部分 reader 拒絕）。

---

## 後續

- **Sprint 191**：多 section + numbering.xml export。多 section 需要把 sectPr
  改 emit 在 paragraph 的 pPr 內（intermediate sections）+ trailing body sectPr
  （final section）；numbering.xml 比照 styles 對稱性策略。
- 依 Phase 6 進度表逐步推進至 100%。

---

## Sprint 190 結尾累積指標

- vitest **1780 passed + 1 skipped**（`npm test` 全套；+28）
- VR mean **0.073191**（byte-identical 第 50 連、半百里程碑）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 189 → **190**
- Phase 6 完成度 ~55% → ~75%（表格完整覆蓋）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       writeBlock + writeTable 系列（+約 135）
M  tests/unit/OoxmlWriter.test.ts                    +16 test（表格 unit + 1 升級）
M  tests/integration/sprint185_export_roundtrip.test.ts  +12 test（表格 round-trip）
```

**淨 production code 變動 = +約 135 行**、表格 round-trip 對稱（含 gridSpan /
vMerge / 巢狀）、VR byte-identical 第 50 連、Phase 6 完成度 ~75%。
