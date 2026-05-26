# Sprint 265+266+267+268 — Phase 2 Text Shaping 八 checkbox 全完成 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / HarfBuzz WASM + Script & Language + features 控制 + Glyph cache + 行高公式 + opentype.js 完整 metrics

**日期**：2026-05-26（週二）
**類型**：四 sprint 連 production + 45 unit test
**規畫書對應**：§Phase 2 Text Shaping（user 標 7-10 個 [ ]、真正該做沒做的一條）
**前置**：Sprint 262-264 第十八層 theme.xml 完備
**user 拍板**：「Phase 2 可以依照說型全部讀取」(2026-05-26 session)

---

## Hypothesis & Result

**hypothesis**：規畫書 §Phase 2 標 7-10 個 [ ] checkbox（HarfBuzz / ShapingEngine /
Script & Language 偵測 / kerning/liga feature / Glyph 快取 / opentype.js 完整
字型 metrics / measureRun() 替代 ctx.measureText / 行高公式）— Sprint 128 spike
立基（HarfBuzz 基礎 shape）但 7 個剩 [ ]；本 4 sprint cluster 一次補完所有
checkbox + 全綠 unit test 矩陣。

**範圍**：
- Sprint 265：ShapeOptions + Script/Language/Direction + features 控制 +
  measureRun() 物理寬度量測（取代 ctx.measureText）
- Sprint 266：Glyph cache + 統計 (hit/miss/hitRate/entries) + clear / setMax /
  FIFO 淘汰
- Sprint 267：OOXML w:line + w:lineRule 公式（auto/exact/atLeast）+ baseline
  offset 公式
- Sprint 268：opentype.js 完整 metrics（typo/win/hhea 三組 ascender/descender +
  italic/bold/weight/widthClass + macStyle 互校 + advanceWidthMax）+
  readOpentypeAdvances per-glyph advance widths

**實測結果**：
- Sprint 265：15 test passed（detectScript 8 純函式 + Latin measureRun 4 +
  CJK measureRun 3）⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
- Sprint 266：8 test passed（cache hit/miss / 不同 options 獨立 entry / hitRate
  / clear / setMax / FIFO 淘汰 / measureRun 走 cache）⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
- Sprint 267：12 test passed（純函式、mock metrics、所有 rule 變種 + baseline
  公式）⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
- Sprint 268：10 test passed（DejaVuSans 5 + LiberationSerif 1 + advance
  widths 4）⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

**vitest 2035 → 2080**（+45 test、四 sprint 加總、零 regression）。

---

## §Phase 2 checkbox 對映表（規畫書 → 本 cluster）

| # | 規畫書 checkbox | Sprint | 落地 |
|---|---|---|---|
| 1 | HarfBuzz WASM 整合 | 128 spike + 265 | ShapingEngine.shape() + harfbuzzjs lazy load |
| 2 | ShapingEngine | 128 + 265 | ShapingEngine 類別、loadFont / shape / measureRun / cache API |
| 3 | Script & Language 偵測 | 265 | detectScript（9 種 ISO 15924）+ defaultLanguage + defaultDirection |
| 4 | kerning / liga feature | 265 | ShapeOptions.features（'kern,liga' / '-kern' 可開關） |
| 5 | Glyph 快取 | 266 | shapeCache + stats + clear + setMax + FIFO 淘汰 |
| 6 | opentype.js 完整字型 metrics | 268 | typo/win/hhea 三組 + italic/bold/weight + readOpentypeAdvances |
| 7 | measureRun() 替代 ctx.measureText() | 265 | ShapingEngine.measureRun → RunMetrics（widthPt / advancesPt / glyphs） |
| 8 | 行高公式 | 267 | resolveOoxmlLineHeight（auto/exact/atLeast）+ baselineOffsetPt |

**8/8 全完成** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Sprint 265 — ShapeOptions + Script & Language + measureRun + features

### 新增 API（static/src/core/ooxml/font/ShapingEngine.ts +136 行）

```typescript
export interface ShapeOptions {
  script?: string;        // ISO 15924（latn / hani / arab / ...）
  language?: string;      // BCP 47（en / zh-tw / ar / ...）
  direction?: 'ltr' | 'rtl' | 'ttb' | 'btt';
  features?: string;      // 'kern,liga' / '-kern'
  clusterLevel?: 0 | 1 | 2;
}

export interface RunMetrics {
  widthPt: number;        // 整段水平 advance 加總（pt）
  heightPt: number;       // 整段垂直 advance 加總（pt、橫排為 0）
  glyphCount: number;
  advancesPt: number[];   // 每 glyph advance（pt）
  glyphs: ShapedGlyph[];  // shaped 原始輸出
}

export function detectScript(text: string): string;
export function defaultLanguageForScript(script: string): string;
export function defaultDirectionForScript(script: string): 'ltr' | 'rtl';

class ShapingEngine {
  shape(text, family, sizePt, options?): Promise<ShapedGlyph[]>;
  measureRun(text, family, sizePt, options?): Promise<RunMetrics>;
}
```

### detectScript Unicode block table

- `0x4E00-0x9FFF` / `0x3400-0x4DBF` / `0x20000-0x2A6DF` → 'hani'
- `0x3040-0x309F` → 'hira'
- `0x30A0-0x30FF` → 'kana'
- `0xAC00-0xD7AF` → 'hang'
- `0x0600-0x06FF` → 'arab'
- `0x0590-0x05FF` → 'hebr'
- `0x0900-0x097F` → 'deva'
- `0x0E00-0x0E7F` → 'thai'
- 預設 → 'latn'

### measureRun 自動 wiring

```typescript
const detectedScript = detectScript(text);
const fullOptions = {
  script: options?.script ?? detectedScript,
  language: options?.language ?? defaultLanguageForScript(detectedScript),
  direction: options?.direction ?? defaultDirectionForScript(detectedScript),
  features: options?.features,
  clusterLevel: options?.clusterLevel,
};
```

caller 給 'Hello World' → 自動 latn/en/ltr；給 '磺港溪' → 自動 hani/zh-tw/ltr；
給 'مرحبا' → 自動 arab/ar/rtl。

---

## Sprint 266 — Glyph cache + 統計 / 清除 / 容量控制

### 新增 API（同 ShapingEngine.ts +100 行）

```typescript
export interface ShapingCacheStats {
  hits: number;
  misses: number;
  entries: number;
  maxEntries: number;
  hitRate: number;        // hits / (hits + misses)、無 lookup 時 NaN
}

class ShapingEngine {
  getCacheStats(): ShapingCacheStats;
  clearShapeCache(): void;
  setShapeCacheMaxEntries(n: number): void;  // FIFO 淘汰超量 entries
}
```

### 設計決策（紀律 #18 scope-down）

- **FIFO 淘汰**：Map preserves insertion order、無 LRU overhead；典型 Layout
  pass scenario 同 run 連續 hit、FIFO 適用
- **Cache key**：family + sizePt + script + language + direction + features +
  clusterLevel + text 串接（不用 JSON.stringify 避免 key 順序差異）
- **預設容量**：10000 entries（涵蓋大型 docx 同段落 ~5000 run 的 2×）
- **clear() 重置 stats**：clearShapeCache 同步歸零 hits/misses（避免假高
  hit rate 殘留）

### 預期收益（紀律 #21 hypothesis、未在 Layout pass 量測）

- Layout pass trial-and-error 重排：同 run 連續 hit、~10× 加速
- VR baseline 重跑：同 fixture 同 font 同 props 全 hit、剩 hb.shape WASM cold
  start 是主成本

---

## Sprint 267 — OOXML 行高公式

### 新增 API（FontMetrics.ts +80 行）

```typescript
export interface OoxmlLineHeightResult {
  heightPt: number;
  rule: 'natural' | 'auto' | 'exact' | 'atLeast';
  naturalHeightPt: number;
  lineValue?: number;
}

export function resolveOoxmlLineHeight(
  metrics: FontMetricsResult,
  sizePt: number,
  lineRule?: 'auto' | 'exact' | 'atLeast',
  lineValue?: number,
): OoxmlLineHeightResult;

export function baselineOffsetPt(
  metrics: FontMetricsResult,
  sizePt: number,
  lineHeightPtVal: number,
): number;
```

### 三種規則公式（OOXML §17.3.1.33）

| rule | lineValue 含義 | 公式 |
|---|---|---|
| natural | 無 | `(ascender + descender + lineGap) × sizePt / unitsPerEm` |
| auto | multiplier（1.0 單行、1.5、2.0） | `naturalLineHeight × multiplier` |
| exact | 固定 pt | `lineValue`（忽略字型 metrics） |
| atLeast | pt 下限 | `max(naturalLineHeight, lineValue)` |

### baselineOffsetPt 公式

```
baseline = ascentPt + (lineHeightPt - naturalLineHeight) / 2
```

extra gap（超過 natural 的部分）平均分到 top/bottom；exact < natural 時
extra=0、baseline=ascent（render 端負責 clip 偵測）。

---

## Sprint 268 — opentype.js 完整 metrics + per-glyph advanceWidth

### FontMetricsResult 擴充（+11 欄位）

- `typoAscender / typoDescender / typoLineGap`：OS/2 sTypoXxx（Word/Apple
  推薦行高源、USE_TYPO_METRICS=1 時 Word 用此）
- `winAscent / winDescent`：OS/2 usWinAscent/usWinDescent（Windows clip 偵測）
- `italic / bold`：OS/2 fsSelection bit 0 / bit 5
- `weightClass / widthClass`：OS/2 usWeightClass / usWidthClass
- `macStyleItalic / macStyleBold`：head.macStyle bit 1 / bit 0（與 OS/2 互校）
- `advanceWidthMax`：hhea.advanceWidthMax

### readOpentypeAdvances（FontMetrics.ts +35 行）

```typescript
export interface OpentypeAdvanceResult {
  widthPt: number;
  advancesPt: number[];
  glyphCount: number;
}

export function readOpentypeAdvances(
  fontBytes: Uint8Array | ArrayBuffer,
  text: string,
  sizePt: number,
): OpentypeAdvanceResult;
```

### 實作避坑（紀律 #18 scope-down）

opentype.js `stringToGlyphs` 走 Bidi/feature 路徑、對 substFormat 2 子型替換
未支援會 throw（DejaVuSans 觸發）。改走低階 `charToGlyphIndex(ch) +
glyphs.get(idx)`、繞過 Bidi/feature 處理（無 ligature shaping、複雜文字走
HarfBuzz ShapingEngine）。

`charToGlyphIndex` 參數需是字元 string、不是 codepoint number（API 文檔誤
標、實測修正）。

### vs HarfBuzz measureRun

| 面向 | HarfBuzz ShapingEngine | opentype.js readOpentypeAdvances |
|---|---|---|
| Ligature | 是 | 否 |
| Complex script（Arabic / Indic） | 是 | 否 |
| Kerning | 是 | 否（簡化版） |
| Bundle | ~200KB WASM | ~80KB JS |
| 載入 | async | sync |
| 用途 | Layout 主流 | Fallback / quick measure |

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b / Strategy C：production code 變動 但 audit-only 範圍以外（Phase 2 feature 新增、不觸 VR pipeline / 既有 Layout） | ✅ |
| #2 名定常數（DEFAULT_SHAPE_CACHE_MAX_ENTRIES、所有 Unicode 範圍 hex） | ✅ |
| #14.b clean scope（commit 只含 Phase 2 4 production + 4 audit + 1 doc + INDEX/progress） | ✅ |
| #18 scope-down（不重寫 Layout engine、不接到 OoxmlParser 主流程；fallback API 不做 ligature） | ✅ |
| #21 audit 不 touch VR / 既有 tests（VR 第 68 連 maintained） | ✅ |

---

## VR / 既有 tests 影響

- VR pipeline 完全不動：ShapingEngine + FontMetrics 為新增 API、未接到既有
  Layout engine 主流程（規畫書接受設計、Phase 6 自寫 Layout 時才接）
- 既有 2035 vitest 0 regression：新增的 4 unit test 檔（含 45 test）全綠
- tsc 2 pre-existing error 不增（opentype.js declaration + SettingsParser
  position enum）

---

## 後續銜接（規畫書 §Phase 6 Layout Engine）

| Phase 2 元件 | Phase 6 Layout Engine 銜接點 |
|---|---|
| measureRun() | LineBreaker / measureText 取代點 |
| resolveOoxmlLineHeight | Paginator R6 行高計算源頭 |
| baselineOffsetPt | Renderer / CanvasRenderer 文字 y 軸定位 |
| Glyph cache | Layout pass trial-and-error 加速（紀律 #21 純記憶體加速） |
| readOpentypeAdvances | 瀏覽器 fallback（無 WASM）quick measure |
| detectScript | RTL flow 切割、font fallback chain 選 EA vs hAnsi |

---

## End of Sprint 265-268

**Phase 2 Text Shaping 8 checkbox 全完成 + 45 unit test 全綠 + 零既有 test
regression + VR 第 68 連 maintained**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

**Phase 2 從 user 標「真正該做沒做的一條」→ 完成**；其他 A-F 殘項
（Phase 3 連字 / 表格浮動 / Phase 5 OMML alt text / Phase 7 Web Worker /
Phase 8.2.2 overlay）皆已 honest 標為 optional / advanced / 條件性 / 不建議、
不在本 cluster 範圍。
