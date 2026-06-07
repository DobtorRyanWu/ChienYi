# Sprint 2 — PackageReader + Units（Phase 1 §1.1-1.2）

**日期**：2026-06-07
**Phase**：1（OOXML SpreadsheetML Parser）開工
**對齊**：規劃書 §1.1 Package 與 Relationships、§1.2 單位系統

---

## Root cause（開工前假設）

Phase 1 目標是把 xlsx 100% 解析成 Workbook AST，但所有上層 parser（workbook/worksheet/styles）
都依賴兩個地基：
1. **取得 part bytes 的能力** — xlsx 是 OPC zip，必須先能解 zip、依 Content_Types 知道每個 part 型別、
   依 .rels 知道 part 之間的引用關係（含相對路徑 `../`）。
2. **單位換算** — xlsx 內 EMU/point/字元欄寬混用，渲染前必須統一成 pixel。

假設：fflate（解 zip）+ fast-xml-parser（解 XML）足以實作 §1.1，無需自寫 zip/XML parser。

## 修法（實際做的事）

### `static/src/core/ooxmlspreadsheet/units.ts`（§1.2）
- 具名常數（紀律：禁 magic number）：`EMU_PER_INCH=914400`、`EMU_PER_POINT=12700`、`DEFAULT_DPI=96`、`DEFAULT_MDW=7`
- point↔px、EMU↔px、EMU↔point、列高(pt)→px
- 欄寬：依 ECMA-376 §18.3.1.13 反算式 `Trunc(((256*w+Trunc(128/MDW))/256)*MDW)` 字元數→px
- **修正規劃書筆誤**：§1.2 寫「row height = half-points」，但 ECMA-376 §18.3.1.73 明定 row@ht 為
  point（半點是 WordprocessingML 慣例）；依規格以 point 實作並於註解標注。

### `static/src/core/ooxmlspreadsheet/package_reader.ts`（§1.1）
- `PackageReader.fromBuffer(ArrayBuffer|Uint8Array)`：fflate `unzipSync`，缺 `[Content_Types].xml` 即丟錯
- `getPart` / `getPartText`（UTF-8）/ `listParts` / `hasPart`
- `getContentType`：Override（完整 part 名）優先、否則 Default（副檔名），結果快取
- `getRels(part)`：對 `dir/name.xml` 讀 `dir/_rels/name.xml.rels`，解析 `Relationship`，
  **相對 target 解析**（支援 `../`、`/` 絕對、`TargetMode=External` 保留原值），結果快取
- `getRootRels()`：`_rels/.rels` 捷徑
- 完整 TS 型別、無 `any`（fast-xml-parser 回傳以 `Record<string,unknown>` + `toArray` 正規化）

## 三層 SOP 結果

- **L1 vitest**：**78 passed**（unit 29 + integration 49）
  - `units.test.ts`（12）：常數、point/EMU/px 互轉、欄寬 spec 錨點值（width10@MDW7=70px、8.43=59px）
  - `package_reader.test.ts`（15）：**合成最小 package** 精確驗證 Content_Types Override/Default、
    rels 相對路徑（`worksheets/sheet1.xml`→`xl/worksheets/sheet1.xml`、`../docProps/core.xml`→`docProps/core.xml`）、
    External 保留、缺 Content_Types 丟錯
  - `package_reader_corpus.test.ts`（49）：**全 48 份 ChienYi fixture** 逐檔 PackageReader 無 error、
    根→officeDocument→workbook→worksheet 關聯鏈全解出且 target part 實存
- **L2 visual regression**：N/A（渲染層 Phase 2+）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（12.6s，fflate+fast-xml-parser 正常打包）

## 對齊 Phase 1 Exit Criteria 進度

| Exit 條件 | 狀態 |
|---|---|
| Parser 對 50 份 fixture 全部無 error | 🟢 §1.1 層級達成（48/48 corpus 綠） |
| Cell values 提取率 > 95% | ⚪ 待 §1.4/1.6 |
| Merged cells 100% 結構正確 | ⚪ 待 §1.6 |
| 完整 TypeScript 型別（無 any） | 🟢 本批達成 |
| Vitest unit test > 80 個 case | 🟡 目前 78（含 integration） |

## 負面結果 / 待解（紀律 #4）

1. **欄寬 8.43→59px vs Excel 常見 64px**：兩者差異源於「stored width 屬性」≠「displayed 8.43 字元」。
   本實作忠於 stored width 反算式（parser 讀到的就是 stored 值）。待 §2.1 StyleResolver + 實檔 col width
   比對時再校準 MDW（不同預設字型 MDW 不同）。標為 hypothesis，非 bug。
2. **fast-xml-parser 單/多節點型別不一致**：以 `toArray` helper 統一；若日後遇 namespace prefix
   （如 `<x:Relationship>`）需確認 parser 設定（目前 .rels/Content_Types 無 prefix，OK）。

## 下一步（Sprint 3）

§1.3 WorkbookParser（`xl/workbook.xml` → sheets/definedNames/workbookView）+ §1.4 SharedStringsParser。
依賴本 sprint 的 PackageReader.getPartText + getRels 取 worksheet 對應。
