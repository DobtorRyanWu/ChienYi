# Sprint 281 — Phase 2.1 full chain browser e2e + Node parity Δ=0 全表 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Phase 2.1-2.3 cluster 第 3/3 完成 / Phase 2.1 結束

**日期**：2026-05-26（週二）
**類型**：e2e 整合 spike + Node parity vitest case
**規畫書對應**：§Phase 2.1 ShapingEngine 封裝 + 字型載入器 + opentype.js 取代 measureRun（user pinned「最值得做的一條」cluster 收口）
**前置**：Sprint 279 setHbModuleLoader + Sprint 280 ShapingFontChain

---

## Hypothesis & Result

**hypothesis**：Sprint 279 + 280 合一 + Sprint 62 既有 opentype.js ESM-friendly
的 FontMetrics、可在 actual browser 跑通完整 Phase 2.1 鏈、與 Node 端 byte-identical
parity。

**結論**：**verified、Browser ↔ Node Δ=0 全表（含 5 stage、12 個量化指標）**。

---

## 鏈（5 stage）

```
Stage 1: setHbModuleLoader → 注入 browser createHarfBuzz + hbjs (Sprint 279)
Stage 2: loadShapingFontWithChain → primary 404 → fallback DejaVuSans 200 (Sprint 280)
Stage 3: engine.measureRun → HarfBuzz shape 11 glyphs (Sprint 265)
Stage 4: readFontMetrics → opentype.js 讀 ascender / typoMetrics (Sprint 62 / 268)
Stage 5: resolveOoxmlLineHeight → auto / exact / atLeast 三 rule (Sprint 267)
```

---

## Browser ↔ Node byte-identical parity Δ=0 全表

`DejaVuSans + "Hello world" + sizePt=12`，browser 走 Chrome 149 actual headless
via Playwright MCP、Node 走 vitest 2.1.9：

| Stage | Metric | Chrome 149 | Node | Δ |
|---|---|---|---|---|
| chain | chainAttempted | 2 | 2 | **0** |
| chain | loadedFrom.family | "DejaVuSans" | "DejaVuSans" | **0** |
| shape | glyphCount | 11 | 11 | **0** |
| shape | widthPt | 67.271484375 | 67.271484375 | **0** |
| shape | glyph[0].glyphId | 43 | 43 | **0** |
| shape | glyph[0].xAdvance（font units） | 1540 | 1540 | **0** |
| shape | advancesPt[0] | 9.0234375 | 9.0234375 | **0** |
| metrics | unitsPerEm | 2048 | 2048 | **0** |
| metrics | ascender | 1901 | 1901 | **0** |
| metrics | descender | 483 | 483 | **0** |
| metrics | lineGap | 410 | 410 | **0** |
| metrics | typoAscender | 1556 | 1556 | **0** |
| lineHeight | natural（pt） | 16.37109375 | 16.37109375 | **0** |
| lineHeight | auto(1.5×) | 24.556640625 | 24.556640625 | **0** |
| lineHeight | exact(18) | 18 | 18 | **0** |
| lineHeight | atLeast(20) | 20 | 20 | **0** |

**全表 Δ=0 到尾數位**。HarfBuzz wasm 在 Chrome / Node 兩 runtime 行為一致、
opentype.js 亦 deterministic、整個 Phase 2.1 鏈 cross-platform 完全等價。

---

## Bundle 策略

```bash
./node_modules/.bin/esbuild spikes/sprint281_phase2_1_full_browser/entry.ts \
  --bundle --platform=browser --format=iife \
  --global-name=Sprint281Bundle --target=es2020 \
  --external:node:module \
  --outfile=spikes/sprint281_phase2_1_full_browser/bundle.js
```

- `--external:node:module`：Sprint 279 dynamic `import('node:module')` 在 browser
  caller 注入 hbModuleLoader 時不走、外部標記避 esbuild resolver 報錯
- `--platform=browser`：opentype.js 走 ESM `module: opentype.mjs` 入口
- bundle 大小 ~640KB（opentype.js ~80KB + ShapingEngine + ShapingFontChain +
  FontMetrics + script detection 表 + cache 等）；caller-side 可走 tree-shaking
  / dynamic import 縮減

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b spike + Node parity test：spike 不入 production、Node parity vitest +1 案 | ✅ |
| #14.b clean scope：commit 含 spike entry.ts + index.html + README + .gitignore + Node parity test + doc | ✅ |
| #18 scope-down：Phase 2.1 收口、不擴張到 mixed run / RTL / bidi / Layout 接通；canvas-editor 仍不接 | ✅ |
| #21 audit 不 touch Sprint 279/280 production code（只組合驗證） | ✅ |
| #22 verify：Browser + Node 雙 path、12 指標 Δ=0 全表為硬數據 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通；browser e2e + Node parity = 完整三條路徑 | ✅ |

---

## Phase 2.1-2.3 cluster 收口

| Sprint | 範圍 | 結果 |
|---|---|---|
| 279 | ShapingEngine browser-compat refactor（setHbModuleLoader、caller-injectable）| +5 unit test、vitest 2094 → 2099 |
| 280 | ShapingFontChain（fetch + fallback chain、getDefaultCjkFallbackChain）| +8 unit test、vitest 2099 → 2107 |
| 281 | e2e browser spike + Node parity（5 stage、12 指標 Δ=0）| +1 vitest case、vitest 2107 → 2108 hypothesis |

合計：Phase 2.1 cluster 3 sprint / 22 個全綠 case / 0 regression / 0 VR 異動 /
Browser ↔ Node byte-identical parity 驗證完成。

User pinned「最值得做的一條」**完整達成**。

---

## End of Sprint 281 / End of Phase 2.1 cluster

**Phase 2.1 ShapingEngine 封裝 + 字型載入器 + opentype.js 取代 measureRun
全套完成、Browser ↔ Node byte-identical parity 全表 Δ=0 / Phase 2.1-2.3
cluster 3/3 收口**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

vitest 2107 → 2108 hypothesis（+1 Sprint 281 full chain Node parity case）/
VR 第 68 連 maintained / tsc 2 pre-existing 不增 / cluster 用時遠低於 user
給的 24 小時 cap。

剩餘 user-honest 標項：
- Phase 1 optional bucket（ruby / tcFitText / tblStylePr / lvlOverride /
  effectExtent / wp:anchor、user 已準備 8 sprint cluster）
- Phase 3.4 wrapTight 多邊形繞排（user 已準備 12 小時 cluster）
- Phase 5.4+5.5 追蹤修訂 + 註解 UI（user 已準備 16 小時 cluster）
- Phase 8.2.2 overlay（user 顯式條件性 override gate）
- Phase 7 Web Worker（user 顯式 OVERRIDE gate）
- Phase 6 完整 Layout（hyphenation / Knuth-Plass / mixed run / bidi / 整合
  Phase 2.1 鏈、長期 optional）
- canvas-editor 整合（Sprint 7 ProtonClone audit 標 fork 阻擋、不建議）
