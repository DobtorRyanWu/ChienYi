# Sprint 193 — 頁首頁尾 export（Phase 6 docx export 擴充）

**日期**：2026-05-23
**類型**：export 擴充（Phase 6 header/footer 部件 + sectPr references、round-trip 對稱）
**規畫書對應**：§6 階段 E Phase 6「docx export 對稱性」
**前置**：Sprint 185-192（文件流 + 樣式 + 表格 + 多 section + numbering + 圖片）

---

## Hypothesis

Sprint 192 完成圖片 export。本 sprint 補頁首頁尾 export：
- 每個 header/footer 寫成獨立 part（`word/header{N}.xml` / `word/footer{N}.xml`）
- Content_Types Override + document rels 加 header/footer 關係
- `<w:sectPr>` 內 `<w:headerReference>` / `<w:footerReference>` 引用 + `<w:titlePg/>`

完成後 Phase 6 進度從 ~95% 推到 ~98%（剩 Phase 5 子功能 export 一塊）。

---

## 修法

### 1. 2 個新關係型別常數（+4 行）

`REL_TYPE_HEADER` / `REL_TYPE_FOOTER`（紀律 #2）。

### 2. `HeaderFooterItem` 型別 + `collectHeadersFooters(doc)`（+約 25 行）

把 `doc.headers` / `doc.footers` 整理為 `HeaderFooterItem[]`：
- `kind: 'header' | 'footer'`、`rId`、`filename`、`content: BlockNode[]`
- 檔名用序號流水（`word/header1.xml` / `word/header2.xml` ...）—— 與
  image collectMedia 同模式、與原 docx 的 target 無關、export 端自由命名。

### 3. `writeHeaderFooterPart(hf)`（+約 12 行）

寫單一 header/footer 部件 XML：
- root `<w:hdr>` 或 `<w:ftr>`，宣告 `xmlns:w` + `xmlns:r`（備內含 hyperlink/
  image 引用）
- 內容：reuse `writeBlock` dispatcher → 段落 / 表格 / 巢狀自然支援

### 4. `writeContentTypes(imageExts, hfItems)` 擴展（+8 行）

為每個 header/footer 加 Override：
- header: `application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml`
- footer: `application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml`

### 5. `writeDocumentRels(mediaItems, hfItems)` 擴展（+10 行）

為每個 header/footer 加 `<Relationship>`：
- `Id` 從 `doc.headers/footers` Map keys 原樣帶入（rId 保留）
- `Type` = `REL_TYPE_HEADER` / `REL_TYPE_FOOTER`
- `Target` = 相對 word/ 路徑（`header1.xml` 等）

### 6. `writeSectPr(section)` 重構（+約 25 行）

依 OOXML CT_SectPr schema（§17.6.17）順序輸出：
- `<w:headerReference w:type r:id>` × 1..3（default/first/even、有 rId 才 emit）
- `<w:footerReference w:type r:id>` × 1..3
- `<w:pgSz>` / `<w:pgMar>`
- `<w:titlePg/>`（toggle、`section.titlePage === true` 才 emit）

新 helper `writeRefs(elementName, refs)` 共用 header/footer reference 序列化。

### 7. `<w:document>` root 加 `xmlns:r` 宣告（+1 行）

給 `<w:headerReference r:id>` 用。

### 8. `OoxmlWriter.write()` 整合（+5 行）

- `collectHeadersFooters(doc)` → `hfItems`
- 傳入 `writeContentTypes(imageExts, hfItems)` / `writeDocumentRels(mediaItems, hfItems)`
- parts 字典加每個 header/footer 部件 bytes

### 9. 測試（+17）

- `tests/unit/OoxmlWriter.test.ts` Sprint 193 區塊（+11）：
  - 單一 header → word/header1.xml + `<w:hdr>` 結構（含 xmlns:w/xmlns:r）
  - 單一 footer → word/footer1.xml + `<w:ftr>` 結構
  - 多 header/footer → 流水號 headerN/footerN
  - header 內含表格 → BlockNode 遞迴 dispatcher 正確輸出
  - Content_Types 含 header/footer override
  - document rels 含 header/footer rel（rId 保留）
  - sectPr 含 headerReference + footerReference（依 default/first/even）
  - titlePage = true → `<w:titlePg/>`
  - `<w:document>` root 含 xmlns:r
  - schema 順序：headerReference 在 pgSz 之前
  - 無 header/footer → 不輸出對應部件
- `tests/integration/sprint185_export_roundtrip.test.ts` Sprint 193 區塊（+6）：
  - 單一 header round-trip（doc.headers 保留 + content 還原）
  - 單一 footer round-trip
  - headerRefs default 引用保留
  - multi-type refs（default + first）round-trip
  - titlePage round-trip
  - header + footer 同時 round-trip

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1817 → **1834 passed + 1 skipped**（+17） |
| L2 VR v14 | ✅ **byte-identical 第 53 連** | rendered 42/42、comparedPages 126、failedPages 0；export 仍在 VR pipeline 外 |
| L3 round-trip | ✅ 6 個 header/footer 案例（含內容 / refs / titlePage / 多 type） | 端到端對稱 |

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
| 表格 | ✅ | 190 |
| 多 section + numbering.xml | ✅ | 191 |
| 圖片 / media | ✅ | 192 |
| **頁首頁尾 + sectPr refs + titlePg** | ✅ | **193** |
| Phase 5 子功能（OMML / SmartArt / Chart / 浮水印 / 追蹤修訂）export | ⏳ | Sprint 194-195 |

**Phase 6 完成度估算：~95% → ~98%**

---

## 紀律

- **#1.b / Strategy C**：export 仍 VR pipeline 外、byte-identical 第 53 連。
- **#1.a**：parser path 不動、bundle 重建跑全 VR。
- **#14（DRY）**：`writeHeaderFooterPart` 透過 `writeBlock` dispatcher reuse
  paragraph/table/nested 邏輯；`writeRefs` 共用 header/footer reference 序列化；
  filename 序列流水模式同 collectMedia。
- **#18 scope-down**：header/footer 內含 image / hyperlink 時、目前不為各 header
  獨立寫 rels 檔（依賴 doc 主 rels）；多數簡單頁首頁尾為純文字無 rels 需求；
  進階場景留後續 optional。
- **#21**：headerRefs / footerRefs 各 type 缺漏不 emit；無 header/footer →
  不輸出 part / Override / Relationship。
- **#2 magic number**：2 個新常數（REL_TYPE_HEADER / REL_TYPE_FOOTER）。
- **schema-order**：sectPr 子元素依 CT_SectPr schema 順序（refs → pgSz → pgMar
  → titlePg）。

---

## 後續

- **Sprint 194-195**：Phase 5 子功能 export（OMML / SmartArt / Chart / 浮水印 /
  追蹤修訂）。capture-only 時這些只是讀進來、render 用 fallback；export 端要
  決定是寫回原始結構（high-fidelity）還是寫成 fallback。建議走 mc:Fallback
  策略：把 OMML capture-only 儲存的 attrs/children 樹寫回 `<m:oMath>`；SmartArt/
  Chart 寫回 `<w:drawing>` 中嵌入的資料模型；追蹤修訂寫回 `<w:ins>` / `<w:del>`。
- 收尾 Phase 6 到 100%。

---

## Sprint 193 結尾累積指標

- vitest **1834 passed + 1 skipped**（`npm test` 全套；+17）
- VR mean **0.073191**（byte-identical 第 53 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 192 → **193**
- Phase 6 完成度 ~95% → ~98%（頁首頁尾 + sectPr refs + titlePg 完整覆蓋）

---

## File-level summary

```
M  static/src/core/ooxml/export/OoxmlWriter.ts       collectHeadersFooters + writeHeaderFooterPart + writeSectPr 重構 + writeRefs + Content_Types/rels 擴充 + xmlns:r（+約 95）
M  tests/unit/OoxmlWriter.test.ts                    +11 test
M  tests/integration/sprint185_export_roundtrip.test.ts  +6 test
```

**淨 production code 變動 = +約 95 行**、頁首頁尾 round-trip 對稱、VR byte-identical
第 53 連、Phase 6 完成度 ~98%。
