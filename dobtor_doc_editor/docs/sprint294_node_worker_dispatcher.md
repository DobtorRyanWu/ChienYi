# Sprint 294 — NodeWorkerThreadDispatcher 真實實作 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A spike

**日期**：2026-05-27（週三）
**類型**：⑥ follow-up — node:worker_threads 真實 dispatcher + 9 tests
**前置**：Sprint 292 ParseWorkerHarness + protocol + MainThreadDispatcher

User 指令：「繼續執行」⑥ honest gap「真實 Browser Worker / node:worker_threads dispatcher 未做」。

---

## 範圍

Sprint 292 鋪了 API contract 與 MainThread fallback；本 sprint 補真實
`node:worker_threads` dispatcher 實作：

| Module | 角色 | Status |
|---|---|---|
| `parse_worker_protocol.ts` | message types + interface | Sprint 292 done |
| `ParseWorkerHarness.ts` | Promise-based caller API | Sprint 292 done |
| `MainThreadDispatcher.ts` | fallback dispatcher | Sprint 292 done |
| **`node_worker_entry.mjs`** | **node worker entry script** | **Sprint 294 新增** |
| **`NodeWorkerThreadDispatcher.ts`** | **真實 worker dispatcher** | **Sprint 294 新增** |
| `BrowserWorkerDispatcher.ts` | browser `Worker` API | future polish sprint |

紀律 #18 scope-down：**actual OoxmlParser inside worker 為 future polish sprint**
（structured clone of DocumentNode 含 Map / class instance 風險未解、會擋下游
ImageBitmap cache）；本 sprint 只跑 stub function（echo / byteLength / sum-bytes）
驗證 worker_threads 接線 + protocol round-trip。

---

## 設計細節

### Worker entry：[node_worker_entry.mjs](../static/src/core/ooxml/worker/node_worker_entry.mjs)

純 JS（無 TS 編譯依賴）、由 `worker_threads.Worker` 直接 spawn。

```javascript
parentPort.on('message', (msg) => {
  if (msg.kind === 'parse') handleParse(msg);
  else if (msg.kind === 'cancel') cancelled.add(msg.requestId);
});
```

workerData 接受：
- `parseStub`: 'echo' | 'byteLength' | 'sum-bytes' — 內建 stub function
- `delayMs`: number — 模擬 parse 耗時（給 timeout / cancel 測試）

回應 protocol 與 Sprint 292 主進程 dispatcher 共用 ParseWorkerRequest/Response 型別。

### Dispatcher：[NodeWorkerThreadDispatcher.ts](../static/src/core/ooxml/worker/NodeWorkerThreadDispatcher.ts)

```typescript
const dispatcher = new NodeWorkerThreadDispatcher({
  parseStub: 'byteLength',
  delayMs: 0,
});
await dispatcher.waitReady();
const harness = new ParseWorkerHarness({ dispatcher });
const { ast, parseTimeMs, wallClockMs } = await harness.parse(bytes);
```

特色：
- **Dynamic import**：`await import('node:module:worker_threads')` 避免 browser bundle 撞 node 模組
- **PendingPosts queue**：caller 在 worker 啟動前 post → queue、worker ready 後 flush
- **onError 觀察**：給上層診斷用
- **waitReady() Promise**：給測試確保 race-free（pendingPosts 也保險）
- **terminate fire-and-forget**：dispose 時 worker terminate 不阻塞 caller

---

## 9 unit test 場景（[tests/unit/sprint294_node_worker_dispatcher.test.ts](../tests/unit/sprint294_node_worker_dispatcher.test.ts)）

### Round-trip（3 案）
| Test | 驗證 |
|---|---|
| byteLength stub | { byteLength: N } + wallClockMs >= parseTimeMs |
| sum-bytes stub | worker 內真實 CPU sum 計算 |
| echo stub | structured-clone Uint8Array 原樣回 |

### Concurrency（1 案）
| Test | 驗證 |
|---|---|
| 多 parse 同時 in-flight | 各自 byteLength 正確、requestId 不串 |

### Timeout / cancel（2 案）
| Test | 驗證 |
|---|---|
| delayMs > timeoutMs | reject "timeout" |
| cancel nonexistent id | no-op |

### Dispose lifecycle（2 案）
| Test | 驗證 |
|---|---|
| dispose 進行中 parse | reject "disposed" |
| dispose 後 post | no-op、不 throw |

### PendingPosts（1 案）
| Test | 驗證 |
|---|---|
| 啟動前 post | waitReady 後 worker 收到、正確回應 |

**9/9 passed / 542ms（含 worker spawn + IPC）**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A spike：真實 worker + 9 tests | ✅ |
| #14.b clean scope：commit 含 2 worker module + 1 index 更新 + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：actual OoxmlParser inside worker 留 future polish；BrowserWorkerDispatcher 留 future | ✅ |
| #21 worker isolation：worker 為 isolated process、不污染 main thread OoxmlParser / VR pipeline | ✅ |
| #22 verify：3 種 stub function + concurrency + timeout + cancel + dispose + pendingPosts | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 294

vitest 2242 → 2251（+9）/ tsc 2 pre-existing 不增 / +~100 行 worker entry .mjs + ~140 行 NodeWorkerThreadDispatcher.ts / 0 行 production parse pipeline 變動。

下一步：Sprint 295 = ⑤ alignment guide visual indicator（user 「繼續執行」honest gap）。
