# Sprint 308-312 — 「繼續執行」honest gap 5 項第四輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-27（週三）
**範圍**：① canvas-editor patch probe / ③ wrap polygon paginator / ④ revision diff summary / ⑤ overlay selection state / ⑥ worker health monitor
**前置**：Sprint 298+299 第二輪、Sprint 300+301+302 第二輪、Sprint 303-307 第三輪

User 指令：「繼續執行」honest gap 5 項第四輪深推。

---

## 五 sprint cluster 對齊

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **308** | ① canvas-editor 接管 measureText | `CanvasEditorPatchProbe.ts` | `wrapCanvasContext` ES Proxy 包 ctx + `canSafelyPatchPrototype` 環境偵測 |
| **309** | ③ wrap polygon 跨頁 | `wrap_polygon_paginator.ts` | `clipPolygonToYRange`（Sutherland–Hodgman）+ `shiftPolygonForPage` + `preparePolygonForPages` |
| **310** | ④ revision UI 摘要 | `RevisionDiffSummary.ts` | `summarizeByAuthor` + `summarizeByType` + `formatSummaryMarkdown` |
| **311** | ⑤ overlay 多選狀態 | `OverlaySelectionState.ts` | `select(id, mode)` + bulk ops + `subscribe` listeners + SelectionChange events |
| **312** | ⑥ worker observability | `WorkerHealthMonitor.ts` | wrap dispatcher + latency/p50/p95/errorRate/timeout 累積 + clearStats |

---

## Sprint 308 — CanvasEditorPatchProbe

Sprint 303 CanvasEditorMeasureBridge 第二輪 PROBE。Sprint 303 提供 caller 顯式呼叫
的 `measureText(text, family, sizePt)`；本 sprint PROBE **如何接管 caller 的
ctx.measureText**。

- `wrapCanvasContext(ctx, bridge, opts)` — ES Proxy 包原 ctx：
  - 攔截 `measureText` → bridge cache 走 / cache miss fallback native
  - 其他屬性透傳（fillStyle 等）
  - `__patchProbeStats` 追蹤 hits / fallbacks
- `canSafelyPatchPrototype()` — 環境偵測（Node / 已被 patch / native）

紀律 #18 scope-down：
- 紀律 #21：production 不走 prototype patch；只提供 instance-level wrap factory
- caller 顯式 opt-in、不污染 prototype

### 9 unit tests
- bridge cache hit（單次 / 多次 stats 累積）×2
- cache miss fallback（fallbackToNative=true/false）×2
- ES Proxy 透傳（get / set）×2
- canSafelyPatchPrototype（Node / mock non-native）×2
- defaultFamily 對應（caller 改 sizePt 後 cache miss）×1

---

## Sprint 309 — WrapPolygon paginator helpers

Sprint 296/298/304 polygon math + LineBreaker + render；本 sprint 補
**跨頁時** polygon 與 paginator 的對位邏輯。

- `clipPolygonToYRange(poly, yMin, yMax)` — Sutherland–Hodgman Y-axis clip
- `shiftPolygonForPage(poly, startY)` — 絕對 Y → page-local Y
- `splitPolygonAcrossPages(poly, pages)` — 每頁子 polygon
- `preparePolygonForPages(poly, pages)` — split + shift 一次完成

紀律 #18 scope-down：
- 不接 Paginator real path（紀律 #21）
- 只裁 Y range（X 跨欄分割留 future）

### 13 unit tests
- clipPolygonToYRange（完全內 / 完全外×2 / 部分跨界×2 / 空 polygon）×6
- shiftPolygonForPage（Y 平移 / X 不變）×2
- splitPolygonAcrossPages（全在第 1 頁 / 跨頁）×2
- preparePolygonForPages 整合（split+shift / 完全在某頁）×2
- 非矩形 polygon 三角形跨頁 ×1

---

## Sprint 310 — RevisionDiffSummary

Sprint 300 + 305 後第三輪深推。給 UI 顯示 / PR review 用的人類可讀 summary。

- `summarizeByAuthor(doc)` — 依 author 群組（author 缺失 → "Unknown"）
- `summarizeByType(doc)` — 依 revision type 統計
- `formatSummaryMarkdown(doc)` — 產 Markdown 表格（Total + By Author + By Type）

紀律 #18 scope-down：
- 不展開具體文字（caller 自做）
- 不做 i18n（caller 翻譯 label）
- 不做 trend over time（單 doc 快照）

### 9 unit tests
- summarizeByAuthor（多 author / Unknown / 空 doc / 混合 source）×4
- summarizeByType（基本 / 混合 source）×2
- formatSummaryMarkdown（完整 / 空 doc / 單複數 "revision"）×3

---

## Sprint 311 — OverlaySelectionState

Sprint 291/295/301/306 overlay 系列第三輪深推。Single + multi selection 狀態機。

API：
```typescript
const sel = new OverlaySelectionState();
sel.select(id, 'replace' | 'toggle' | 'add' | 'remove');
sel.replaceAll(ids);   // marquee
sel.addAll(ids);
sel.removeAll(ids);
sel.clear();
sel.subscribe(change => ...);
sel.getIds(); sel.has(id); sel.isMulti(); sel.size();
```

紀律 #18 scope-down：
- 不接 doc_editor.js OWL real path（紀律 #21、同 295/301/306 政策）
- 不做 keyboard navigation
- 不做 z-order / hit testing

### 16 unit tests
- 初始狀態 ×1
- select 四 mode（replace / toggle / add / remove）×4
- bulk ops（replaceAll / addAll / removeAll）×3
- clear ×2
- SelectionChange events（added/removed / 無變動不 emit / unsubscribe / listener throw）×4
- 邊界（replaceAll([]) / 重複 id dedup）×2

---

## Sprint 312 — WorkerHealthMonitor

Sprint 292/294/299/307 worker cluster 第三輪深推。observability layer。

特性：
- Wrap 一個 dispatcher、追蹤 inflight request 從 post 到 response 的 latency
- 累積 stats：postCount / successCount / errorCount / timeoutCount / meanLatency /
  p50 / p95 / errorRate / inflightCount
- `recordTimeout(requestId)` — caller 顯式標 timeout（ParseWorkerHarness timeout 時呼叫）
- `clearStats()` — reset 累積（保留 inflight）

紀律 #18 scope-down：
- 不接 production monitoring（caller decide export）
- 不主動 alert
- 不做 sliding window（lifetime stats、caller 自管 reset）

### 12 unit tests
- latency 記帳（單筆 / 多筆 mean+p50+p95）×2
- error rate（混合 success+error / 0 完成回 0）×2
- recordTimeout（inflight / 非 inflight）×2
- listener fan-out（subscribe / unsubscribe）×2
- terminate fan-out（給底層 / post no-op / 不再 emit）×3
- clearStats（保留 inflight）×1

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 59 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 3 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列（real-path 不接 / monitoring 不接 / X-axis 不裁） | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：59 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 308-312 cluster

vitest 2387 → 2446（+59 deterministic）/ tsc 2 pre-existing 不增 / +~800 行新模組 /
0 行 production canvas-editor / parser / layout / render / doc_editor.js / paginator 變動。

5 個 honest gap 第四輪深推完成（總計四輪 / 20 sprints / +172 tests）：
- ① canvas-editor measureText：sync proxy → Canvas-shape bridge → AST prewarm → Proxy patch
- ③ wrapPolygon：math → LineBreaker → render → paginator clip
- ④ accept/reject：pure-fn helpers → review state machine → diff summary
- ⑤ overlay：clamp/align → multi-select helpers → guide session → selection state machine
- ⑥ worker dispatcher：single → cluster (MainThread/Node/Browser) → pool → health monitor
