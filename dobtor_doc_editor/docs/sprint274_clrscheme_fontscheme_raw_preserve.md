# Sprint 274 — clrScheme + fontScheme raw XML preserve ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / writer 真實修法第十三次 / ChienYi 99.6% + LibreOffice 98.6% raw byte retention（近完全 byte-identical）

**日期**：2026-05-26（週二）
**類型**：1 sprint 真實修法（Sprint 218→219 模式重現第七次、Sprint 271 第十九層延伸）
**規畫書對應**：§6 黃金測試第十九層 theme raw byte preserve 精修
**前置**：Sprint 270-273 第十九層 raw byte preserve（97.9% / 96.7%）

---

## Hypothesis & Result

**hypothesis**：Sprint 270-273 第十九層 raw byte 97.9% 剩 2.1% drift 為
sysClr → srgbClr eager resolve（Sprint 1-178 既有 colorScheme.dk1/lt1 雙重
渲染）+ attr order minor whitespace；解法 = 同時 capture clrScheme + fontScheme
完整 raw XML、writer 端優先用 raw、保 Sprint 262 結構化 capture 並存供
eager resolve。

**範圍**：
- ThemeRawExtras 加 `clrSchemeRawXml?` + `fontSchemeRawXml?`
- parseTheme 加 `extractRawElement(xml, 'a:clrScheme')` + `extractRawElement(xml, 'a:fontScheme')`
- OoxmlWriter.writeTheme refactor：raw XML 優先、reconstructed path 作為 fallback
- 抽 `buildClrSchemeXml` / `buildFontSchemeXml` 二個 helper 函式維持 Sprint 262
  reconstructed 路徑（為 DEFAULT_THEME_MAP / 缺檔 / 程式化合成 docx 場景保留）

**實測結果**：

| Sprint | corpus | retention 修前 | retention 修後 | Δ |
|---|---|---|---|---|
| 270 | ChienYi 42 | 97.9% | **99.6%** | **+1.7pp** |
| 272 | LibreOffice 254 hasTheme | 96.7% | **98.6%** | **+1.9pp** |
| 273 | Phase 5 18 | trivially | trivially | — |

每 ChienYi fixture：7334B → **7332B（差僅 2B）**、近完全 byte-identical。
每 LibreOffice 平均：4400B 級別、retention 98.6% 達極致 byte preserve。

---

## 為何 99.6% 不是 100%

剩 0.4% drift（每 fixture ~2B）主來源：
- XML declaration 細微差異：原 `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`、writer 同樣輸出但可能 attr 順序 / quote style 不同
- root element xmlns attr 序 / whitespace

紀律 #18 scope-down：不修。99.6% 對 round-trip semantic / Word UI 已無實質差異；
修需重寫 xmlDecl + xmlns serialization、scope creep。

---

## 修法 +~60 行跨二檔

### ThemeResolver.ts +~12 行

```typescript
export interface ThemeRawExtras {
  // ... 既有
  clrSchemeRawXml?: string;   // Sprint 274
  fontSchemeRawXml?: string;  // Sprint 274
}

// parseTheme 內：
const clrSchemeRawXml = extractRawElement(xml, 'a:clrScheme');
const fontSchemeRawXml = extractRawElement(xml, 'a:fontScheme');
if (clrSchemeRawXml !== undefined) extras.clrSchemeRawXml = clrSchemeRawXml;
if (fontSchemeRawXml !== undefined) extras.fontSchemeRawXml = fontSchemeRawXml;
```

### OoxmlWriter.ts refactor +~45 行

```typescript
function writeTheme(t: ThemeMap): string {
  // Sprint 274：rawXml 優先、reconstructed 作 fallback
  const clrSchemeXml = t.extras?.clrSchemeRawXml ?? buildClrSchemeXml(t);
  const fontSchemeXml = t.extras?.fontSchemeRawXml ?? buildFontSchemeXml(t);
  // ... 其餘同 Sprint 271
}

function buildClrSchemeXml(t: ThemeMap): string { /* 12 色 srgbClr 重建 */ }
function buildFontSchemeXml(t: ThemeMap): string { /* major/minor + scriptFonts 重建 */ }
```

### 共存策略

- parser 端：Sprint 262 ThemeColors / ThemeFonts 結構化 capture 仍走、供 eager
  resolve themeColor → hex 寫進 RunProps.color（既有行為不變）
- writer 端：raw XML 優先輸出（preserve sysClr / 原始 attr order）、reconstructed
  path 作為 fallback（DEFAULT_THEME_MAP / 程式化合成 docx 場景）

---

## 三 corpus 十九層 byte-identical 對稱矩陣（截至 Sprint 274）

| 層 | sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 |
|---|---|---|---|---|
| 1-18 AST | 218-264 | 100% | 93-100% | 100% |
| 19 raw byte | 270-274 | **99.6%** | **98.6%** | trivially |

---

## writer 真實修法記分卡（13 次）

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
| 12 | 271 | theme raw byte preserve (fmt+obj+extra+scriptFonts+name) |
| **13** | **274** | **clrScheme + fontScheme raw XML preserve（sysClr 區分、retention 97.9→99.6%）** |

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C exception：writer 真實修法第十三次 | ✅ |
| #14.b clean scope（無新 audit test、只擴展現有 Sprint 270/272 assertion） | ✅ |
| #18 scope-down（不修 xmlDecl / xmlns 細微差異、99.6% 已極致） | ✅ |
| #21 audit 不 touch VR / 既有 tests / Layout / Render | ✅ |
| #22 verify 結論誠實標 hypothesis（0.4% 剩餘 drift 為 xmlDecl normalize） | ✅ |
| VR 第 68 連 maintained | ✅ |

---

## End of Sprint 274

**clrScheme + fontScheme raw XML preserve + writer 真實修法第十三次 +
Sprint 270-273 cluster 精修收口**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

vitest 2083 維持（無新 audit、reuse Sprint 270/272 既有 audit、修法後重跑、零 regression）
/ VR 第 68 連 maintained / tsc 2 pre-existing error 不增。

剩餘工作（全 user honest 標）：
- Phase 8.2.2 overlay polish（等 Phase 2.1 反饋）
- Phase 7 OffscreenCanvas / Web Worker（雙驗不建議）
- 第十九層 xmlDecl / xmlns normalize（紀律 #18 scope-down 不修、99.6% 已極致）
- Phase 6 Layout Engine 自寫（長期 optional、Phase 2 已就緒銜接）
