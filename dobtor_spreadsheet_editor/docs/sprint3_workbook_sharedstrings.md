# Sprint 3 — WorkbookParser + SharedStringsParser（Phase 1 §1.3-1.4）

**日期**：2026-06-07
**Phase**：1（OOXML SpreadsheetML Parser）
**對齊**：規劃書 §1.3 Workbook、§1.4 SharedStrings

---

## Root cause（開工前假設）

§1.1 PackageReader 已能取 part 與解 rels，但尚未有任何試算表語意層。Cell value 提取（Phase 1 Exit 的
核心指標）需要兩塊前置：
1. **Workbook 結構** — 知道有哪些 sheet、各 sheet 對應哪個 worksheet part（透過 r:id）、隱藏狀態、
   定義名稱（公式 compiler 需要）、refMode（A1/R1C1）。
2. **SharedStrings 池** — worksheet cell（t="s"）以索引引用字串，必須先建好字串陣列才能解 cell value。

假設：fast-xml-parser 足以解析 workbook.xml / sharedStrings.xml；rich text 的 run 結構需保留供 Phase 2。

## 修法（實際做的事）

### `xml_util.ts`（共用層）
抽出全 parser 共用的 fast-xml-parser 設定與 helper：`parseXml` / `toArray` / `attr` / `intAttr` /
`boolAttr` / `textOf` / `decodeOoxmlEscapes`。
- 關鍵設定：`parseTagValue:false`（"1.1.1" 不被當數字）、`trimValues:false`（保留 xml:space 空白）
- **package_reader.ts 一併重構**接 xml_util，刪除自帶 xmlParser/toArray（去重，15 個既有測試全綠驗證無回歸）

### `workbook_parser.ts`（§1.3）
- `WorkbookParser(pkg).parse()` → `ParsedWorkbook`：
  - `sheets[]`：name / sheetId / **r:id（帶命名空間前綴屬性，fast-xml-parser 存為 `@_r:id`）** /
    state（預設 visible、hidden、veryHidden）/ **target（r:id 經 workbook .rels 解析成實際 worksheet part）**
  - `definedNames[]`：name / localSheetId / hidden / formula（文字內容）/ **reserved（`_xlnm.` 前綴判定）**
  - `view`：activeTab / firstSheet（取第一個 bookView）
  - `calc`：refMode（A1/R1C1）/ iterate
- 便利方法：`worksheetParts()` / `sharedStringsPart()` / `stylesPart()` / `themePart()`（依 rel type 解析，供後續 sprint）

### `shared_strings_parser.ts`（§1.4）
- `SharedStringsParser.parse(xmlText)` → `SharedString[]`（索引 = sst 索引）
- 每個 si 攤平出 `text`（cell value 用）、保留 `runs`（rich text，Phase 2 套樣式）
- 涵蓋：純文字、空 `<t/>`、`xml:space="preserve"`、**`_xHHHH_` 控制字元解碼**、rich text 多 `<r>` run（rPr：bold/italic/underline/strike/size/color/font/family/charset/vertAlign）
- `_x005F_` 單次掃描正確還原字面底線（不誤吃後續）

## 三層 SOP 結果

- **L1 vitest**：**151 passed**（unit 54 + integration 97）
  - `workbook_parser.test.ts`（14）：合成 2-sheet package（含隱藏表、保留/全域定義名稱、R1C1、part 解析）
    + 真實**契約詳細表 16 sheet**（全 sheet target 實存、含 _xlnm 保留名）
  - `shared_strings_parser.test.ts`（11）：合成 6 si（純文字/空/preserve/`_x000D_`→CR/`_x005F_`字面/rich bold紅字）
    + 真實契約詳細表（**uniqueCount 3303 條**、索引0=工程處抬頭、含多 run rich text、**全池無殘留 `_xHHHH_`**）
  - `workbook_corpus.test.ts`（48）：**全 48 fixture** WorkbookParser 解析無 error、每 sheet→worksheet part 實存、
    sharedStrings 解析無未解碼 escape（跨 Excel/WPS/LibreOffice 方言驗證）
- **L2 visual regression**：N/A（渲染層 Phase 2+）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（13.1s）

## 對齊 Phase 1 Exit Criteria 進度

| Exit 條件 | 狀態 |
|---|---|
| Parser 對 50 份 fixture 全部無 error | 🟢 §1.1/1.3/1.4 層級達成（2 個 corpus × 48 全綠） |
| Cell values 提取率 > 95% | ⚪ 待 §1.6 WorksheetParser（sharedStrings 池已就緒） |
| Merged cells 100% 結構正確 | ⚪ 待 §1.6 |
| 完整 TypeScript 型別（無 any） | 🟢 維持 |
| Vitest unit test > 80 個 case | 🟢 達成（unit 54 + integration 97 = 151） |

## 負面結果 / 待解（紀律 #4）

1. **corpus activeTab 容錯**：部分檔 activeTab 指向已刪 sheet，故 corpus 只檢 `>=0` 不檢上界。
   標為 hypothesis：真實檔的 view 狀態未必自洽，渲染層需自行 clamp。
2. **rich text rPr 的 color 僅取 rgb**：theme/indexed color（`<color theme=.. tint=..>`）此 sprint 未解，
   待 §2.2 ThemeResolver。目前 ChienYi rich text 多為 `rgb="FFFF0000"` 直接色，影響小。
3. **defined name 公式未 parse**：formula 僅存原始文字（如 `'Sheet1'!$A$1`），結構化解析待 Phase 3 公式 compiler。

## 下一步（Sprint 4）

§1.5 StylesParser（`xl/styles.xml`：numFmts / fonts / fills / borders / cellXfs / dxfs）★ —
這是 Phase 2 樣式還原的資料來源，Phase 1 內容量最大的一塊（規劃書估 2 週）。
或先做 §1.6 WorksheetParser（cell value 提取，直接拉高「cell value 提取率」Exit 指標）。
