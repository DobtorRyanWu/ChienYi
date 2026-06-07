# Sprint 8 — ThemeParser + ThemeResolver（§1.9 + §2.2）

**日期**：2026-06-07
**Phase**：1 §1.9（ThemeParser）+ Phase 2 §2.2（ThemeResolver）
**對齊**：規劃書 §1.9 Theme、§2.2 ThemeResolver

---

## Root cause（開工前假設）

§2.1 StyleResolver 攤平出 ResolvedStyle，但 font.color / fill.fgColor / border.color 仍是
**抽象 `Color`**（theme/indexed/tint/rgb），尚非具體 RGB。Phase 4.5 餵 o-spreadsheet、Phase 4 VR 像素比對
都需要具體色。假設：解析 theme1.xml clrScheme + 套 indexed palette + HSL tint 即可把任何 Color → 6-hex。

紀律 #18：§1.9 只解析 theme、§2.2 只做 color → RGB。

## 修法（實際做的事）

### `theme_parser.ts`（§1.9）
- `ThemeParser.parse(xml)` → `ParsedTheme`：clrScheme 12 色（dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink）
  + fontScheme（major/minor 的 latin/ea/cs）
- 色值：srgbClr 取 val、sysClr 取 lastClr；缺值以 Office 預設 scheme fallback
- `ThemeParser.default()`：無 theme part 時的 Office 預設主題
- 新增 `xml_util.parseXmlNoNs`（removeNSPrefix）處理 theme1.xml 的 `a:` 前綴（不影響主 parser 的 r:id）

### `theme_resolver.ts`（§2.2）
- `ThemeResolver(theme).resolveColor(color)` → 6-hex RGB 或 undefined（系統色）
  - **theme 索引映射含 0/1、2/3 互換**：`[lt1,dk1,lt2,dk2,accent1..6,hlink,folHlink]`
    （Excel：theme 0=Background1=lt1、1=Text1=dk1）
  - indexed：舊版 56 色 palette（0-63）；64/65 系統色 → undefined
  - rgb：ARGB 8-hex 去 alpha → 6-hex
  - auto → undefined（系統相關，由 caller 決定黑/白）
- **tint（HSL luminance）** port 自 dobtor_doc_editor Sprint 130：
  - tint>0 變亮 `L'=L+(1-L)·tint`、tint<0 變暗 `L'=L·(1+tint)`，只調 L 保留 hue/sat

## 三層 SOP 結果

- **L1 vitest**：**374 passed**（unit 139 + integration 235）
  - `theme_parser.test.ts`（5）：合成 a:-前綴 clrScheme（sysClr lastClr / srgbClr val）+ fontScheme；
    default fallback；**真實 fixture theme1.xml**（標準 Office 色）
  - `theme_resolver.test.ts`（14）：theme 索引映射（**0=lt1/1=dk1、2/3 互換、4-9=accent1-6**）、
    **accent4 + tint 0.8 = FFF2CC（Excel「Gold, Lighter 80%」對標）**、變亮/變暗方向、
    黑 tint1→白、白 tint-1→黑、ARGB 去 alpha、indexed palette、64/65→undefined、auto→undefined
  - `theme_resolver_corpus.test.ts`（48）：**全 48 fixture** styles 內所有 fill/font/border 色 →
    合法 6-hex 或 undefined、不丟錯
- **L2 visual regression**：N/A（VR pipeline 待 Phase 4 接入）
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過（12.9s）

## 關鍵驗證

1. **tint 對標 Excel**：accent4(FFC000) + tint 0.7999 → **FFF2CC**，與 Excel 內建「Gold, Accent 4,
   Lighter 80%」完全一致 → 證明 HSL tint 演算法與 theme 索引映射正確。
2. **theme 0/1 互換**：實作 `[lt1,dk1,...]`（非 clrScheme XML 的 [dk1,lt1,...] 順序），符合 Excel
   color picker 的 Background1/Text1 慣例。

## 負面結果 / 待解（紀律 #4）

1. **純黑白文件 resolved=0 屬正常**：5 個 ChienYi 檔全用 auto/系統色（字型無 color、邊框 auto、填色 none），
   解析後皆 undefined。**事實**：營造文書多為黑白，非 resolver 失效。corpus 斷言已改為「不強制有色」。
2. **indexed 64/65 回 undefined**：系統前/背景色 context 相關，本層不臆測（由渲染層決定黑/白）。
3. **無像素級驗證**：tint 正確性以 FFF2CC 對標 Excel 值間接驗證；完整像素比對待 Phase 4 VR pipeline。

## 對齊 Phase 2 進度

| 項目 | 狀態 |
|---|---|
| §2.1 StyleResolver（cascade 攤平） | 🟢（Sprint 7） |
| §2.2 ThemeResolver（color → RGB） | 🟢 本 sprint |
| §2.3 NumberFormat（日期最小版） | 🟢（Sprint 6） |
| §2.4+ 完整 number format 渲染 / text metrics | ⚪ 待續 |

→ ResolvedStyle + ThemeResolver 組合後，cell 樣式可完全具體化（font/fill/border 皆具體 RGB），
具備餵 o-spreadsheet（Phase 4.5）或 VR 像素比對（Phase 4）的條件。

## 下一步（Sprint 9）

可選：
- **§1.7 CFParser**（條件格式 rules：cellIs/expression/colorScale/dataBar/iconSet；dxfs + ThemeResolver 已就緒）
- **整合 StyleResolver + ThemeResolver → ConcreteStyle**（font/fill/border 全 RGB 的單一物件，Phase 4.5 對接層）
- **§2.3 完整 number format**（千分位/貨幣/百分比/時間 token 渲染）
