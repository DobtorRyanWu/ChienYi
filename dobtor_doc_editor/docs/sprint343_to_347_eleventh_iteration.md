# Sprint 343-347 — 「繼續執行」honest gap 5 項第十一輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① cache coordinator / ③ multi polygon baseline / ④ revision statistics / ⑤ overlay clipboard / ⑥ worker priority queue
**前置**：十輪深推（Sprint 298-342）

User 指令：「繼續」第十一輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **343** | ① canvas-editor cache coordinator | `CanvasEditorCacheCoordinator.ts` | restore/persist/dirty orchestration（整合 328+333+338） |
| **344** | ③ multi polygon baseline | `multi_polygon_baseline.ts` | 一行避開多 cluster + safe bands + fittable lines |
| **345** | ④ revision statistics | `RevisionStatistics.ts` | net change + author churn + type dist + activity span |
| **346** | ⑤ overlay clipboard | `OverlayClipboard.ts` | copy/cut/paste buffer + 階梯 offset + cut-consume |
| **347** | ⑥ worker priority queue | `WorkerPriorityQueue.ts` | static priority + aging 防 starvation + FIFO tie-break |

---

## Sprint 343 — CanvasEditorCacheCoordinator

Sprint 328 snapshot + 333 lifecycle + 338 warmer 第四層整合。

- `restore(snapshot, valueFactory)` → warm 進內部 cache（不標 dirty）
- `get/set/setByEntry/has` 透傳；set 標 dirty
- `persist(entriesMeta)` → dump 成 snapshot + 清 dirty + persistCount++
- `invalidate/invalidateByPrefix/purgeExpired` 透傳並按需標 dirty
- `isDirty()` + `getStats()`（cache stats + restoredCount/persistCount/dirty）

紀律 #18：`snapshotNow`（string）與 lifecycle `now`（number）刻意分名、避免型別衝突；
不接 storage / production canvas-editor。

### 14 unit tests
- restore（warm + 回數 / 不標 dirty / restoredCount 累計）×3
- set/get dirty + setByEntry keyFor ×2
- persist（dump + 清 dirty / 空 entries）×2
- invalidate（命中 dirty / 未命中不 dirty / prefix dirty）×3
- purgeExpired（注入 now clock 過期清 / 未過期回 0）×2
- round-trip ×1
- 補 1

---

## Sprint 344 — multi_polygon_baseline

Sprint 314 baseline + Sprint 334 multi cluster 之後深推。一行避開多 polygon（OR）。

- `lineBoxHitsAnyPolygon(baselineY, opts)` → 撞任一即 true
- `findSafeBaselineMulti(opts)` → 範圍內找不撞任一的 baseline（全空 → yMin）
- `findSafeBands(opts)` → 連續安全帶 [startY, endY] list
- `countFittableLines(bands, lineHeightPt)` → 估可容納行數

紀律 #18：純函式；OR 邏輯（caller 想 union 先用 Sprint 334）；不接 Paginator real path。

### 17 unit tests
- lineBoxHitsAnyPolygon（撞 / 不撞 / 空 polygon 跳過）×3
- findSafeBaselineMulti（全空 / 都 empty / 上方有圖推下 / 兩圖夾擊中間空檔 /
  範圍不夠 undefined / step<=0 throw）×6
- findSafeBands（全空單段 / 中間有圖切段 / 全擋空 / step<=0 throw）×4
- countFittableLines（單 band / 多 band / lineHeight<=0 / 空）×4

---

## Sprint 345 — RevisionStatistics

Sprint 330 RevisionExportRow 之上算 churn 統計。

- `computeNetChange(rows)` → insertions/deletions/moves/propChanges/net
- `computeAuthorChurn(rows)` → 每作者各計、total 降序、empty → Unknown
- `computeTypeDistribution(rows)` → counts + fractions（佔比）
- `computeActivitySpan(rows)` → earliest/latest（ISO 字典序）+ datedCount
- `buildStatisticsReport(rows)` → 一次算齊四項

紀律 #18：純 array reduce；不接 doc walk；無時區轉換；不做時序 bucket（用 Sprint 325）。

### 17 unit tests
- computeNetChange（ins-del / moves / props / 空）×4
- computeAuthorChurn（每作者+降序 / Unknown / 空）×3
- computeTypeDistribution（計數+佔比 / 空）×2
- computeActivitySpan（最早最晚 / 忽略 empty / 全無 date）×3
- buildStatisticsReport ×1
- 補（共 17）

---

## Sprint 346 — OverlayClipboard

Sprint 316 keyboard copy/cut/paste command 之後補 clipboard buffer model。

- `copy(items)` / `cut(items)` → snapshot 存 buffer、重置 paste 階梯
- `paste()` → 回 { items, pasteIndex, offset, sourceMode, isFirstCutPaste }
- cut 第一次 paste → isFirstCutPaste=true（caller 刪原件）、之後變 copy 行為
- `hasContent / peek / clear / getStats`（copy/cut/paste ops 累計）

紀律 #18：純記憶體；不接系統 clipboard API；payload generic；不接 doc_editor.js real path。

### 18 unit tests
- constructor（pasteStep<0 throw / default 10）×2
- copy/paste（offset 遞增 / copy isFirstCutPaste 永 false / sourceMode / snapshot 隔離）×4
- cut（第一次 true / 第二次 false）×2
- empty（paste null / hasContent）×2
- peek/clear（不影響 count / 回 payload / clear）×3
- 重新 copy/cut 重置（pasteCount 歸零 / cutConsumed 重置）×2
- stats ×1
- 補（共 18）

---

## Sprint 347 — WorkerPriorityQueue

Sprint 307 round-robin pool 之後補 priority queue（含 aging 防 starvation）。

- `enqueue(value, basePriority)` / `dequeue()` → 取最高 effective priority
- 同 priority → FIFO（seq tie-break）
- aging：effective = base + floor(waited/agingIntervalMs)*agingBoost
- `peek / size / isEmpty / clear / getStats`

紀律 #18：純記憶體 model；O(n) dequeue（量大自換 heap）；不接 production worker。

### 16 unit tests
- constructor（aging params<0 throw）×1
- static priority（高先 / 同 FIFO / 預設 0 / 空 undefined）×4
- aging（base 差大不反超 / base 差小反超 / agingBoost=0 純 static）×3
- effectivePriority（無 aging）×1
- peek（不移除 / 空）×2
- size/isEmpty/clear/stats ×3
- 補（共 16）

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 82 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 4 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：82 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 343-347 cluster

vitest 2884 → 預期 ~2966（+82 deterministic）/ tsc 2 pre-existing 不增 / +~1100 行新模組 /
0 行 production 路徑變動。

十一輪深推總計（Sprint 298 → 347 / 50 sprints / +698 tests cumulative）：
- ① canvas-editor：sync proxy → bridge → AST prewarm → patch → font parser →
  pipeline → prewarm strategy → cache snapshot → cache lifecycle → cache warmer →
  cache coordinator
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline → union →
  anchor+dist → text-flow shim → multi-polygon flow → multi-polygon paginator →
  multi-polygon baseline
- ④ revision：accept/reject → review session → diff summary → conflict detector →
  filter view → timeline → exporter → merger → batch action → statistics
- ⑤ overlay：clamp/align → multi-select → guide session → selection state →
  keyboard → history stack → executor → touch mapper → history snapshot →
  accessibility annotator → clipboard
- ⑥ worker：single → cluster → pool → health monitor → circuit breaker → load
  balancer → retry wrapper → metrics collector → alert evaluator → alert cooldown →
  priority queue
