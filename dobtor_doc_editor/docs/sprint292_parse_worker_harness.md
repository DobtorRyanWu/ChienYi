# Sprint 292 — ⑥ Phase 7 Worker parse harness SPIKE ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / OVERRIDE

**日期**：2026-05-27（週三）
**類型**：⑥ cluster — API contract design + MainThread fallback + 12 tests
**OVERRIDE**：user 「繼續執行 1-6」= explicit OVERRIDE（Sprint 197 final audit 判定「不建議」cost vs benefit marginal）

User 指令：「繼續執行 1-6」cluster ⑥（Phase 7 Worker）。

---

## Scope decision

Sprint 197 final audit 判定 Worker 改造**不建議**：
- ChienYi 監造文件實際 20-50p
- cache 五連發已達 ~10× warm path 加速
- worker 改造收益與成本比 marginal

user OVERRIDE = 仍要鋪基礎。本 sprint **不啟動真實 Worker**（structured clone of
DocumentNode AST 含 Map / class instance 風險未解、會擋下游 ImageBitmap cache 等），
改鋪 **API contract + main-thread fallback dispatcher**，為未來實際 Worker 改造
鋪 interface：

| Module | 角色 |
|---|---|
| `parse_worker_protocol.ts` | request / response 訊息型別 + `ParseWorkerDispatcher` interface |
| `ParseWorkerHarness.ts` | Promise-based caller API（parse / cancel / dispose）、timeout、progress |
| `MainThreadDispatcher.ts` | fallback：不啟動 Worker、在 main thread 同步執行（測試 + graceful degrade） |
| `index.ts` | barrel export |

未來實際 Worker 改造：
- `BrowserWorkerDispatcher.ts`（browser `Worker` API）
- `NodeWorkerThreadDispatcher.ts`（node `worker_threads`）

兩者實作此 dispatcher interface，harness API contract 不變、可無痛切換。

---

## 設計細節

### Protocol（[parse_worker_protocol.ts](../static/src/core/ooxml/worker/parse_worker_protocol.ts)）

```typescript
type ParseWorkerRequest =
  | { kind: 'parse'; requestId: string; bytes: Uint8Array | ArrayBuffer; timeoutMs?: number }
  | { kind: 'cancel'; requestId: string };

type ParseWorkerResponse =
  | { kind: 'success'; requestId: string; ast: unknown; parseTimeMs: number }
  | { kind: 'error'; requestId: string; reason: 'parse-error' | 'timeout' | 'unknown'; message: string; stack?: string }
  | { kind: 'progress'; requestId: string; progress: number }
  | { kind: 'cancelled'; requestId: string };
```

requestId 用於對接 in-flight pending requests 與 response（caller 可同時 dispatch 多個 parse）。

### Harness（[ParseWorkerHarness.ts](../static/src/core/ooxml/worker/ParseWorkerHarness.ts)）

```typescript
const harness = new ParseWorkerHarness({
  dispatcher: new MainThreadDispatcher({ parse: (bytes) => parser.parse(bytes) }),
  defaultTimeoutMs: 60_000,
  onProgress: (p) => console.log(`parse ${p * 100}%`),
});

const { ast, parseTimeMs, wallClockMs } = await harness.parse(docxBytes);
// ...
harness.dispose();
```

- timeout：超時自動 cancel + reject
- 並發：多 parse 同時 in-flight、requestId 區隔
- cancel：caller 取消 + worker 端被通知（main-thread fallback 立即 emit cancelled）
- progress：optional callback

---

## 12 unit test 場景（[tests/unit/sprint292_parse_worker_harness.test.ts](../tests/unit/sprint292_parse_worker_harness.test.ts)）

### MainThreadDispatcher（5 案）

| Test | 驗證 |
|---|---|
| parse 成功 | ast + parseTimeMs + wallClockMs 都拿到 |
| sync throw | reject "parse-error" |
| async reject | reject 同樣 |
| 多並發 parse | 各自獨立、結果順序對應 |
| timeout | reject "timeout after Nms" |

### Progress（1 案）

| Test | 驗證 |
|---|---|
| dispatcher emit progress | onProgress callback 收到 |

### Cancel / dispose（2 案）

| Test | 驗證 |
|---|---|
| dispose 進行中 parse | reject "disposed" |
| cancel 不存在 requestId | no-op、不 throw |

### Dispatcher API contract（4 案）

| Test | 驗證 |
|---|---|
| subscribe 回 unsubscribe fn | unsub 後不再收 |
| 多 listener | 全部都收到 |
| listener throw | 不影響其他 listener |
| terminate | listener 清空 + 之後 post 不 emit |

**12/12 passed / 78ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b SPIKE：API contract + fallback + 12 tests、0 行 production parse 接 | ✅ |
| #14.b clean scope：commit 含 4 新 worker module + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：不啟動真實 Worker（browser Worker / node:worker_threads 留 future polish sprint）；不接 OoxmlParser production pipeline | ✅ |
| #21 read-only：harness 為 read-only API、不污染 VR pipeline、不改 layout/render | ✅ |
| #22 verify：5 種 happy / error / timeout / cancel / dispose + 4 種 dispatcher contract edge | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |
| ⑥ OVERRIDE：user「繼續執行 1-6」= explicit override；Sprint 197「不建議」honest 揭露、本 spike 為 future evaluation 鋪基礎 | ✅ |

---

## End of Sprint 292

vitest 2216 → 2228（+12）/ tsc 2 pre-existing 不增 / +~220 行 worker module / 0 行 production parse 接。

---

## 🎉 「繼續執行 1-6」cluster 全清（① ② ③ ④ ⑤ ⑥）

| Sprint | Item | Strategy | +tests |
|---|---|---|---|
| 288 | ① Phase 2.1-2.3 LayoutPipeline 整合 façade | A | +9 |
| (282-287 in prior cluster) | ② Phase 1 optional bucket | mixed | +63 |
| 289 | ③ Phase 3.4 wrapTight 多邊形 capture | A capture-only | +11 |
| 290 | ④ Phase 5.4+5.5 moveFrom/moveTo revision | C+ capture-only | +6 |
| 291 | ⑤ Phase 8.2.2 overlay 幾何工具抽取 | C+ utility extraction | +19 |
| **292** | **⑥ Phase 7 Worker parse harness SPIKE** | **SPIKE / OVERRIDE** | **+12** |
| **合計 1-6** | **5 sprint（① ③ ④ ⑤ ⑥）+ ② 為 6-sprint Phase 1 optional bucket** | | **+120 tests** |

vitest 2155（Sprint 287 起點）→ **2228**（Sprint 292 結尾）= **+73 tests in 5 sprints**
（Sprint 288-292，⑥ 為最後）+ Phase 1 optional bucket 282-287 +63 = 「② + 1-6 全 cluster」+136 tests。

VR 第 68 連 maintained / tsc 2 pre-existing 不增 / 零 regression / 8 commits 全 push。

**STOP for user review**（user 「繼續執行 1-6」cluster 完整完成）。
