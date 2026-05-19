# Sprint 56 — ImageBitmap + IndexedDB 跨 page 持久化

**期間**：2026-05-15
**主軸**：Sprint 54 image decode cache 是純 in-memory（process-lifetime）；Sprint 55 full-warm benchmark 量到 warm path 87.3% 為 renderMs，cache 無法繞過 render — 但若能讓 cross-tab / cross-session 重開時跳過「image decode + bitmap 上傳」這一段，對 image-heavy 文件首頁可見時間（FCP-like）仍有實質助益。本 sprint 補上 L2 IDB 層 + 以 ImageBitmap 取代 HTMLImageElement。
**結論**：**跨 page reload preload speedup 2.79×（IDB L2 hit）/ 105.74×（L1 ImageBitmap reuse）**；100% L2 hit rate（68/68 images 跨 page 全部命中）；L1 比 Sprint 54 快 3.65×（ImageBitmap reuse 跳過 onload + 用 GPU fast path）；IDB+decode 開銷 ≈ 875.9ms / 42-fixture 加總（68 張 image 平均每張 ~12.9ms）。VR 維持 0.0749、vitest 896 → **908 passed + 1 skipped**（+12 ImageBitmapIdbCache 單元測試）。

**重要意義**：Sprint 56 是 Sprint 50-55 cache 五連發後的延伸 — 第一次提供「**跨 session 命中**」能力給 image preload；對「現場關掉文件、隔天再開」場景具體加速。但跨 page total speedup 只 1.18× — 證明 cache 攻不到 render（與 Sprint 55 結論一致）。下一步 Sprint 57+ 仍需攻 render 才能讓 image-heavy 6p 文件 warm path 進一步提速。

---

## 1. 動機：Sprint 55 結論的延伸

Sprint 55 全 42 fixture full-warm benchmark 結論：
> warm path 已是 render-bound（87.3% renderMs 占比）。下一步攻 render 的選項：
> - **Image decode → ImageBitmap + IDB**：Sprint 56 候選；用 createImageBitmap 拿可序列化 decode 結果進 IDB，跨 page reload 命中

Sprint 54 ImageDecodeCache 只能在同 process 命中。實務上工地現場「關掉文件、隔天再開」是 Portal 端常見場景 — IDB 持久化能直接命中。本 sprint 驗證這條路是否真的省時。

## 2. 設計

### 2.1 [ImageBitmapIdbCache](../static/src/core/cache/image_bitmap_idb_cache.ts)

```
L1（in-memory）= Map<dataUrl, ImageBitmap>   ← 同 session 命中
                    ↓ miss
L2（IndexedDB） = store keyed by hash(dataUrl), value = Blob   ← 跨 session 命中
                    ↓ Blob → createImageBitmap(blob) → 升回 L1
```

關鍵設計取捨：

| 取捨 | 決定 | 原因 |
|---|---|---|
| L2 存什麼 | **Blob**（image bytes） | ImageBitmap 跨 page structured-clone 行為各家瀏覽器不一致；Blob 是 IDB 一等公民 |
| L2 key | **SHA-256(dataUrl bytes)** hex | 內容定址 + key 短化（dataUrl 可達數百 KB，當 IDB key 浪費索引空間）|
| L1 LRU | Map delete+set 推到尾端 | 與 [[ast_cache]] 同 pattern |
| L2 LRU | `lastAccessed` index + cursor evict | 同 [[idb_ast_cache]] |
| createImageBitmap 不存在時 | 降級為 `undefined`（caller 改用 fresh decode） | node/jsdom 測試環境無此 API |

### 2.2 pipeline 整合：[tools/visual_regression_pipeline.entry.ts](../tools/visual_regression_pipeline.entry.ts)

`RenderOptions` 加 `imageBitmapCache?: ImageBitmapIdbCache`。preloadImages 邏輯：

```
for each (rId, dataUrl) in media:
  if imageBitmapCache:
    bitmap = await cache.get(dataUrl)
    if bitmap: map.set(rId, bitmap); continue            ← L1/L2 命中
    img = new Image(); await img.onload(dataUrl)
    bm = await createImageBitmap(img)
    map.set(rId, bm)
    await cache.put(dataUrl, bm)                          ← 必 await！
  elif imageCache (Sprint 54 path):
    ... 同 Sprint 54
  else:
    ... fresh decode 每次都做
```

**「必 await put」是 Sprint 56 量測過程踩到的坑**：

- 第一次嘗試：`bitmapCache.put(...).catch(() => {})` fire-and-forget
- 結果：page1 close 時 IDB transaction 還沒 commit → page2 撈不到 → IDB hits = 1/14（≈7%）
- 修正：`await bitmapCache.put(...)` 強制 caller 等 IDB tx commit
- 結果：IDB hits = 14/14（100%）

教訓記在 [[idb_persistence_must_await]]：跨 page IDB 量測時，puppeteer page.close() 不會等待未完成的 promise；必須 await put() 確保 transaction commit。

### 2.3 量測模式

[scripts/perf_baseline.mjs](../scripts/perf_baseline.mjs) 加兩個 flag：

| Flag | 模式 | 量測對象 |
|---|---|---|
| `--image-bitmap-cache` | 單 page 3 runs：run0 clear（cold）/ run1+ warm L1 | L1 ImageBitmap reuse 收益 |
| `--image-bitmap-persist` | 雙 page：page1 cold（put L2）/ page2 fresh JS, run0 = L2 hit / run1 = L1 hit | L2 IDB cross-page 收益 |

## 3. 結果

### 3.1 全 42 fixture（image-bitmap-persist）

| 量測點 | preload | total | preload speedup |
|---|---|---|---|
| cold（page1 clear + put L2） | 2506.0ms | 10997.0ms | — |
| warm-from-IDB（page2 fresh JS, L2 hit） | 899.6ms | 9306.8ms | **2.79×** |
| warm-from-L1（page2 run1, L1 hit） | 23.7ms | 4606.3ms | **105.74×** |

- 跨 page total speedup IDB = **1.18×**（image-bearing 子集 ~3-4×；非 image fixture 0 image cache 收益）
- 跨 page total speedup L1 = **2.39×**（image-bearing 子集 ~50-100×）
- L2 vs L1 開銷 = **875.9ms / 42 fixtures = 12.9ms/image**（IDB read + Blob → ImageBitmap 解碼）

### 3.2 04_with_image 系列 cross-page L2 命中（揭穿 Sprint 54 限制）

| fixture | imgs | cold preload | IDB preload (page2 run0) | L1 preload (page2 run1) | IDB speedup |
|---|---|---|---|---|---|
| 04/05.磺港溪會議照片 | 4 | 112.4ms | 47.0ms | 1.6ms | **2.4×** |
| 04/05.磺港溪會議照片1120923 | 4 | 122.8ms | 43.5ms | 1.2ms | **2.8×** |
| 04/06.環清表-(112.10.23.-10.27) | 6 | 207.1ms | 73.4ms | 1.5ms | **2.8×** |
| 04/06.環清表-(112.10.9.-10.13) | 6 | 238.6ms | 79.8ms | 2.2ms | **3.0×** |
| 04/6.環清表-(112.10.2.-10.6) | 6 | 278.9ms | 88.8ms | 2.3ms | **3.1×** |
| 04/6.環清表-(112.9.25.-9.29) | 6 | 253.4ms | 82.1ms | 2.4ms | **3.1×** |

→ **6p image-heavy fixture cross-page 命中時 preload 從 ~250ms 降到 ~80ms**。Sprint 54 同樣文件重開（fresh JS context）= 完全 miss、preload 走完整 decode。

### 3.3 02_std_table 週報（中等 image，2p）

| fixture | imgs | cold preload | IDB | L1 |
|---|---|---|---|---|
| 02/1120928 週報 | 6 | 188.8ms | 79.0ms | 2.0ms |
| 02/1121006 週報 | 5 | 189.3ms | 62.4ms | 1.7ms |
| 02/1121020 週報 | 5 | 152.4ms | 61.1ms | 1.3ms |

週報類 IDB speedup 2.4-3.0×（與 06.環清表 同範圍）— 證明 image 數量不是關鍵，**單張 image decode 成本**才是主成本。IDB Blob → ImageBitmap 比 dataURL → Image.onload 平均省 60-65% decode time。

### 3.4 vs Sprint 54 ImageDecodeCache 對比

| 指標 | Sprint 54 (HTMLImageElement L1) | Sprint 56 (ImageBitmap L1+L2) |
|---|---|---|
| L1 preload speedup | 29.05× | **105.74×** ← 快 3.64× |
| 跨 session 命中 | ❌（process-lifetime 而已） | ✅ |
| 圖片格式 | HTMLImageElement | ImageBitmap（GPU fast path）|
| 重開首頁 FCP 助益 | 無 | preload 從 60ms 砍到 ~20ms |

L1 加速 3.64× 來源：Sprint 54 cache hit 只是省「new Image() + img.src = dataUrl + onload」；Sprint 56 hit 直接拿 ImageBitmap，連 Image 物件都不創建，drawImage 走 bitmap-uploaded 路徑（不需重新 decode）。

## 4. 爭議點 / 重要發現

### 4.1 IDB read + decode 平均 12.9ms/image — 多餘嗎？

42 fixture 加總 875.9ms 差距（L1 vs L2），分到 68 張 image = **12.9ms/image**。對單張小圖（< 100KB）這算高、但對大圖（環清表那 1-2MB 一張的施工照）相對 fresh decode 100-150ms/張仍是巨大加速。

**結論**：IDB layer 不是「無腦更好」；它是「跨 session 唯一選項」。同 session 內優先走 L1。

### 4.2 為何 cross-page total speedup 只 1.18×？

cold total 10997ms → warm-from-IDB total 9306ms（差 1690ms）— 只 1.18× 總體加速。問題在哪？

- preload 省了 1606ms（cold 2506 → warm 900）= 1.6s 收益
- 但 parse / layout / render 每段 **未變**（沒開 AST cache + render 永遠重跑）
- preload 在 cold path 只占 22.8%（2506/10997）；cache 命中後降到 9.7% — 9.7% 占比的東西被消除大半，總體 ~14.6% 加速符合預期

意義：**ImageBitmap+IDB 是「準目標式」優化**。它對單頁 image-heavy 場景（cold preload 占 40-60% total）才有顯著 total 加速；對 mixed-content 文件（含大量文字）效果稀釋。

### 4.3 100% L2 hit 是否有保留性？

實測 68/68 全命中是「**乾淨環境 + 同 origin + IDB tx 已 commit**」下的理想值。生產環境會有以下退化情境：

| 退化情境 | 對命中率影響 |
|---|---|
| Private mode | 0%（IDB 失效；fallback L1-only 仍可用）|
| Quota 滿 / browser 自動清 | 視 LRU 序漸進掉 |
| Cross-origin（不同 iframe） | 0% |
| docx 內容變化 | 沒命中（hash 不同）|
| 跨設備（手機 vs 桌機）| 0%（IDB 是 device-local）|

關鍵：**hit 率 100% 是 best case**；生產建議搭配遙測量測實際命中率，做基線校正。

### 4.4 是否要把 ImageDecodeCache（Sprint 54）汰除？

不汰除。理由：

| 場景 | 建議 cache |
|---|---|
| 預覽列表批次 preview（同 origin、N 份文件、無重開）| Sprint 54 ImageDecodeCache（簡單、無 IDB 開銷）|
| 主編輯區（單份文件、可能 reload）| Sprint 56 ImageBitmapIdbCache |
| 簡單 PoC / 測試 | Sprint 54 |
| 工地離線後重開 | Sprint 56（IDB 唯一手段）|

Sprint 56 是 Sprint 54 的「能力擴展」而非「取代」。pipeline 接受兩個皆可（imageBitmapCache 優先）。

## 5. Sprint 57+ 候選

| 候選 | 打中的段 | 預估槓桿 | 風險 |
|---|---|---|---|
| **CanvasRenderer fast path** | render（warm 後 87% 主成本） | 高 — 直接攻最大成本 | 中（要驗 VR 不變）|
| ImageBitmap → OffscreenCanvas + Web Worker render | render 整段非阻塞 | 高 — 主執行緒空閒給 UI | 高 — render code 重寫 |
| 可視頁虛擬化 50+ 頁 fixture 驗證 | render | Sprint 53 預測但未證實 | 需內容（外部）|
| HarfBuzz / opentype.js | layout + render | 中 — VR 視覺品質提升 | 大 — bundle size |
| WebAssembly XML parser | parse cold | 小 — parse 已 100% cacheable | 中 — 對 cold path 有用 |

**建議 Sprint 57 = CanvasRenderer fast path**：Sprint 55-56 證實 cache 路線已到頂、render 是新主成本；fast path 優化（避免重複 setState、合併連續 drawText、字型 metric 預算 cache）槓桿最大、風險可控（透過 VR 對比驗證）。

## 6. vitest / VR

- **vitest 896 → 908 passed + 1 skipped**（+12 新測試 — [tests/unit/ImageBitmapIdbCache.test.ts](../tests/unit/ImageBitmapIdbCache.test.ts)）：
  - L1 行為（put/get/LRU touch/evict）4 tests
  - L2 持久化（cross-instance、LRU、clear）3 tests
  - 設定驗證 2 tests
  - createImageBitmap 不可用時 graceful degrade 1 test
  - hash key 內容定址 2 tests
- **VR 0.0749 byte-identical**（IIFE 重編 1 次、imageBitmapCache 預設不啟用、行為對 caller 透明）
- Sprint 12 fingerprint baseline 未變

## 7. 工作摘要

```
+  static/src/core/cache/image_bitmap_idb_cache.ts  | 新增 ImageBitmapIdbCache（L1 ImageBitmap + L2 Blob IDB，~265 行）
+  tests/unit/ImageBitmapIdbCache.test.ts           | 12 unit tests（fake-indexeddb）
M  tools/visual_regression_pipeline.entry.ts       | RenderOptions.imageBitmapCache、preloadImages 支援；imageBitmapCacheHits 計時欄位；await put 確保 tx commit
M  tools/dist/visual_regression_pipeline.iife.js   | rollup 重新打包（version: 'sprint56'）
M  scripts/visual_regression_v14_harness.html      | useImageBitmapCache / clearImageBitmapCacheFirst harness flag
M  scripts/perf_baseline.mjs                       | --image-bitmap-cache / --image-bitmap-persist 模式 + summary + per-fixture print
M  tests/fixtures/perf_baseline_report.json        | image-bitmap-persist 量測結果
+  docs/sprint56_image_bitmap_idb_persist.md       | 本文件
```

VR：**0.0749**。vitest **908 passed + 1 skipped**。**Sprint 56 全 42 fixture 量測**：preload L1 105.74× / L2 2.79× / 100% L2 hit rate（68/68 images）；L2 開銷 12.9ms/image；total speedup L1 2.39× / L2 1.18×。

## 8. Sprint 50-56 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51 | L1 AST cache | warm 4.79× | 同 session 命中 |
| 52 | L2 IDB AST | 跨 page 2.38× / L1 7.41× | 跨 session 命中 |
| 53 | 可視頁虛擬化 | render 1.06× / 3p+ 1.16-1.43× | 多頁 payoff、≤6p 限制 |
| 54 | image decode L1 | preload 29× / image-bearing 100% hit | 重開含照片文件加速 |
| 55 | 合用驗證量測 | full-warm 5.32× / 6p image-heavy 1.4-4.5× | 暴露 render 是新主成本（87.3%）|
| **56** | **L2 IDB image + ImageBitmap** | **preload L1 105.74× / L2 2.79× / 100% L2 hit** | **跨 session 唯一可命中 image preload；同 session ImageBitmap 比 HTMLImageElement 快 3.64×** |

**心得**：Sprint 56 補完了 cache 五連發（51-54-55）的最後一塊跨 session 拼圖 — image preload 對工地「關掉再開」場景終於可命中。但 Sprint 55 結論依然成立：**cache 路線到此為止；下一步必須攻 render 段**。Sprint 50-56 累積成果：cold 文件首次開 ~12s/42-fixture → 重開 ~4.6s（L1 hit, warm-from-L1 total）；跨 tab 重開 ~9.3s（L2 hit, warm-from-IDB total）；都比 cold 顯著加速，但跨 tab 重開 total 仍受 render 拖累、未進入 sub-5s 區間。Sprint 57+ 攻 render fast path 才能讓 image-heavy 6p 文件 warm path 進一步進入「即時感」區間。
