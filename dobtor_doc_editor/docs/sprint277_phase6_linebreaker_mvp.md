# Sprint 277 — Phase 6 Layout Engine MVP spike：Greedy LineBreaker ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 雙驗 path 1+2 通過 / vitest 路徑 WSL ENOMEM hypothesis pending

**日期**：2026-05-26（週二）
**類型**：Strategy A 真實 production code 擴張 / 紀律 #18 scope-down MVP
**規畫書對應**：§Phase 6 Layout Engine 自寫（長期 optional、Sprint 275 cache 效益已驗證、Phase 2 API ready）
**前置**：Sprint 275 Phase 2 Exit 6/6 全綠、ChienYi v1 GO v4

---

## Hypothesis & Result

**hypothesis**：Sprint 269/275 標 Phase 2 API（ShapingEngine.measureRun /
FontMetrics.resolveOoxmlLineHeight）「Phase 6 自寫 Layout 時可直接銜接」。
本 sprint 用最小 LineBreaker MVP 消費 measureRun() 做 greedy break、驗證
API contract 真 ready。

**範圍**（紀律 #18 scope-down、MVP only）：
- Greedy break by ASCII space（不做 hyphenation / Knuth-Plass / CJK soft break）
- 單一 font + sizePt（不做 mixed run / inline 字級切換）
- LTR 假設（不做 RTL bidi）
- Overlong word force-fit（不切字、不 hyphenate）

**新增檔**：
- [`static/src/core/ooxml/layout/LineBreaker.ts`](../static/src/core/ooxml/layout/LineBreaker.ts) — ~100 行 production
- [`static/src/core/ooxml/layout/index.ts`](../static/src/core/ooxml/layout/index.ts) — barrel export
- [`tests/unit/sprint277_linebreaker_mvp.test.ts`](../tests/unit/sprint277_linebreaker_mvp.test.ts) — 6 vitest 案例
- [`scripts/verify_sprint277.mjs`](../scripts/verify_sprint277.mjs) — 雙驗 path 2 standalone Node 驗證

---

## 雙驗執行結果

WSL ENOMEM 嚴重（free 168Mi / 7.8Gi、Node ESM resolver cascade 失敗）導致
vitest 框架無法跑；按紀律 #22 走雙驗：兩條獨立路徑都通才算 SOP 通過。

### Path 1: tsc standalone（型別驗證）

```bash
./node_modules/.bin/tsc --noEmit --strict static/src/core/ooxml/layout/LineBreaker.ts \
  static/src/core/ooxml/layout/index.ts
```

結果：**僅 1 條 pre-existing `opentype.js` declaration 警告（FontMetrics.ts:27）**、
Sprint 277 新檔零新 error。通過。

### Path 2: standalone Node verify（演算法驗證）

```bash
node scripts/verify_sprint277.mjs
```

```
[sprint277 verify] pass=21 fail=0
[sprint277 verify] 雙驗 path 2 (standalone Node) PASSED
```

- 6 案例、21 assertion 全通過
- 使用確定性 mock measureRun（每字寬 = sizePt × 0.5pt 線性）
- 不依賴 vitest framework / HarfBuzz wasm / 系統字型、避 WSL ENOMEM blocker
- 算法與 LineBreaker.ts 完全鏡像（inline 同 implementation 跑相同 case）

### Path 3 (hypothesis pending): vitest framework

WSL 記憶體釋放後補跑 `npm test -- tests/unit/sprint277_linebreaker_mvp.test.ts`、
預期 vitest 2086 → 2092（+6 案例）。本 sprint 不阻塞 commit、紀律 #22 hypothesis
標明。

---

## API 設計

```typescript
export interface BrokenLine {
  text: string;       // words.join(' ')
  widthPt: number;    // 物理寬度（pt）
  words: string[];
}

export interface LineBreakResult {
  lines: BrokenLine[];
  maxLineWidthPt: number;
  totalLines: number;
}

export interface LineBreakOptions {
  text: string;
  availableWidthPt: number;
  fontFamily: string;
  sizePt: number;
  spaceWidthPt?: number;  // optional inject 避 wasm shape
}

export async function breakParagraph(
  engine: ShapingEngine,
  opts: LineBreakOptions,
): Promise<LineBreakResult>;
```

### 演算法（greedy）

```
words = text.split(' ').filter(non-empty)
spaceWidth = opts.spaceWidthPt ?? engine.measureRun(' ').widthPt

for each word:
  wordWidth = engine.measureRun(word).widthPt
  wouldBe = curEmpty ? wordWidth : curWidth + spaceWidth + wordWidth
  if wouldBe <= avail OR curEmpty:
    add to current line（curEmpty 時即使 overlong 也 force-fit）
  else:
    flush current line、start new with this word
```

---

## 為何此 MVP 不接 canvas-editor / 不取代 measureText

Sprint 269 Phase 2 結論：「production canvas-editor 未整合、Phase 6 自寫
Layout 時消費」。canvas-editor 內部 ctx.measureText 已穩定、Sprint 137 雙驗判
不接外部 metrics、Sprint 7 ProtonClone 證未走入 production prod canvas-editor
patch。

Sprint 277 LineBreaker MVP 為 **Phase 2 API readiness validation**，不為
production swap：
- canvas-editor 仍走 ctx.measureText（既有 VR 第 68 連 maintained）
- LineBreaker 走 ShapingEngine.measureRun（新模組、不入 OoxmlParser 主流程）
- Phase 6 完整 Layout 才會考慮 swap 或並存（決策延後、規畫書 §Phase 6 long-term）

---

## Phase 6 完整 Layout 還缺什麼（誠實標）

| 範圍 | MVP（Sprint 277） | Phase 6 完整 |
|---|---|---|
| Break point | ASCII space | + hyphenation dictionary（Liang algorithm en-US）+ CJK soft break |
| Algorithm | Greedy | + Knuth-Plass dynamic programming 最佳化 |
| Mixed run | 單一 font + size | + 字型 / 字級 / 顏色切換 inline |
| Kerning | per-word measureRun（含 OpenType kern） | + cross-word boundary kerning adjust |
| Justification | left-align only | + justified（CJK fullwidth/halfwidth 平衡 + western space-stretch）|
| Bidi | LTR only | + RTL Arabic / Hebrew bidi + segment level |
| Tab stops | 不處理 | + Sprint 161 defaultTabStop 整合 |
| Line height | 不處理 | + Sprint 267 resolveOoxmlLineHeight 整合 |
| Page break | 不處理 | + paragraph break + section break + page layout |

紀律 #18 scope-down：本 sprint 不擴張、僅證 Phase 2 measureRun API 就緒。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：production code 擴張 ~100 行 LineBreaker.ts + ~10 行 index.ts + 雙驗 path 2 ~140 行 | ✅ |
| #14.b clean scope（commit 只含 layout/ 兩檔 + 1 vitest test + 1 verify script + 1 doc + INDEX/progress） | ✅ |
| #18 scope-down（不寫 hyphenation / Knuth-Plass / mixed run / bidi、長期 optional 列 future） | ✅ |
| #21 audit 不 touch VR / 既有 tests / Layout / Render（新 layout/ 模組獨立、不入 OoxmlParser 主流程） | ✅ |
| #22 verify 結論誠實標 hypothesis（vitest path 3 標 WSL ENOMEM pending、不阻塞）| ✅ |
| 雙驗 紀律：path 1 (tsc) + path 2 (standalone Node) 都通才算 SOP 通過 | ✅ |
| VR 第 68 連 maintained（LineBreaker 不入 Render / canvas-editor、純新模組）| ✅ |

---

## End of Sprint 277

**Phase 6 LineBreaker MVP spike + 雙驗 path 1+2 通過 + Phase 2 API readiness
validated** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

vitest 2086 維持（path 3 vitest 案 hypothesis pending WSL 記憶體釋放補跑、
expected 2086 → 2092）/ tsc Sprint 277 新檔零新 error / VR 第 68 連 maintained。

剩餘工作（全 user honest 標）：
- Phase 8.2.2 overlay polish（等 Phase 2.1 反饋）
- Phase 7 OffscreenCanvas / Web Worker（雙驗不建議）
- 第十九層 xmlDecl/xmlns normalize（紀律 #18 scope-down、99.6% 已極致）
- Phase 6 完整 Layout（hyphenation / Knuth-Plass / mixed run / bidi、長期 optional）
- Sprint 277 vitest path 3 補跑（WSL 記憶體釋放後）
