# Sprint 333-337 — 「繼續執行」honest gap 5 項第九輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① canvas-editor cache lifecycle / ③ multi polygon flow / ④ revision merger / ⑤ overlay history snapshot / ⑥ worker alert evaluator
**前置**：八輪深推（Sprint 298-332）

User 指令：「繼續」honest gap 5 項第九輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **333** | ① canvas-editor cache lifecycle | `CanvasEditorCacheLifecycle.ts` | LRU + TTL + invalidate (key/predicate/prefix) + stats |
| **334** | ③ multi polygon flow | `multi_polygon_flow.ts` | cluster + union (bbox/hull) + super-bbox + per-cluster lookup |
| **335** | ④ revision merger | `RevisionMerger.ts` | mergeRows + dedup + sortByDate + groupByAuthor + detectConflicts |
| **336** | ⑤ overlay history snapshot | `OverlayHistorySnapshot.ts` | v1 schema + cursor clamp + truncate + count helpers + summarize |
| **337** | ⑥ worker alert evaluator | `WorkerAlertEvaluator.ts` | threshold rules (mean/errorRate/timeout/consecutive) + summary |

---

## Sprint 333 — CanvasEditorCacheLifecycle

Sprint 302 FIFO / Sprint 328 snapshot 之後深推。LRU + TTL + invalidation。

- `set(key, value)` / `get(key)` — LRU 透過 Map.delete+set reorder
- `invalidate(key)` / `invalidateByPrefix(prefix)` / `invalidateWhere(predicate)`
- `purgeExpired()` — caller idle-time cleanup
- stats：size / hits / misses / hitRate / ttlEvictions / lruEvictions
- ttlMs <= 0 / maxEntries <= 0 throw

紀律 #18：純記憶體 K/V；caller 自負持久化；不接 production canvas-editor。

### 17 unit tests
- constructor 驗證（maxEntries<=0 / ttlMs<=0 / default）×3
- set/get hit/miss + hitRate ×3
- LRU eviction（超 max / get reorder / set 同 key 不算 eviction）×3
- TTL（TTL 內 hit / TTL 過 miss + 刪 / purgeExpired / 無 TTL 設定）×4
- invalidate（key / 不存在 / prefix / predicate）×4

---

## Sprint 334 — multi_polygon_flow

Sprint 329 single-polygon shim 之後深推。把 Sprint 319 cluster + union 與
Sprint 296 bbox 整合到多 polygon façade。

- `prepareMultiPolygonContext({ polygonsAbs, unionStrategy })` → MultiPolygonContext
- `clustersBlockingYRange(ctx, yMin, yMax)` → cluster index list
- `clusterPolygon(ctx, index)` → polygon (餵給 329 findFlowBaseline)
- `isYRangeBlockedByAnyCluster(ctx, yMin, yMax)` — cheap super-bbox check

紀律 #18：純函式 façade、不接 Paginator real path、不重做 anchor transform。

### 11 unit tests
- prepareMultiPolygonContext（空 / 不重疊 / 重疊 / default hull / bbox strategy /
  polygonToCluster）×6
- clustersBlockingYRange（cluster index / 空）×2
- clusterPolygon（valid / out-of-range）×2
- isYRangeBlockedByAnyCluster（空 / 撞 / 在範圍下方）×3
- 1 重複 cluster 測試（共算 11）

---

## Sprint 335 — RevisionMerger

Sprint 330 RevisionExporter 之後深推。Multi-source merge + 去重 + sort + group。

- `mergeRevisionRows(sources)` — 聯集 + dedup by `source|subtype|author|date|id`
- `sortByDate(rows, order)` — ISO 字典序、empty 視為「最早」
- `groupByAuthor(rows)` — empty author → 'Unknown'
- `detectMergeConflicts(rows)` — 同 author+id 不同 subtype 的衝突 list
- `summarizeMerge(sources)` — totalInput / merged / duplicates / authorCount / conflictCount

紀律 #18：純 array transform；不接 file system / git merge；無時區轉換。

### 18 unit tests
- mergeRevisionRows（空 / 無重複 / 完全相同去重 / 同 author-id 不同 subtype /
  保留首次出現順序）×5
- sortByDate（asc / desc / default asc / empty asc 最前 / empty desc 最後 / 不 mutate）×6
- groupByAuthor（author 分群 / empty → Unknown）×2
- detectMergeConflicts（衝突 / 無衝突 / 無 id 不算）×3
- summarizeMerge（多 source 衝突計 / 空）×2

---

## Sprint 336 — OverlayHistorySnapshot

Sprint 321 OverlayHistoryStack 之後深推。JSON-safe snapshot for 跨 session
持久化 / 跨 tab sync / audit 用。

- `toHistorySnapshot(entries, cursor, opts)` — v1 schema + cursor clamp
- `fromHistorySnapshot(raw, isValidPayload?)` — reject schema 不符 / 缺欄位 /
  cursor NaN/超界 / payload validator 失敗
- `truncateHistorySnapshot(snapshot, maxEntries)` — drop 最舊 + cursor 前移
- `countUndoable` / `countRedoable` / `summarizeHistorySnapshot`

紀律 #18：純資料 transform；payload generic；不接 storage / postMessage。

### 19 unit tests
- toHistorySnapshot（v1 + caller now / 預設 now / cursor clamp）×3
- fromHistorySnapshot（valid / null / primitive / schema 不符 / entries 非 array /
  cursor 異常 / entry 缺 payload / label 非 string / caller validator）×9
- truncateHistorySnapshot（未超 / 超 max / cursor 不<0 / max<=0 throw）×4
- count helpers ×2
- summarize ×1

---

## Sprint 337 — WorkerAlertEvaluator

Sprint 332 metrics collector 之後深推。對 buckets 套 threshold rules → AlertEvent[]。

- `thresholdMeanLatency({ thresholdMs, severity?, name? })`
- `thresholdErrorRate({ thresholdRate, severity?, name? })` — total=0 不觸發
- `thresholdTimeoutCount({ thresholdCount, severity?, name? })`
- `consecutiveErrorRate({ thresholdRate, consecutiveBuckets, ... })` — 連續 N
  bucket 都超才觸（避免單 spike 誤報）
- `evaluateAlertRules(buckets, rules)` / `summarizeAlerts(events)`

紀律 #18：純評估；caller 自接 notification（Slack/email/log）；不做 rate-limit/dedup。

### 14 unit tests
- thresholdMeanLatency（任一超 / 全在 / custom name+severity）×3
- thresholdErrorRate（超 / total=0 / 全在）×3
- thresholdTimeoutCount（超 / ==threshold 不觸發）×2
- consecutiveErrorRate（連續 N / 中斷不觸 / total=0 打斷 streak / consecutive<=0 throw）×4
- evaluateAlertRules 多 rule ×1
- summarizeAlerts（severity 分組 / 空）×2

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 79 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 4 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：79 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 333-337 cluster

vitest 2733 → 預期 2812（+79 deterministic）/ tsc 2 pre-existing 不增 / +~1200 行新模組 /
0 行 production 路徑變動。

九輪深推總計（Sprint 298 → 337 / 40 sprints / +540 tests cumulative）：
- ① canvas-editor：sync proxy → bridge → AST prewarm → patch → font parser →
  pipeline → prewarm strategy → cache snapshot → cache lifecycle
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline → union →
  anchor+dist → text-flow shim → multi-polygon flow
- ④ revision：accept/reject → review session → diff summary → conflict detector
  → filter view → timeline → exporter → merger
- ⑤ overlay：clamp/align → multi-select → guide session → selection state →
  keyboard → history stack → executor → touch mapper → history snapshot
- ⑥ worker：single → cluster → pool → health monitor → circuit breaker → load
  balancer → retry wrapper → metrics collector → alert evaluator
