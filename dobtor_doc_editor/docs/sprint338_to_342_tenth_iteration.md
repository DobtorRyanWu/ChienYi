# Sprint 338-342 — 「繼續執行」honest gap 5 項第十輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① cache warmer / ③ multi polygon paginator / ④ revision batch action / ⑤ overlay a11y / ⑥ worker alert cooldown
**前置**：九輪深推（Sprint 298-337）

User 指令：「雙驗之後繼續」第十輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **338** | ① canvas-editor cache warmer | `CanvasEditorCacheWarmer.ts` | snapshot → lifecycle seeder + keyFor + footprint predict |
| **339** | ③ multi polygon paginator | `multi_polygon_paginator.ts` | 多 cluster × 多頁切割 + spread map + per-page stats |
| **340** | ④ revision batch action | `RevisionBatchAction.ts` | dry-run plan + apply + predicate composition (and/or/not) |
| **341** | ⑤ overlay accessibility annotator | `OverlayAccessibilityAnnotator.ts` | selection → ARIA + command → announcement + summary |
| **342** | ⑥ worker alert cooldown | `WorkerAlertCooldown.ts` | rule+severity cooldown + suppressed/passed stats + purge |

---

## Sprint 338 — CanvasEditorCacheWarmer

Sprint 328 CacheSnapshot + Sprint 333 CacheLifecycle 串成 seeder。

- `keyFor(entry)` → `family|sizePt|text` 標準化 key
- `warmFromSnapshot(cache, snapshot, valueFactory)` → 回實際寫入數
- `exportLifecycleAsEntries(cache, entries)` → 反向 dump 成 PrewarmEntryWithMeta
- `predictWarmFootprint(snapshot, cacheMaxEntries)` → caller 預估 kept/dropped

紀律 #18：generic value type；caller 自負 valueFactory 與 keyFor 對齊。

### 11 unit tests
- keyFor（format / 含 | 不 mangle）×2
- warmFromSnapshot（seed 全部 / maxEntries LRU 驅逐 / valueFactory / 空 snapshot）×4
- exportLifecycleAsEntries（簡單 dump / 帶 charset / 空）×3
- predictWarmFootprint（全留 / 部分丟 / cacheMax=0 全丟）×3 - 1 重複（共算 11 含 round-trip）
- round-trip 場景 ×1

---

## Sprint 339 — multi_polygon_paginator

Sprint 309 paginator + Sprint 334 multi flow 之後深推。多 cluster × 多頁切割。

- `splitMultiPolygonAcrossPages(ctx, pages)` → 二維 `[page][cluster]` 子 polygon
- `summarizePagesClusters(sliced)` → 每頁 active cluster index list
- `clustersOnPage(sliced, pageIndex)` → 該頁所有 active cluster polygons（copy）
- `clusterPageSpread(sliced)` → Map<clusterIndex, pageIndexes[]>

紀律 #18：純函式整合層、不接 Paginator real path。

### 11 unit tests
- splitMultiPolygonAcrossPages（2x2 / 空 cluster / 空 pages / 順序保留）×4
- summarizePagesClusters（active index / 全空）×2
- clustersOnPage（active polygons / out-of-range / 回 copy 不 mutate）×3
- clusterPageSpread（跨頁 / 單頁）×2

---

## Sprint 340 — RevisionBatchAction

Sprint 300 accept/reject 之上做 dry-run plan + predicate composition + summary。

- `planBatch(doc, mode, predicate?)` → BatchPlan { affected, bySource, totalAffected }
- `applyBatch(doc, mode, predicate?)` → DocumentNode
- `andP / orP / notP` 合 predicate
- `byAuthor / byId / byIdSet / byRunType` 常用 factory
- `summarizePlan(plan)` → hasRunRevisions / hasPropChanges / hasCellRevisions

紀律 #18：純函式 planner；plan 與 apply 都需要 caller 傳相同 predicate（不在
plan 內保存）。

### 18 unit tests
- planBatch（全 / predicate / 空）×3
- applyBatch（accept ins / reject del / predicate 過濾）×3
- predicate composition（andP / orP / notP / byId / byIdSet / byRunType 0 命中）×6
- summarizePlan（runRevision / pPrChange）×2
- 補（共 18）

---

## Sprint 341 — OverlayAccessibilityAnnotator

Selection state + keyboard command → ARIA attributes / screen reader 文字。

- `ariaForSelection(state)` → role + aria-label（空 / 1 image / textbox / shape /
  group / unknown / 多選）
- `ariaForItem(item)` → role + label
- `announcementForCommand(command)` → 純英文 announcement（caller 自負 i18n）
- `summarizeSelectionA11y(state)` → hasImage / hasTextFrame / description with plural

紀律 #18：pure-fn；不接 DOM ARIA attribute 套線。

### 19 unit tests
- ariaForSelection（空 / 1 image / image 無 label / textbox / figure / group /
  unknown / 多選）×8
- ariaForItem（label override）×1
- announcementForCommand（10 種 command）×6
- summarizeSelectionA11y（空 / mixed plural / 1 shape 單數）×3
- 1 預留（共 19）

---

## Sprint 342 — WorkerAlertCooldown

Sprint 337 evaluator 之後深推。同 rule+severity cooldown N ms 抑制重複 alert。

- `filter(events)` → 通過的 events list（cooldown 內者 suppressed）
- `isInCooldown(ruleName, severity)` → 純 query、不更新 state
- `purgeExpired()` → 主動清過期 key、回清掉數
- `reset()` → 全清
- stats：passed / suppressed / activeKeys

紀律 #18：純記憶體；caller 自負 notification 接線；不做指數 cooldown / 不接
production worker。

### 14 unit tests
- constructor（cooldownMs<=0 throw / default 60000）×2
- filter（第一次通過 / cooldown 內 suppressed / cooldown 過重新 / 不同 severity 不同 key /
  不同 ruleName 不同 key / 空 input）×6
- isInCooldown（未通過 / 在 cooldown / 過期 / query 不更新 state）×4
- purgeExpired ×1
- reset ×1

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

## End of Sprint 338-342 cluster

vitest 2815 → 預期 2888（+73 deterministic）/ tsc 2 pre-existing 不增 / +~1100 行新模組 /
0 行 production 路徑變動。

十輪深推總計（Sprint 298 → 342 / 45 sprints / +616 tests cumulative）：
- ① canvas-editor：sync proxy → bridge → AST prewarm → patch → font parser →
  pipeline → prewarm strategy → cache snapshot → cache lifecycle → cache warmer
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline → union →
  anchor+dist → text-flow shim → multi-polygon flow → multi-polygon paginator
- ④ revision：accept/reject → review session → diff summary → conflict detector
  → filter view → timeline → exporter → merger → batch action
- ⑤ overlay：clamp/align → multi-select → guide session → selection state →
  keyboard → history stack → executor → touch mapper → history snapshot →
  accessibility annotator
- ⑥ worker：single → cluster → pool → health monitor → circuit breaker → load
  balancer → retry wrapper → metrics collector → alert evaluator → alert cooldown
