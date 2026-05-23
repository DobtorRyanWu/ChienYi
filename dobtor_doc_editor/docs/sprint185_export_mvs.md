# Sprint 185 — Phase 6 docx export probe + MVS（純文字 round-trip）

**日期**：2026-05-23
**類型**：新模組 + 架構 probe + minimum viable slice（Phase 6 docx export 0% → 開工）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性、AST → XML serializer + 黃金測試 `import(export(doc))` ≅ `doc`」
**前置**：Sprint 178-184（Phase 5 全 6 子功能 capture + render 全數完成）

---

## Hypothesis

Phase 5 capture + render 都完成、規畫書剩 Phase 6 docx export 對稱性 0% 是最大
缺口。本 sprint 走通 Phase 6 端到端骨架：

- **架構決定**：per-part writer 函式（鏡像 parser 的 per-part class 模式）、
  主流程 `OoxmlWriter.write()` orchestrator 組裝、`fflate.zipSync` 打包。
- **MVS 切片**：純文字段落 round-trip——driver 寫一個 paragraph + run，
  經 `OoxmlWriter` → bytes → `OoxmlParser` → DocumentNode、再驗證 text 對稱。
- **覆蓋率**：MVS 覆蓋最小但 round-trip 已可驗證；後續 sprint 逐步擴充
  RunProps / ParagraphProps / 樣式 / 表格 / 圖片 / Phase 5 子功能。

**為何 MVS 而非全保真**：規畫書 §6 提示 export 是「對稱性」工作、不是
import 的反向重寫。從零做到 100% 需 10+ sprint。MVS 先走通骨架、Round-trip
testing infrastructure 建好後、後續擴充每個 part 都有明確的對稱性 gate。

---

## 修法

### 1. 新模組 `export/OoxmlWriter.ts`（+約 175 行）

`OoxmlWriter.write(doc): Uint8Array` 主流程：
- 組裝 5 個必要 part：`[Content_Types].xml` / `_rels/.rels` /
  `word/_rels/document.xml.rels` / `word/document.xml` / `word/styles.xml`
- `fflate.zipSync` 打包為 Uint8Array

Per-part writer 函式（鏡像 parser）：
- `writeContentTypes()` — 宣告 document.xml / styles.xml 兩個 override
- `writeRootRels()` — root → word/document.xml（officeDocument 型別）
- `writeDocumentRels()` — document → styles.xml
- `writeStyles()` — 空骨架 `<w:styles/>`（parser 接受、後續擴充）
- `writeDocument(doc)` — 多 section 段落串成單 body、用末 section 的 sectPr
- `writeParagraph(para)` → `writeRun(run)` → `escapeXml` + `xml:space="preserve"`
- `writeSectPr(section)` — pgSz / pgMar、pt → twips（×20、四捨五入）

XML 工具：
- `xmlDecl()` — UTF-8 / standalone="yes"
- `escapeXml(s)` — & < > " '
- `ptToTwips(pt)` — pt × 20 取整

### 2. 新 `export/index.ts`：re-export OoxmlWriter

### 3. 測試（+25）

- `tests/unit/OoxmlWriter.test.ts`（+16）：5 必要 part 結構、段落 / Run /
  多段落 / 多 Run 順序、XML 特殊字元跳脫、xml:space="preserve"、非 run
  InlineNode（image/break/field）跳過、表格跳過、sectPr twips 換算、
  多 section 退化、無 section fallback、XML 宣告格式、Uint8Array round-trip。
- `tests/integration/sprint185_export_roundtrip.test.ts`（+9）：規畫書 §6
  黃金測試的純文字切片——空文件 / 單 / 多段落 / 多 Run / 特殊字元 / 前後
  空白 / CJK + emoji / 多 section 退化 / page+margin 量化對稱。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1651 → **1676 passed + 1 skipped**（+25） |
| L2 VR v14 | ✅ **byte-identical 第 45 連** | rendered 42/42、comparedPages 126、failedPages 0；export 模組在 VR pipeline 外（VR 走 parse → render、不呼叫 writer）|
| L3 round-trip | ✅ MVS 切片對稱 | 9 個 round-trip 案例（純文字 / CJK / emoji / 特殊字元 / 空白 / 多 section / page-margin）全綠 |

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js / SettingsParser
  position enum）、**無新增**。
- frontend bundle + VR IIFE bundle 重建（export 模組在 ooxml 依賴樹）。

---

## MVS 範圍 vs 後續 sprint 預估

| 覆蓋項 | Sprint 185 MVS | 後續 sprint |
|---|---|---|
| 段落 + run 文字 | ✅ | — |
| 單 section pgSz/pgMar | ✅ | — |
| 5 必要 part 結構 | ✅ | — |
| XML 跳脫 + xml:space | ✅ | — |
| RunProps（粗體/斜體/字級/顏色/字型） | ❌ | Sprint 186 候選 |
| ParagraphProps（對齊/縮排/spacing） | ❌ | Sprint 186-187 |
| Styles.xml 完整輸出 + 繼承 | ❌ | Sprint 187-188 |
| 多 section / sectPr in pPr | ❌ | Sprint 188 |
| Numbering / List | ❌ | Sprint 189 |
| 表格（grid / row / cell / borders / vMerge） | ❌ | Sprint 190-191 |
| 圖片 / media | ❌ | Sprint 192 |
| 頁首頁尾 / 註腳 / 註解 | ❌ | Sprint 193-194 |
| Phase 5 子功能（OMML / SmartArt / Chart / 浮水印 / 追蹤修訂） | ❌ | Sprint 195+ |

**Phase 6 100% 完成預估剩 10-12 sprint**（按 archetype 每 sprint 1-2 part / 覆蓋類別）。

---

## 紀律

- **#1.b / Strategy C**：export 模組在 parser / mapper / render 路徑之外、VR pipeline
  不呼叫；42 fixture VR 完全不變、byte-identical 第 45 連。
- **#1.a**：新模組加進 ooxml 依賴樹、bundle 重建後跑全 VR 確認無 side effect。
- **#14（DRY）**：per-part writer 函式鏡像 parser 的 per-part class 模式；
  `escapeXml` / `ptToTwips` 等工具獨立函式、避免單檔過大時可拆。
- **#18 scope-down**：MVS 純文字段落、其他全部留後續 sprint；避免「export 從零
  做到 100%」單 sprint 不可能達成的 over-scope；每 sprint 增量 1-2 個覆蓋類別。
- **#21**：MVS 不輸出 `<w:rPr>` / `<w:pPr>` 屬性容器（runs/paras 無 RunProps/
  ParagraphProps 輸出時、不掛空 key、保持 XML 乾淨）。
- **#2 magic number**：8 個具名常數（TWIPS_PER_PT / DEFAULT_PAGE_* /
  DEFAULT_MARGIN_*）；2 個 namespace URI 常數；rels type URI 常數。

---

## 後續

- **Sprint 186**：RunProps 輸出（粗體 b / 斜體 i / 底線 u / 字級 sz / 字型 rFonts /
  顏色 color）+ 對應 round-trip 對稱驗證。
- **Sprint 187+**：依上表逐步擴充 Phase 6 覆蓋率。
- **Phase 6 完成度目標**：每 sprint +5-10pp、預估 10-12 sprint 達 100%。

---

## Sprint 185 結尾累積指標

- vitest **1676 passed + 1 skipped**（`npm test` 全套；+25）
- VR mean **0.073191**（byte-identical 第 45 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 184 → **185**
- Phase 6 docx export 0% → **MVS 切片完成、純文字段落 round-trip 對稱**

---

## File-level summary

```
A  static/src/core/ooxml/export/OoxmlWriter.ts        新模組 5-part 寫出 + zipSync（+約 175）
A  static/src/core/ooxml/export/index.ts              re-export
A  tests/unit/OoxmlWriter.test.ts                     +16 test
A  tests/integration/sprint185_export_roundtrip.test.ts  +9 test（round-trip 黃金測試）
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
M  tools/dist/visual_regression_pipeline.iife.js      VR bundle 重建
```

**淨 production code 變動 = +約 175 行**、純文字 round-trip MVS、VR byte-identical
第 45 連、Phase 6 docx export 開工。
