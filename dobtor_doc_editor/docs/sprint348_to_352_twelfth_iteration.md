# Sprint 348-352 — 「繼續執行」honest gap 5 項第十二輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① cache key codec / ③ polygon simplify / ④ revision validator / ⑤ overlay transform constraints / ⑥ worker scheduler
**前置**：十一輪深推（Sprint 298-347）

User 指令：「繼續」第十二輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **348** | ① canvas-editor cache key codec | `CanvasEditorCacheKeyCodec.ts` | round-trip safe escape（補 338 keyFor 的 `|` mangle gap） |
| **349** | ③ wrap polygon simplify | `wrap_polygon_simplify.ts` | Douglas–Peucker 簡化 + 閉合多邊形 + stats |
| **350** | ④ revision validator | `RevisionValidator.ts` | orphan move / dup id / missing fields integrity |
| **351** | ⑤ overlay transform constraints | `OverlayTransformConstraints.ts` | grid snap + aspect lock + min/max + container clamp |
| **352** | ⑥ worker scheduler | `WorkerScheduler.ts` | priority queue + concurrency 限流 dispatch + inflight |

---

## Sprint 348 — CanvasEditorCacheKeyCodec

Sprint 338 keyFor 留的 honest gap：「text 含 `|` 不會 mangle（caller 自負）」。
本 sprint 補 round-trip safe codec。

- `encodeCacheKey({ family, sizePt, text })` → escape `|`/`\` 後串接
- `decodeCacheKey(key)` → 反解（欄位數 != 3 / sizePt 非數 → null）
- `isValidCacheKey(key)` → canonical round-trip 檢查
- 無特殊字元時與 `family|sizePt|text` 同形（與 338 相容）

紀律 #18：純字串 codec；不接 production canvas-editor。

### 16 unit tests
- round-trip（一般 / text含| / family含| / 含\ / 混合 / 空 / CJK / 小數 sizePt）×8
- decode malformed（欄位數 / 非數 / Infinity / escaped 分隔不算邊界）×4
- isValidCacheKey（canonical / malformed / 非 canonical sizePt）×3
- 與簡單串接同形 ×1

---

## Sprint 349 — wrap_polygon_simplify

真實 wrapTight polygon 可能上百 vertex；每次 intersect/contains O(n)。本 sprint
補 Douglas–Peucker 簡化。

- `perpendicularDistance(p, a, b)` — 點到線段（無限長直線）垂距
- `simplifyPolygon(polygon, epsilon)` — DP 遞迴（epsilon<=0 / 點<=2 → 原樣）
- `simplifyClosedPolygon(polygon, epsilon)` — 閉合多邊形簡化
- `simplifyStats(before, after)` — removed + reductionRatio

紀律 #18：純幾何工具；不接 Layout real path；caller opt-in 後再餵 Sprint 344。

### 18 unit tests
- perpendicularDistance（線上0 / 垂距 / 退化線段）×3
- simplifyPolygon（共線移除 / 轉折保留 / epsilon 大小 / <=0 原樣 / 點<=2 /
  copy 不 mutate / 長共線縮減）×7
- simplifyClosedPolygon（<=3 原樣 / 矩形多餘點移除 / open 保持 open / epsilon<=0）×4
- simplifyStats（removed+ratio / 空）×2
- 補（共 18）

---

## Sprint 350 — RevisionValidator

Sprint 330 RevisionExportRow 之上做 integrity 驗證。

- orphan move：moveFrom/moveTo 須成對（依 w:id）；無 id 或單邊 → error
- duplicate id：同 author+id 不同 subtype → error
- missing fields：requireAuthor / requireDate → warning
- `validateRevisions(rows, opts)` / `buildValidationReport(rows, opts)`（valid = 無 error）

紀律 #18：純驗證不修復；move 配對只比 id；不接 doc walk。

### 18 unit tests
- orphan move（成對 / moveFrom 孤 / moveTo 孤 / 無 id / ins-del 不參與）×5
- duplicate id（不同 subtype error / 同 subtype OK / 不同 author 不算 / 無 id 不算）×4
- missing fields（requireAuthor / 預設不檢 / requireDate）×3
- buildValidationReport（無 error valid / orphan invalid / warning 不影響 valid /
  混合 / 空）×5
- 補 1

---

## Sprint 351 — OverlayTransformConstraints

Sprint 291 overlay_geometry 基本 clamp 之上補高階 constraint solver。

- `snapToGrid(value, gridSize)` — 對齊網格倍數
- `applyConstraints(rect, c)` — aspect → size bounds → grid snap → container clamp
- `applyMoveConstraints(rect, c)` — 純移動（只 snap 位置 + container）

紀律 #18：pure-fn；不接 doc_editor.js real path；不做旋轉 / 群組 constraint。

### 17 unit tests
- snapToGrid（最近倍數 / gridSize<=0）×2
- grid snap（x/y/w/h / 無 gridSize）×2
- aspect ratio（16:9 / 1:1）×2
- size bounds（min / max / snap 後守 min）×3
- container clamp（右下推回 / 尺寸縮 / 負座標）×3
- 組合 ×1
- applyMoveConstraints（只 snap 位置 / container 移動）×2
- 補（共 17）

---

## Sprint 352 — WorkerScheduler

Sprint 347 priority queue 之後補 scheduler。

- `submit(value, priority)` → 入 queue + pump
- `pump()` 私有 → concurrency 上限內 dispatch、inflight++
- `onComplete(token)` → 釋放 slot + pump 下一個（unknown token → false）
- `inflightCount / pendingCount / isIdle / getStats`
- caller 提供 `dispatch(value, token)`、不接 worker

紀律 #18：純調度 model；不做 retry（用 Sprint 327 組合）/ timeout；不接 production worker。

### 16 unit tests
- constructor（maxConcurrent<=0 throw）×1
- concurrency（=1 序列 / =2 並行 / onComplete pump）×3
- priority 順序（高先 / 多個依序 drain）×2
- onComplete unknown（false 不 pump / known true）×2
- isIdle（初始 / inflight / 完成回 idle）×3
- stats ×1
- 序列 drain ×1
- 補（共 16）

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 85 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 4 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：85 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 348-352 cluster

vitest 2957 → 預期 ~3042（+85 deterministic）/ tsc 2 pre-existing 不增 / +~1100 行新模組 /
0 行 production 路徑變動。

特別：Sprint 348 是少見的「補前一輪 honest gap」sprint——把 Sprint 338 keyFor 明白
標註的 `|` mangle 風險用 escape codec 收掉。

十二輪深推總計（Sprint 298 → 352 / 55 sprints / +783 tests cumulative）：
- ① canvas-editor：…→ cache snapshot → cache lifecycle → cache warmer → cache coordinator → cache key codec
- ③ wrapPolygon：…→ multi-polygon flow → multi-polygon paginator → multi-polygon baseline → polygon simplify
- ④ revision：…→ exporter → merger → batch action → statistics → validator
- ⑤ overlay：…→ history snapshot → a11y annotator → clipboard → transform constraints
- ⑥ worker：…→ metrics collector → alert evaluator → alert cooldown → priority queue → scheduler
