# Sprint 15 圖片真渲染 + 揭露 layout pagination 為下一瓶頸

**狀態**：W11+ 主線 Sprint 15 — 影像 pipeline 接通 + 第二份 baseline（揭露隱形 layout 問題）
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §0.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint14_visual_regression.md](sprint14_visual_regression.md)

---

## 1. 範圍

Sprint 14 audit doc §8 列建議優先 1：**圖片真渲染**（drawImage no-op → 接 OoxmlPackage `word/media/`），預期降 04_with_image diff 8-10%。

Sprint 15 把 image pipeline 從 `BrowserCanvasRenderContext` 一路接到 entry。**結果出乎預期**：04_with_image diff 從 0.2606 升至 **0.4850**。

下文先說做了什麼、為何成功（image pipeline 真的通了），再說為何 diff 反而升（揭露原本被 no-op 隱藏的 layout / pagination divergence）。

---

## 2. 落地檔案

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `tools/visual_regression_pipeline.entry.ts` | M | render 改 async；新增 `preloadImages()` pre-load `documentNode.media`（rId → dataURL → HTMLImageElement Map）；BrowserCanvasRenderContext 餵入 `imageResolver` |
| `scripts/visual_regression_v14_harness.html` | M | `__bootDobtorPipeline` 改 async；status 文字顯示 imagesLoaded 數 |
| `tools/dist/visual_regression_pipeline.iife.js` | M（重編） | 仍 ~578KB；無新依賴 |

**核心改動**：

```ts
// preload async（render 內，paint 前）
async function preloadImages(media: Map<string, string>) {
  const map = new Map<string, HTMLImageElement>();
  const errors: string[] = [];
  const tasks: Promise<void>[] = [];
  for (const [rId, dataUrl] of media) {
    const img = new Image();
    const task = new Promise<void>((resolve) => {
      img.onload = () => { map.set(rId, img); resolve(); };
      img.onerror = () => { errors.push(rId); resolve(); }; // 不 reject
    });
    img.src = dataUrl;
    tasks.push(task);
  }
  await Promise.all(tasks);
  return { map, errors };
}

// caller 端
const { map: imageMap, errors } = await preloadImages(documentNode.media);
const imageResolver = (rId: string) => imageMap.get(rId);
const browserCtx = new BrowserCanvasRenderContext(ctx2d, { scale, imageResolver });
```

**驗證 image pipeline 通**：
- 04_with_image / 05.112磺港溪監造會議照片.docx：4 images 全部 `onload` 成功，`imageErrors=[]`
- 渲染 PNG 從 ~40KB（純文字）變 ~474KB（含照片內容）
- 視覺確認：照片真的畫在 canvas 上

---

## 3. Baseline 變化（Sprint 14 → Sprint 15）

`scripts/visual_regression_v14.mjs --max-diff 1.0` 全 42 fixtures：

| 類別 | Sprint 14 mean | Sprint 15 mean | Δ | 解讀 |
|---|---|---|---|---|
| 01_simple | 0.1152 | **0.1152** | 0 | 無內嵌圖片，不受影響 |
| 02_std_table | 0.2187 | **0.2674** | +0.049 | 含少量 logo/圖示，painting 後位置差 |
| 03_complex_table | 0.2281 | **0.2943** | +0.066 | 同上 |
| 04_with_image | 0.2606 | **0.4850** | **+0.224** | 大量照片，且 pagination 差 |
| 05_header_footer | 0.0504 | **0.0504** | 0 | 無內嵌圖片，不受影響 |
| 06_template | 0.0325 | **0.0325** | 0 | 無內嵌圖片，不受影響 |
| **總計** | **0.1291** | **0.1773** | **+0.048** | |

**為何 diff 升而非降**：

Sprint 14 的「drawImage no-op」實際上是把圖片區塊留白。pixelmatch 之下：
- golden 的圖片區塊：彩色照片
- 我們的圖片區塊：純白
- → 該區塊全部 pixel 「不同」，但只占整頁 ~25%

Sprint 15 接通後：
- golden 的圖片區塊：彩色照片，position (X, Y, W, H)
- 我們的圖片：彩色照片，但 position 偏移或 page break 不同
- → 該區塊 pixel 仍大量不同（位置 / 大小 mismatch），且**現在不只圖片區塊不同——任何因為 image 推擠而連帶位移的文字也跟著不同**

**揭露的真實問題**：5 / 6 個 04_with_image fixture 的 page count 不對：

| Fixture | 我們 pages | golden pages | Δ |
|---|---|---|---|
| 05.112磺港溪監造會議照片.docx | 2 | 2 | 0 |
| 05.112磺港溪監造會議照片1120923-1121001.docx | 2 | 2 | 0 |
| 06.環清表安全衛生抽查照片(再造)-(112.10.23.-10.27).docx | 3 | **6** | **-3** |
| 06.環清表安全衛生抽查照片(再造)-(112.10.9.-10.13).docx | 3 | **6** | **-3** |
| 6.環清表安全衛生抽查照片(再造)-(112.10.2.-10.6).docx | 3 | **6** | **-3** |
| 6.環清表安全衛生抽查照片(再造)-(112.9.25.-9.29).docx | 3 | **6** | **-3** |

我們把 6 頁 golden 內容塞進 3 頁。當 pixelmatch 拿「我們的 p1 對 golden p1」「我們的 p2 對 golden p2」「我們的 p3 對 golden p3」時，比對的根本是不同內容。

**這個問題在 Sprint 14 被 no-op drawImage 隱藏了**：當 pages 都是白底時，「我們的 p3 全白 vs golden p3 全白」反而 diff 低；現在我們真的畫圖了，「p3 我們畫照片 X vs golden p3 是照片 Y」全部不同。

---

## 4. 關鍵設計決策

### 4.1 為何 pre-load 而非 lazy

`CanvasRenderer.render` → `BrowserCanvasRenderContext.drawImage` 是**同步**的。imageResolver 拿到的必須是已 decode 的 HTMLImageElement，否則 `canvas2d.drawImage(img, ...)` 會跳過（image 還沒 load）。

兩個方案：
1. **pre-load 全部**（採用）— 開渲染前 await 所有 onload；缺點：大量 image 時等待時間長
2. **改 renderer 為 async** — 工程量大；要動 CanvasRenderer 整鏈

當前 fixture 最多 ~10 image，pre-load 平均 ~50ms；用方案 1 是合理 trade-off。

### 4.2 onerror 不 reject

某張圖片解碼失敗（壞 EMF / WMF 等罕見格式）不該讓整份文件 render 失敗。pre-load Promise 在 onerror 時 resolve 並把 rId 收入 errors 清單，imageResolver 該 rId 回 undefined → 該圖位置留白，其餘照畫。

### 4.3 為何不在 Sprint 15 同步修正 layout pagination

Sprint 15 範圍刻意限定「圖片渲染管線本身」。揭露 pagination 問題後馬上動 Paginator 會：
- 混淆 commit 邊界（Sprint 15 的 image preload 與 Paginator 多頁 split 是兩件事）
- 動 Paginator 就會動 Sprint 12 fingerprint snapshot，需要重 review

留待 Sprint 16 專案處理。

### 4.4 audit 報「diff 上升」是好事

「設備接好但讀數變差」聽起來糟，但比起「設備沒接但讀數偽好」更接近事實。Sprint 14 的 0.2606 是被 white-background-coincidence 拉低的，Sprint 15 的 0.4850 是真實狀態。下個 sprint 從這個誠實 baseline 收斂。

---

## 5. 對 Sprint 1-14 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | **完全不變** | 2 case 全綠（render ops 路徑沒動，imageResolver 是 BrowserCanvasRenderContext 才用） |
| Sprint 13 unit tests | 無 | 22 case 全綠 |
| Sprint 14 visual regression（v14） | **重跑** | 42/42 boot OK，diff 0.1291 → 0.1773（揭露 pagination） |
| Python integration | 無 | 54 case 全綠 |

**vitest 全套**：45 files / **699 tests pass**（與 Sprint 13/14 完全一致）。

---

## 6. 已知限制（Sprint 16+ 補完）

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| **Pagination 不對齊 golden（核心問題）** | Paginator 對 image 推擠的處理與 canvas-editor 不同 | **Sprint 16 主軸** |
| Image position 在頁內偏移 | Layout 沒精確還原 OOXML wrap mode（square/tight/inFront/behind） | Sprint 16+ §3.4 |
| EMF / WMF 圖片不顯示 | 瀏覽器 native Image 不解碼 EMF/WMF；onerror → 留白 | Sprint 16+（需要 emf-parser polyfill）|
| 圖片濃度 / colorspace 差異 | golden 是 canvas-editor 用瀏覽器解碼，我們也是同一條，但 anti-alias 算法可能不同 | Sprint 16+ 細修 |
| pixelmatch threshold（0.1） | 仍寬鬆 | Sprint 17+ pipeline 收斂後可降至 0.05 |

---

## 7. 驗證指令

```bash
# 1. 編譯 IIFE bundle（首次或改 entry 後執行）
npx rollup -c rollup.visual_regression.config.js

# 2. 跑 Sprint 15 visual regression（已含 image pipeline）
node scripts/visual_regression_v14.mjs --max-diff 1.0

# 3. 限制範圍快速驗證
node scripts/visual_regression_v14.mjs --filter 04_with_image --max-fixtures 1 --no-diff

# 4. 既有 vitest（確認沒影響其他護欄）
npm test

# 5. Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 8. 下個 Sprint（Sprint 16）建議

Sprint 15 揭露了真正的瓶頸：**Paginator 對含圖文件的頁數計算**。Sprint 16 主軸：

1. **Pagination 對齊 fixture**：先寫一個 vitest test 確認 6 個 04_with_image fixture 的 layout `pages.length` 等於 golden 頁數；目前差 -3 / -3 / -3 / -3 / 0 / 0
2. **追究原因**：可能是 InlineImage box height 沒納入 Y 累積；或 page break 的 minHeight 預設不對
3. **重跑 Sprint 15 baseline**，預期 04_with_image 從 0.4850 降至 0.1-0.2 範圍

之後再走 Sprint 14 audit doc §8 的 priority 2-6（HarfBuzz / 註腳 / wrapTight / K-P 預設化評估 / report.html 並列預覽）。

---

**附註**：Sprint 1-15 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值
- Sprint 12：完整 field 系統（DATE/TIME/AUTHOR/FILENAME）+ Renderer ops fingerprint regression
- Sprint 13：OOXML docProps/core.xml 自動讀取 + Knuth-Plass 斷行器（opt-in）
- Sprint 14：自家 pipeline IIFE bundle + puppeteer harness + 42 fixture / 100 頁 baseline（mean diff 12.91%）
- **Sprint 15：圖片真渲染（pre-load + imageResolver + async render）；揭露 Paginator 對含圖文件的 pagination divergence（mean diff 17.73%，但是真實狀態）**

到 Sprint 15，Parser 端 + Layout 端 + Renderer 端 全套接通；瀏覽器 IIFE bundle 能畫出含圖頁面；honest baseline 指向 Sprint 16 必須處理的 Paginator 對齊問題。
