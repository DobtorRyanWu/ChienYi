# Sprint 302 — TextMeasureProxy canvas-editor sync/async bridge PROBE ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A PROBE

**日期**：2026-05-27（週三）
**類型**：① deeper — sync proxy + caller pre-warm PROBE + 8 tests
**前置**：Sprint 265 ShapingEngine.measureRun()、Sprint 269/275 Phase 2 Exit、Sprint 277 LineBreaker MVP

User 指令：「繼續執行」① 推進 LayoutPipeline ↔ canvas-editor 整合鋪基礎。

---

## 範圍

Sprint 297 audit doc 揭示「LayoutPipeline 未接 canvas-editor、ctx.measureText
sync 與 measureRun async 不相容」honest gap。本 sprint PROBE 一個 **sync proxy
+ caller pre-warm pattern** 來解：

```
caller pre-warm (async)：proxy.prewarm([(text, family, sizePt), ...])
  → 每筆呼叫 engine.measureRun 並寫進內部 Map

canvas-editor sync 呼叫：proxy.measureSync(text, family, sizePt)
  → cache hit 回 widthPt（轉 px 後直接給 ctx）
  → cache miss 回 null（caller 自行 fallback 到 ctx.measureText）
```

PROBE 範圍（紀律 #18 scope-down）：
- ❌ 不接 canvas-editor 真實 measureText override（caller 顯式呼叫才生效）
- ❌ 不取代 ctx.measureText（紀律 #21、避免破現有 canvas-editor 路徑）
- ❌ 不解決「不知道要 prewarm 哪些字串」問題（caller 決策）
- ✅ 提供 production-grade 雙模式 API + LRU/FIFO eviction
- ✅ stats（hit / miss / hitRate）為 future 量測 Phase 2 Exit ④ cache 條件用

---

## 設計細節

### MeasureRunFn injection

```typescript
const proxy = new TextMeasureProxy(engine.measureRun.bind(engine));
```

不直接 import ShapingEngine（避免 cycle 與 over-coupling）；type signature 對齊
`measureRun(text, family, sizePt) → Promise<RunMetrics>`。

### Cache key

`${family}|${sizePt}|${text}` — 同 Sprint 266 Glyph cache 規格、key collision
不可能（pipe 字元在 family / size 路徑為非法字元）。

### FIFO eviction

Map 保證 insertion order、超過 maxEntries 時刪第一個 key（紀律 #18 同 Sprint 266
Glyph cache scope-down、不做完整 LRU 因為 production 量測未證實 LRU 收益）。

### 為何 sync 不能在 cache miss 觸發 async fetch

canvas-editor 的 ctx.measureText 是同步、用於 reflow 路徑（input event 內逐字
測寬決定 cursor 位置）。同步 caller 拿不到 Promise 結果、回 null 是唯一 honest
選項；caller 自行決定 fallback（用 ctx.measureText 估、或推遲渲染等 prewarm 完成）。

### 紀律 #18 scope-down 細項

- 不支援 letter-spacing / kerning 後處理（measureRun 已包含 HarfBuzz 級 kerning）
- 不嘗試自動拆字 prewarm（caller 比 proxy 更懂自己 layout 需要哪些字串）
- 不接 canvas-editor real path（紀律 #21、避免破 13 Playwright E2E）

---

## 8 unit test 場景（[tests/unit/sprint302_text_measure_proxy.test.ts](../tests/unit/sprint302_text_measure_proxy.test.ts)）

### prewarm + measureSync（3 案）
| Test | 驗證 |
|---|---|
| 未 prewarm → null | sync 不副作用 |
| prewarm 後 measureSync hit | cache entry 結構正確 |
| 不同 family / sizePt 獨立 cache key | 3 種變體 |

### measureAsync（1 案）
| Test | 驗證 |
|---|---|
| 動態 warm | 首次 measure + 二次 cache hit |

### FIFO eviction（1 案）
| Test | 驗證 |
|---|---|
| 超過 maxEntries=2 | 第 3 筆寫入時最舊 evict |

### stats（1 案）
| Test | 驗證 |
|---|---|
| hits / misses / hitRate | 數字精確、hitRate 浮點 |

### clear（1 案）
| Test | 驗證 |
|---|---|
| clear 後 cache 空 + stats 歸零 | 完整 reset |

### prewarm dedup（1 案）
| Test | 驗證 |
|---|---|
| 重複 key 不重 measure | 假 measureRun 計次 |

**8/8 passed / 6ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A PROBE：sync proxy + pre-warm pattern + 8 tests | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 barrel + 1 test + 1 doc | ✅ |
| #18 scope-down：不接 canvas-editor real path / 不取代 ctx.measureText / FIFO 不 LRU | ✅ |
| #21 不污染既有 canvas-editor 路徑：caller 顯式呼叫才生效 | ✅ |
| #22 verify：prewarm + measureSync + FIFO + stats + clear 全覆蓋 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 302

vitest +8 / tsc 2 pre-existing 不增 / +~110 行 TextMeasureProxy.ts + ~5 行 barrel /
0 行 production canvas-editor 變動。

Sprint 300-302 cluster 完整：
- Sprint 300 ④ AST accept/reject pure-fn（14 tests）
- Sprint 301 ⑤ overlay multi-select / resize-by-handle（21 tests）
- Sprint 302 ① canvas-editor measureText proxy PROBE（8 tests）

vitest 2290 → 2333（+43 deterministic、+7 環境 skip 維持）。

下一步：user「繼續執行」honest gap 第三輪深推（depends on user 是否要繼續）。
