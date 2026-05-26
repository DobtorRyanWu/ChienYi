# Sprint 280 — ShapingFontChain：fetch + fallback chain wire-up ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Phase 2.1-2.3 cluster 第 2/3

**日期**：2026-05-26（週二）
**類型**：Strategy A production code 擴張 / 紀律 #18 scope-down（不重造 IDB cache、不接 canvas-editor）
**規畫書對應**：§Phase 2.1 字型載入器（browser 端）
**前置**：Sprint 279 setHbModuleLoader（ShapingEngine 已 caller-injectable）

---

## Hypothesis & Result

**hypothesis**：browser/Node 通用的 fetch + fallback chain helper、第一個成功就
register 到 ShapingEngine。和 Sprint 64b font_loader.ts（canvas-editor 路徑 +
IDB cache）互補不重疊。

**結論**：**verified、8/8 unit test 包含 fetch mock / fallback / timeout /
empty / CJK helper / e2e measureRun**。

---

## API 設計

### 新增（在 `font/ShapingFontChain.ts`、~150 行）

```typescript
export interface ShapingFontChainEntry {
  family: string;
  url: string;
}

export interface LoadShapingFontWithChainOptions {
  engine: ShapingEngine;
  primary: ShapingFontChainEntry;
  fallbacks?: readonly ShapingFontChainEntry[];
  timeoutMs?: number;          // 預設 10000
  fetchImpl?: typeof fetch;    // 測試用注入
  warn?: (msg: string) => void;
}

export interface LoadShapingFontResult {
  loadedAs: string;            // = primary.family（即使實際載入 fallback）
  loadedFrom: ShapingFontChainEntry;
  bytes: Uint8Array;
  attemptedCount: number;
}

export class FontChainExhaustedError extends Error { ... }

export async function loadShapingFontWithChain(
  opts: LoadShapingFontWithChainOptions,
): Promise<LoadShapingFontResult>;

export function getDefaultCjkFallbackChain(
  urlBuilder: (family: string) => string,
): readonly ShapingFontChainEntry[];
```

### 關鍵設計

| 決策 | 為何 |
|---|---|
| 純 fetch、不做 IDB cache | Sprint 64b font_loader.ts 已有 IDB cache 走 canvas-editor 路徑；Sprint 280 不重疊。caller 想要 cache 可外包一層 |
| Register under `primary.family`（不是 fallback 真實 family） | shape() caller 端 RunProps.fontFamily 不變、不需知 fallback 替換（Sprint 157/166 既有行為） |
| fetchImpl 注入 | 測試友好、避免 mock global.fetch；caller 可注入自訂 cache 層 |
| AbortController + timeoutMs | 慢 endpoint 不阻塞 fallback；單 fetch timeout 後視為失敗試下個 |
| Empty chain（只有 primary）失敗 → 仍 throw FontChainExhaustedError | 統一錯誤路徑、caller 可 try/catch 一處 |

---

## 8 unit test

| Test | 驗證 |
|---|---|
| Primary 200 → register、不試 fallback | attemptedCount=1、warn 未呼叫 |
| Primary 404 → fallback、register under primary.family | attemptedCount=2、warn 含 primary+fallback 名 |
| 全 chain 失敗 → FontChainExhaustedError | 含 primary + fallbacks + errors 陣列 |
| Empty fallbacks + primary 失敗 → throw | 統一錯誤路徑 |
| fetchImpl 缺省 + global.fetch undefined → 顯式 throw | caller 收到清楚錯誤 |
| Timeout 30ms < slow fetch 100ms → abort → fallback 接管 | AbortController + signal handling 正確 |
| getDefaultCjkFallbackChain helper → ['思源黑體', '微軟正黑體', '新細明體'] + urlBuilder 被呼叫 | Sprint 166 既有 chain 重現 |
| End-to-end smoke：load + measureRun | 5 glyphs / widthPt > 0 |

**8/8 passed / 217ms**。

---

## 與 Sprint 64b font_loader.ts 的分工

| 維度 | Sprint 64b `font_loader.ts` | Sprint 280 `ShapingFontChain.ts` |
|---|---|---|
| Adapter target | FontMetricsAdapter（canvas-editor） | ShapingEngine |
| Cache 層 | IDB（dobtor-font-cache store） | 無（caller 自行包） |
| Endpoint | 寫死 `/dobtor/fonts/<family>`（Odoo） | URL 由 caller 傳 |
| CJK chain | 寫死、由 fontTable.charset 自動觸發 | 由 caller 傳；helper `getDefaultCjkFallbackChain` 可取預設 |
| 用途 | 既有 canvas-editor 流程 lazy load | Phase 6 Layout 自寫 + browser shape 路徑 |
| Production wire-up | 未直接走（Sprint 64b honest note） | 同 — caller-side infrastructure |

**兩者互補不重疊**、紀律 #21：不修 Sprint 64b、不擴張到 canvas-editor。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：production code 擴張 ~150 行 ShapingFontChain.ts + index.ts barrel | ✅ |
| #14.b clean scope：commit 含 ShapingFontChain.ts + barrel + 1 unit test + 1 doc | ✅ |
| #18 scope-down：不做 IDB cache、不擴張到 canvas-editor、不寫死 endpoint | ✅ |
| #21 audit 不 touch Sprint 64b font_loader.ts / VR / 既有測試 | ✅ |
| #22 verify：unit test 8/8、含 fetch mock + abort + e2e smoke 為硬數據 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通；browser e2e 整合留 Sprint 281 | ✅ |

---

## End of Sprint 280

**Phase 2.1-2.3 cluster 第 2/3 完成**：browser/Node 通用 fetch chain + register
到 ShapingEngine。

vitest 2099 → 2107 hypothesis（+8 Sprint 280 unit test）/ VR 第 68 連 maintained。

下一步：Sprint 281 opentype.js browser-side wire-up + e2e browser spike
（含 setHbModuleLoader + loadShapingFontWithChain + opentype.js metrics 完整路徑）。
