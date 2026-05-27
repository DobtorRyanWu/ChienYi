# Sprint 313-317 — 「繼續執行」honest gap 5 項第五輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① font CSS parser / ③ baseline-aware polygon / ④ conflict detector / ⑤ keyboard commands / ⑥ circuit breaker
**前置**：Sprint 298+299、300+301+302、303-307、308-312 共四輪深推

User 指令：「繼續執行」honest gap 5 項第五輪深推。

---

## 五 sprint cluster 對齊

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **313** | ① canvas-editor 接管 measureText | `CanvasEditorFontResolver.ts` | parse `ctx.font` CSS shorthand → `{ family, sizePt, style?, weight?, fallbacks? }` + formatter |
| **314** | ③ wrap polygon baseline | `wrap_polygon_baseline.ts` | `lineBoxFromBaseline` + `findSafeBaselineY` + `clampBaselineAvoidingPolygon` + `polygonBaselineUnsafeRange` |
| **315** | ④ revision 衝突 | `RevisionConflictDetector.ts` | 5 種 conflict kind 偵測（mixed-author / move-pair mismatch / orphan / props+revision coexist / pPrChange+runs） |
| **316** | ⑤ overlay 鍵盤操作 | `OverlayKeyboardCommands.ts` | `mapKeyToCommand` 12 種 OverlayCommand（delete / nudge / select-all / copy / undo 等）+ platform-aware modifier |
| **317** | ⑥ worker 容錯 | `WorkerCircuitBreaker.ts` | 三狀態（closed / open / half-open）+ primary + fallback + sliding window |

---

## Sprint 313 — CanvasEditorFontResolver

Sprint 303/308 之後深推。Canvas2D `ctx.font` 是 CSS shorthand 字串、caller 接管
measureText 時必須從中解 family + sizePt 才能餵 bridge。本 sprint 補 PROBE-grade
parser。

- 支援單位：pt / px / em / rem / %
- 支援前綴：bold / italic / oblique / 100-900 numeric weight
- 支援 quoted family（'Noto Sans CJK TC'）+ fallback list
- 反向 `formatCanvasFont` 提供 round-trip

紀律 #18 scope-down：
- 不對齊 browser native 100%（caller 環境精準需求自行用 CSSStyleDeclaration）
- 不處理 stretch / variant / line-height（紀律 #18）

### 19 unit tests
- 基本（pt/px/em/rem/%）×4
- style/weight 前綴（bold/italic/順序顛倒/numeric weight）×5
- quoted family + fallback list ×4
- formatCanvasFont round-trip ×2
- 錯誤處理（空字串 / 無 size / 無 family / 不識別 unit）×4

---

## Sprint 314 — WrapPolygon baseline-aware

Sprint 296/298/304/309 之後深推。考慮 polygon 跨 baseline 的 line 高度。

- `lineBoxFromBaseline(baseline, ascent, descent)` → `{ top, bottom, height }`
- `findSafeBaselineY(opts)` → 在 [yMin, yMax] 找第一條安全 baseline；找不到 undefined
- `clampBaselineAvoidingPolygon(desired, opts)` → 目標撞 polygon 時推到下一安全位置
- `polygonBaselineUnsafeRange(polygon, ascent, descent)` → 該 polygon 的不安全 baseline Y 區間

紀律 #18 scope-down：
- 不接 Paginator real path（紀律 #21）
- 單一 polygon（多 polygon caller 自管 union）

### 13 unit tests
- lineBoxFromBaseline ×2
- findSafeBaselineY（polygon 外 / 空 polygon / 完全擋住 / 跨下緣 / step<=0 throw）×5
- clampBaselineAvoidingPolygon（不撞 / 撞推下一安全 / 找不到 undefined）×3
- polygonBaselineUnsafeRange（矩形 / 空 / 三角形）×3

---

## Sprint 315 — RevisionConflictDetector

Sprint 300/305/310 之後深推。5 種 conflict kind：

| ConflictKind | 描述 |
|---|---|
| `mixed-author-in-paragraph` | 同段落內多 author 的 revision |
| `move-pair-author-mismatch` | moveFrom 與 moveTo 配對 id 但 author 不同 |
| `move-pair-orphan` | moveFrom 沒 moveTo（或反之）對應 |
| `run-props-and-revision-coexist` | 同 run 同時帶 revision + rPrChange |
| `paragraph-pPrChange-and-runs-revision` | 段落 pPrChange + 內部 run revision 共存 |

API：`detectConflicts(doc)` / `detectConflictsInParagraph(p)` / `summarizeConflicts(reports)`

紀律 #18 scope-down：
- 不做語意衝突（同段不同位置但語意相關 → 不解）
- 不主動建議解法（caller 自決）
- moveFrom/moveTo 比對只看 id + author、不看 content

### 14 unit tests
- mixed-author-in-paragraph ×2
- move-pair-author-mismatch ×2
- move-pair-orphan（moveFrom 無 moveTo / 反之）×2
- run-props-and-revision-coexist ×1
- paragraph-pPrChange-and-runs-revision ×2
- summarizeConflicts ×2
- detectConflictsInParagraph 增量 API ×1
- 邊界（空 doc / 無 revision）×2

---

## Sprint 316 — OverlayKeyboardCommands

Sprint 291/295/301/306/311 之後深推。Pure-fn 把 keyboard event → overlay command。

Commands：
- `delete` / `nudge(dx,dy)` / `select-all` / `clear-selection`
- `copy` / `cut` / `paste` / `duplicate`
- `undo` / `redo`
- `noop`

Platform-aware：
- Mac → Cmd modifier；PC → Ctrl modifier
- Shift 修飾 nudge → 大步（10pt vs 1pt，可 caller 覆寫）

紀律 #18 scope-down：
- 不接 doc_editor.js real path（紀律 #21、同政策）
- 不處理 IME composition events
- copy/paste 只回 command name、不負責 clipboard

### 23 unit tests
- delete（Backspace / Delete / 無 selection noop）×3
- nudge（4 方向 / Shift big step / custom step / 無 selection noop）×7
- select-all / clear-selection（Mac / PC / 跨 platform / Escape）×4
- copy / cut / paste（有 selection / paste 無 selection / copy 無 selection noop）×4
- undo / redo / duplicate（Mod+Z / Mod+Shift+Z / Mod+D / Mod+D 無 selection noop）×4
- unknown key noop ×2

---

## Sprint 317 — WorkerCircuitBreaker

Sprint 292/294/299/307/312 之後深推。3 狀態 state machine：

```
closed → 錯誤率超閾值 → open → cooldown 過 → half-open
                                    ↓
                       probe primary 成功 → closed
                       probe primary 失敗 → open
```

- `errorRateThreshold`（預設 0.5）/ `windowSize`（10）/ `minSamples`（5）/ `cooldownMs`（5000）
- 純記憶體 state machine、caller 提供 clock
- Sliding window 最近 N 筆（紀律 #18 簡化、非時間 window）
- `forceState` 測試 / 手動干預用

紀律 #18 scope-down：
- 不主動定時 retry（caller 必須 post 才 trigger half-open transition）
- 不持久化

### 14 unit tests
- closed 路由給 primary ×1
- closed → open transition（達閾值 / minSamples 不足 / 錯誤率<閾值）×3
- open 路由給 fallback ×1
- open → half-open cooldown（cooldown 未到 / 過 → probe 走 primary / probe 成功→closed / probe 失敗→open / half-open 期間其他走 fallback）×5
- stats 累積（primary / fallback）×2
- terminate fan-out ×2

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 83 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 3 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：83 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 313-317 cluster

vitest 2446 → 2529（+83 deterministic）/ tsc 2 pre-existing 不增 / +~900 行新模組 /
0 行 production canvas-editor / parser / layout / render / doc_editor.js / paginator 變動。

5 個 honest gap 第五輪深推完成（總計五輪 / 25 sprints / +257 tests cumulative）：
- ① canvas-editor measureText：sync proxy → Canvas-shape bridge → AST prewarm → Proxy patch → font CSS parser
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline adjust
- ④ accept/reject：pure-fn → review session → diff summary → conflict detector
- ⑤ overlay：clamp/align → multi-select → guide session → selection state → keyboard commands
- ⑥ worker dispatcher：single → cluster → pool → health monitor → circuit breaker
