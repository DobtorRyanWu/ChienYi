# Sprint 353-357 — 「繼續執行」honest gap 5 項第十三輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① cache namespace / ③ polygon metrics / ④ revision sessionizer / ⑤ overlay z-order / ⑥ worker batch coalescer
**前置**：十二輪深推（Sprint 298-352）

User 指令：「繼續」第十三輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **353** | ① canvas-editor cache namespace | `CanvasEditorCacheNamespace.ts` | 多 doc 分區（codec 348 + lifecycle 333 組合） |
| **354** | ③ wrap polygon metrics | `wrap_polygon_metrics.ts` | area / centroid / perimeter / winding direction |
| **355** | ④ revision sessionizer | `RevisionSessionizer.ts` | author + time-gap 分 edit session |
| **356** | ⑤ overlay z-order | `OverlayZOrder.ts` | bring-to-front/back/forward/backward + normalize |
| **357** | ⑥ worker batch coalescer | `WorkerBatchCoalescer.ts` | window 收集 + maxBatchSize / 手動 flush |

---

## Sprint 353 — CanvasEditorCacheNamespace

Sprint 333 lifecycle + Sprint 348 codec 之後深推。多 doc cache 分區。

- `nsKey(namespace, parts)` → `namespace::<encoded>`；ns 含 `::` throw
- `parseNsKey(key)` → 反解（首個 `::` 為分隔、encoded 含 `:` 不影響）
- `invalidateNamespace(cache, ns)` → lifecycle prefix 失效
- `nsSet / nsGet` 便利包裝；`groupKeysByNamespace(keys)` 計數

紀律 #18：ns 不可含 `::`；不接 production canvas-editor；cache 不列舉 key（caller 提供集合）。

### 17 unit tests
- nsKey/parseNsKey（round-trip / text含| / ns含:: throw / 無:: null / decode 失敗 /
  encoded 含: 不影響）×6
- namespacePrefix ×1
- nsSet/nsGet（取回 / 不同 ns 隔離）×2
- invalidateNamespace（只清指定 / 不存在 0）×2
- groupKeysByNamespace（計數 / 非 ns 忽略 / 空）×3
- 補（共 17）

---

## Sprint 354 — wrap_polygon_metrics

polygon 基礎幾何度量、給排序 / clip 方向統一用。

- `signedArea`（shoelace、正 CCW 負 CW）/ `area`（絕對）
- `perimeter` / `centroid`（面積加權、退化 fallback 算術平均）
- `windingDirection`（ccw / cw / degenerate）/ `ensureWinding`（不是則反轉）
- `computeMetrics`（一次算齊）

紀律 #18：簡單多邊形假設（非自交）；不處理帶洞；不接 Layout real path。

### 18 unit tests
- signedArea/area（CCW 正 / CW 負 / 絕對 / 點<3 / 三角形）×5
- perimeter（正方形 40 / 點<2 / 3-4-5）×3
- centroid（正方形中心 / CW 一樣 / 退化 fallback / 空 / 三角形）×5
- windingDirection（ccw / cw / degenerate）×3
- ensureWinding（已是 / 反方向 / 退化 / 不 mutate）×4 - computeMetrics ×2（合 18）

---

## Sprint 355 — RevisionSessionizer

Sprint 325 timeline + Sprint 345 statistics 之後深推。author + time-gap 分 session。

- `sessionize(rows, { gapMs })` → EditSession[]（同 author 連續、gap <= threshold 同 session）
- date 轉 epoch ms（不可解析 → undated session）
- empty author → 'Unknown'；不跨 author 合併
- `summarizeSessions(sessions)` → totalSessions / per-author / largestSessionSize

紀律 #18：純函式分群；date parse via Date.parse；不接 doc walk。

### 11 unit tests
- sessionize（間隔小同 / 間隔大切 / 不同 author / 排序 / Unknown / undated /
  恰好等於 gap 同 session / 空 / 預設 5min）×9
- summarizeSessions（統計 / 空）×2

---

## Sprint 356 — OverlayZOrder

overlay item z-order 管理（對應 OOXML relativeHeight）。

- `add / remove`；`bringToFront / sendToBack / bringForward / sendBackward`
- `zIndexOf`（0=底）/ `orderedIds`（copy）/ `normalize`（0..n-1 連續）/ `has`
- 邊界：已在頂/底 forward/backward → no-op 但回 true；不存在 → false

紀律 #18：純 id 排序 model；caller 對應 relativeHeight；不接 doc_editor.js real path。

### 19 unit tests
- constructor（保留順序 / 去重 / 空）×3
- add/remove（頂層 / 已存在 no-op / remove true / false）×4
- bringToFront/sendToBack（移末 / 移首 / 不存在 false）×3
- bringForward/sendBackward（上移 / 已頂 no-op / 下移 / 已底 no-op / 不存在）×5
- zIndexOf/normalize/has ×4
- 連續操作 ×1（合 19）

---

## Sprint 357 — WorkerBatchCoalescer

Sprint 352 scheduler 之後補 batch coalescing。

- `add(item)` → 達 maxBatchSize 立即 auto-flush
- `addAll(items)` → 可觸發多次 flush + 留 pending
- `flush()` 手動（空 → no-op）；`discard()` 丟棄不 flush
- caller 提供 onFlush(batch)；stats item/flush/autoFlush

紀律 #18：純收集/flush 邏輯；caller 提供 onFlush + flush timer；不做 per-item priority。

### 12 unit tests
- constructor（maxBatchSize<=0 throw）×1
- add auto flush（達上限 / 未達 / 連續多次）×3
- addAll（多 flush + pending）×1
- 手動 flush（flush pending / 空 no-op）×2
- discard ×1
- stats ×1
- 補（共 12）

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 77 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 4 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：77 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 353-357 cluster

vitest 3034 → 預期 ~3111（+77 deterministic）/ tsc 2 pre-existing 不增 / +~1000 行新模組 /
0 行 production 路徑變動。

十三輪深推總計（Sprint 298 → 357 / 60 sprints / +860 tests cumulative）：
- ① canvas-editor：…→ cache warmer → cache coordinator → cache key codec → cache namespace
- ③ wrapPolygon：…→ multi-polygon baseline → polygon simplify → polygon metrics
- ④ revision：…→ batch action → statistics → validator → sessionizer
- ⑤ overlay：…→ clipboard → transform constraints → z-order
- ⑥ worker：…→ priority queue → scheduler → batch coalescer
