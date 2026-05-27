# Sprint 328-332 — 「繼續執行」honest gap 5 項第八輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① canvas-editor cache snapshot / ③ text-flow integration shim / ④ revision exporter / ⑤ overlay touch mapper / ⑥ worker metrics collector
**前置**：七輪深推（Sprint 298-327）

User 指令：「繼續執行」honest gap 5 項第八輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **328** | ① canvas-editor cache snapshot | `CanvasEditorCacheSnapshot.ts` | JSON-safe schema v1 + merge + filter + summarize |
| **329** | ③ text flow integration shim | `text_flow_around_polygon.ts` | prepareWrapContext / findFlowBaseline / flowParagraphAroundWrapCtx |
| **330** | ④ revision exporter | `RevisionExporter.ts` | JSON rows + CSV escape (RFC 4180) + summarize |
| **331** | ⑤ overlay touch mapper | `OverlayTouchMapper.ts` | classifyTap / recognizePinch / mapGestureToCommand |
| **332** | ⑥ worker metrics collector | `WorkerMetricsCollector.ts` | time-series bucket stats vs Sprint 312 lifetime |

---

## Sprint 328 — CanvasEditorCacheSnapshot

Sprint 323 PrewarmStrategy 之後深推。Caller 想跨 session 持久化 prewarm
result（localStorage / IndexedDB / disk）；本 sprint 補 JSON-safe schema +
versioning + merge + filter。

- `toSnapshot(entries, { now })` → v1 snapshot
- `fromSnapshot(raw)` → reject unknown schema / 缺欄位 / NaN / 非預設 charset；
  回 null 不 throw
- `mergeSnapshots(a, b)` → same (text,family,sizePt) frequency 累加
- `pickByMinFrequency(entries, n)` → 過濾低頻
- `summarizeSnapshot(snapshot)` → totalEntries / totalFrequency / byCharset

紀律 #18：純 JSON / 記憶體；caller 自負 storage / 壓縮 / 加密。

### 17 unit tests
- toSnapshot 結構（caller now / default now）×2
- fromSnapshot（valid / null / primitive / wrong schema / non-array / 缺欄位 /
  NaN / Infinity / 非預設 charset / 無 charset OK）×9
- mergeSnapshots（frequency 累加 / 不同 key / b 有 a 無 charset / a 優先）×4
- pickByMinFrequency（過濾 / min=0）×2
- summarizeSnapshot（累加 / 空）×2

---

## Sprint 329 — text_flow_around_polygon

Sprint 296/298/304/309/314/319/324 polygon 系列第八輪整合 shim。把 anchor +
baseline + LineBreaker 三層串成 caller-friendly 的 pure-fn pipeline。

- `prepareWrapContext({ polygon, imageRect, dist })` → polygonAbs + bbox + imageRect copy
- `findFlowBaseline(ctx, opts)` → 委派 Sprint 314 findSafeBaselineY
- `flowLineBox(baselineY, ascent, descent)` → 委派 Sprint 314 lineBoxFromBaseline
- `flowParagraphAroundWrapCtx(ctx, engine, opts)` → 委派 Sprint 298 breakParagraphAroundPolygon（async）
- `isYRangeBlockedByWrap(ctx, yMin, yMax)` → bbox-cheap check

紀律 #18 scope-down：單 polygon、不接 Paginator real path、caller 自負字型 load。

### 11 unit tests
- prepareWrapContext（square / dist margin / empty）×3
- findFlowBaseline（空 → yMin / square → 推到下方 / yMax 不足 → undefined）×3
- flowLineBox（baseline/ascent/descent）×1
- flowParagraphAroundWrapCtx 整合 LineBreaker ×1
- isYRangeBlockedByWrap（空 / 撞 / 不撞）×3

---

## Sprint 330 — RevisionExporter

Sprint 300/305/310/315/320/325 revision 系列第七輪深推。匯出整 doc 內所有
revision metadata 為外部 audit tool 可吃的格式。

- `exportRevisionsAsJson(doc)` → 扁平 RevisionExportRow[]（source / subtype / author / date / id）
- `escapeCsvField(s)` → RFC 4180 escape（逗號 / 引號 / 換行）
- `exportRevisionsAsCsv(doc)` → header + rows string
- `summarizeExport(rows)` → bySubtype { ins / del / moveFrom / moveTo / props }

紀律 #18 scope-down：純 string + object；不接 file system / Buffer / streaming；
不做時區轉換；不做 diff inline 還原。

### 16 unit tests
- exportRevisionsAsJson（空 / 單一 ins / 缺欄位 / moveFrom/moveTo / pPr+rPr → props）×5
- escapeCsvField（普通 / 逗號 / 引號 / 換行 / 空）×5
- exportRevisionsAsCsv（空 → header / 單筆 / author 含逗號 escape）×3
- summarizeExport（累加 / 空）×2
- 補：moveFrom/moveTo combined test ×1

---

## Sprint 331 — OverlayTouchMapper

Sprint 291/295/301/306/311/316/321/326 overlay 系列第八輪深推。Sprint 316 做
keyboard → command；本 sprint 補 touch/pointer gesture → command（手機/平板）。

- `classifyTap(durationMs, moveDistance, opts)` → 'tap' / 'long-press' / 'drag'
- `recognizePinch(start[2], end[2])` → { scale, dx, dy } | null
- `mapGestureToCommand(gesture, opts)` → OverlayCommand（複用 Sprint 316 type）
- `createGestureStats()` / `recordGesture(stats, kind)` → telemetry

紀律 #18 scope-down：pure-fn；不接 DOM PointerEvent / doc_editor.js real
path；不做 momentum / inertia；不處理 3+ 指。

### 16 unit tests
- classifyTap（短小 tap / 長 long-press / 移動 drag / drag 優先 / caller threshold）×5
- recognizePinch（放大 / 縮小 / 非 2 指 / 起距 0 / 中心漂移）×5
- mapGestureToCommand（tap noop / long-press duplicate / 無 selection / copy / noop /
  two-finger nudge / drag-pinch-unknown noop）×7
- gesture stats（record 累加 / unknown 不增）×2
- 補 1：long-press 默認 duplicate

---

## Sprint 332 — WorkerMetricsCollector

Sprint 292/294/299/307/312/317/322/327 worker 系列第八輪深推。Sprint 312
WorkerHealthMonitor 是 lifetime cumulative（mean / p50 / p95、不分時段）；本
sprint 補 time-series bucket stats 給 dashboard 用。

- `WorkerMetricsCollector` class（maxEvents FIFO buffer、預設 1000）
- `record(event)` / `getBuckets(fromMs, toMs, bucketSizeMs)` → BucketStats[]
- `size()` / `clear()` / `exportSnapshot()`
- `recordSuccess` / `recordError` / `recordTimeout` helpers

每 bucket：startMs / endMs / successCount / errorCount / timeoutCount / meanLatencyMs / maxLatencyMs

紀律 #18 scope-down：純記憶體；caller 自負持久化；不接 production worker
dispatcher；不做 sliding window aggregation；maxEvents FIFO 自然淘汰。

### 13 unit tests
- constructor（maxEvents <= 0 throw / default）×2
- record FIFO eviction ×1
- getBuckets（throw / 空 / 連續 0-count / mean+max latency / outside / endMs clamp）×6
- timeout count ×1
- clear ×1
- helpers (recordSuccess/Error/Timeout) ×1
- 補 1：default maxEvents = 1000

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 73 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 4 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：73 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 328-332 cluster

vitest 2658 → 預期 2731（+73 deterministic）/ tsc 2 pre-existing 不增 / +~1100 行新模組 /
0 行 production 路徑變動。

八輪深推總計（Sprint 298 → 332 / 35 sprints / +459 tests cumulative）：
- ① canvas-editor：sync proxy → bridge → AST prewarm → Proxy patch → font parser → pipeline → prewarm strategy → cache snapshot
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline → union → anchor+dist → text-flow shim
- ④ revision：pure-fn → review session → diff summary → conflict detector → filter view → timeline → exporter
- ⑤ overlay：clamp/align → multi-select → guide session → selection state → keyboard → history stack → executor → touch mapper
- ⑥ worker：single → cluster → pool → health monitor → circuit breaker → load balancer → retry wrapper → metrics collector
