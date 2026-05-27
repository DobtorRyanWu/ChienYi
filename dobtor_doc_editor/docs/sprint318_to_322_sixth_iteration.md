# Sprint 318-322 — 「繼續執行」honest gap 5 項第六輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① canvas pipeline / ③ polygon union / ④ revision filter / ⑤ overlay history / ⑥ worker load balancer
**前置**：Sprint 298+299, 300+301+302, 303-307, 308-312, 313-317 共五輪深推

User 指令：「繼續執行」honest gap 5 項第六輪深推。

---

## 五 sprint cluster 對齊

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **318** | ① canvas-editor 整合層 | `CanvasEditorPipeline.ts` | resolver + bridge + ctx 整合 drop-in API（`measureWithCtxFont`） |
| **319** | ③ polygon union | `wrap_polygon_union.ts` | bbox 聯集 / convex hull / overlap 偵測 / cluster 分組 |
| **320** | ④ revision filter | `RevisionFilter.ts` | preview view + status marking + predicate factories（byAuthor / byIds / idBefore） |
| **321** | ⑤ overlay history | `OverlayHistoryStack.ts` | generic undo/redo 棧 + listener + maxEntries eviction |
| **322** | ⑥ worker load balancer | `WorkerLoadBalancer.ts` | 3 strategies（least-inflight / lowest-p95 / lowest-error-rate）+ round-robin tie-break |

---

## Sprint 318 — CanvasEditorPipeline

Sprint 303 bridge + Sprint 308 patch + Sprint 313 resolver 三者整合為單一 API：

```typescript
const pipeline = new CanvasEditorPipeline(engine.measureRun.bind(engine));
await pipeline.prewarmFromAst(doc, 'DejaVu Sans', 12);
ctx.font = "14pt 'Noto Sans CJK TC', sans-serif";
const m = pipeline.measureWithCtxFont(ctx, 'Hello');  // 一行搞定
```

紀律 #18 scope-down：
- 仍是 PROBE / caller 顯式呼叫
- 不快取 ctx.font 解析結果
- 不依 font.style / font.weight 影響 bridge cache key

### 10 unit tests
- 基本 hit / miss / fallback 控制 ×3
- ctx.font 解析失敗 fallback ×2
- 多 ctx.font 切換獨立 cache ×1
- measureSync / measureAsync passthrough ×2
- stats + clear ×2

---

## Sprint 319 — wrap_polygon_union

Sprint 296/298/304/309/314 polygon 系列第六輪深推。多 polygon union：

- `unionBoundingBox`：N polygon bbox 聯集 → 矩形 polygon
- `unionConvexHull`：Andrew's monotone chain → convex hull
- `polygonsOverlap`：bbox 快篩 + rect/polygon 雙向檢查
- `clusterByOverlap`：union-find 分群（彼此重疊 → 同組）

紀律 #18 scope-down：
- 不做精準 Vatti / Greiner-Hormann Boolean union
- convex hull 不保 polygon order

### 18 unit tests
- unionBoundingBox（多 / 空 / 全 empty / 單 polygon）×4
- unionConvexHull（兩矩形 / 空 / <3 點 / 共線去中間 / 重複點 dedup）×5
- polygonsOverlap（明顯交 / 不交 / 空 / 內含）×4
- clusterByOverlap（兩重疊+一獨立 / 全獨立 / 全重疊 / 空 / 鏈式 union-find）×5

---

## Sprint 320 — RevisionFilter

Sprint 300/305/310/315 revision 系列第五輪深推。

差異於 acceptRevisions（mutation）：filter view 是 **preview-only** — caller 看
「若 accept Alice、會長什麼樣」但不變動 doc，每個 revision 標 status：
will-accept / will-reject / pending。

API：
- `filterView(doc, { acceptIf?, rejectIf? })` → entries 含 status
- `summarizeFilterView(entries)` → { total, willAccept, willReject, pending }
- `previewAccepted(doc, predicate)` → 直接套用、新 DocumentNode
- Predicate factories：`predicateByAuthor` / `predicateByIds` / `predicateIdBefore`

紀律 #18 scope-down：
- filterView 不展開 inline diff
- 不做 partial accept

### 12 unit tests
- filterView（無 predicate / acceptIf / rejectIf / accept 優先）×4
- summarizeFilterView ×2
- previewAccepted（套用 + immutability）×2
- predicate factories（3 種）×3
- 邊界 ×1

---

## Sprint 321 — OverlayHistoryStack

Sprint 291/295/301/306/311/316 overlay 第五輪深推。Generic undo/redo 棧。

特性：
- Caller-defined payload（generic `<P>`）
- push 後丟棄 cursor 之後 redo 路徑（不允許分支歷史）
- maxEntries FIFO eviction
- subscribe listener（push / undo / redo / clear events）
- peek 不移動 cursor

紀律 #18 scope-down：
- 不接 doc_editor.js OWL real path（紀律 #21）
- 不做 transaction batch
- 不持久化

### 14 unit tests
- 初始 + push（初始狀態 / push 後 cursor）×2
- undo/redo cycle（push x2 + undo + undo + redo / 無 undo / 無 redo）×3
- push 丟棄 redo 路徑 ×1
- maxEntries eviction ×1
- peek（不移動 / 空 stack）×2
- clear ×1
- subscribe events（4 種 emit / unsubscribe / listener throw）×3
- position ×1

---

## Sprint 322 — WorkerLoadBalancer

Sprint 292/294/299/307/312/317 worker 第六輪深推。Smart pool 基於
`WorkerHealthMonitor` stats 選 worker。

策略：
- `least-inflight`：選 inflight 最少
- `lowest-p95`：選 p95 latency 最低
- `lowest-error-rate`：選 errorRate 最低

Tie-break：多 monitor 同分時 round-robin（caller 可關）。

紀律 #18 scope-down：
- 純基於 HealthMonitor stats（caller 必須先 wrap dispatcher）
- 不做加權組合
- 不做動態 worker 增刪

### 11 unit tests
- least-inflight（peek / 多 post 分配）×2
- lowest-p95 ×1
- lowest-error-rate ×1
- tie-break round-robin（on / off）×2
- fan-out subscribe ×1
- terminate fan-out（all monitors / post no-op）×2
- constructor 驗證 ×1
- getMetrics ×1

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 65 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 3 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：65 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 318-322 cluster

vitest 2529 → 預期 2594（+65 deterministic）/ tsc 2 pre-existing 不增 / +~900 行新模組 /
0 行 production canvas-editor / parser / layout / render / doc_editor.js / paginator 變動。

5 個 honest gap 第六輪深推完成（總計六輪 / 25 sprints / +322 tests cumulative）：
- ① canvas-editor：sync proxy → bridge → AST prewarm → Proxy patch → font parser → pipeline 整合
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline → union
- ④ revision：pure-fn → review session → diff summary → conflict detector → filter view
- ⑤ overlay：clamp/align → multi-select → guide session → selection state → keyboard → history stack
- ⑥ worker：single → cluster → pool → health monitor → circuit breaker → load balancer
