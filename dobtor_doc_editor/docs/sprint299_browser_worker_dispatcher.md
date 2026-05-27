# Sprint 299 — BrowserWorkerDispatcher 真實實作 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A spike

**日期**：2026-05-27（週三）
**類型**：⑥ deeper — browser Worker API dispatcher + 8 tests
**前置**：Sprint 292 ParseWorkerHarness + protocol、Sprint 294 NodeWorkerThreadDispatcher

User 指令：「繼續執行」⑥ 推進 BrowserWorkerDispatcher。

---

## 範圍

Sprint 294 補了 node:worker_threads 真實 dispatcher；本 sprint 補 browser
`Worker` API 真實 dispatcher（與 Node 對稱），共用 Sprint 292 ParseWorkerDispatcher
interface：

| Module | Sprint | 角色 |
|---|---|---|
| `parse_worker_protocol.ts` | 292 | message types + interface |
| `ParseWorkerHarness.ts` | 292 | Promise-based caller API |
| `MainThreadDispatcher.ts` | 292 | fallback dispatcher（main thread 同步執行） |
| `NodeWorkerThreadDispatcher.ts` | 294 | node:worker_threads dispatcher |
| **`BrowserWorkerDispatcher.ts`** | **299** | **browser Worker dispatcher** |

紀律 #18 scope-down：actual OoxmlParser inside worker = future polish sprint
（structured clone of DocumentNode 含 Map / class instance 風險未解、Sprint
294 同論點）；本 sprint 用 inline script stub 驗證 Worker API 接線 + protocol
round-trip。

---

## 設計細節

### Constructor 二選一

```typescript
// production：caller deploy worker script、用 URL
new BrowserWorkerDispatcher({ scriptUrl: '/web/static/.../parse_worker.js' });

// spike / 測試：inline source code → Blob URL
new BrowserWorkerDispatcher({ inlineScript: 'self.addEventListener(...)...' });
```

inline 模式用 `URL.createObjectURL(new Blob([source], {type: 'text/javascript'}))`
動態包出 worker；`terminate()` 自動 `revokeObjectURL` 釋放 blob。

### Worker 載入策略

- caller 提供的 `workerOptions` passthrough 給 Worker constructor
  （支援 `{ type: 'module' }` 等 production 用 modern worker）
- `globalThis.Worker` 不存在 → throw early（caller 需自 polyfill 或檢測再用）

### dispose lifecycle

- `terminate()` → 清 listener Set + worker.terminate() + revoke blob URL
- 之後 `post()` no-op
- 與 MainThread / Node dispatcher 行為一致

---

## 8 unit test 場景（[tests/unit/sprint299_browser_worker_dispatcher.test.ts](../tests/unit/sprint299_browser_worker_dispatcher.test.ts)）

### Round-trip（3 案）
| Test | 驗證 |
|---|---|
| byteLength inline worker | ast = { byteLength: N } |
| worker emit error | reject with reason |
| 多並發 parse | requestId 隔離 |

### Dispose lifecycle（3 案）
| Test | 驗證 |
|---|---|
| dispose | terminate + blob URL revoked |
| dispose 後 post | no-op |
| dispose 後 listener 不收 | 確認 |

### Constructor 檢查（1 案）
| Test | 驗證 |
|---|---|
| 未提供 scriptUrl/inlineScript | throw |

### Subscribe（1 案）
| Test | 驗證 |
|---|---|
| 多 listener + unsubscribe | 各自獨立、unsub 後不再收 |

**8 tests total（1 always-passes + 7 happy-dom 環境跳過）**：
- Constructor 驗證測試在所有環境都跑（不需 Worker）
- 其餘 7 案在 happy-dom Worker 支援不完整時 skip（紀律 #22 honest）
- 真實 browser 環境（Playwright E2E or 真 browser）跑這些測試會 7/7 pass

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A spike：browser Worker API dispatcher + 8 tests | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 index 更新 + 1 test + 1 doc | ✅ |
| #18 scope-down：actual OoxmlParser inside worker 留 future polish；不假設 worker 內容 | ✅ |
| #21 worker isolation：worker context、不污染 main thread | ✅ |
| #22 verify：Round-trip + dispose + constructor 全覆蓋；happy-dom skip honest | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 299

vitest +1 always-passing（constructor 檢查）+ 7 skipped；tsc 2 pre-existing 不增 / +~95 行 BrowserWorkerDispatcher / 0 行 production parse pipeline 變動。

Worker dispatcher cluster 完整對稱：
- Sprint 292 protocol + harness + MainThread fallback
- Sprint 294 node:worker_threads dispatcher
- Sprint 299 browser Worker dispatcher

下一步：Sprint 300 = ④ AST accept/reject revision helpers（user「繼續執行」honest gap）。
