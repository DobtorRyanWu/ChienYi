# Sprint 12 完整 field 系統 + Renderer ops fingerprint regression

**狀態**：W11+ 主線 Sprint 12 — Renderer 完整化 + Regression 基線
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.6 Phase 5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint11_header_footer_render.md](sprint11_header_footer_render.md)

---

## 1. 範圍

Sprint 11 完成 page header/footer 渲染後，Sprint 12 收尾兩塊：

1. **A. 完整 field 系統（DATE / TIME / AUTHOR / FILENAME）**
   - `LayoutOptions.documentMetadata` 注入點：`now / dateFormat / timeFormat / author / filename / title`
   - `resolveFieldValues` 取代 `resolvePageNumberFields`，同 post-pass 一次處理 6 種 fieldType
   - 自帶簡化版 `formatDate`：支援 `yyyy / MM / dd / HH / mm / ss` token，無外部 lib
   - metadata 缺 author/filename 時保留 placeholder（`Author` / `Filename`），不 throw
2. **B. Renderer ops fingerprint regression**
   - `serializeOps` / `serializeOpsToJson` / `serializeOpsToNdjson`：把 RenderOp[] 序列化為 deterministic JSON（數字 round 0.01pt、color 統一大寫無 #、optional 欄位空值不寫）
   - `fingerprintOps`：每類 op 計數 + 文字 char 總數 + fnv-1a 32bit 文字 hash，能快速偵測「結構性 regression」
   - `tests/integration/08_render_ops_trace.test.ts`：對 42 fixture 跑完整 pipeline → fingerprint → vitest snapshot；snapshot 變動即代表 Renderer 輸出有變

落地：

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `static/src/core/layout/types.ts` | M | `LayoutOptions.documentMetadata` |
| `static/src/core/layout/Paginator.ts` | M | `resolvePageNumberFields` → `resolveFieldValues`（含 DATE/TIME/AUTHOR/FILENAME）+ `formatDate` |
| `static/src/core/render/serializeOps.ts` | A | `serializeOps` / `serializeOpsToJson` / `serializeOpsToNdjson` / `fingerprintOps` |
| `static/src/core/render/index.ts` | M | export Sprint 12 工具 |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/Sprint12.test.ts`（新檔） | 10 | DATE / TIME / AUTHOR / FILENAME 替換、預設格式、自訂 format、metadata 缺欄位 fallback、PAGE regression、header/footer DATE |
| `tests/unit/render/serializeOps.test.ts`（新檔） | 12 | 數字 round / color 大寫 / optional 不寫出 / NDJSON / JSON / fingerprint |
| `tests/integration/08_render_ops_trace.test.ts`（新檔） | 2 | 42 fixture fingerprint snapshot + reasonable 範圍 |

**全套**：vitest 43 files / **677 tests pass**（Sprint 11 後 40/653 → 43/677，+3 files +24 case）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 為何自寫 `formatDate` 而非引外部 lib（dayjs / date-fns）？

只用到 6 個 token、format 邏輯 < 20 行；引一個 NPM 套件等於 +50KB bundle、+1 個依賴鏈。OOXML date format 範圍非常窄（fixture 觀察主要是 `yyyy/MM/dd` / `yyyy-MM-dd` / `yyyy年MM月dd日`），自寫的 token 替換已能 cover 所有實際使用。

不在 Sprint 12 範圍：
- `MMM` / `MMMM`（英文月名）
- 12 小時制 `am/pm`
- 中文 `年月日` 在 fixture 直接是文字字面值，不是 format token，所以 `formatDate('yyyy年MM月dd日', d)` 會輸出 `2026年05月08日` — 自然行為，不必特例

### 2.2 Renderer ops fingerprint vs 完整 trace

對 42 fixture 跑出的 Renderer ops 總計上萬 ops（01_simple 平均 1841 ops）。直接 snapshot 完整 trace 會：
- snapshot 檔大（500KB+），diff 難讀
- 浮點微擾每次跑略有不同（layout 算術 path 排序）

`fingerprintOps` 拆出三個維度：
- **byKind counts**：fillText / drawLine / fillRect 各幾個 — 抓「漏畫一行」「多畫一條邊框」這類結構錯誤
- **textCharCount**：所有 fillText 的字元總數 — 抓「文字內容多/少了」
- **textHash**：fnv-1a 32bit 雜湊所有 fillText 的字 — 抓「同字數但內容變了」

**為何不用位置 hash**：浮點 path 微差會讓 hash 大變，false positive 太多。fingerprint 刻意只看「結構與內容」，位置變化讓 vitest snapshot 變動更具體去看 trace。

### 2.3 為何 fingerprint snapshot 用 vitest snapshot 而非另寫 JSON 檔？

vitest snapshot 有現成 update-snapshot UI（`vi --update`），diff 顯示在 test runner 內、CI 失敗訊息有完整 diff。自寫 JSON 檔比對需要另寫 update / compare / report 三件事，重造 vitest 已經做好的事。

### 2.4 `resolveFieldValues` 取代 `resolvePageNumberFields`

Sprint 10 加 `resolvePageNumberFields` 時只處理 PAGE / NUMPAGES。Sprint 12 擴展到 6 種 fieldType，函式名也改成更通用的 `resolveFieldValues`。

實作策略：
- 一次 pass 走訪所有 entries（line / table cell / 巢狀表）— 與 Sprint 11 結構一致
- 在 outer 算好「公用 dateStr / timeStr」一次，避免每個 box 重算 `formatDate`
- meta.author / filename 缺欄位時不覆寫 box.text — Box.fieldType 仍保留，placeholder 仍可見（除錯時看得出原本是 field）

### 2.5 fingerprint 寫了 snapshot 後，未來 sprint 改動怎麼辦？

預期工作流：
- 故意改 Layout / Renderer → 跑 vitest → snapshot mismatch
- 看 diff：哪份 fixture 的 fillText / drawLine 變了多少
- 確認改動符合預期 → `npx vitest -u` 更新 snapshot
- commit 內含 snapshot 變動 → 同事 review 時看 diff 即知影響範圍

這是「accept regression」的成本明確化。Sprint 12 之前每改 Renderer 都得跑 console 觀察，現在 snapshot 是強制 review 入口。

---

## 3. fixture 影響

| 類別 | Sprint 11 avgPages | Sprint 12 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.1 | 1.1 |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 2.3 | 2.3 |

Sprint 12 不改 Layout 演算法。

**新增的可觀察基線**：fingerprint snapshot（`tests/integration/__snapshots__/08_render_ops_trace.test.ts.snap`）對每份 fixture 記錄 fillText / drawLine / fillRect / textChars / textHash。例如 01_simple 的「03.1120210-監造會議記錄」：

```
{ beginPage: 1, drawLine: 640, fillRect: 31, fillText: 1168, textChars: 1453, textHash: 'da1c4c3c', total: 1841 }
```

往後 sprint 改任何渲染相關代碼，這份 snapshot 變動即觸發 review。

---

## 4. Sprint 12 已知限制

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| MMM / MMMM 英文月名 / am-pm | 自寫 formatDate 簡化版 | Sprint 13+（如真有 fixture 需要） |
| Visual regression（PNG 像素級） | fingerprint 只是結構性，不是視覺驗證 | Sprint 13 主軸（puppeteer + BrowserCanvasRenderContext） |
| HarfBuzz async batch shape | 仍 estimate width | Sprint 13+ Phase 2 |
| Knuth-Plass 精細斷行 | 仍貪婪 | Sprint 13+ §3.1 |
| wrapTight polygon | 仍降級 square | Sprint 13+ §3.4 |
| 註腳 / 尾註 | Paginator 沒概念 | Sprint 13+ §3.6 |
| OOXML core.xml docProps 自動讀進 metadata | caller 需要手動傳 | Sprint 13+（OoxmlParser 補 docProps 解析） |

---

## 5. 對 Sprint 1-11 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無（DATE/TIME 預設 fallback `new Date()`） | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| Sprint 2-11 unit tests | 無 | 全綠 |
| Python integration | 無 | 54 case 全綠 |
| **Sprint 10 PAGE / NUMPAGES tests** | 邏輯整併到 `resolveFieldValues`；行為一致 | 通過 |
| **Sprint 11 header/footer + PAGE in footer** | 同上 | 通過 |

**vitest 全套**：43 files / **677 tests pass**（Sprint 11 後 40/653 → 43/677，新增 24 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（40 → 43 files；653 → 677 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 12 三檔
npx vitest run tests/unit/layout/Sprint12.test.ts \
              tests/unit/render/serializeOps.test.ts \
              tests/integration/08_render_ops_trace.test.ts

# 更新 fingerprint snapshot（故意改 Renderer 後）
npx vitest run tests/integration/08_render_ops_trace.test.ts -u

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 13）建議

到 Sprint 12，Layout / Renderer / 完整 field / regression 基線已 stable。Sprint 13 起點建議：

1. **Visual Regression（Playwright/Puppeteer + BrowserCanvasRenderContext）** — 真瀏覽器跑、PNG diff vs 251 份 golden；scripts/visual_regression.mjs 已有 puppeteer + canvas-editor 版本，Sprint 13 起 fork 一份用 BrowserCanvasRenderContext 渲染我們自家 pipeline
2. **HarfBuzz async batch shape** — BoxBuilder 改 async pre-shape，replaces estimate width；行高 + advance 都接真實 metrics
3. **Knuth-Plass 精細斷行** — `LayoutItem` model 已用 K-P 結構；換 algorithm 即可
4. **OOXML core.xml docProps 自動讀進 metadata** — 補 OoxmlParser 解析 dc:creator / dc:title / cp:lastModifiedBy 等
5. **wrapTight polygon** — drawing.xml polygon path 解析 + LineBreaker per-y lineWidth
6. **註腳 / 尾註**

**建議優先順序**：1（用 fingerprint snapshot 作為 visual diff 篩選器）→ 2（精度核心）→ 4（小但 demo 加分）→ 3, 5, 6（高階優化）

---

**附註**：Sprint 1-12 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值
- **Sprint 12：完整 field 系統（DATE/TIME/AUTHOR/FILENAME）+ Renderer ops fingerprint regression baseline**

到 Sprint 12，Renderer 端能完整呈現 ChienYi 監造文件常見的全部欄位（PAGE / NUMPAGES / DATE / TIME / AUTHOR / FILENAME）、頁眉頁腳、shading / 文字裝飾 / 欄分隔線；fingerprint snapshot 鎖住「結構性 regression」入口。Sprint 13 起進入 Visual Regression（puppeteer 像素級驗證）+ HarfBuzz async shape 階段。
