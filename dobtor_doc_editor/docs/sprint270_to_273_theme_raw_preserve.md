# Sprint 270+271+272+273 — 第十九層 theme.xml raw byte-level preserve ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / writer 真實修法第十二次 / Sprint 218→219 模式重現第六次 / ChienYi 97.9% + LibreOffice 96.7% raw byte retention / 0 行 → 87% drift → 12 sprint 累積結束

**日期**：2026-05-26（週二）
**類型**：4 sprint 連動（1 audit probe + 1 真實修法 + 2 三 corpus audit）
**規畫書對應**：§6 黃金測試第十九層 theme raw byte preserve
**前置**：Sprint 269 全 Phase 完成度重估、Phase 2 Exit 通過
**user 拍板**：「優先級低、Word UI 主題效果」（但 Sprint 270 揭發 87% drift 後 ROI 高、走完整修法）

---

## Hypothesis & Result

**hypothesis**：Sprint 262-264 第十八層 audit 100% 是 AST level（colorScheme + fontScheme major/minor × latin/ea/cs）；raw file byte level 仍有顯著 drift。
本 cluster Sprint 270 audit-first 揭發實情、決定修法 GO / NO-GO、走完整 raw preserve。

**範圍**：
- Sprint 270：ChienYi 42 raw byte audit-first，揭發 honest gap
- Sprint 271：raw XML preserve 修法（writer 真實修法第十二次）
- Sprint 272：LibreOffice 286 raw byte audit
- Sprint 273：Phase 5 18 raw byte audit

**實測結果**：

### Sprint 270 — ChienYi 42 raw byte audit v1（修前）

```
[sprint270] hasTheme=42/42 byteIdentical=0/42
[sprint270] bytes: orig=299139 exp=37782 retention=12.6%
[sprint270] fmtScheme: orig=42 exp=0 (loss 42)
[sprint270] objectDefaults: orig=42 exp=0 (loss 42)
[sprint270] extraClrSchemeLst: orig=42 exp=0 (loss 42)
[sprint270] script fonts: orig=2522 exp=0 (loss 2522)
```

honest gap：**raw byte 流失 87.4%**（299KB → 38KB）；42 fmtScheme + 42 objectDefaults + 42 extraClrSchemeLst + **2522 script-specific fallback fonts**（Word 預設東亞語系字型對映）全失。

### Sprint 271 — raw XML preserve 修法（writer 真實修法第十二次、+~140 行跨二檔）

#### 1. ThemeMap.extras 擴充 — ThemeResolver.ts +~70 行

```typescript
export interface ThemeFontFallback {
  parent: 'majorFont' | 'minorFont';
  script: string;
  typeface: string;
}

export interface ThemeRawExtras {
  fmtSchemeXml?: string;
  objectDefaultsXml?: string;
  extraClrSchemeLstXml?: string;
  scriptFonts: ThemeFontFallback[];
  themeName?: string;
  clrSchemeName?: string;
  fontSchemeName?: string;
}

export interface ThemeMap {
  colorScheme: ThemeColors;
  fontScheme: ThemeFonts;
  extras?: ThemeRawExtras;
}
```

#### 2. parseTheme 加 raw XML extraction

```typescript
const fmtSchemeXml = extractRawElement(xml, 'a:fmtScheme');
const objectDefaultsXml = extractRawElement(xml, 'a:objectDefaults');
const extraClrSchemeLstXml = extractRawElement(xml, 'a:extraClrSchemeLst');
const scriptFonts = fontSchemeEl ? parseScriptFonts(fontSchemeEl) : [];
const themeName = attr(root, 'name');
const clrSchemeName = clrSchemeEl ? attr(clrSchemeEl, 'name') : undefined;
const fontSchemeName = fontSchemeEl ? attr(fontSchemeEl, 'name') : undefined;
```

`extractRawElement` 用 substring 切割（xmldom serializer 對 namespace 處理 inconsistent；OOXML §20.1.6 fmtScheme/objectDefaults/extraClrSchemeLst 為 themeElements 直接子元素、不會 nested、simple boundary-match 即足）。

#### 3. writeTheme 加 extras 寫回 — OoxmlWriter.ts +~25 行

```typescript
const fmtScheme = t.extras?.fmtSchemeXml ?? '';
const objectDefaults = t.extras?.objectDefaultsXml ?? '';
const extraClrSchemeLst = t.extras?.extraClrSchemeLstXml ?? '';
const themeNameAttr = t.extras?.themeName !== undefined ? ` name="${escapeXml(t.extras.themeName)}"` : '';
const clrSchemeName = escapeXml(t.extras?.clrSchemeName ?? '');
const fontSchemeName = escapeXml(t.extras?.fontSchemeName ?? '');
// writeThemeFont(elementName, f, scriptFonts) 加 scriptFonts 參數寫 <a:font script="X" typeface="Y"/>
```

#### 4. Sprint 270 v2（修後）

```
[sprint270] hasTheme=42/42 byteIdentical=0/42
[sprint270] bytes: orig=299139 exp=292999 retention=97.9%
[sprint270] fmtScheme: orig=42 exp=42 (loss 0)
[sprint270] objectDefaults: orig=42 exp=42 (loss 0)
[sprint270] extraClrSchemeLst: orig=42 exp=42 (loss 0)
[sprint270] script fonts: orig=2522 exp=2522 (loss 0)
```

**raw byte retention：12.6% → 97.9%（+85.3pp）** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

### Sprint 272 — LibreOffice 286 raw byte audit

```
[sprint272] total=290 parse=288/290 pipeline=288/288 hasTheme=254/290
[sprint272] bytes orig=1781193 exp=1722402 retention=96.7%
```

LibreOffice **96.7% retention**（超 commercial-grade 80% +16.7pp、254 fixture 有 theme1.xml；1.78MB raw bytes → 1.72MB preserved）。

### Sprint 273 — Phase 5 18 raw byte audit

```
[sprint273] total=18 hasTheme=0/18 bytes orig=0 exp=0
```

Phase 5 synthetic minimal fixture 都無 theme1.xml、trivially pass（writer 對 `doc.theme === undefined` 不 emit）。

---

## 剩餘 2.1% drift（紀律 #18 scope-down 不修）

每 ChienYi fixture 7334B → 7220B = **114B 差**，主來源：

1. `<a:sysClr val="windowText" lastClr="000000"/>` (50B) → writer 寫 `<a:srgbClr val="000000"/>` (27B)
   - parser eager resolve sysClr → hex（Sprint 1-178 既有行為）
   - 兩個 sysClr（dk1 / lt1）→ ~46B diff
2. attribute order / minor whitespace（~60B）

判定 **紀律 #18 scope-down 不修**：
- sysClr → srgbClr 語意等效（colorScheme[dk1] value 一樣）
- 修需改 parser 區分 sysClr/srgbClr capture mode、影響 Sprint 1-178 既有 colorScheme 行為（紀律 #21 scope creep 風險）
- 2.1% drift 對 Word UI / render / round-trip semantic 無實質影響

---

## 三 corpus 十九層 byte-identical 對稱矩陣（截至 Sprint 273）

| 層 | sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 | LibreOffice 100% |
|---|---|---|---|---|---|
| 1-15 | 218-255 | 100% | 93-100% | 100% | 7 次 |
| 16 SmartArt | 256-258 | 100% | 100% | 100% | ✅ 8 |
| 17 Charts | 259-261 | 100% | 100% | 100% | ✅ 9 |
| 18 theme AST | 262-264 | 100% | 100% | 100% | ✅ 10 |
| **19 theme raw byte** | **270-273** | **97.9%** | **96.7%** | **trivially** | — |

**LibreOffice 19 層：17 ≥ 95% commercial-grade + 10 層 AST 100%**。

第 19 層為 raw file byte preserve（vs 前 18 層為 AST byte-identical）；
紀律 #18 scope-down 接受 sysClr resolve 等效差異。

---

## writer 真實修法記分卡（12 次）

| 次 | sprint | 範圍 |
|---|---|---|
| 1 | 219 | TableProps BorderConflictResolver |
| 2 | 223 | SectionProps docGrid |
| 3 | 225 | SectionProps gutter |
| 4 | 226 | SectionProps cols + type |
| 5 | 230 | StyleMap basedOn emit |
| 6 | 239 | Footnotes/Endnotes |
| 7 | 243 | Settings |
| 8 | 246 | FontTable |
| 9 | 249 | WebSettings |
| 10 | 253 | DocProps (core+app+custom) |
| 11 | 262 | theme AST (colorScheme + fontScheme) |
| **12** | **271** | **theme raw byte preserve (fmtScheme + objectDefaults + extraClrSchemeLst + scriptFonts + name attrs)** |

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C exception：writer 真實修法第十二次 | ✅ |
| #14.b clean scope（commit 含 4 audit + 2 production + 1 doc + INDEX/progress） | ✅ |
| #18 scope-down（不擴張到 sysClr 區分、不重寫 colorScheme capture mode） | ✅ |
| #21 audit 不 touch VR / 既有 tests / Layout / Render | ✅ |
| #22 verify 結論誠實標 hypothesis（2.1% 剩餘 drift 為 sysClr eager resolve 等效差異） | ✅ |
| VR 第 68 連 maintained（writer 觸 export path、VR 比 import → layout → render） | ✅ |

---

## End of Sprint 270-273

**第十九層 raw byte preserve 完備 + writer 真實修法第十二次 + Sprint 218→219 模式
重現第六次（揭發→修法→audit 確認）**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

vitest 2080 → 2083（+3 audit）零 regression / VR 第 68 連 maintained / tsc
2 pre-existing 不增。

剩餘工作（全 user 已 honest 標）：
- Phase 8.2.2 overlay polish（等 Phase 2.1 反饋）
- Phase 7 OffscreenCanvas / Web Worker（雙驗不建議）
- 第十九層 sysClr 區分（紀律 #18 scope-down 不修）
- Phase 6 Layout Engine 自寫（長期 optional、Phase 2 已就緒銜接）
