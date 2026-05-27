# Sprint 303-307 — 「繼續執行」honest gap 5 項第三輪深推 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 五 sprint 合併 doc

**日期**：2026-05-27（週三）
**範圍**：① canvas-editor bridge / ③ wrapPolygon render / ④ review session / ⑤ guide session / ⑥ worker pool
**前置**：Sprint 298+299 第二輪、Sprint 300+301+302 第二輪

User 指令：「繼續執行」honest gap 5 項第三輪深推。

---

## 五 sprint cluster 對齊

| Sprint | Gap | 新模組 | 角色 |
|---|---|---|---|
| **303** | ① LayoutPipeline 未接 canvas-editor | `CanvasEditorMeasureBridge.ts` | Canvas-shape `measureText(text) → { width }` + `prewarmFromAst(doc)` + pt → px 換算（dpi 可覆寫） |
| **304** | ③ wrapPolygon render clip 未做 | `wrap_polygon_render.ts` | `polygonToSvgPath` + `polygonToCanvasCommands` + `applyClipPathToContext` + `polygonWithInflate` |
| **305** | ④ UI accept/reject 面板 未做 | `revision/RevisionReviewSession.ts` | 逐筆 review state machine：current/accept/reject/skip + stats + resetCursor |
| **306** | ⑤ alignment guide visual indicator 未做 | `AlignmentGuideSession.ts` | idle ↔ active 狀態機 + render data：guides + snappedRect + snapX/snapY |
| **307** | ⑥ 真實 dispatcher（pool 層） | `worker/WorkerPoolDispatcher.ts` | Round-robin pool / fan-out subscribe / inflight tracking / terminate fan-out |

---

## Sprint 303 — CanvasEditorMeasureBridge

Sprint 302 PROBE 第二輪深化。Sprint 302 提供 TextMeasureProxy sync/async bridge
解 ctx.measureText sync 與 measureRun async 不相容；本 sprint 補：

1. **Canvas-shape API**：`measureText(text) → { width }`、與 browser native
   ctx.measureText 形狀相容、可 drop-in 取代 canvas-editor 內部呼叫
2. **pt → px 換算**：96 dpi（預設）、192 Retina、72 print 等可 caller 設定
3. **prewarmFromAst(doc)**：遍歷 DocumentNode 自動收集 unique (text, family,
   sizePt) tuples、給 caller 一次 batch prewarm

紀律 #18 scope-down：
- 不接 canvas-editor real path（紀律 #21）
- 只回 `{ width }` 不模擬完整 TextMetrics（caller 真用到時 follow-up extend）

### 11 unit tests
- pt → px 換算（96 / 192 / 72 dpi）×3
- sync measureText（未 prewarm null / prewarm 後 hit）×2
- prewarmFromAst（dedup / table cell 遞迴 / default fallback / 空字串跳過）×4
- stats / clear passthrough ×2

---

## Sprint 304 — WrapPolygon render helpers

Sprint 296 補 polygon math、Sprint 298 LineBreaker 整合；本 sprint 補 render side：

- `polygonToSvgPath`：polygon 點陣列 → `M-L-L-L-Z` SVG path 字串
- `polygonToCanvasCommands`：Path2D-compatible command 序列
- `applyClipPathToContext`：直接設成 Canvas2D clip region（even-odd fill rule）
- `polygonWithInflate`：radial bbox-center 膨脹（caller padding for wrap）

紀律 #18 scope-down：
- 不接 production CanvasRenderer 主路徑（紀律 #21）
- 不支援 Bezier 平滑（OOXML wrapPolygon spec 是線段折線）
- Inflate 用 radial scale（非嚴格 Minkowski sum；對 image wrap polygon 足夠）

### 13 unit tests
- polygonToSvgPath（square / 空 / 單點 / 三角形）×4
- polygonToCanvasCommands（square / 空）×2
- applyClipPathToContext（呼叫 ctx + even-odd / 空 polygon no-op）×2
- polygonWithInflate（delta 0/正/負 / 空 / 單點 dist=0 跳過）×5

---

## Sprint 305 — RevisionReviewSession

Sprint 300 補 accept/reject pure-fn；本 sprint 補 UI-agnostic 逐筆 review session。

API：
```typescript
const session = new RevisionReviewSession(doc);
while (!session.isDone()) {
  const cur = session.current();
  const choice = await uiAskUser(cur);
  if (choice === 'accept') session.acceptCurrent();
  else if (choice === 'reject') session.rejectCurrent();
  else session.skipCurrent();
}
const finalDoc = session.getDocument();
```

紀律 #18 scope-down：
- UI binding 留 future（OWL/React/vanilla 任一 caller 都可消費）
- 不做「一鍵 accept-all」batch（caller loop 或直接呼 Sprint 300 acceptRevisions）
- 不支援 undo/redo（caller wrap session 自管歷史）

### id-based predicate 精準對位
`acceptCurrent` / `rejectCurrent` 用 entry.meta.id 建 predicate、確保只影響當前
這筆 revision 而非全部 type 相符的；多筆同 type 不同 id 場景 verified。

### 9 unit tests
- cursor 推進（current/isDone/stats / done throw）×2
- accept / reject 累積套用（ins/del / mixed accept/reject/skip）×3
- id-based predicate 精準對位 ×1
- resetCursor（cursor 0 / 已 applied 不還原）×1
- 邊界（空 doc / all() 列舉）×2

---

## Sprint 306 — AlignmentGuideSession

Sprint 291/295/301 補 pure-fn 計算；本 sprint 補狀態機 wrapper：idle ↔ active
+ start/update/end + render data。

API：
```typescript
const session = new AlignmentGuideSession({ threshold: 4 });
onDragStart: session.start(initialRect, siblings, pageBounds);
onDragMove:  session.update(rectFollowingMouse);
             view.render(session.getRenderData());
onDragEnd:   session.end();
```

紀律 #18 scope-down：
- 不接 doc_editor.js OWL real path（紀律 #21、同 295/301 政策、避免破 13 E2E）
- 不做 RAF batching（caller 自管 60fps）
- 同 axis 只一條 snap target

### 9 unit tests
- 狀態轉換（初始 idle / start→active+end→idle / idle update no-op）×3
- snap target（page 左邊 / 距離超過 threshold / sibling 對齊）×3
- update 連動（多次 update / end 後 no-op）×2
- guide styles（active 時 buildGuideStyles 產出）×1

---

## Sprint 307 — WorkerPoolDispatcher

Sprint 292/294/299 dispatcher cluster 完整；本 sprint 補 pool 層：

- Round-robin post 派發
- Fan-out subscribe（任一底層 emit → pool listener 全收）
- Inflight tracking（caller backpressure 用）
- Terminate fan-out（先撤底層 subscribe 再 terminate）

紀律 #18 scope-down：
- 純 round-robin（不做 least-busy / least-pending；要 dispatcher 暴露 pending
  count 的 follow-up）
- 不主動 spawn worker（caller 自建傳入）
- 不做 crash recovery（dispatcher fail 由 caller timeout 處理）

### 11 unit tests
- Round-robin（3 dispatcher 4 request 平均 / size=1）×2
- Fan-out subscribe（多 emit / unsubscribe / listener throw 不影響）×3
- Inflight tracking（post 增、response 清）×1
- Terminate（fan-out / post no-op / 不再 emit）×3
- Constructor 驗證（空陣列 throw）×1
- size() ×1

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A/C+ 混合：5 個 pure-fn 或 stateful module + 53 tests | ✅ |
| #14.b clean scope：commit 含 5 新 module + 3 barrel + 5 test + 1 合併 doc | ✅ |
| #18 scope-down：5 sprint 全 scope-down 明列（real-path 不接 / batch 不做 / RAF 不做） | ✅ |
| #21 不污染既有 production：5 個新 module、零 production 路徑變動 | ✅ |
| #22 verify：53 unit tests 覆蓋全 path + 邊界 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 303-307 cluster

vitest 2334 → 2387（+53 deterministic）/ tsc 2 pre-existing 不增 / +~750 行新模組 /
0 行 production canvas-editor / parser / layout / render / doc_editor.js 變動。

5 個 honest gap 第三輪深推完成：
- ① canvas-editor measureText：sync proxy → Canvas-shape bridge + AST prewarm
- ③ wrapPolygon：polygon math → render helpers（SVG path / Canvas clip）
- ④ accept/reject：pure-fn helpers → review state machine
- ⑤ overlay guide：pure-fn 計算 → drag-and-snap session 狀態機
- ⑥ worker dispatcher：single dispatcher cluster → pool 層 round-robin
