# Sprint 186 — RunProps export（Phase 6 docx export 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 RunProps 序列化、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性、AST → XML serializer」
**前置**：Sprint 185（Phase 6 MVS 純文字 round-trip 骨架）

---

## Hypothesis

Sprint 185 MVS 走通 export 端到端骨架（純文字段落 round-trip）。本 sprint 補
RunProps（粗體 / 斜體 / 底線 / 字級 / 顏色 / 字型 / 高亮 / 上下標 / 字距 / 語言）
序列化、把 Phase 6 從「文字 only」推到「文字 + run 樣式」。

按 Sprint 185 預估的覆蓋類別表，本 sprint 完成 RunProps、Phase 6 進度 ~+10pp。

---

## 修法

### 1. `writeRPr(props)`（OoxmlWriter.ts、+約 50 行）

把 RunProps 序列化為 `<w:rPr>` 屬性容器。子元素順序依 OOXML CT_RPr schema
（§17.3.2）大致排序：

```
rFonts → b → i → strike → dstrike → color → spacing → sz → highlight →
u → vertAlign → lang
```

每個欄位的 OOXML 對應：
- `fontFamily` / `fontFamilyEastAsia` / `fontFamilyHAnsi` / `fontFamilyCs`
  → `<w:rFonts w:ascii w:eastAsia w:hAnsi w:cs/>`（缺漏屬性跳過）
- `bold` / `italic` / `strike` / `dstrike`：toggle property
  - true → 空 element `<w:b/>`
  - **false → `<w:b w:val="0"/>`（顯式關閉、覆蓋 style 繼承）**
- `color`（HexColor）→ `<w:color w:val="RRGGBB"/>`
- `spacing`（Pt）→ `<w:spacing w:val="N"/>`（twips = pt × 20、可正可負）
- `fontSize`（Pt）→ `<w:sz w:val="N"/>`（**half-points = pt × 2**、12pt = 24）
- `highlight` → `<w:highlight w:val="..."/>`（具名色 yellow / cyan / red…）
- `underline`（Underline 列舉）→ `<w:u w:val="..."/>`
- `vertAlign` → `<w:vertAlign w:val="superscript|subscript|baseline"/>`
- `lang` → `<w:lang w:val="..."/>`

紀律 #21：所有欄位皆 optional、無值不掛子元素；props 全空 → 回空字串
（不輸出 `<w:rPr/>` 標籤、與 parser 「無 rPr 視為無 props」對稱）。

### 2. `writeRun` 整合（+2 行）

`writeRun` 在 `<w:r>` 開頭呼叫 `writeRPr(run.props)`、把回傳字串插入
`<w:r>...</w:r>` 內、緊接 `<w:t>` 之前。

### 3. 具名常數（+1）

`HALF_POINTS_PER_PT = 2`（紀律 #2、避免 magic number）。

### 4. 測試（+23）

- `tests/unit/OoxmlWriter.test.ts` Sprint 186 區塊（+14）：無 props 不輸出 rPr /
  粗體 true / 粗體 false 顯式關閉 / 斜體+刪除線+雙刪除線 / 字級 half-points /
  顏色 hex / 高亮具名色 / 底線多種列舉 / 上下標 super-sub / 字型四欄位完整 /
  字型部分欄位 / 字距 twips / 語言 / 多 prop 組合 schema 順序。
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 186 區塊（+9）：
  粗體+斜體+刪除線 / 字級 / 顏色（大小寫正規化）/ 底線多列舉 / 上下標 /
  字型四欄位 / 高亮 / 語言 / 多 props 組合 round-trip。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1676 → **1699 passed + 1 skipped**（+23） |
| L2 VR v14 | ✅ **byte-identical 第 46 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 9 個 RunProps 案例全綠 | 粗體 / 斜體 / 字級 / 顏色 / 底線 / 上下標 / 字型 / 高亮 / 語言 / 多 prop 組合對稱 |

- `tsc --noEmit`：2 個 pre-existing error、**無新增**。
- frontend bundle + VR IIFE bundle 重建（rollup tree-shake、export 仍未被 entry
  引用、輸出 byte-identical）。

---

## Phase 6 完成度進度

| 子目標 | 狀態 | 累積 sprint |
|---|---|---|
| MVS 純文字骨架（5 part / paragraph+run+sectPr） | ✅ | Sprint 185 |
| **RunProps（粗體 / 斜體 / 字級 / 顏色 / 字型 / 高亮 / 上下標 / 字距 / 語言）** | ✅ | **Sprint 186** |
| ParagraphProps（對齊 / 縮排 / spacing） | ⏳ | Sprint 187 |
| Styles.xml 完整 + 繼承 | ⏳ | Sprint 188 |
| 多 section / numbering | ⏳ | Sprint 189 |
| 表格 | ⏳ | Sprint 190-191 |
| 圖片 / media | ⏳ | Sprint 192 |
| 頁首頁尾 / 註腳 / 註解 | ⏳ | Sprint 193-194 |
| Phase 5 子功能 | ⏳ | Sprint 195+ |

**Phase 6 完成度估算：~15% → ~25%**（MVS 骨架 15% + RunProps ~10%）

---

## 紀律

- **#1.b / Strategy C**：export 路徑仍在 VR pipeline 外、bundle tree-shake 排除、
  VR byte-identical 第 46 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR 確認無 side effect。
- **#14（DRY）**：每個 RunProps 欄位對應一個 OOXML 元素、寫法統一；
  `escapeXml` / `ptToTwips` / `ptToHalfPoints` 工具化複用。
- **#18 scope-down**：僅 RunProps、ParagraphProps / 樣式 / 表格留後續 sprint。
- **#21**：所有 RunProps 欄位 optional、無值不掛子元素；無 props → `<w:rPr>`
  整段不輸出（與 parser 對稱）。
- **#2 magic number**：`HALF_POINTS_PER_PT = 2`（新具名常數）。
- **schema-order**：依 OOXML CT_RPr schema 子元素順序輸出（Word 對亂序通常寬容、
  但有助 byte-level diff 與某些 strict reader 相容）。

---

## 後續

- **Sprint 187**：ParagraphProps export（對齊 alignment / 縮排 indent / spacing /
  numbering 引用 / textAlignment / pBdr 邊框）+ 對應 round-trip。
- **Sprint 188+**：依 Sprint 185 預估表逐步擴充至 Phase 6 100%。

---

## Sprint 186 結尾累積指標

- vitest **1699 passed + 1 skipped**（`npm test` 全套；+23）
- VR mean **0.073191**（byte-identical 第 46 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 185 → **186**
- Phase 6 完成度 ~15% → ~25%（MVS + RunProps）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       writeRPr + writeRun 整合 + HALF_POINTS_PER_PT（+約 55）
M  tests/unit/OoxmlWriter.test.ts                    +14 test（RunProps 區塊）
M  tests/integration/sprint185_export_roundtrip.test.ts  +9 test（RunProps round-trip）
```

**淨 production code 變動 = +約 55 行**、RunProps round-trip 對稱、VR byte-identical
第 46 連、Phase 6 完成度 ~25%。
