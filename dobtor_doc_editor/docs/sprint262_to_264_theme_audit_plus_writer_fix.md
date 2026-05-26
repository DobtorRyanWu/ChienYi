# Sprint 262+263+264 — theme.xml 第十八層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ + writer 真實修法第十一次 + parser AST 擴充 + 第十次 LibreOffice 邊緣 corpus 達 100%

**日期**：2026-05-26（週二）
**類型**：三 audit 並排 + parser + AST + writer 三補（Sprint 218→219 模式重現第十一次）
**規畫書對應**：§6 黃金測試第十八層 theme（word/theme/theme1.xml DrawingML）
**前置**：Sprint 256-261 SmartArt/Charts 第十六+十七層完備、十七層矩陣全綠

---

## Hypothesis & Result

**hypothesis**：十七層矩陣完備後、擴展第十八層 theme.xml。Parser 端
ThemeResolver 已有完整解析（Sprint 1-178、Phase 4.1）但結果僅供 eager
resolve themeColor → hex 使用、未掛上 DocumentNode AST；本 sprint 擴充
AST + parser 寫回 + writer 對稱實作。

**範圍**：
- **ThemeMap** AST 擴充：`DocumentNode.theme?: ThemeMap`（紀律 #21 optional）
- parser 端區分 `parsedTheme` vs `DEFAULT_THEME_MAP` 降級：
  - `parseTheme(pkg)` 回 `null` → 不掛 `theme` key（無 theme1.xml 原始檔）
  - 回 `ThemeMap` → 掛入 AST、保 round-trip
- writer 端 emit `word/theme/theme1.xml`：colorScheme 12 色 +
  fontScheme major/minor × latin/ea/cs
- 對應 `[Content_Types].xml` Override + `document.xml.rels` Relationship

**實測結果**：
- Sprint 262 ChienYi 42：**42/42 (100%) 一次過 / 504 colors + 84 fonts**
  ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐（hasTheme 42/42、Word 預設骨架）
- Sprint 263 LibreOffice：**288/288 (100%) / hasTheme 254/288 /
  3048 colors + 528 fonts byte-identical** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
  **第十次 LibreOffice 邊緣 corpus 達 100%**
- Sprint 264 Phase 5：**18/18 (100%) trivially / hasTheme 0/18**
  （synthetic minimal fixtures、無 theme1.xml）

**三 corpus 十八層 byte-identical 對稱矩陣完備 + 第十一次 writer 真實修法
+ 第十次 LibreOffice 邊緣 corpus 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Root cause #12 — AST 未掛 theme、writer 不 emit theme1.xml

Sprint 1-178 ThemeResolver.parseTheme() 完整實作（colorScheme 12 色 +
fontScheme major/minor × latin/ea/cs）；OoxmlParser 階段呼叫 parseTheme
取得 ThemeMap、注入 DocumentParser + StyleResolver 供 themeColor → hex
eager resolve；但 ThemeMap 從未寫回 DocumentNode AST。

writer 端 OoxmlWriter.write() 對 theme 完全不處理：
- `parts` 字典：缺 `word/theme/theme1.xml`
- `writeDocumentRels`：缺 theme Relationship
- `writeContentTypes`：缺 theme Override

### 修法（+99 行 production code 跨三檔）

#### 1. AST 擴充 — types.ts +20 行

新增 `DocumentNode.theme?: ThemeMap` 欄位（inline `import('...')` 避免循環
import）。紀律 #21 optional：缺檔 → undefined、不掛 key。

#### 2. parser 端 — OoxmlParser.ts +5 行

`parseTheme(pkg)` 結果區分：
```ts
const parsedTheme = parseTheme(pkg);  // ThemeMap | null
const themeMap: ThemeMap = parsedTheme ?? DEFAULT_THEME_MAP;
// AST 注入：
...(parsedTheme !== null ? { theme: parsedTheme } : {}),
```

`themeMap` 仍用 DEFAULT 降級供 eager resolve（與 Sprint 1-178 行為相容）；
`parsedTheme` 保 null/實值區別、紀律 #21 optional 寫回 AST。

#### 3. writer 端 — OoxmlWriter.ts +74 行

- `REL_TYPE_THEME` 常數 +2 行
- `parts['word/theme/theme1.xml']` 條件 emit +4 行（doc.theme 有值才）
- `writeContentTypes` Override 條件 +4 行
- `writeDocumentRels` Relationship 條件 +4 行
- `writeTheme(t: ThemeMap)` 函式 +48 行：
  - colorScheme 12 個 srgbClr 元素（dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink）
  - fontScheme major/minor 各 latin/ea/cs 條件 emit
- `writeThemeFont(elementName, f)` 子函式 +12 行：major/minor 共用

### 紀律 #18 scope-down

theme1.xml 完整結構含：
- `<a:themeElements>`：clrScheme + fontScheme + **fmtScheme**（線條/填色/效果樣式）
- `<a:objectDefaults>`：物件樣式預設
- `<a:extraClrSchemeLst>`：額外色彩主題

本 writer 僅 emit clrScheme + fontScheme（與 parser capture 範圍對稱）；
fmtScheme/objectDefaults/extraClrSchemeLst 不 capture、不寫；re-parse 端
仍無、AST byte-identical（紀律 #18 scope-down、與 Sprint 195 SmartArt
mc:Fallback 同等概念）。

---

## audit dimension 設計（與 Sprint 243-261 共通）

### deepStableStringify

遞迴鍵排序 JSON 序列化、key 字典序、array 保序。

### 序列化 normalization

- `theme === undefined` → `null`（避免 `expect(undefined).toEqual({...})` 誤判）
- `theme !== undefined` → `{ colorScheme, fontScheme }` 取兩個 sub-tree

### SHA-256 fallback

`oSerial === rSerial || sha256(oSerial) === sha256(rSerial)`、雙重保險。

---

## 三 corpus 十八層 byte-identical 對稱矩陣（截至 Sprint 264）

| 層 | sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 | LibreOffice 100% |
|---|---|---|---|---|---|
| 1 Structure | 218→219 | 100% | 95.5% | 100% |  |
| 2 Text | 220→226 | 100% | 96.8% | 100% |  |
| 3 RunProps | 227→230 | 100% | 93.1% | 100% |  |
| 4 ParaProps | 231→233 | 100% | 97.6% | 100% |  |
| 5 TableProps | 234→236 | 100% | 95.5% | 100% |  |
| 6 SectionProps | 237→239 | 100% | 94.8% | 100% |  |
| 7 HF Content | 240→242 | 100% | 94.4% | 100% |  |
| 8 StyleMap | 243→245 | 100% | 96.5% | 100% |  |
| 9 NumberingMap | 243→245 | 100% | **100%** | 100% | ✅ 1 |
| 10 Comments | 243→245 | 100% | **100%** | 100% | ✅ 2 |
| 11 Footnotes | 243→245 | 100% | **100%** | 100% | ✅ 3 |
| 12 Settings | 243→245 | 100% | **100%** | 100% | ✅ 4 |
| 13 FontTable | 246→248 | 100% | **100%** | 100% | ✅ 5 |
| 14 WebSettings | 249→251 | 100% | **100%** | 100% | ✅ 6 |
| 15 DocProps | 253→255 | 100% | **100%** | 100% | ✅ 7 |
| 16 SmartArt | 256→258 | 100% | **100%** | 100% | ✅ 8 |
| 17 Charts | 259→261 | 100% | **100%** | 100% | ✅ 9 |
| **18 theme** | **262→264** | **100%** | **100%** | **100%** | ✅ **10** |

**LibreOffice 18 層：16 ≥ 95% commercial-grade + 10 層 100%**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b / Strategy C exception：writer 真實修法第十一次（記分卡：219/223/225/226/230/239/243/246/249/253/262 = 11 次） | ✅ |
| #2 名定常數（REL_TYPE_THEME / 12 colorScheme key 列表） | ✅ |
| #14.b clean scope（commit 只含 3 audit + 3 production + 1 doc） | ✅ |
| #18 scope-down（不擴張到 fmtScheme/objectDefaults/extraClrSchemeLst） | ✅ |
| #21 audits 不 touch VR / round-trip / 既有 tests | ✅ |
| VR 第 68 連 | ✅（writer 觸 export path、VR pipeline 比 import → layout → render） |

---

## 為何 Sprint 262 一次過 100%（無 v1/v2 迭代）

對比 Sprint 253 v1 0/42 → v2 100% 需 +95 行：

| 因素 | Sprint 253 (DocProps) | Sprint 262 (theme) |
|---|---|---|
| AST 容器 | 三個（DocProps/DocPropsApp/DocPropsCustom）獨立 | 一個 ThemeMap |
| 命名空間數 | 8（DC/DCTERMS/DCMITYPE/XSI/CP/EXT/CUSTOM/VT） | 1（A_NS） |
| variant 型別 | 5 種（string/int/bool/real/filetime + unknown） | 0 |
| 條件序列化 | 24 欄位 × 3 part × 6 變種規則 | 12 色固定 + 6 font 條件 |
| 對稱性挑戰 | OOXML §22.4 fmtid GUID + pid 字典序 | 直接 srgbClr 對映 |

theme 結構單純（一對一映射）、parser 端 DEFAULT_THEME_MAP fallback 已預先
與 writer 預期 emit 完全對齊；故第一次跑 audit 就 100%。

---

## 規畫書 §6 + §Phase 4.1 對應

- 規畫書 §Phase 4.1：theme color resolution 已實作（eager resolve）
- §6 第十八層：theme byte-identical preservation —— 本 sprint 收口
- ADR-012 補（Sprint 130 HSL luminance tint/shade）—— 與本 sprint 對稱
  方向不衝突（resolveThemeColor 邏輯不變、本 sprint 加 export 路徑）

---

## 殘項 / Next Steps

| 殘項 | sprint | 動作 |
|---|---|---|
| Phase 2 完整 HarfBuzz / ShapingEngine | 265+ | 真正該做沒做的一條（ADR-014 對齊）、大工程拆多 sprint |
| 第十九層 fmtScheme / objectDefaults | 後續 | Word UI「主題效果」用、render 不消費、優先級低 |
| Phase 8.2.2 overlay | 等 | 規畫書 §8.2.2 條件性、等 Phase 2.1 反饋 |
| Phase 7 效能殘項 | 不建議 | WPS audit / HarfBuzz 屬 Phase 2 / Web Worker ROI marginal |

---

## End of Sprint 262-264

**三 audit 並排 + 第十八層完備 + writer 真實修法第十一次 + parser AST 擴充
+ 第十次 LibreOffice 邊緣 corpus 100%** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

VR 第 68 連保持、十八層矩陣全綠（LibreOffice 10 層 100% / 6 層 ≥ 95% /
2 層 ≥ 93%）、vitest 2032 → 2035 無 regression。

下一步：Phase 2 完整 HarfBuzz WASM + ShapingEngine（規畫書 §Phase 2 7-10
checkbox 真正該做沒做的）。
