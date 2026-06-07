# Sprint 5 — StylesParser（Phase 1 §1.5，★ 內容最大）

**日期**：2026-06-07
**Phase**：1（OOXML SpreadsheetML Parser）
**對齊**：規劃書 §1.5 Styles

---

## Root cause（開工前假設）

§1.6 已能提取 cell value 達 98.53%，唯一缺口是日期序號未轉日期字串（1.47%）。要補這缺口（§2.3）
必須先有 numFmt 資料——而 numFmt 在 `xl/styles.xml`。同時 Phase 2 全部樣式還原（字型/填色/邊框/對齊）
都以 styles.xml 為資料源。假設：完整解析 styles.xml 各池 + cellXfs 索引，即可同時餵養 §2.3 與 Phase 2。

紀律 #18 對齊：本 sprint 範圍嚴守 §1.5「解析」。把 xf 串接攤平成 ResolvedStyle 是 §2.1 StyleResolver，
日期序號→字串是 §2.3 NumberFormatCompiler，皆不在本 sprint。

## 修法（實際做的事）

### `color.ts`
`Color`（rgb / theme+tint / indexed / auto 四種互斥來源）+ `parseColor`。只保真擷取，
theme/tint/indexed → 具體 RGB 是 §2.2 ThemeResolver 的工作。

### `styles_parser.ts`（§1.5）
- `StylesParser.parse(xml)` → `ParsedStyles`：
  - `customNumFmts`（id≥164 → formatCode）
  - `fonts`（name/size/bold/italic/underline/strike/color/family/charset/vertAlign）
  - `fills`（patternType/fgColor/bgColor）
  - `borders`（left/right/top/bottom/diagonal × style+color、diagonalUp/Down）
  - `cellXfs` / `cellStyleXfs`（numFmtId/fontId/fillId/borderId/xfId + 5 個 apply 旗標 + alignment）
  - `dxfs`（CF differential format：font/fill/border/numFmt）
- `numberFormatCode(styles, id)`：自訂優先、否則**內建格式表**（ECMA-376 §18.8.30 常用 0-49）
- `isDateFormatCode(code)`：移除 `[...]`/`"..."`/`\x` 跳脫後檢 y/m/d/h/s token
- `isDateNumberFormat(styles, id)`：內建日期 id（14-22/45-47）∪ 自訂日期 code → 供 §2.3

## 三層 SOP 結果

- **L1 vitest**：**239 passed**（unit 100 + integration 139）
  - `styles_parser.test.ts`（24）：合成涵蓋自訂 numFmt/粗體紅字 font/theme+tint+indexed fill/
    thin+auto border/cellXf apply 旗標+alignment/dxf；內建表查詢；isDateFormatCode 與 isDateNumberFormat
    （內建 14、自訂 176 年月日 → true；179 #,##0.00、估驗附表字面 → false）
    + 真實估驗差異表（4 自訂 numFmt、12 font/2 fill/9 border/34 cellXf）
  - `styles_corpus.test.ts`（48）：**全 48 fixture** 每 cellXf 的 font/fill/border/xfId 索引在界內、
    每 cell.styleIndex 指向有效 cellXf（跨方言結構完整性）
- **L2 visual regression**：N/A（渲染層 Phase 2+）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（13.1s）

## §2.3 就緒驗證（核心成果）

對 §1.6 量到的 **10,322 個日期缺口 cell**，逐格用 `isDateNumberFormat(cell.styleIndex → cellXf.numFmtId)`
判定：**100%（10322/10322）正確偵測為日期格式**。

→ 證明 StylesParser 正確、且 §2.3 補日期缺口的路徑完全打通：每個日期 cell 都能識別，
§2.3 只需把序號 + formatCode → 日期字串。預期 §2.3 完成後提取率 98.53% → ~100%。

## 對齊 Phase 1 Exit Criteria

| Exit 條件 | 狀態 |
|---|---|
| Parser 對 50 份 fixture 全部無 error | 🟢（4 corpus × 48 全綠） |
| Cell values 提取率 > 95% | 🟢 98.53%（§2.3 後 ~100%） |
| Merged cells 100% 結構正確 | 🟢 |
| 完整 TypeScript 型別（無 any） | 🟢 維持 |
| Vitest unit test > 80 個 case | 🟢 239 |

## 負面結果 / 待解（紀律 #4）

1. **內建 numFmt 表為部分**：只收 ECMA-376 常用 0-49 子集，未含 5-8（locale 貨幣）、23-36（East Asian
   日期）、50-58（東亞曆）。**事實**：corpus 日期幾乎全走自訂 id（≥164，如 176/177 年月日），故 100% 偵測；
   但若日後遇 builtin 27-36 東亞日期需補表。標為 hypothesis，非當前 bug。
2. **gradient fill 未解**：fills 只處理 patternFill；gradientFill（漸層）此 sprint 略過（ChienYi 未見）。
3. **indexed color 56 色 palette 未展開**：parseColor 只記 indexed 值，→ RGB 待 §2.2。

## 下一步（Sprint 6）

兩條路擇一：
- **§2.3 NumberFormatCompiler**（最小：先做日期序號→日期字串）→ 立即把提取率推到 ~100%、補完 1.47% 缺口
- **§1.7 CFParser**（條件格式 rules：cellIs/colorScale/dataBar/iconSet，dxfs 已就緒）→ 續推 Phase 1 廣度

建議先 §2.3 日期最小版（槓桿最高、直接收掉提取率缺口、且 isDateNumberFormat 已 100% 就緒）。
