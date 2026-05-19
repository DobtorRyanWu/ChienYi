# Sprint 64b — Portal/canvas-editor font 供應 infrastructure（Strategy B）

**期間**：2026-05-16
**主軸**：Sprint 64 audit §4.2 列 Sprint 64b 為 external resource、需 user 認可 Strategy A/B/C；user 選 B（portal lazy load + IDB cache）。本 sprint 建立 backend controller + frontend FontLoader module + unit tests，**誠實定位**為「未來自家 pipeline migrate production 時的 font 供應 infrastructure」。
**結論**：
- ✅ Backend：`/dobtor/fonts/<family>` HTTP endpoint serve LO 系統字型 bytes（DroidSansFallback + LiberationSerif）+ `/dobtor/fonts/list` discovery endpoint
- ✅ Frontend：`static/src/core/font_loader.ts` — IDB cache hit / miss-then-fetch / registerFont 到 FontMetricsAdapter；9 unit tests（fake-indexeddb + fetch mock）全綠
- ✅ vitest **976 passed + 1 skipped**（+9 FontLoader 測試、967 → 976）
- ✅ VR 0.073191 不變（Sprint 65 baseline 保持）；IIFE rebuild 含 FontMetricsAdapter + FontLoader（FontLoader 只在 caller 需要時 import）
- ⚠️ **誠實定位**：目前 production `doc_editor.js` 走 `window["canvas-editor"].Editor`、**不直接使用本 module**；本 sprint 是「未來 migrate 自家 pipeline production rendering 時的 caller-side font 供應 infrastructure」

---

## 1. 範圍

Sprint 60-65 audit 一直建議 Sprint 64b commit 後「production user 看到 -1.7% VR 改善」。Sprint 64b 開工前用戶問清楚架構，發現 production 走 canvas-editor、不走自家 pipeline。誠實修正定位後仍做這個 sprint，原因：
1. **infrastructure 是低風險、可重用 building block**：backend endpoint + IDB cache 機制本身無爭議
2. **future-ready**：當 ChienYi 將來決定自家 pipeline 取代 canvas-editor 時，無需再建這層
3. **Sprint 60-65 的 VR baseline 與 production caller 連結**：caller 啟用 fontAdapter（用本 FontLoader 載 fonts）時、實際 render 對齊 VR baseline 0.073191

## 2. 設計

### 2.1 Backend：[`controllers/font_serve.py`](../controllers/font_serve.py)

```python
FONT_PATH_MAP = {
    "Times New Roman": ".../LiberationSerif-Regular.ttf",
    "Arial": ".../LiberationSans-Regular.ttf",
    "標楷體": ".../DroidSansFallbackFull.ttf",
    "微軟正黑體": "...",
    "新細明體": "...",
    # ...
}

@http.route("/dobtor/fonts/list", type="json", auth="public")
def list_fonts(self):
    # 回傳可用 family + URL + size

@http.route("/dobtor/fonts/<string:family>", type="http", auth="public")
def serve_font(self, family, **kwargs):
    # URL-decoded family → FONT_PATH_MAP lookup → 回 TTF bytes
    # Cache-Control: public, max-age=31536000, immutable
    # Access-Control-Allow-Origin: *
```

Design decisions：
- **`auth="public"`**：fonts 非機密、不需登入；簡化 CORS（portal user / internal user / 訪客都可用）
- **1 年 immutable cache**：fonts 不變、瀏覽器 cache + IDB cache 雙重命中
- **family 與 visual_regression_v14.mjs 一致**：對齊 Sprint 62 已驗證的 LO fallback font set

### 2.2 Frontend：[`static/src/core/font_loader.ts`](../static/src/core/font_loader.ts)

```ts
export async function loadFontsAndBuildAdapter(
  families: string[],
  opts?: { endpoint?, adapter?, fetchTimeoutMs? }
): Promise<FontMetricsAdapter> {
  // 對每 family 並行 IDB cache 或 fetch
  // 成功 → adapter.registerFont(family, bytes)
  // 失敗 → silent fallback（family 未註冊、pipeline fallback EstimateMetrics）
}
```

關鍵設計：
- **silent fallback per family**：任一 family 載入失敗不影響其他 family
- **IDB schema 與 ast_cache / image_bitmap_idb_cache 分離**：`dobtor-font-cache` DB / `fonts` store
- **caller-injected adapter**：vitest mock 可注入；正式使用通常讓 module 自己 new
- **fetchTimeoutMs 10s**：避免慢網路阻塞整個 render

### 2.3 Caller-side usage（未來 migrate 時）

```ts
// 自家 pipeline production caller（hypothetical, 未來）
import { loadFontsAndBuildAdapter } from './core/font_loader';

async function renderDocx(docxBytes, container) {
  // 1. lazy load fonts（第一次跨網路、之後 IDB hit）
  const adapter = await loadFontsAndBuildAdapter([
    '標楷體', 'Times New Roman', 'Arial',
    '微軟正黑體', '新細明體',
  ]);

  // 2. 注入 pipeline render（fontAdapter 不傳 → fallback EstimateMetrics）
  return pipeline.render(docxBytes, container, { fontAdapter: adapter });
}
```

## 3. 三層 SOP 驗證

### 3.1 vitest

新增 [`tests/unit/FontLoader.test.ts`](../tests/unit/FontLoader.test.ts) — 9 unit tests（fake-indexeddb + fetch mock）：
- IDB miss → fetch → 註冊 adapter → 存 IDB
- IDB hit → 跳過 fetch
- fetch 404 / error → silent fallback
- 多 family 並行
- clearFontCache 重置
- caller 注入 adapter
- CJK family URL-encode 正確
- 自訂 endpoint

執行結果：vitest **976 passed + 1 skipped**（從 967 +9 FontLoader）。

### 3.2 VR

VR 不動：default 0.073191（Sprint 65 baseline）— 因為 FontLoader 是 caller-side module、VR pipeline 走自己的 `--font-metrics` 路徑（直接 readFileSync）、不經 FontLoader。

### 3.3 IIFE bundle

rollup 重編成功；FontMetricsAdapter 已在 bundle 內（Sprint 62 IIFE 修復）。FontLoader 不需進 bundle — 因為 VR pipeline 不用它，production caller 才會 import。

## 4. 為何不直接整合進 doc_editor.js

Sprint 64b 開工發現 [doc_editor.js:280](../static/src/components/doc_editor/doc_editor.js#L280)：
```js
this.editor = new EditorConstructor(container, initialData, editorOptions);
```
這是 `window["canvas-editor"].Editor`、不是 `__dobtorPipeline.render()`。

若硬加 `await loadFontsAndBuildAdapter(...)` 到 `_initCanvasEditor()`：
- canvas-editor 沒有 fontAdapter API、bytes 無處用
- 增加 boot 時間 + IDB IO、產品行為不變、純損失
- 違反 Sprint 57 教訓（unit ≠ 整合 ≠ production）

**正確路徑**：Sprint 64b 只做 infrastructure；當 ChienYi 將來決策 migrate 自家 pipeline 時、再加 caller-side `await loadFontsAndBuildAdapter(...)`。

## 5. Sprint 50-64b 軌跡

| Sprint | 類型 | 關鍵成果 |
|---|---|---|
| 50-58 | perf cache 八連發 | warm 7.01× |
| 59 | drawLine path coalescing | 邊際遞減 |
| 60 | OffscreenCanvas probe | 純診斷 GREEN |
| 61 | BrowserTextMetrics negative | 揭示 goldens = LO anchor |
| 62 | FontMetricsAdapter + IIFE bundle 修復 | VR -0.0017 第一次打進 |
| 63 | per-fixture delta | 0 regression > 0.001 |
| 64 | baseline drift probe | page+ops 0/42、fp 42/42（Y 平移）|
| 65 | VR baseline commit 0.074899 → 0.073191 | mechanical commit |
| **64b** | **portal font 供應 infrastructure（Strategy B）** | **Backend controller + Frontend FontLoader + 9 tests；ready for future migrate** |

## 6. Sprint 66+ 候選（不變）

- 🟡 **重生 goldens 用 Word desktop 渲染**：換 metric anchor（副作用大）
- 🟡 **OffscreenCanvas + Web Worker render**：Sprint 60 probe 已證實可行
- 🟡 **大文件 fixture 50+ 頁**：待 user 提供
- 🔴 **Migrate doc_editor.js 從 canvas-editor 到自家 pipeline**：策略決策、scope 大、超出單 sprint 範圍

## 7. 工作摘要

```
+  controllers/font_serve.py                       | Backend：/dobtor/fonts/list + /dobtor/fonts/<family> Odoo controller
M  controllers/__init__.py                         | import font_serve
+  static/src/core/font_loader.ts                  | Frontend：loadFontsAndBuildAdapter + IDB cache + fetch + silent fallback
+  tests/unit/FontLoader.test.ts                   | 9 unit tests（fake-indexeddb + fetch mock）
M  tools/dist/visual_regression_pipeline.iife.js   | rollup 重編（無新內容、本 sprint 改的 FontLoader 不進 VR bundle）
+  docs/sprint64b_font_supply_infrastructure.md    | 本文件
```

vitest **976 passed + 1 skipped**（+9 FontLoader tests）；VR **0.073191 不變**（Sprint 65 baseline 保持）。

## 8. 心得：誠實定位避免「打到不該打的目標」

Sprint 60-65 audit 連續 6 個 sprint 暗示「promote default-on 後 production user 看到 -1.7%」。Sprint 64b 開工發現 production 走 canvas-editor、不走自家 pipeline、Sprint 60-65 的 VR 改善只對「未來自家 pipeline migrate」這條 hypothetical 路徑生效。

如果硬把 Sprint 64b 做成「production caller 立刻啟用」：
- 加 `await loadFontsAndBuildAdapter(...)` 到 doc_editor.js `_initCanvasEditor()`
- canvas-editor 拿不到 fontAdapter、bytes 浪費
- 產品行為不變 + boot 時間增加 = **負收益**

User 選「仍做、但誠實定位為未來 migrate 準備 infrastructure」是正確的：
- backend endpoint 是 reusable building block（任何 caller 將來需要 fonts 都可用）
- FontLoader module 是標準介面（caller 載 fonts 的單一入口）
- 9 unit tests 鎖定 IDB cache + fetch fallback 行為

**比硬硬硬做、卻發現 production 沒接到 +更便宜**。

**新紀律補充（Sprint 64b 第 8 條）**：
> **架構發現的 sprint 也要記下來** — Sprint 60-65 audit 都假設 production 走自家 pipeline；Sprint 64b 開工前 grep doc_editor.js 才發現走 canvas-editor。**架構認知與假設不符時、優先誠實定位 sprint scope、而非硬做**。
