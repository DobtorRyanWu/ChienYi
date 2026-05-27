# Sprint 323-327 — 「繼續執行」honest gap 5 項第七輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-28（週四）
**範圍**：① prewarm strategy / ③ polygon anchor resolver / ④ revision timeline / ⑤ overlay executor / ⑥ worker retry
**前置**：六輪深推（Sprint 298-322）

User 指令：「繼續執行」honest gap 5 項第七輪深推。

---

## 五 sprint cluster

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **323** | ① canvas-editor prewarm heuristic | `CanvasEditorPrewarmStrategy.ts` | 3 strategies（top-frequency / family-whitelist / charset）+ classifyCharset |
| **324** | ③ polygon anchor + dist margin | `wrap_polygon_anchor.ts` | inflateByDistMargins / resolveAnchorPolygon / inflateAbsolutePolygon |
| **325** | ④ revision timeline | `RevisionTimelineBuilder.ts` | 3 granularity（day/hour/author-day）+ unknown bucket + summarize |
| **326** | ⑤ overlay command + history 整合 | `OverlayCommandExecutor.ts` | 整合 311+316+321、handleKey/dispatch/recordToHistory |
| **327** | ⑥ worker retry + backoff | `WorkerRetryWrapper.ts` | Retryable reasons + exponential backoff + inflight tracking |

---

## Sprint 323 — CanvasEditorPrewarmStrategy

Sprint 303 prewarmFromAst + Sprint 318 pipeline 之後深推。問題：整 doc 的 unique
(text, family, sizePt) 三元組可能成千上萬筆；caller 在記憶體 / 啟動延遲限制下
需要 heuristic 選 prewarm 子集。

- `collectPrewarmCandidates(doc, ...)` → 全集 + frequency + charset
- `byTopFrequency(c, n)` → 取 top N
- `byFontFamilyWhitelist(c, list)` → 過濾 family
- `byCharsetClassification(c, charsets)` → 過濾 charset
- `classifyCharset(text)` → 'cjk' / 'latin' / 'mixed' / 'empty'

### 16 unit tests
- classifyCharset（CJK / Latin / mixed / empty / non-ASCII non-CJK）×5
- collectPrewarmCandidates（frequency 累計 / 多 bucket / default fallback / charset 推測）×4
- byTopFrequency（top N / undefined / n<=0）×3
- byFontFamilyWhitelist（filter / 空 whitelist）×2
- byCharsetClassification（filter / 空 charsets）×2

---

## Sprint 324 — wrap_polygon_anchor

Sprint 296/298/304/309/314/319 polygon 系列第七輪深推。把 image-coords polygon
加上 dist margin（Sprint 287 AnchorMetadata 中的 distT/distB/distL/distR）→
真實 wrap-avoid 區域。

- `inflateByDistMargins(polygon, dist)` → bbox-relative remap
- `resolveAnchorPolygon(WrapPolygon, imageRect, dist)` → transform + inflate
- `inflateAbsolutePolygon(absolute, dist)` → 已 transformed 的 fast path
- `totalHorizontalMargin` / `totalVerticalMargin` helpers

### 10 unit tests
- inflateByDistMargins（全 0 / 單軸 / 四方 / 空 / degenerate）×5
- resolveAnchorPolygon（含 distR / 全 0）×2
- inflateAbsolutePolygon fast path ×1
- total margin helpers ×2

---

## Sprint 325 — RevisionTimelineBuilder

Sprint 300/305/310/315/320 revision 系列第六輪深推。

API：
- `buildTimeline(doc, { granularity, order })` → TimelineBucket[]
- 3 granularity：'day' / 'hour' / 'author-day'
- `summarizeTimeline(buckets)` → { totalBuckets, hasUnknown, earliestDate, latestDate }

紀律 #18 scope-down：
- date 用 ISO string 比較（不轉 Date 物件、避免時區歧異）
- 不展開 inline diff
- 不做 sliding window

### 12 unit tests
- day granularity（同日 / 不同日 / asc order）×3
- hour granularity（同日不同 hour / 無 hour fallback）×2
- author-day granularity（不同 author / 無 author=Unknown）×2
- unknown date（缺 date / 解析失敗）×2
- 邊界 ×1
- summarizeTimeline（含數據 / 空）×2

---

## Sprint 326 — OverlayCommandExecutor

Sprint 291/295/301/306/311/316/321 overlay 第七輪深推。整合三模組：

- SelectionState（311）：當前 selection ids
- KeyboardCommands（316）：key event → OverlayCommand
- HistoryStack（321）：undo/redo with generic payload

提供 `handleKey(event)` / `dispatch(command)` 單一 API、回 ExecutorAction：
- `'apply'`：caller 套用 command（recordable=true 表示已記 history）
- `'apply-from-history'`：undo/redo 對應 entry
- `'noop'`：無事

特性：
- `clear-selection` 自動執行（動 SelectionState）
- `undo` / `redo` 自動處理（autoHandleUndoRedo=true）
- `payloadFactory` 由 caller 提供 → 自動 push history

### 15 unit tests
- handleKey dispatch（delete / 無 selection noop / arrow nudge）×3
- clear-selection 自動執行 ×1
- undo/redo（hasEntry / 空 history / Mod+Shift+Z redo）×3
- payloadFactory（自動 push / 回 null 不 push / 沒 factory）×3
- recordToHistory 外部觸發 ×1
- platform 差異（Mac Cmd / PC Ctrl / Mac Ctrl noop）×3
- autoHandleUndoRedo=false（Mod+Z 變 apply command）×1

---

## Sprint 327 — WorkerRetryWrapper

Sprint 292/294/299/307/312/317/322 worker 第七輪深推。Wrap dispatcher、
transient error 自動重試 + exponential backoff。

- `maxAttempts`（預設 3）
- `baseBackoffMs`（100）/ `maxBackoffMs`（5000）
- `retryableReasons`（預設 ['parse-error', 'timeout', 'cancelled']）
- `schedule` 可注入（測試用 sync scheduler）
- inflight tracking + clearStats

紀律 #18 scope-down：
- 純記憶體 retry state
- 不做 jitter（caller 自行包）
- 不做 circuit-breaker（用 Sprint 317 組合）

### 11 unit tests
- success direct propagate ×1
- retryable error 重試（最終成功 / 用完 attempts 最終失敗）×2
- non-retryable error 直接 propagate ×1
- exponential backoff（公式 / maxBackoffMs cap）×2
- inflight tracking ×1
- unknown requestId 不追蹤 ×1
- terminate fan-out（給底層 / post no-op）×2
- clearStats（保留 inflight）×1

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 64 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 3 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列 | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：64 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 323-327 cluster

vitest 2594 → 預期 2658（+64 deterministic）/ tsc 2 pre-existing 不增 / +~1000 行新模組 /
0 行 production 路徑變動。

七輪深推總計（Sprint 298 → 327 / 30 sprints / +386 tests cumulative）：
- ① canvas-editor：sync proxy → bridge → AST prewarm → Proxy patch → font parser → pipeline → prewarm strategy
- ③ wrapPolygon：math → LineBreaker → render → paginator → baseline → union → anchor+dist
- ④ revision：pure-fn → review session → diff summary → conflict detector → filter view → timeline
- ⑤ overlay：clamp/align → multi-select → guide session → selection state → keyboard → history stack → executor
- ⑥ worker：single → cluster → pool → health monitor → circuit breaker → load balancer → retry wrapper
